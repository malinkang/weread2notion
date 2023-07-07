import argparse
import json
import logging
import re
import time
from notion_client import Client
from datetime import datetime
import hashlib
from api import weread
from collections import defaultdict
from treelib import Tree

ROOT_NODE_ID = "#root"
BOOK_MARK_KEY = '#bookmarks'
NOTION_MAX_LEVEL = 3

def get_table_of_contents():
    """获取目录"""
    return {
        "type": "table_of_contents",
        "table_of_contents": {
            "color": "default"
        }
    }


def get_heading(level, content):
    if level == 1:
        heading = "heading_1"
    elif level == 2:
        heading = "heading_2"
    else:
        heading = "heading_3"
    return {
        "type": heading,
        heading: {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": content,
                }
            }],
            "color": "default",
            "is_toggleable": False
        }
    }


def get_quote(content):
    return {
        "type": "quote",
        "quote": {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": content
                },
            }],
            "color": "default"
        }
    }


def get_callout(content, style, colorStyle, reviewId):
    # 根据不同的划线样式设置不同的emoji 直线type=0 背景颜色是1 波浪线是2
    emoji = "🌟"
    if style == 0:
        emoji = "💡"
    elif style == 1:
        emoji = "⭐"
    # 如果reviewId不是空说明是笔记
    if reviewId != None:
        emoji = "✍️"
    color = "default"
    # 根据划线颜色设置文字的颜色
    if colorStyle == 1:
        color = "red"
    elif colorStyle == 2:
        color = "purple"
    elif colorStyle == 3:
        color = "blue"
    elif colorStyle == 4:
        color = "green"
    elif colorStyle == 5:
        color = "yellow"
    return {
        "type": "callout",
        "callout": {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": content,
                }
            }],
            "icon": {
                "emoji": emoji
            },
            "color": color
        }
    }


def delete_record(bookId):
    """检查是否已经插入过 如果已经插入了就删除"""
    time.sleep(0.3)
    filter = {
        "property": "BookId",
        "rich_text": {
            "equals": bookId
        }
    }
    response = client.databases.query(database_id=database_id, filter=filter)
    for result in response["results"]:
        time.sleep(0.3)
        client.blocks.delete(block_id=result["id"])

def insert_to_notion(bookName='', bookId='', cover='', sort=0, author='', isbn='', rating=0, noteCount=0, read_info=None):
    """插入到notion"""
    time.sleep(0.3)
    parent = {
        "database_id": database_id,
        "type": "database_id"
    }
    properties = {
        "BookName": {"title": [{"type": "text", "text": {"content": bookName}}]},
        "BookId": {"rich_text": [{"type": "text", "text": {"content": bookId}}]},
        "ISBN": {"rich_text": [{"type": "text", "text": {"content": isbn}}]},
        "URL": {"url": f"https://weread.qq.com/web/reader/{calculate_book_str_id(bookId)}"},
        "Author": {"rich_text": [{"type": "text", "text": {"content": author}}]},
        "Sort": {"number": sort},
        "Rating": {"number": rating},
        "Cover": {"files": [{"type": "external", "name": "Cover", "external": {"url": cover}}]},
        "NoteCount": {"number": noteCount},
    }
    
    if read_info:
        markedStatus = read_info.get("markedStatus", 0)
        readingTime = read_info.get("readingTime", 0)
        format_time = ""
        hour = readingTime // 3600
        if hour > 0:
            format_time += f"{hour}时"
        minutes = readingTime % 3600 // 60
        if minutes > 0:
            format_time += f"{minutes}分"
        properties["Status"] = {"select": {"name": "读完" if markedStatus == 4 else "在读"}}
        properties["ReadingTime"] = {"rich_text": [{"type": "text", "text": {"content": format_time}}]}

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
    response = client.pages.create(parent=parent, icon=icon, properties=properties)
    return response["id"]


