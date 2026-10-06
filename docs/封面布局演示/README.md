# 封面布局演示（方案）

> 生成物：`封面布局演示.pdf`（A4，16 页）
> 生成器：`gen_cover_demo.py`（真实渲染 + 编号标注）

## 1. 目的

把「**合并时加封面封底、说明（以下所有内容）**」总开关打开后，PDF 合并
**所有可能出现的页**集中到一份自解释的演示文档里：每页顶部灰字标注该页的
**控制设置**，封面页左侧编号对应页内「封面元素图例」，文末附完整
「封面元素对照表」——用户据此即可知道每个封面元素的布局与样式。

## 2. 总开关与模式

| 项 | 设置名（GUI） | 配置键 | 说明 |
|---|---|---|---|
| 总开关 | 合并时加封面封底、说明（以下所有内容） | `cover.enabled` | 关闭＝直接拼接原文件，仅生成书签，不插任何封面/封底/说明页 |
| 模式 | PDF 合并模式（打印模式 / 阅读模式） | `cover.mode` | `print`＝自动补空白页；`reading`＝去空白页 |

## 3. 页序（`cover.mode=print` 打印模式）

1. 封面页
2. 空白页（封面后）
3. 封面图页
4. 空白页（封面图后）
5. 编辑说明页（全局 → 丛书特定，可多页）
6. 空白页（编辑说明后，按需）
7. 空白页（说明页前，按需）
8. 说明页（部类统计 + 完整清单，可多页）
9. 空白页（说明页后，按需）
10. 目录页
11. 空白页（目录后，按需）
12. 正文（各经书逐部）
13. 空白页（正文补偶页，按需）
14. 封底图页
15. 封底（空白）

> `cover.mode=reading` 时去掉所有空白页（适合屏幕阅读）。
> 各段补白与 `ebook_merger._merge_pdfs_impl` 一致（封面/封面图/编辑说明/说明/目录
> 从奇数页起；正文示意为单页，按打印模式补了一页偶页）。

## 4. 元素对照表

