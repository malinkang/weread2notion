

import argparse
import json
import logging
import re
import time
from notion_client import Client
import requests
from requests.utils import cookiejar_from_dict
from http.cookies import SimpleCookie
from datetime import datetime
import hashlib

WEREAD_URL = "https://weread.qq.com/"
WEREAD_NOTEBOOKS_URL = "https://i.weread.qq.com/user/notebooks"
WEREAD_BOOKMARKLIST_URL = "https://i.weread.qq.com/book/bookmarklist"
WEREAD_CHAPTER_INFO = "https://i.weread.qq.com/book/chapterInfos"
WEREAD_READ_INFO_URL = "https://i.weread.qq.com/book/readinfo"
WEREAD_REVIEW_LIST_URL = "https://i.weread.qq.com/review/list"
WEREAD_BOOK_INFO = "https://i.weread.qq.com/book/info"


def parse_cookie_string(cookie_string):
    cookie = SimpleCookie()
    cookie.load(cookie_string)
    cookies_dict = {}
    cookiejar = None
    for key, morsel in cookie.items():
        cookies_dict[key] = morsel.value
        cookiejar = cookiejar_from_dict(
            cookies_dict, cookiejar=None, overwrite=True
        )
    return cookiejar


def get_bookmark_list(bookId):
    """获取我的划线"""
    params = dict(bookId=bookId)
    r = session.get(WEREAD_BOOKMARKLIST_URL, params=params)
    if r.ok:
        updated = r.json().get("updated")
        updated = sorted(updated, key=lambda x: (
            x.get("chapterUid", 1), int(x.get("range").split("-")[0])))
        return r.json()["updated"]
    return None


def get_read_info(bookId):
    params = dict(bookId=bookId, readingDetail=1,
                  readingBookIndex=1, finishedDate=1)
    r = session.get(WEREAD_READ_INFO_URL, params=params)
    if r.ok:
        return r.json()
    return None


def get_bookinfo(bookId):
    """获取书的详情"""
    params = dict(bookId=bookId)
    r = session.get(WEREAD_BOOK_INFO, params=params)
    isbn = ""
    if r.ok:
        data = r.json()
        isbn = data["isbn"]
        newRating = data["newRating"]/1000
    return (isbn, newRating)


def get_review_list(bookId):
    """获取笔记"""
    params = dict(bookId=bookId, listType=11, mine=1, syncKey=0)
    r = session.get(WEREAD_REVIEW_LIST_URL, params=params)
    reviews = r.json().get("reviews")
    summary = list(filter(lambda x: x.get("review").get("type") == 4, reviews))
    reviews = list(filter(lambda x: x.get("review").get("type") == 1, reviews))
    reviews = list(map(lambda x: x.get("review"), reviews))
    reviews = list(map(lambda x: {**x, "markText": x.pop("content")}, reviews))
    return summary, reviews


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


def check(bookId):
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


def get_chapter_info(bookId):
    """获取章节信息"""
    body = {
        'bookIds': [bookId],
        'synckeys': [0],
        'teenmode': 0
    }
    r = session.post(WEREAD_CHAPTER_INFO, json=body)
    if r.ok and "data" in r.json() and len(r.json()["data"]) == 1 and "updated" in r.json()["data"][0]:
        update = r.json()["data"][0]["updated"]
        return {item["chapterUid"]: item for item in update}
    return None


def insert_to_notion(bookName, bookId, cover, sort, author,isbn,rating):
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
    }
    read_info = get_read_info(bookId=bookId)
    if read_info != None:
        markedStatus = read_info.get("markedStatus", 0)
        readingTime = read_info.get("readingTime", 0)
        format_time = ""
        hour = readingTime // 3600
        if hour > 0:
            format_time += f"{hour}时"
        minutes = readingTime % 3600 // 60
        if minutes > 0:
            format_time += f"{minutes}分"
        properties["Status"] = {"select": {
            "name": "读完" if markedStatus == 4 else "在读"}}
        properties["ReadingTime"] = {"rich_text": [
            {"type": "text", "text": {"content": format_time}}]}
        if "finishedDate" in read_info:
            properties["Date"] = {"date": {"start": datetime.utcfromtimestamp(read_info.get(
                "finishedDate")).strftime("%Y-%m-%d %H:%M:%S"), "time_zone": "Asia/Shanghai"}}

    icon = {
        "type": "external",
        "external": {
            "url": cover
        }
    }
    # notion api 限制100个block
    response = client.pages.create(
        parent=parent, icon=icon, properties=properties)
    id = response["id"]
    return id