def add_children(id, children):
    results = []
    for i in range(0, len(children)//100+1):
        time.sleep(0.3)
        response = client.blocks.children.append(
            block_id=id, children=children[i*100:(i+1)*100])
        results.extend(response.get("results"))
    return results if len(results) == len(children) else []


def add_grandchild(grandchild, results):
    for key, value in grandchild.items():
        time.sleep(0.3)
        id = results[key].get("id")
        client.blocks.children.append(block_id=id, children=[value])


def get_db_latest_sort():
    """获取database中的最新时间"""
    filter = {
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
        database_id=database_id, filter=filter, sorts=sorts, page_size=1)
    if (len(response.get("results")) == 1):
        return response.get("results")[0].get("properties").get("Sort").get("number")
    return 0

def gen_chapter_tree(chapter_list):
    tree = Tree()
    root = tree.create_node(identifier=ROOT_NODE_ID)  # root node
    p = {}
    for u in chapter_list:
        level = u.get('level', 1)
        if level <= 0:
            level = 1
        elif level > NOTION_MAX_LEVEL: # 目前仅支持header1-3
            level = NOTION_MAX_LEVEL

        parent = p.get(level - 1, root)
        chapterUid = u.get('chapterUid')
        p[level] = tree.create_node(tag=chapterUid, identifier=chapterUid, parent=parent, data=u)
    return tree

# mount bookmarks to chapter tree
def mount_bookmarks(chapter_tree, bookmark_list):
    d = defaultdict(list)
    for data in bookmark_list:
        chapterUid = data.get("chapterUid", 1)
        d[chapterUid].append(data)

    for key, value in d.items():
        node = chapter_tree.get_node(key)
        if not node:
            logging.error("chapter info not found.", key)
            continue

        # mount bookmark list to chapter list
        node.data[BOOK_MARK_KEY] = value

# remove chapter without bookmarks    
def remove_empty_chapter(chapter_tree):
    n = chapter_tree.depth()
    for d in range(n, 0, -1):
        ns = list(chapter_tree.filter_nodes(lambda x: chapter_tree.depth(x) == d))

        for n in ns:
            if n.data.get(BOOK_MARK_KEY) is None and n.is_leaf():
                #print('remove:', n)
                chapter_tree.remove_node(n.identifier)

def get_children(chapters_list, summary, bookmark_list):
    children = []
    grandchild = {}

    if len(chapters_list) > 0:
        # 添加目录
        children.append(get_table_of_contents())
        
        chapter_tree = gen_chapter_tree(chapters_list)
        mount_bookmarks(chapter_tree, bookmark_list)
        remove_empty_chapter(chapter_tree)
        
        for n in chapter_tree.expand_tree(mode=Tree.DEPTH):
            #print(tree[n].data)
            #for key, value in d.items():
            if chapter_tree[n].is_root():
                continue

            data = chapter_tree[n].data
            children.append(get_heading(data.get("level"), data.get("title")))

            #if key in chapter_dict:
            #    # 添加章节信息
            #    children.append(get_heading(chapter_dict.get(key).get("level"), chapter_dict.get(key).get("title")))
            
            for i in data.get(BOOK_MARK_KEY, []):
                children.append(get_callout(i.get("markText"), data.get("style"), i.get("colorStyle"), i.get("reviewId")))
                
                if i.get("abstract"): ## 评语，写入quote信息
                    quote = get_quote(i.get("abstract"))
                    grandchild[len(children)-1] = quote
    else:
        # 如果没有章节信息
        for data in bookmark_list:
            children.append(
                get_callout(data.get("markText"), data.get("style"), data.get("colorStyle"), data.get("reviewId")))
    
    # 追加推荐评语
    if summary:
        children.append(get_heading(1, "点评"))
        for i in summary:
            children.append(
                get_callout(i.get("review").get("content"), i.get("style"), i.get("colorStyle"), i.get("review").get("reviewId")))
    
    return children, grandchild


def transform_id(book_id):
    id_length = len(book_id)

    if re.match("^\d*$", book_id):
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("weread_cookie")
    parser.add_argument("notion_token")
    parser.add_argument("database_id")
    options = parser.parse_args()

    database_id = options.database_id
    notion_token = options.notion_token

    client = Client(
        auth=notion_token,
        log_level=logging.ERROR
    )
    latest_sort = get_db_latest_sort()

    wreader = weread.WeReadAPI(options.weread_cookie)

    books = wreader.get_notebooklist()
    for _book in books:
        sort = _book["sort"]
        if sort <= latest_sort: # 笔记无更新，跳过
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

        # delete before reinsert
        delete_record(bookID)
        
        id = insert_to_notion(bookName=book_dict.get("title"), 
                              bookId=bookID, cover=book_dict.get("cover"), 
                              sort=sort, author=book_dict.get("author"), 
                              isbn=isbn, rating=rating, noteCount=_book.get("noteCount"),
                              read_info=read_info)
        
        children, grandchild = get_children(chapters_list, summary, bookmark_list)
        results = add_children(id, children)
        if len(grandchild) > 0:
            add_grandchild(grandchild, results)
