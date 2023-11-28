# 将微信读书划线和笔记同步到Notion


本项目通过Github Action每天定时同步微信读书划线到Notion。

预览效果：https://book.malinkang.com

> [!WARNING]  
> 请不要在Page里面添加自己的笔记，有新的笔记的时候会删除原笔记重新添加。


## 使用

1. star本项目

2. fork这个工程
3. 获取微信读书的Cookie
    * 浏览器打开 https://weread.qq.com/
    * 微信扫码登录确认
    * 按F12进入开发者模式，依次点 Network -> Doc -> Headers-> cookie。复制 Cookie 字符串;
4. 获取NotionToken
    * 浏览器打开https://www.notion.so/my-integrations
    * 点击New integration 输入name提交
    * 然后copy

5. 复制[这个Notion模板](https://malinkang.notion.site/e27842548a6d4a81bc7aea736d90d6dd?v=b255858d3eaa409f97f1ecb32a14a5b6&pvs=4)，

6. 在Connections添加你第4步创建的Integration。

7. 获取NotionDatabaseID
    * 打开Notion数据库，点击右上角的Share，然后点击Copy link
    * 获取链接后比如 https://www.notion.so/malinkang/1b78f0fd0d03484caa00154285ffec0c?v=7ed7e3fbe69043a28d2847e76f075d99&pvs=4 中间的1b78f0fd0d03484caa00154285ffec0c就是DatabaseID

8. 在Github的Secrets中添加以下变量
    * 打开你fork的工程，点击Settings->Secrets and variables->New repository secret
    * 添加以下变量
        * WEREAD_COOKIE
        * NOTION_TOKEN
        * NOTION_DATABASE_ID

## 捐赠

如果你觉得本项目帮助了你，请作者喝一杯咖啡，你的支持是作者最大的动力。本项目会持续更新。

![](./asset/WechatIMG27.jpg)

## 问题解答

1. 如果发现数据没有同步，请点击Action查看运行状态。红色表示失败，绿色代表成功，如果有失败的点击去查看详情，检查值是否填写正确
2. Categories is expected to be select. 这个是模板设置的问题，将模板中的Categories修改为Multi-select类型
3. 模板中的属性解释
    * BookName：书名
    * BookId：书Id
    * Sort：主要用于增量同步没啥实际意义
    * Cover：封面
    * Author：作者
    * Status：状态
    * ReadingTime：阅读时长
    * Date：读完日期
    * Rating：评分
    * URL：网页链接
    * Categories：分类
    * Progress：阅读进度


## 微信群
> [!WARNING]  
> 微信群已满，加我备注微信读书，我拉你进群。
> 也可以加TG群：https://t.me/wereadnotion

 ![image](./asset/WechatIMG24.jpg)


