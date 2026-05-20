# WeRead2Notion

将微信读书的书籍、划线和笔记同步到 Notion。

本项目使用微信读书 API Key 读取数据，并通过 GitHub Actions 定时同步到 Notion。新版不再需要复制微信读书 Cookie。

预览效果：https://malinkang.notion.site/weread2notion?

> [!WARNING]
> WeRead2Notion 会在检测到书籍笔记更新时删除原来的同步页面，然后重新写入微信读书数据。请不要在同步生成的 Notion 书籍页面里添加自己的笔记、批注或其他重要内容，否则下次同步时可能会被删除且无法恢复。

## 使用文档

完整教程请查看：

https://www.notionhub.app/docs/weread2notion.html

文档里包含：

- Notion 模板复制和授权
- 微信读书 API Key 获取
- GitHub Fork 和 Actions 配置
- 常见问题排查

## 关注公众号

如果你想获取后续更新，或了解更多 Notion 自动化工具，欢迎关注公众号：**Notion自动化**。

![公众号：Notion自动化](https://cdn.notionhub.app/notionhub/gzh.jpg)
