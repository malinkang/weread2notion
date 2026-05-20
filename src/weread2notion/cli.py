import argparse
import logging
import os
import re
import time
from notion_client import Client
import requests
from datetime import datetime
import hashlib
from dotenv import load_dotenv
from retrying import retry
from .blocks import (
    get_callout,
    get_date,
    get_file,
    get_heading,
    get_icon,
    get_multi_select,
    get_number,
    get_quote,
    get_rich_text,
    get_select,
    get_title,
    get_url,
)

client = None
database_id = None
weread = None

load_dotenv()
WEREAD_URL = "https://weread.qq.com/"
WEREAD_GATEWAY_URL = "https://i.weread.qq.com/api/agent/gateway"
WEREAD_SKILL_VERSION = "1.0.3"


class WeReadGatewayClient:
    def __init__(self, api_key):
        if not api_key or not api_key.strip():
            raise Exception("没有找到 WEREAD_API_KEY，请在 GitHub Actions Secrets 中配置")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def request(self, api_name, **kwargs):
        payload = {
            "api_name": api_name,
            "skill_version": WEREAD_SKILL_VERSION,
            **kwargs,
        }
        response = self.session.post(WEREAD_GATEWAY_URL, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get("upgrade_info"):
            raise Exception(f"微信读书 skill 需要升级: {data.get('upgrade_info')}")
        if data.get("errcode", 0) != 0:
            raise Exception(f"微信读书 Gateway 请求失败: {api_name}, errcode={data.get('errcode')}, response={data}")
        return data


def get_range_start(item):
    note_range = item.get("range") or ""
    try:
        return int(note_range.split("-")[0] or 0)
    except (ValueError, TypeError):
        return 0


def get_note_sort_key(item, chapter=None):
    chapter_uid = item.get("chapterUid", 1)
    chapter_info = None
    if chapter:
        chapter_info = chapter.get(chapter_uid) or chapter.get(str(chapter_uid))
    chapter_idx = (
        chapter_info.get("chapterIdx", 1000000)
        if chapter_info
        else chapter_uid
    )
    return (chapter_idx, get_range_start(item))


@retry(stop_max_attempt_number=3, wait_fixed=5000)
def get_bookmark_list(bookId):
    """获取我的划线"""
    data = weread.request("/book/bookmarklist", bookId=bookId)
    updated = data.get("updated") or []
    return sorted(updated, key=get_note_sort_key)


@retry(stop_max_attempt_number=3, wait_fixed=5000)
def get_read_info(bookId):
    data = weread.request("/book/getprogress", bookId=bookId)
    book = data.get("book") or {}
    progress = book.get("progress") or 0
    finish_time = book.get("finishTime") or 0
    update_time = book.get("updateTime") or 0
    if finish_time or progress >= 100:
        marked_status = 4
    elif update_time or book.get("isStartReading") or progress > 0:
        marked_status = 2
    else:
        marked_status = 1
    return {
        "markedStatus": marked_status,
        "readingTime": book.get("recordReadingTime") or 0,
        "readingProgress": progress,
        "finishedDate": finish_time,
    }


def normalize_rating(value):
    value = value or 0
    if value > 100:
        return value / 1000
    if value > 10:
        return value / 10
    return value


@retry(stop_max_attempt_number=3, wait_fixed=5000)
def get_bookinfo(bookId):
    """获取书的详情"""
    data = weread.request("/book/info", bookId=bookId)
    isbn = data.get("isbn", "")
    newRating = normalize_rating(data.get("newRating"))
    return (isbn, newRating)


@retry(stop_max_attempt_number=3, wait_fixed=5000)
def get_review_list(bookId):
    """获取笔记"""
    reviews_data = []
    hasMore = 1
    synckey = 0
    while hasMore:
        data = weread.request("/review/list/mine", bookid=bookId, synckey=synckey, count=100)
        hasMore = data.get("hasMore", 0)
        synckey = data.get("synckey", 0)
        batch = data.get("reviews") or []
        reviews_data.extend(batch)
        if not batch:
            hasMore = 0
    summary = list(filter(lambda x: (x.get("review") or {}).get("type") == 4, reviews_data))
    reviews = list(filter(lambda x: (x.get("review") or {}).get("type") == 1, reviews_data))
    reviews = list(map(lambda x: x.get("review") or {}, reviews))
    reviews = list(map(lambda x: {**x, "markText": x.pop("content", "")}, reviews))
    return summary, reviews


def check(bookId):
    """检查是否已经插入过 如果已经插入了就删除"""
    filter = {"property": "BookId", "rich_text": {"equals": bookId}}
    response = client.databases.query(database_id=database_id, filter=filter)
    for result in response["results"]:
        try:
            client.blocks.delete(block_id=result["id"])
        except Exception as e:
            print(f"删除块时出错: {e}")


@retry(stop_max_attempt_number=3, wait_fixed=5000)
def get_chapter_info(bookId):
    """获取章节信息"""
    data = weread.request("/book/chapterinfo", bookId=bookId)
    chapters = data.get("chapters") or []
    return {item["chapterUid"]: item for item in chapters if "chapterUid" in item}


def insert_to_notion(bookName, bookId, cover, sort, author, isbn, rating, categories):
    """插入到notion"""
    if not cover or not cover.startswith("http"):
        cover = "https://www.notion.so/icons/book_gray.svg"
    parent = {"database_id": database_id, "type": "database_id"}
    properties = {
        "BookName": get_title(bookName),
        "BookId": get_rich_text(bookId),
        "ISBN": get_rich_text(isbn),
        "URL": get_url(
            f"https://weread.qq.com/web/reader/{calculate_book_str_id(bookId)}"
        ),
        "Author": get_rich_text(author),
        "Sort": get_number(sort),
        "Rating": get_number(rating),
        "Cover": get_file(cover),
    }
    if categories != None:
        properties["Categories"] = get_multi_select(categories)
    read_info = get_read_info(bookId=bookId)
    if read_info != None:
        markedStatus = read_info.get("markedStatus", 0)
        readingTime = read_info.get("readingTime", 0)
        readingProgress = read_info.get("readingProgress", 0)
        format_time = ""
        hour = readingTime // 3600
        if hour > 0:
            format_time += f"{hour}时"
        minutes = readingTime % 3600 // 60
        if minutes > 0:
            format_time += f"{minutes}分"
        properties["Status"] = get_select("读完" if markedStatus == 4 else "在读")
        properties["ReadingTime"] = get_rich_text(format_time)
        properties["Progress"] = get_number(readingProgress)
        if "finishedDate" in read_info:
            properties["Date"] = get_date(
                datetime.utcfromtimestamp(read_info.get("finishedDate")).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )

    icon = get_icon(cover)
    # notion api 限制100个block
    response = client.pages.create(parent=parent, icon=icon,cover=icon, properties=properties)
    id = response["id"]
    return id


def add_children(id, children):
    results = []
    for i in range(0, len(children) // 100 + 1):
        time.sleep(0.3)
        response = client.blocks.children.append(
            block_id=id, children=children[i * 100 : (i + 1) * 100]
        )
        results.extend(response.get("results"))
    return results if len(results) == len(children) else None


def add_grandchild(grandchild, results):
    for key, value in grandchild.items():
        time.sleep(0.3)
        id = results[key].get("id")
        client.blocks.children.append(block_id=id, children=[value])


def get_notebooklist():
    """获取笔记本列表"""
    books = []
    hasMore = 1
    lastSort = None
    while hasMore:
        params = {"count": 100}
        if lastSort is not None:
            params["lastSort"] = lastSort
        data = weread.request("/user/notebooks", **params)
        hasMore = data.get("hasMore", 0)
        batch = data.get("books") or []
        books.extend(batch)
        if batch:
            lastSort = batch[-1].get("sort")
        else:
            hasMore = 0
    books.sort(key=lambda x: x.get("sort") or 0)
    return books


def get_sort():
    """获取database中的最新时间"""
    filter = {"property": "Sort", "number": {"is_not_empty": True}}
    sorts = [
        {
            "property": "Sort",
            "direction": "descending",
        }
    ]
    response = client.databases.query(
        database_id=database_id, filter=filter, sorts=sorts, page_size=1
    )
    if len(response.get("results")) == 1:
        return response.get("results")[0].get("properties").get("Sort").get("number")
    return 0


def get_children(chapter, summary, bookmark_list):
    children = []
    grandchild = {}
    all_chapters = []
    if chapter:
        for uid, info in chapter.items():
            item = dict(info)
            item["chapterUid"] = item.get("chapterUid", uid)
            all_chapters.append(item)
        all_chapters.sort(key=lambda x: x.get("chapterIdx", 0))
    chapter_nodes = {node.get("chapterUid"): node for node in all_chapters}

    def get_ancestor_chain(current_chapter_info):
        if not current_chapter_info:
            return []
        try:
            current_pos = all_chapters.index(current_chapter_info)
        except ValueError:
            return [current_chapter_info]

        chain = []
        target_level = current_chapter_info.get("level", 1)
        for index in range(current_pos - 1, -1, -1):
            candidate = all_chapters[index]
            if candidate.get("level", 1) < target_level:
                chain.insert(0, candidate)
                target_level = candidate.get("level", 1)
                if target_level <= 1:
                    break
        chain.append(current_chapter_info)
        return chain

    if chapter:
        grouped_bookmarks = []
        last_uid = None
        current_group = None

        for data in bookmark_list:
            uid = data.get("chapterUid", 1)
            if uid != last_uid:
                if current_group:
                    grouped_bookmarks.append(current_group)
                info = chapter.get(uid) or chapter.get(str(uid))
                current_group = {
                    "chapterUid": uid,
                    "bookmarks": [],
                    "chapterInfo": info,
                }
                last_uid = uid
            current_group["bookmarks"].append(data)
        if current_group:
            grouped_bookmarks.append(current_group)

        previous_path_uids = []
        for group in grouped_bookmarks:
            info = group["chapterInfo"]
            if info:
                current_info = chapter_nodes.get(group["chapterUid"]) or chapter_nodes.get(
                    str(group["chapterUid"])
                )
                if current_info is None:
                    current_info = dict(info)
                    current_info["chapterUid"] = current_info.get("chapterUid", group["chapterUid"])
                path = get_ancestor_chain(current_info)

                divergence_index = 0
                min_len = min(len(path), len(previous_path_uids))
                while divergence_index < min_len:
                    path_uid = path[divergence_index].get("chapterUid")
                    if path_uid != previous_path_uids[divergence_index]:
                        break
                    divergence_index += 1

                for chapter_node in path[divergence_index:]:
                    children.append(
                        get_heading(
                            chapter_node.get("level"), chapter_node.get("title")
                        )
                    )
                previous_path_uids = [node.get("chapterUid") for node in path]
            else:
                previous_path_uids = []

            for i in group["bookmarks"]:
                markText = i.get("markText") or ""
                if not markText:
                    continue
                for j in range(0, len(markText) // 2000 + 1):
                    children.append(
                        get_callout(markText[j * 2000 : (j + 1) * 2000])
                    )
                if i.get("abstract") != None and i.get("abstract") != "":
                    quote = get_quote(i.get("abstract"))
                    grandchild[len(children) - 1] = quote

    else:
        # 如果没有章节信息
        for data in bookmark_list:
            markText = data.get("markText") or ""
            if not markText:
                continue
            for i in range(0, len(markText) // 2000 + 1):
                children.append(
                    get_callout(markText[i * 2000 : (i + 1) * 2000])
                )
    if summary != None and len(summary) > 0:
        children.append(get_heading(1, "点评"))
        for i in summary:
            content = (i.get("review") or {}).get("content") or ""
            if not content:
                continue
            for j in range(0, len(content) // 2000 + 1):
                children.append(
                    get_callout(content[j * 2000 : (j + 1) * 2000])
                )
    return children, grandchild


def transform_id(book_id):
    id_length = len(book_id)

    if re.match(r"^\d*$", book_id):
        ary = []
        for i in range(0, id_length, 9):
            ary.append(format(int(book_id[i : min(i + 9, id_length)]), "x"))
        return "3", ary

    result = ""
    for i in range(id_length):
        result += format(ord(book_id[i]), "x")
    return "4", [result]


def calculate_book_str_id(book_id):
    md5 = hashlib.md5()
    md5.update(book_id.encode("utf-8"))
    digest = md5.hexdigest()
    result = digest[0:3]
    code, transformed_ids = transform_id(book_id)
    result += code + "2" + digest[-2:]

    for i in range(len(transformed_ids)):
        hex_length_str = format(len(transformed_ids[i]), "x")
        if len(hex_length_str) == 1:
            hex_length_str = "0" + hex_length_str

        result += hex_length_str + transformed_ids[i]

        if i < len(transformed_ids) - 1:
            result += "g"

    if len(result) < 20:
        result += digest[0 : 20 - len(result)]

    md5 = hashlib.md5()
    md5.update(result.encode("utf-8"))
    result += md5.hexdigest()[0:3]
    return result


def extract_page_id():
    url = os.getenv("NOTION_PAGE")
    if not url:
        url = os.getenv("NOTION_DATABASE_ID")
    if not url:
        raise Exception("没有找到NOTION_PAGE，请按照文档填写")
    # 正则表达式匹配 32 个字符的 Notion page_id
    match = re.search(
        r"([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
        url,
    )
    if match:
        return match.group(0)
    else:
        raise Exception(f"获取NotionID失败，请检查输入的Url是否正确")


def sync():
    global client, database_id, weread
    database_id = extract_page_id()
    notion_token = os.getenv("NOTION_TOKEN")
    if not notion_token or not notion_token.strip():
        raise Exception("没有找到 NOTION_TOKEN，请在 GitHub Actions Secrets 中配置")
    weread = WeReadGatewayClient(os.getenv("WEREAD_API_KEY"))
    client = Client(auth=notion_token, log_level=logging.ERROR)
    latest_sort = get_sort()
    books = get_notebooklist()
    if books != None:
        for index, book in enumerate(books):
            sort = book["sort"]
            if sort <= latest_sort:
                continue
            book = book.get("book") or book
            title = book.get("title") or ""
            cover = (book.get("cover") or "").replace("/s_", "/t7_")
            bookId = book.get("bookId")
            author = book.get("author") or ""
            if not bookId:
                continue
            categories = book.get("categories")
            if categories != None:
                categories = [x["title"] for x in categories]
            print(f"正在同步 {title} ,一共{len(books)}本，当前是第{index+1}本。")
            check(bookId)
            isbn, rating = get_bookinfo(bookId)
            id = insert_to_notion(
                title, bookId, cover, sort, author, isbn, rating, categories
            )
            chapter = get_chapter_info(bookId)
            bookmark_list = get_bookmark_list(bookId)
            summary, reviews = get_review_list(bookId)
            bookmark_list.extend(reviews)
            bookmark_list = sorted(
                bookmark_list,
                key=lambda x: get_note_sort_key(x, chapter),
            )
            children, grandchild = get_children(chapter, summary, bookmark_list)
            results = add_children(id, children)
            if len(grandchild) > 0 and results != None:
                add_grandchild(grandchild, results)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="weread2notion",
        description="Sync WeRead highlights and notes to Notion.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="sync",
        choices=["sync"],
        help="Command to run. Defaults to sync.",
    )
    parser.parse_args(argv)
    sync()


if __name__ == "__main__":
    main()
