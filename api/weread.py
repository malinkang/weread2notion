# 封装微信api的调用


class WeReadAPI:
    WEREAD_NOTEBOOKS_URL = "https://i.weread.qq.com/user/notebooks"

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
