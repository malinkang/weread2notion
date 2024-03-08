from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from json import dump
from typing import Callable, Dict, List, Optional, Union

import requests


class Weread2ReadwiseError(Exception):

    def __init__(self, message: str):
        self.message = message

        super().__init__(self.message)


@dataclass
class ReadwiseAPI:
    """Dataclass for ReadWise API endpoints"""

    base_url: str = "https://readwise.io/api/v2"
    highlights: str = base_url + "/highlights/"
    books: str = base_url + "/books/"


class Category(Enum):
    articles = 1
    books = 2
    tweets = 3
    podcasts = 4


@dataclass
class ReadwiseHighlight:
    text: str
    title: Optional[str] = None
    author: Optional[str] = None
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    source_type: Optional[str] = None
    category: Optional[
        str] = None  # One of: books, articles, tweets or podcasts
    note: Optional[str] = None
    location: Union[int, None] = 0
    location_type: Optional[str] = "page"
    highlighted_at: Optional[str] = None
    highlight_url: Optional[str] = None

    def __post_init__(self):
        if not self.location:
            self.location = None

    def get_nonempty_params(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if v}


class Readwise:

    def __init__(self, readwise_token: str):
        self._token = readwise_token
        self._header = {"Authorization": f"Token {self._token}"}
        self.endpoints = ReadwiseAPI
        self.failed_highlights: List = []

    def create_highlights(self, highlights: List[Dict]) -> None:

        resp = requests.post(
            url=self.endpoints.highlights,
            headers=self._header,
            json={"highlights": highlights},
        )
        if resp.status_code != 200:
            error_log_file = (
                f"error_log_{resp.status_code}_failed_post_request_to_readwise.json"
            )
            with open(error_log_file, "w") as f:
                dump(resp.json(), f)
            raise Weread2ReadwiseError(
                f"Uploading to Readwise failed with following details:\n"
                f"POST request Status Code={resp.status_code} ({resp.reason})\n"
                f"Error log is saved to {error_log_file} file.")

    @staticmethod
    def convert_tags_to_readwise_format(tags: List[str],
                                        preprocess: Optional[Callable] = None
                                        ) -> str:
        """
        Readwise supports inline tagging e.g. .tag1 .tag2
        """
        func = lambda x: x if preprocess is None else preprocess
        return " ".join([f".{func(t.lower())}" for t in tags])

    def format_readwise_note(self,
                             tags: Optional[List[str]] = None,
                             comment: str = '') -> Union[str, None]:
        rw_tags = self.convert_tags_to_readwise_format(tags) if tags else ""
        highlight_note = ""
        if rw_tags:
            highlight_note += rw_tags + "\n"
        if comment:
            highlight_note += comment
        return highlight_note if highlight_note else None

    def convert_weread_hilights_to_readwise(
        self,
        title,
        author,
        chapter,
        bookmark_list,
        source_url,
        cover,
    ):  
        highlights = []
        if author == "公众号":
            cat = Category.articles.name
        else:
            cat = Category.books.name
        if chapter != None:
            # 添加目录
            d = {}
            for data in bookmark_list:
                chapterUid = data.get("chapterUid", 1)
                if chapterUid not in d:
                    d[chapterUid] = []
                d[chapterUid].append(data)
            for key, value in d.items():
                ch = chapter.get(key)
                chapter_title=ch.get("title") if ch else ""
                for data in value:
                    createTime = float(data.get("createTime"))
                    # convert unixtime to UTC format Example: "2020-07-14T20:11:24+00:00"
                    createTime = datetime.utcfromtimestamp(createTime).strftime(
                        '%Y-%m-%dT%H:%M:%S+00:00')
                    location = 0 if (data.get("range", "") == "" or
                                    data.get("range").split("-")[0] == "") else int(
                                        data.get("range").split("-")[0])
                    markText = chapter_title + '\n\n' + data.get("markText")
                    abstract = data.get("abstract")
                    if abstract and isinstance(abstract, str):
                        markText = markText + "\n" + abstract
                    highlights.append(
                        ReadwiseHighlight(
                            text=markText,
                            title=title,
                            author=author,
                            category=cat,
                            highlighted_at=createTime,
                            source_url=source_url,
                            image_url=cover,
                            location=location,
                            location_type="order",
                    ))

        else:
            for data in bookmark_list:
                markText = data.get("markText")
                createTime = float(data.get("createTime"))
                # convert unixtime to UTC format Example: "2020-07-14T20:11:24+00:00"
                createTime = datetime.utcfromtimestamp(createTime).strftime(
                    '%Y-%m-%dT%H:%M:%S+00:00')
                location = 0 if (data.get("range", "") == "" or
                                data.get("range").split("-")[0] == "") else int(
                                    data.get("range").split("-")[0])
                highlights.append(
                    ReadwiseHighlight(
                        text=markText,
                        title=title,
                        author=author,
                        category=cat,
                        highlighted_at=createTime,
                        source_url=source_url,
                        image_url=cover,
                        location=location,
                        location_type="order",
                    ))
        return [h.get_nonempty_params() for h in highlights]
