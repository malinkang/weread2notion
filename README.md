# 将微信读书划线和笔记同步到Notion


本项目通过Github Action每天定时同步微信读书笔记（划线、评语、推荐评论）到Notion。

注意：请不要在Page里面添加自己的笔记，有新的笔记的时候会删除原笔记重新添加。

## 使用

1. star本项目
2. fork这个工程
3. 获取微信读书的Cookie
    * 浏览器打开 https://weread.qq.com/
    * 微信扫码登录确认，提示没有权限忽略即可
    * 按F12进入开发者模式，依次点 Network -> Doc -> Headers-> cookie。复制 Cookie 字符串;
4. 获取NotionToken
    * 浏览器打开https://www.notion.so/my-integrations
    * 点击New integration 输入name提交
    * 点击show，然后copy
5. 复制[这个Notion模板](https://gelco.notion.site/67639069c7b84f55b6394f16ecda0c4f?v=b5d09dc635db4b3d8ba13b200b88d823&pvs=25)，删掉所有的数据，并点击右上角设置，Connections添加你创建的Integration。

6. 获取NotionDatabaseID
    * 打开Notion数据库，点击右上角的Share，然后点击Copy link
    * 获取链接后比如https://gelco.notion.site/67639069c7b84f55b6394f16ecda0c4f?v=b5d09dc635db4b3d8ba13b200b88d823&pvs=25 中间的67639069c7b84f55b6394f16ecda0c4f就是DatabaseID
7. 在Github的Secrets中添加以下变量来实现每日自动同步
    * 打开你fork的工程，点击Settings->Secrets and variables->New repository secret
    * 添加以下变量
        * WEREAD_COOKIE
        * NOTION_TOKEN
        * NOTION_DATABASE_ID
8. 也可以本地运行脚本: python3 ./main.py sync 

## 更新

- feat: 新增noteCount字段，删除无用的部分字段
- feat: 调整内容组织方式，增加对多级目录的支持。会将笔记归属的目录链条全部写入notion。注意notion仅支持1-3级目录，大于3时全部当做3级目录。
- feat: 增加lastReadingDate。注意如果没有笔记操作则不会更新该条记录。
- feat: 增加内容block组织形式配置，可以将内容展现形态指定为paragraph/list/callout，详见default.ini配置
