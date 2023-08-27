"""
封装notion相关操作
"""

# class NotionAPI:
#     """暂未启用"""

#     def __init__(self, token):
#         self.token = token

#     def dumy(self):
#         """pass"""
#         pass

class BlockHelper:
    """生成notion格式的工具函数"""

    headings = {
        1: "heading_1",
        2: "heading_2",
        3: "heading_3",
    }

    table_contents = {
        "type": "table_of_contents",
        "table_of_contents": {
            "color": "default"
        }
    }

    color_styles = {
            1: "red",
            2: "purple",
            3: "blue",
            4: "green",
            5: "yellow",
        }

    def __init__(self):
        pass

    @classmethod
    def table_of_contents(cls):
        """获取目录"""
        return cls.table_contents

    @classmethod
    def heading(cls, level, content):
        """取heading格式"""""
        heading_type = cls.headings.get(level, "heading_3")
        return {
            "type": heading_type,
            heading_type: {
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

    @classmethod
    def quote(cls, content):
        """取引用格式"""
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
    
    @classmethod
    def emoj_style(cls, style, review_id):
        """根据不同的划线样式设置不同的emoji 直线type=0 背景颜色是1 波浪线是2"""
        emoji = "🌟"
        if style == 0:
            emoji = "💡"
        elif style == 1:
            emoji = "⭐"
        # 如果reviewId不是空说明是笔记
        if review_id is not None:
            emoji = "✍️"
        return emoji

    @classmethod
    def callout(cls, content, style, color, review_id, enable_emoj=False):
        """取callout格式"""
        emoji = ""
        if enable_emoj:
            emoji = cls.emoj_style(style, review_id)
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
                "color": cls.color_styles.get(color, "default"),
            }
        }

    @classmethod
    def paragraph(cls, content, style, color, review_id, enable_emoj=False):
        """取text格式"""
        emoji = ""
        if enable_emoj:
            emoji = cls.emoj_style(style, review_id)
        return {
            "type": "paragraph",
            "paragraph": {
                    "rich_text": [{
                        "type": "text",
                        "text": {
                            "content": emoji+content,
                    }
                }],
            "color": cls.color_styles.get(color, "default"),
            }
        }

    @classmethod
    def bullet_list(cls, content, style, color, review_id, enable_emoj=False):
        """取callout格式"""
        emoji = ""
        if enable_emoj:
            emoji = cls.emoj_style(style, review_id)
        return {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{
                    "type": "text",
                    "text": {
                        "content": emoji+content,
                    }
                }],
                "color": cls.color_styles.get(color, "default"),
            }
        }
