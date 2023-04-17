

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


def get_hot(bookName,cover, bookId):
    """获取热门划线"""
    params = dict(bookId=bookId)
    r = session.get(WEREAD_BOOKMARKLIST_URL, params=params)
    if r.ok:
        datas = r.json()["updated"]
        for data in datas:
            if not check(data["bookmarkId"]):
                insert_to_notion(bookName,cover, data)
            else:
                print("已经插入过了")


def check(bookmarkId):
    """检查是否已经插入过"""
    filter = {
        "property": "BookmarkId",
        "rich_text": {
            "equals": bookmarkId
        }
    }
    response = client.databases.query(database_id=database_id,filter=filter)
    return len(response["results"]) > 0



def insert_to_notion(bookName,cover, data):
    time.sleep(0.3)
    """插入到notion"""
    parent = {
        "database_id": database_id,
        "type": "database_id"
    }
   
    properties = {
        "BookName": {"title": [{"type": "text", "text": {"content": data["markText"]}}]},
        "BookId": {"rich_text": [{"type": "text", "text": {"content": data["bookId"]}}]},
        "BookmarkId": {"rich_text": [{"type": "text", "text": {"content": data["bookmarkId"]}}]},
        "MarkText": {"rich_text": [{"type": "text", "text": {"content": bookName}}]},
        "Type": {"select": {"name": str(data["type"])}},
        "Cover":{"files":[{"type":"external","name":"Cover","external":{"url":cover}}]},
       
    }
    if("createTime" in data):
        date = datetime.utcfromtimestamp(data["createTime"]).strftime("%Y-%m-%d %H:%M:%S")
        properties["Date"] = {"date": {"start":date,"time_zone": "Asia/Shanghai"}}
    if("style" in data):
        properties["Style"] =  {"select": {"name": str(data["style"])}}
    client.pages.create(parent=parent, properties=properties)


def get_notebooklist():
    """获取笔记本列表"""
    r = session.get(WEREAD_NOTEBOOKS_URL)
    books = []
    with open("notebooks.json", "w", encoding="utf-8") as f:
        f.write(r.text)
    if r.ok:
        data = r.json()
        books = data["books"]
        for book in books:
            title = book["book"]["title"]
            cover = book["book"]["cover"]
            bookId = book["book"]["bookId"]
            get_hot(title,cover,bookId)

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
        log_level=logging.DEBUG
    )
    session.get(WEREAD_URL)
    get_notebooklist()

