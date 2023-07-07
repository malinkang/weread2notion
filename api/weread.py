# 封装微信api的调用

class WeReadAPI:
    WEREAD_NOTEBOOKS_URL = "https://i.weread.qq.com/user/notebooks"
    WEREAD_CHAPTER_INFO = "https://i.weread.qq.com/book/chapterInfos"
    WEREAD_BOOKMARKLIST_URL = "https://i.weread.qq.com/book/bookmarklist"
    WEREAD_REVIEW_LIST_URL = "https://i.weread.qq.com/review/list"
    WEREAD_BOOK_INFO = "https://i.weread.qq.com/book/info"

    def __init__(self, session):
        self.session = session

    def get_notebooklist(self):
        """全量书籍笔记信息列表，仅包括笔记更新时间、数量等，不包括笔记明细"""
        r = self.session.get(self.WEREAD_NOTEBOOKS_URL)
        if r.ok:
            data = r.json()
            books = data.get("books")
            books.sort(key=lambda x: x["sort"])  # 最近更新（划线、评语以及推荐都算更新）时间
            return books
        else:
            print(r.text)
            return []
        
    def get_chapter_list(self, bookId):
        """获取章节信息列表"""
        body = {
            'bookIds': [bookId],
            'synckeys': [0],
            'teenmode': 0
        }
        r = self.session.post(self.WEREAD_CHAPTER_INFO, json=body)
        if r.ok and "data" in r.json() and len(r.json()["data"]) == 1 and "updated" in r.json()["data"][0]:
            update = r.json()["data"][0]["updated"]
            #d = {item["chapterUid"]: item for item in update}
            return update
        else:
            print(r.text)
        return {}
    
    def get_bookmark_list(self, bookId):
        """获取书籍划线列表"""
        params = dict(bookId=bookId)
        r = self.session.get(self.WEREAD_BOOKMARKLIST_URL, params=params)
        if r.ok:
            updated = r.json().get("updated")
            updated = sorted(updated, key=lambda x: (
                x.get("chapterUid", 1), int(x.get("range").split("-")[0])))
            return r.json()["updated"]
        else:
            print(r.text)
        return []
    
    def get_review_list(self, bookId):
        """获取笔记列表，包括笔记、推荐总结"""
        params = dict(bookId=bookId, listType=11, mine=1, syncKey=0)
        r = self.session.get(self.WEREAD_REVIEW_LIST_URL, params=params)
        if r.ok:
            reviews = r.json().get("reviews")
            # 总结
            summary = list(filter(lambda x: x.get("review").get("type") == 4, reviews))
            # 笔记（评语）
            reviews = list(filter(lambda x: x.get("review").get("type") == 1, reviews))
            reviews = list(map(lambda x: x.get("review"), reviews))
            reviews = list(map(lambda x: {**x, "markText": x.pop("content")}, reviews))
            return summary, reviews
        else:
            print(r.text)
            return [], []


    def get_bookinfo(self, bookId):
        """获取书的详情"""
        params = dict(bookId=bookId)
        r = self.session.get(self.WEREAD_BOOK_INFO, params=params)
        isbn = ""
        if r.ok:
            data = r.json()
            isbn = data["isbn"]
            newRating = data["newRating"]/1000
        return (isbn, newRating)
