
class NotionAPI:
    def __init__(self, token):
        self.token = token

class BlockHelper:
    """生成notion格式的工具函数"""
    def __init__(self):
        pass

    """获取目录"""
    @staticmethod
    def table_of_contents():
        return {
            "type": "table_of_contents",
            "table_of_contents": {
                "color": "default"
            }
        }

    @staticmethod
    def heading(level, content):
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

    @staticmethod
    def quote(content):
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

    @staticmethod
    def callout(content, style, colorStyle, reviewId):
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