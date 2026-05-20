# 将微信读书划线和笔记同步到 Notion

本项目通过 GitHub Actions 定时同步微信读书划线、想法和书籍信息到 Notion。
当前版本使用微信读书 API Key（Gateway 新接口），不再使用 Cookie。

预览效果：https://book.malinkang.com

> [!WARNING]
> 请不要在同步生成的 Notion 书籍页面里直接添加自己的笔记；有新笔记时，脚本会删除原页面并重新写入。

## 推荐用法：GitHub Action

新用户不需要 fork 源码，只需要在自己的仓库里创建一个 workflow 文件，例如 `.github/workflows/weread.yml`：

```yaml
name: weread sync

on:
  workflow_dispatch:
  schedule:
    - cron: "0 0 * * *"

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: malinkang/weread2notion@v1
        with:
          weread-api-key: ${{ secrets.WEREAD_API_KEY }}
          notion-token: ${{ secrets.NOTION_TOKEN }}
          notion-page: ${{ secrets.NOTION_PAGE }}
          # 或直接使用新版 Notion data source ID
          # notion-data-source-id: ${{ secrets.NOTION_DATA_SOURCE_ID }}
```

然后在 GitHub 仓库的 `Settings -> Secrets and variables -> Actions -> Repository secrets` 中配置：

| Secret | 说明 |
| --- | --- |
| `WEREAD_API_KEY` | 微信读书 API Key |
| `NOTION_TOKEN` | Notion Integration Token |
| `NOTION_PAGE` | 目标 Notion 数据库页面链接或数据库 ID |
| `NOTION_DATA_SOURCE_ID` | 可选，Notion data source ID，优先级高于 `NOTION_PAGE` |

也可以使用 `NOTION_DATABASE_ID`，对应 Action 输入是 `notion-database-id`。新版 Notion API 使用 `Notion-Version: 2026-03-11` 和 data source API；如果传入的是旧 database ID/URL，脚本会自动解析并使用第一个 data source。

## 版本选择

推荐普通用户使用稳定大版本：

```yaml
- uses: malinkang/weread2notion@v1
```

这样在 `v1` 内的兼容更新可以自动生效。如果你希望完全固定版本，可以使用具体 tag：

```yaml
- uses: malinkang/weread2notion@v1.0.0
```

## 已 fork 用户如何迁移

如果你以前 fork 了本仓库，并且 workflow 仍然运行：

```yaml
python scripts/weread.py
```

那么 fork 不会自动获得新版本。建议把 workflow 改成上面的 `uses: malinkang/weread2notion@v1`。迁移完成后，以后的兼容更新会在下一次 Action 运行时自动使用。

本仓库仍保留 `scripts/weread.py` 兼容入口，但新 workflow 推荐使用 GitHub Action 或 CLI。

## Python CLI 用法

如果你想在本地或自己的 CI 中直接使用 Python 包，可以从 GitHub 安装稳定 tag：

```bash
pip install "git+https://github.com/malinkang/weread2notion.git@v1"
weread2notion sync
```

如果后续发布到 PyPI，也可以改成 `pip install weread2notion`。

需要提供环境变量：

```bash
export WEREAD_API_KEY="..."
export NOTION_TOKEN="..."
export NOTION_PAGE="https://www.notion.so/..."
# 或 export NOTION_DATABASE_ID="..."
# 或优先使用 export NOTION_DATA_SOURCE_ID="..."
weread2notion sync
```

从源码运行：

```bash
pip install -e .
weread2notion sync
```

兼容旧入口：

```bash
python scripts/weread.py
```

## 群

> [!IMPORTANT]
> 欢迎加入群讨论。可以讨论使用中遇到的任何问题，也可以讨论 Notion 使用，后续我也会在群中分享更多 Notion 自动化工具。微信群失效的话可以添加我的微信 `malinkang`，我拉你入群。

| 微信群 | QQ群 |
| --- | --- |
| <div align="center"><img src="https://images.malinkang.com/2024/04/d54cd68602ccbb9e2747ce01f02280a3.jpg" width="50%"></div> | <div align="center"><img src="https://images.malinkang.com/2024/04/b225b17d60670e4a6ff3459bbde80d28.jpg" width="50%"></div> |

## 捐赠

如果你觉得本项目帮助了你，请作者喝一杯咖啡，你的支持是作者最大的动力。本项目会持续更新。

| 支付宝支付 | 微信支付 |
| --- | --- |
| <div align="center"><img src="https://images.malinkang.com/2024/03/7fd0feb1145f19fab3821ff1d4631f85.jpg" width="50%"></div> | <div align="center"><img src="https://images.malinkang.com/2024/03/d34f577490a32d4440c8a22f57af41da.jpg" width="50%"></div> |