def add_children(id, children):
    results = []
    for i in range(0, len(children)//100+1):
        time.sleep(0.3)
        response = client.blocks.children.append(
            block_id=id, children=children[i*100:(i+1)*100])
        results.extend(response.get("results"))
    return results if len(results) == len(children) else None


def add_grandchild(grandchild, results):
    for key, value in grandchild.items():
        time.sleep(0.3)
        id = results[key].get("id")
        client.blocks.children.append(block_id=id, children=[value])


def get_notebooklist():
    """获取笔记本列表"""
    r = session.get(WEREAD_NOTEBOOKS_URL)
    if r.ok:
        data = r.json()
        books = data.get("books")
        books.sort(key=lambda x: x["sort"])
        return books
    else:
        print(r.text)
    return None


def get_sort():
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


def get_children(chapter, summary, bookmark_list):
    children = []
    grandchild = {}
    if chapter != None:
        # 添加目录
        children.append(get_table_of_contents())
        d = {}
        for data in bookmark_list:
            chapterUid = data.get("chapterUid", 1)
            if (chapterUid not in d):
                d[chapterUid] = []
            d[chapterUid].append(data)
        for key, value in d .items():
            if key in chapter:
                # 添加章节
                children.append(get_heading(
                    chapter.get(key).get("level"), chapter.get(key).get("title")))
            for i in value:
                callout = get_callout(
                    i.get("markText"), data.get("style"), i.get("colorStyle"), i.get("reviewId"))
                children.append(callout)
                if i.get("abstract") != None and i.get("abstract") != "":
                    quote = get_quote(i.get("abstract"))
                    grandchild[len(children)-1] = quote

    else:
        # 如果没有章节信息
        for data in bookmark_list:
            children.append(get_callout(data.get("markText"),
                            data.get("style"), data.get("colorStyle"), data.get("reviewId")))
    if summary != None and len(summary) > 0:
        children.append(get_heading(1, "点评"))
        for i in summary:
            children.append(get_callout(i.get("review").get("content"), i.get(
                "style"), i.get("colorStyle"), i.get("review").get("reviewId")))
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
    weread_cookie = options.weread_cookie
    database_id = options.database_id
    notion_token = options.notion_token
    session = requests.Session()
    session.cookies = parse_cookie_string(weread_cookie)
    client = Client(
        auth=notion_token,
        log_level=logging.ERROR
    )
    session.get(WEREAD_URL)
    latest_sort = get_sort()
    books = get_notebooklist()
    if (books != None):
        for book in books:
            sort = book["sort"]
            if sort <= latest_sort:
                continue
            book = book.get("book")
            title = book.get("title")
            cover = book.get("cover")
            bookId = book.get("bookId")
            author = book.get("author")
            check(bookId)
            chapter = get_chapter_info(bookId)
            bookmark_list = get_bookmark_list(bookId)
            summary, reviews = get_review_list(bookId)
            bookmark_list.extend(reviews)
            bookmark_list = sorted(bookmark_list, key=lambda x: (
                x.get("chapterUid", 1), 0 if (x.get("range", "") == "" or x.get("range").split("-")[0]=="" ) else int(x.get("range").split("-")[0])))
            isbn,rating = get_bookinfo(bookId)
            children, grandchild = get_children(
                chapter, summary, bookmark_list)
            id = insert_to_notion(title, bookId, cover, sort, author,isbn,rating)
            results = add_children(id, children)
            if(len(grandchild)>0 and results!=None):
                add_grandchild(grandchild, results)
