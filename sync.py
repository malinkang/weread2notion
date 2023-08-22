import logging
import re
import time
from datetime import datetime
import hashlib
from collections import defaultdict

from treelib import Tree
from notion_client import Client

from api import weread
from api.notion import BlockHelper
from config import CONFIG

ROOT_NODE_ID = "#root"
BOOK_MARK_KEY = '#bookmarks'
NOTION_MAX_LEVEL = 3


def delete_page(client, database_id, book_id):
    """检查是否已经插入过 如果已经插入了就删除"""
    time.sleep(0.3)

    response = client.databases.query(
        database_id=database_id,
        filter={
            "property": "BookId",
            "rich_text": {
                "equals": book_id
            }
        })
    for result in response["results"]:
        time.sleep(0.3)
        client.blocks.delete(block_id=result["id"])


def create_page(client, database_id, book_name='', book_id='', cover='', sort=0, author='', isbn='', rating=0, note_count=0, read_info=None):
    """插入到notion"""
    time.sleep(0.3)
    parent = {
        "database_id": database_id,
        "type": "database_id"
    }
    properties = {
        "BookName": {"title": [{"type": "text", "text": {"content": book_name}}]},
        "BookId": {"rich_text": [{"type": "text", "text": {"content": book_id}}]},
        "ISBN": {"rich_text": [{"type": "text", "text": {"content": isbn}}]},
        "URL": {"url": f"https://weread.qq.com/web/reader/{calculate_book_str_id(book_id)}"},
        "Author": {"rich_text": [{"type": "text", "text": {"content": author}}]},
        "Sort": {"number": sort},
        "Rating": {"number": rating},
        "Cover": {"files": [{"type": "external", "name": "Cover", "external": {"url": cover}}]},
        "NoteCount": {"number": note_count},
    }

    if read_info:
        marked_status = read_info.get("markedStatus", 0)
        reading_time = read_info.get("readingTime", 0)
        format_time = ""
        hour = reading_time // 3600
        if hour > 0:
            format_time += f"{hour}时"
        minutes = reading_time % 3600 // 60
        if minutes > 0:
            format_time += f"{minutes}分"
        properties["Status"] = {"select": {
            "name": "读完" if marked_status == 4 else "在读"}}
        properties["ReadingTime"] = {"rich_text": [
            {"type": "text", "text": {"content": format_time}}]}

        # 最近阅读
        detail = read_info.get('readDetail', {})
        if detail.get('lastReadingDate'):
            properties["lastReadingDate"] = {"date": {"start": datetime.utcfromtimestamp(
                detail.get("lastReadingDate")).strftime("%Y-%m-%d %H:%M:%S"), "time_zone": "Asia/Shanghai"}}

        # 完成时间
        if read_info.get("finishedDate"):
            properties["FinishAt"] = {"date": {"start": datetime.utcfromtimestamp(
                read_info.get("finishedDate")).strftime("%Y-%m-%d %H:%M:%S"), "time_zone": "Asia/Shanghai"}}

    icon = {
        "type": "external",
        "external": {
            "url": cover
        }
    }
    # notion api 限制100个block
    response = client.pages.create(
        parent=parent, icon=icon, properties=properties)
    return response["id"]


