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
from notion_client.errors import APIResponseError
from retrying import retry
from .blocks import (
    get_callout,
    get_date,
    get_heading,
    get_icon,
    get_multi_select,
    get_number,
    get_quote,
    get_rich_text,
    get_select,
    get_status,
    get_title,
    get_url,
)

client = None
data_source_id = None
data_source_property_types = {}
title_property_name = None
skipped_property_names = set()
weread = None

load_dotenv()
WEREAD_URL = "https://weread.qq.com/"
WEREAD_GATEWAY_URL = "https://i.weread.qq.com/api/agent/gateway"
WEREAD_SKILL_VERSION = "1.0.3"
NOTION_VERSION = "2026-03-11"
BOOKMARK_CALLOUT_ICON = "〰️"
NOTE_CALLOUT_ICON = "✍️"


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
    reviews = list(
        map(
            lambda x: {
                **x,
                "markText": x.pop("content", ""),
                "_callout_icon": NOTE_CALLOUT_ICON,
            },
            reviews,
        )
    )
    return summary, reviews


def check(bookId):
    """检查是否已经插入过 如果已经插入了就删除"""
    filter = build_equals_filter("BookId", bookId)
    response = query_data_source(filter=filter)
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
    parent = {"type": "data_source_id", "data_source_id": data_source_id}
    raw_properties = {
        title_property_name: bookName,
        "BookId": bookId,
        "ISBN": isbn,
        "URL": f"https://weread.qq.com/web/reader/{calculate_book_str_id(bookId)}",
        "作者": author,
        "Sort": sort,
        "评分": rating,
    }
    if categories != None:
        raw_properties["分类"] = categories
    read_info = (
        get_read_info(bookId=bookId)
        if has_any_property(("状态", "阅读时长", "Progress", "时间"))
        else None
    )
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
        raw_properties["状态"] = "读完" if markedStatus == 4 else "在读"
        raw_properties["阅读时长"] = format_time
        raw_properties["Progress"] = readingProgress
        if "finishedDate" in read_info:
            raw_properties["时间"] = datetime.utcfromtimestamp(
                read_info.get("finishedDate")
            ).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

    properties = build_notion_properties(raw_properties)
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
    """获取 data source 中的最新时间"""
    filter = build_is_not_empty_filter("Sort")
    sorts = [
        {
            "property": "Sort",
            "direction": "descending",
        }
    ]
    response = query_data_source(filter=filter, sorts=sorts, page_size=1)
    if len(response.get("results")) == 1:
        return get_number_property_value(
            response.get("results")[0].get("properties").get("Sort")
        )
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
                callout_icon = i.get("_callout_icon") or BOOKMARK_CALLOUT_ICON
                for j in range(0, len(markText) // 2000 + 1):
                    children.append(
                        get_callout(
                            markText[j * 2000 : (j + 1) * 2000],
                            icon=callout_icon,
                        )
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
                    get_callout(
                        markText[i * 2000 : (i + 1) * 2000],
                        icon=BOOKMARK_CALLOUT_ICON,
                    )
                )
    if summary != None and len(summary) > 0:
        children.append(get_heading(1, "点评"))
        for i in summary:
            content = (i.get("review") or {}).get("content") or ""
            if not content:
                continue
            for j in range(0, len(content) // 2000 + 1):
                children.append(
                    get_callout(
                        content[j * 2000 : (j + 1) * 2000],
                        icon=NOTE_CALLOUT_ICON,
                    )
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


def extract_notion_id():
    url_or_id = (
        os.getenv("NOTION_DATA_SOURCE_ID")
        or os.getenv("NOTION_PAGE")
        or os.getenv("NOTION_DATABASE_ID")
    )
    if not url_or_id:
        raise Exception("没有找到 NOTION_PAGE / NOTION_DATA_SOURCE_ID，请按照文档填写")
    match = re.search(
        r"([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
        url_or_id,
    )
    if match:
        return match.group(0)

    raise Exception(f"获取 Notion ID 失败，请检查输入是否正确: {url_or_id}")


def query_data_source(**body):
    return client.request(
        path=f"data_sources/{data_source_id}/query",
        method="POST",
        body=body,
    )


def load_data_source_schema():
    """读取当前 data source 的真实属性，只强制要求同步游标需要的字段。"""
    global data_source_property_types, title_property_name, skipped_property_names
    response = client.request(path=f"data_sources/{data_source_id}", method="GET")
    properties = response.get("properties") or {}
    data_source_property_types = {
        name: (config or {}).get("type") for name, config in properties.items()
    }
    title_property_name = next(
        (
            name
            for name, prop_type in data_source_property_types.items()
            if prop_type == "title"
        ),
        None,
    )
    skipped_property_names = set()
    if not title_property_name:
        raise Exception("Notion data source 缺少标题属性，请保留一个 Title 类型属性")

    missing = [
        name for name in ("BookId", "Sort") if name not in data_source_property_types
    ]
    if missing:
        raise Exception(
            f"Notion data source 缺少必填属性: {', '.join(missing)}。"
            "请在模板中补充后重试"
        )

    print(
        f"已读取 Notion 属性 {len(data_source_property_types)} 个，"
        f"标题属性: {title_property_name}"
    )


def get_property_type(name):
    return data_source_property_types.get(name)


def has_any_property(names):
    return any(name in data_source_property_types for name in names)


def build_equals_filter(name, value):
    prop_type = get_property_type(name)
    if prop_type in {"title", "rich_text", "url", "email", "phone_number"}:
        return {"property": name, prop_type: {"equals": str(value)}}
    if prop_type == "number":
        return {"property": name, "number": {"equals": to_number(value)}}
    if prop_type == "select":
        return {"property": name, "select": {"equals": str(value)}}
    if prop_type == "status":
        return {"property": name, "status": {"equals": str(value)}}
    raise Exception(f"Notion 属性 {name} 的类型 {prop_type} 暂不支持用于查询")


def build_is_not_empty_filter(name):
    prop_type = get_property_type(name)
    if prop_type in {
        "title",
        "rich_text",
        "url",
        "email",
        "phone_number",
        "number",
        "select",
        "status",
        "date",
    }:
        return {"property": name, prop_type: {"is_not_empty": True}}
    raise Exception(f"Notion 属性 {name} 的类型 {prop_type} 暂不支持用于查询")


def to_text(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(to_text(item) for item in value if item is not None)
    return str(value)


def to_name_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [to_text(item) for item in value if to_text(item)]
    text = to_text(value)
    return [text] if text else []


def to_number(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def normalize_date_value(value):
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
    return value


def build_option_property(prop_type, value):
    names = to_name_list(value)
    if not names:
        return None
    if prop_type == "status":
        return get_status(names[0])
    if prop_type == "select":
        return get_select(names[0])
    return get_multi_select(names)


def build_notion_property(name, value):
    prop_type = get_property_type(name)
    if not prop_type:
        if name not in skipped_property_names:
            print(f"属性 {name} 在 Notion 模板中不存在，自动跳过")
            skipped_property_names.add(name)
        return None
    if value is None:
        return None

    if prop_type == "title":
        return get_title(to_text(value))
    if prop_type == "rich_text":
        return get_rich_text(to_text(value))
    if prop_type == "number":
        number = to_number(value)
        return get_number(number) if number is not None else None
    if prop_type == "url":
        return get_url(to_text(value))
    if prop_type in {"multi_select", "status", "select"}:
        return build_option_property(prop_type, value)
    if prop_type == "date":
        return get_date(normalize_date_value(value))
    if prop_type == "checkbox":
        return {"checkbox": bool(value)}

    if name not in skipped_property_names:
        print(f"属性 {name} 的类型 {prop_type} 暂不支持写入，自动跳过")
        skipped_property_names.add(name)
    return None


def build_notion_properties(raw_properties):
    return {
        name: prop
        for name, value in raw_properties.items()
        if (prop := build_notion_property(name, value)) is not None
    }


def get_number_property_value(property_value):
    if not property_value:
        return 0
    prop_type = property_value.get("type")
    value = property_value.get(prop_type)
    if prop_type == "number":
        return value or 0
    if prop_type in {"title", "rich_text"} and value:
        return to_number(value[0].get("plain_text")) or 0
    if prop_type in {"select", "status"} and value:
        return to_number(value.get("name")) or 0
    return 0


def resolve_data_source_id(notion_id):
    if os.getenv("NOTION_DATA_SOURCE_ID"):
        return notion_id

    try:
        client.request(path=f"data_sources/{notion_id}", method="GET")
        return notion_id
    except APIResponseError as error:
        code = getattr(error.code, "value", error.code)
        if code not in {"object_not_found", "validation_error"}:
            raise

    database = client.request(path=f"databases/{notion_id}", method="GET")
    sources = database.get("data_sources") or []
    if not sources:
        raise Exception(f"数据库 {notion_id} 下没有可用的 data source")
    if len(sources) > 1:
        print(
            f"数据库 {notion_id} 包含 {len(sources)} 个 data sources，默认使用第一个: {sources[0].get('id')}"
        )
    return sources[0]["id"]


def sync():
    global client, data_source_id, weread
    notion_id = extract_notion_id()
    notion_token = os.getenv("NOTION_TOKEN")
    if not notion_token or not notion_token.strip():
        raise Exception("没有找到 NOTION_TOKEN，请在 GitHub Actions Secrets 中配置")
    weread = WeReadGatewayClient(os.getenv("WEREAD_API_KEY"))
    client = Client(
        auth=notion_token,
        log_level=logging.ERROR,
        notion_version=NOTION_VERSION,
    )
    data_source_id = resolve_data_source_id(notion_id)
    print(f"Notion API Version: {NOTION_VERSION}")
    print(f"Notion Data Source ID: {data_source_id}")
    load_data_source_schema()
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
            if has_any_property(("ISBN", "评分")):
                isbn, rating = get_bookinfo(bookId)
            else:
                isbn, rating = "", None
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