| 页 | 元素 | 设置名（GUI） | 配置键 | 样式来源 |
|---|---|---|---|---|
| 封面 | 左上角系列名/落款 | 左上角系列名 | `cover.imprint` | 字体 `styles.cbeta.font`；色 `styles.cbeta.color`；字号 `sizes.cbeta_a4` / ratio `cbeta` |
| 封面 | 封面标题（丛书名｜册名） | 封面标题 | 合并名（`丛书名｜部类行`） | 字体 `styles.title.font`；ratio `title`；色 `title`；Y `positions.title_y_ratio`（缺省 0.25） |
| 封面 | 封面部类行 | 封面部类行 / 显示部类·书名 / 部类行细节 | `cover.bulei.*` | 字体 `styles.toc_item.font`；色 `toc_item`；Y `positions.group_y_ratio`（缺省 0.30） |
| 封面 | 书籍版本/来源 | 书籍版本/来源（官方 / 自制） | `cover.organizer_official` / `cover.organizer_xml` | 字体 `styles.date.font`；色 `organizer`；Y `positions.organizer_y_ratio`（缺省 0.84） |
| 封面 | 日期/署名 | 日期/署名 | `cover.date_text`（`{date}`=今天） | 字体 `styles.date.font`；色 `date`；Y `positions.date_y_ratio`（缺省 0.90） |
| 封面 | 背景色 | 封面背景色 | `cover.styles.background.color` | 整页填充 |
| 封面图页 | 封面图 | 封面图 | `cover.images.buddha` | `assets/images/B01.jpg`（回退 `1.*`，后缀不限）；图占页 80% 居中 |
| 编辑说明页 | 标题/分级标题/正文/对齐/分页 | 加编辑说明页 / 加丛书说明页 | `cover.edit_note` / 丛书 `edit_note` | 字体 `styles.editnote_title.font` / `styles.editnote_body.font`；字号 `sizes.editnote_body` |
| 说明页 | 说明页标题 | 说明页标题 | `cover.intro.title` | 字体 `styles.toc_title.font`；色 `toc_title` |
| 说明页 | 自制书说明 | 自制书说明 | `cover.intro.note` | 字体 `styles.toc_item.font`；仅来源=自制时显示 |
| 说明页 | 简介行（本丛书…/三藏分布） | （自动从书单推导） | `cover.intro.summary` | 字体 `styles.intro_summary.font`（默认仿宋）；色 `toc_item` |
| 说明页 | 部类统计 + 完整清单 | 插入说明页（部类统计 + 完整清单） | `cover.intro.sections` | 字体 `styles.toc_item.font`；部类段每段一行（按 “ / ” 拆） |
| 说明页 | 背景色 | 说明页背景色 | `cover.styles.intro_background.color` | 缺席＝跟随封面背景色 |
| 目录页 | 目录标题（“目录”） | （自动） | — | 字体 `styles.toc_title.font`；色 `toc_title` |
| 目录页 | 目录条目（含序号） | （自动） | — | 字体 `styles.toc_item.font`；色 `toc_item`；同行微右移模拟加粗 |
| 目录页 | 页码（右对齐） | （自动） | — | 字体 `styles.toc_page.font`；色 `toc_page` |
| 目录页 | 背景色 | 目录页背景色 | `cover.styles.toc_background.color` | 缺席＝跟随封面背景色 |
| 目录页 | 标题/条目起始高度 | （自动） | `positions.toc_y_ratio` / `positions.toc_item_y_ratio` | 缺省 0.11 / 0.20 |
| 正文 | 各经书正文 | — | — | 逐部；打印模式每部补偶页 |
| 封底图页 | 封底图 | 封底图 | `cover.images.weituo` | `assets/images/B02.jpg`（回退 `2.*`，后缀不限） |
| 封底 | 空白封底 | — | `cover.mode=print` | 打印模式：无图也保留一张空白封底 |
| 空白页 | 自动补白 | — | `cover.mode=print` | 封面/封面图/编辑说明/说明/目录后按需补白（保证奇数页起） |

> 字号/边距在「封面/版式 → 基准字号 / 边距」子页签，按纸张
> （a5 / a4 / 16k / 32k）分别设置；未配置走出厂默认。字体在「字体」子页签，
> 缺繁体字形时按 `ebook_merger._FALLBACK_FONTS`（黑体 → 微软雅黑 → 宋体）回退。

## 5. 重新生成

在 publish 仓库根目录：

```bat
.venv\Scripts\python docs\封面布局演示\gen_cover_demo.py
.venv\Scripts\python docs\封面布局演示\gen_cover_demo.py --paper a5
.venv\Scripts\python docs\封面布局演示\gen_cover_demo.py --out 自定义路径.pdf
```

- 默认纸张 **A4**；`--paper` 可选 `a4/a5/16k/32k`。
- 依赖 `pymupdf`、`reportlab`（publish 运行环境自带）。
- 演示内容（示例丛书名/说明/编辑说明/目录条目）写在 `gen_cover_demo.py`
  顶部的 `DEMO_*` 常量里，可直接改。
- 封面代码（`ebook_merger._cover_pdf` 等）变动后重新运行即可同步；
  若改了封面默认位置/字号，`_cover_markers` 里的同源公式需一并核对。

## 6. 文件清单

| 文件 | 说明 |
|---|---|
| `gen_cover_demo.py` | 生成器（真实渲染 + 顶部标注 + 封面编号图例 + 对照表页） |
| `封面布局演示.pdf` | 生成物（A4，16 页：前言 1 + 真实 14 + 对照表 1），入库 |
| `README.md` | 本文件（方案 + 对照表） |

## 7. 边界

- 覆盖范围＝**仅 PDF 合并封面**；EPUB 丛书封面页（`_epub_cover_page`）不在本演示内。
- 演示默认走出厂样式（未写 `sizes`/`positions` 覆盖）；自定义配置的观感不在本演示内。
- 对照表/前言页由 reportlab 生成（A4 版式），与真实页共用同一套设置键。