def add_children(client, pid, children):
    """追加child block"""
    results = []
    for i in range(0, len(children)//100+1):
        time.sleep(0.3)
        response = client.blocks.children.append(
            block_id=pid, children=children[i*100:(i+1)*100])
        results.extend(response.get("results"))
    return results if len(results) == len(children) else []


def add_grandchild(client, grandchild, results):
    """追加grand child block"""
    for key, value in grandchild.items():
        time.sleep(0.3)
        block_id = results[key].get("id")
        client.blocks.children.append(block_id=block_id, children=[value])


def get_db_latest_sort(client, database_id):
    """获取database中的最新时间"""
    db_filter = {
        "property": "Sort",
        "number": {
            "is_not_empty": True
        }
    }
    sorts = [
        {
            "property": "Sort",
            "direction": "descending",
        }
    ]
    response = client.databases.query(
        database_id=database_id, filter=db_filter, sorts=sorts, page_size=1)
    if len(response.get("results")) == 1:
        return response.get("results")[0].get("properties").get("Sort").get("number")
    return 0


def gen_chapter_tree(chapter_list):
    """生成章节树"""
    tree = Tree()
    root = tree.create_node(identifier=ROOT_NODE_ID)  # root node
    p = {}
    for chapter in chapter_list:
        level = chapter.get('level', 1)
        if level <= 0:
            level = 1
        elif level > NOTION_MAX_LEVEL:  # 目前仅支持header1-3
            level = NOTION_MAX_LEVEL

        parent = p.get(level - 1, root)  # 取最近一次更新节点
        chapter_uid = chapter.get('chapterUid')
        p[level] = tree.create_node(
            tag=chapter_uid, identifier=chapter_uid, parent=parent, data=chapter)
    return tree

# mount bookmarks to chapter tree


def mount_bookmarks(chapter_tree, bookmark_list):
    """挂载划线、评论到对应的树节点"""
    d = defaultdict(list)
    for data in bookmark_list:
        uid = data.get("chapterUid", 1)
        d[uid].append(data)

    for key, value in d.items():
        node = chapter_tree.get_node(key)
        if not node:
            logging.error("chapter info not found [%s].", key)
            continue

        # mount bookmark list to chapter list
        node.data[BOOK_MARK_KEY] = value

# remove chapter without bookmarks


def remove_empty_chapter(chapter_tree):
    """从底向上，删除章节树中的空节点"""
    max_depth = chapter_tree.depth()
    for d in range(max_depth, 0, -1):
        nodes = list(chapter_tree.filter_nodes(
            lambda x: chapter_tree.depth(x) == d))

        for n in nodes:
            if n.data.get(BOOK_MARK_KEY) is None and n.is_leaf():
                # print('remove:', n)
                chapter_tree.remove_node(n.identifier)


def content_block(text: str, style: str, color: str, review_id: str) -> dict:
    """
    根据配置选择内容block形态
    """
    match CONFIG.get("notion.format", "ContentType"):
        case "callout":
            return BlockHelper.callout(text, style, color, review_id)

        case "list":
            return BlockHelper.bullet_list(text, style, color, review_id)

        case _:
            return BlockHelper.paragraph(text, style, color, review_id)


def get_children(chapters_list, summary, bookmark_list):
    children = []
    grandchild = {}

    if len(chapters_list) > 0:
        # 添加目录
        children.append(BlockHelper.table_of_contents())

        chapter_tree = gen_chapter_tree(chapters_list)
        mount_bookmarks(chapter_tree, bookmark_list)
        remove_empty_chapter(chapter_tree)

        for n in chapter_tree.expand_tree(mode=Tree.DEPTH):
            # print(tree[n].data)
            # for key, value in d.items():
            if chapter_tree[n].is_root():
                continue

            data = chapter_tree[n].data
            children.append(BlockHelper.heading(
                data.get("level"), data.get("title")))

            for i in data.get(BOOK_MARK_KEY, []):
                children.append(content_block(i.get("markText"), data.get(
                    "style"), i.get("colorStyle"), i.get("reviewId")))

                if i.get("abstract"):  # 评语，写入quote信息
                    quote = BlockHelper.quote(i.get("abstract"))
                    grandchild[len(children)-1] = quote
    else:
        # 如果没有章节信息
        for data in bookmark_list:
            children.append(BlockHelper.callout(data.get("markText"), data.get("style"),
                                                data.get("colorStyle"), data.get("reviewId")))

    # 追加推荐评语
    if summary:
        children.append(BlockHelper.heading(1, "点评"))
        for i in summary:
            children.append(content_block(i.get("review").get("content"), i.get("style"),
                                          i.get("colorStyle"), i.get("review").get("reviewId")))

    return children, grandchild


def transform_id(book_id):
    id_length = len(book_id)

    if re.match(r"^\d*$", book_id):
        ary = []
        for i in range(0, id_length, 9):
            ary.append(format(int(book_id[i:min(i + 9, id_length)]), 'x'))
        return '3', ary

    result = ''
    for i in range(id_length):
        result += format(ord(book_id[i]), 'x')
    return '4', [result]


def calculate_book_str_id(book_id):
    md5 = hashlib.md5()
    md5.update(book_id.encode('utf-8'))
    digest = md5.hexdigest()
    result = digest[0:3]
    code, transformed_ids = transform_id(book_id)
    result += code + '2' + digest[-2:]

    for i in range(len(transformed_ids)):
        hex_length_str = format(len(transformed_ids[i]), 'x')
        if len(hex_length_str) == 1:
            hex_length_str = '0' + hex_length_str

        result += hex_length_str + transformed_ids[i]

        if i < len(transformed_ids) - 1:
            result += 'g'

    if len(result) < 20:
        result += digest[0:20 - len(result)]

    md5 = hashlib.md5()
    md5.update(result.encode('utf-8'))
    result += md5.hexdigest()[0:3]
    return result


def sync(weread_cookie, notion_token, database_id):
    """同步到notion"""
    client = Client(
        auth=notion_token,
        log_level=logging.ERROR
    )
    latest_sort = get_db_latest_sort(client, database_id)

    wreader = weread.WeReadAPI(weread_cookie)

    books = wreader.get_notebooklist()
    for _book in books:
        sort = _book["sort"]
        if sort <= latest_sort:  # 笔记无更新，跳过
            logging.info("no update")
            continue

        book_dict = _book.get("book")
        bookID = book_dict.get("bookId")

        chapters_list = wreader.get_chapter_list(bookID)
        bookmark_list = wreader.get_bookmark_list(bookID)
        summary, reviews = wreader.get_review_list(bookID)

        bookmark_list.extend(reviews)
        bookmark_list = sorted(bookmark_list, key=lambda x: (
            x.get("chapterUid", 1), 0 if (x.get("range", "") == "" or x.get("range").split("-")[0] == "") else int(x.get("range").split("-")[0])))

        isbn, rating = wreader.get_bookinfo(bookID)
        read_info = wreader.get_read_info(bookID)

        # delete before insert again
        delete_page(client, database_id, bookID)

        pid = create_page(client, database_id,
                          book_name=book_dict.get("title"),
                          book_id=bookID, cover=book_dict.get("cover"),
                          sort=sort, author=book_dict.get("author"),
                          isbn=isbn, rating=rating, note_count=_book.get(
                              "noteCount"),
                          read_info=read_info)

        children, grandchild = get_children(
            chapters_list, summary, bookmark_list)
        results = add_children(client, pid, children)
        if len(grandchild) > 0:
            add_grandchild(client, grandchild, results)
