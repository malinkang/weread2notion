const DATABASE_ID = "";
const TOKEN = "";

// 选择 type 是 1 的记录
let filter = {
  property: "Type",
  select: {
    equals: "1",
  },
};

let url = `https://api.notion.com/v1/databases/${DATABASE_ID}/query`;
let req = new Request(url);
req.headers = {
  "Authorization": `Bearer ${TOKEN}`,
  "Notion-Version": "2022-06-28",
};
req.method = "POST";
req.body = JSON.stringify({
  filter: filter,
});

let res = await req.loadJSON();

// 随机获取一条记录
let record = res.results[Math.floor(Math.random() * res.results.length)];
let markText = record.properties.MarkText.title[0].text.content;
let bookName = record.properties.BookName.rich_text[0].plain_text;

// 设置组件
let widget = new ListWidget();
widget.addText(markText);
widget.addSpacer();
let bookNameItem = widget.addText(bookName);
bookNameItem.rightAlignText();

// 设置小组件背景颜色和字体颜色
widget.backgroundColor = Color.white();
widget.textColor = Color.black();

// 在桌面上显示组件
Script.setWidget(widget);
Script.complete();
