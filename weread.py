

import argparse
import json
import logging
import time
from notion_client import Client
import requests
from requests.utils import cookiejar_from_dict
from http.cookies import SimpleCookie
from datetime import datetime

WEREAD_URL = "https://weread.qq.com/"
WEREAD_NOTEBOOKS_URL = "https://i.weread.qq.com/user/notebooks"
WEREAD_BOOKMARKLIST_URL = "https://i.weread.qq.com/book/bookmarklist"
WEREAD_CHAPTER_INFO = "https://i.weread.qq.com/book/chapterInfos"
WEREAD_READ_INFO_URL = "https://i.weread.qq.com/book/readinfo"
WEREAD_REVIEW_LIST_URL = "https://i.weread.qq.com/review/list"
WEREAD_REVIEW_BOOK_INFO = "https://i.weread.qq.com/book/info"


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
    url = ""
    params = dict(bookId=bookId)
    r = session.get(url, params=params)
    isbn = ""
    if r.ok:
        data = r.json()
        isbn = data["isbn"]
        title = data["title"]
    return isbn


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
    url = 'https://i.weread.qq.com/book/chapterInfos'
    r = session.post(url, json=body)
    if r.ok and "data" in r.json() and len(r.json()["data"]) == 1 and "updated" in r.json()["data"][0]:
        update = r.json()["data"][0]["updated"]
        return {item["chapterUid"]: item for item in update}
    return None


def insert_to_notion(bookName, bookId, cover, sort, author):
    """插入到notion"""
    time.sleep(0.3)
    parent = {
        "database_id": database_id,
        "type": "database_id"
    }
    properties = {
        "BookName": {"title": [{"type": "text", "text": {"content": bookName}}]},
        "BookId": {"rich_text": [{"type": "text", "text": {"content": bookId}}]},
        "Author": {"rich_text": [{"type": "text", "text": {"content": author}}]},
        "Sort": {"number": sort},
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


def add_blocks(id, children):
    l = []
    for child in children:
        if (len(l) < 100 and child.get("quote") == None):
            l.append(child)
        elif len(l) == 100:
            time.sleep(0.3)
            client.blocks.children.append(block_id=id, children=l)
            l.clear()
            if (child.get("quote") != None):
                quote = child.pop("quote")
                time.sleep(0.3)
                block_id = client.blocks.children.append(
                    block_id=id, children=[child]).get("results")[0].get("id")
                time.sleep(0.3)
                client.blocks.children.append(
                    block_id=block_id, children=[quote])
            else:
                l.append(child)
        elif child.get("quote") != None:
            quote = child.pop("quote")
            time.sleep(0.3)
            client.blocks.children.append(block_id=id, children=l)
            l.clear()
            time.sleep(0.3)
            block_id = client.blocks.children.append(
                block_id=id, children=[child]).get("results")[0].get("id")
            time.sleep(0.3)
            client.blocks.children.append(block_id=block_id, children=[quote])
    if (len(l) > 0):
        time.sleep(0.3)
        client.blocks.children.append(block_id=id, children=l)


def get_notebooklist():
    """获取笔记本列表"""
    r = session.get(WEREAD_NOTEBOOKS_URL)
    if r.ok:
        data = r.json()
        books = data.get("books")
        books.sort(key=lambda x: x["sort"])
        return books
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
                if i.get("abstract") != None and i.get("abstract") != "":
                    quote = get_quote(i.get("abstract"))
                    callout["quote"] = quote
                children.append(callout)

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
    return children


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
                x.get("chapterUid", 1), 0 if x.get("range","") == "" else int(x.get("range").split("-")[0])))
            children = get_children(chapter, summary, bookmark_list)
            id = insert_to_notion(title, bookId, cover, sort, author)
            add_blocks(id, children)
