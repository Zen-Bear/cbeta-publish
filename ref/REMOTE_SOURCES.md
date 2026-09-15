# 远端更新源（备案）

> 本文件记录所有需定期从网络更新到本地缓存的元数据与 XML。程序启动时通过 `remote_manager` 按此表检查更新，支持 `ETag` / `Last-Modified` 增量。

## 1. 目录与经录（heavenchou/cbwork-bin）

| 本地文件 | 远端 URL（GitHub） | Raw 直链（程序用） | 更新频率 | 备注 |
|----------|-------------------|-------------------|----------|------|
| `bulei.txt` | https://github.com/heavenchou/cbwork-bin/blob/master/cbreader2X/bulei/bulei.txt | https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/bulei/bulei.txt | 随部类修订，不定期 | `ref/README.md:4` 所指部类总表，UTF-8 Tab 缩进 |
| `sutra_mapping.txt` | https://github.com/heavenchou/cbwork-bin/tree/master/cbreader2X/sutralist | https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/sutralist/sutralist.txt | 随 XML 发布，频繁 | 原 `sutralist.txt`，8字段 `book,vol,num,juan,first_juan,first_lb,name,byline`，决定 `work->file` 映射。本地已重命名为 `sutra_mapping.txt` 以避 Windows 大小写冲突 |
| `SutraList.json` | https://github.com/heavenchou/cbwork-bin/tree/master/cbreader2X/nav | https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/nav/SutraList.json | 同上 | 藏册扁平目录，JSON 结构 `[{title:"T 大正...", children:[...]}]`。`SutraList.txt` 为同数据 TSV 版，已确认 JSON 足够（见 §3） |
| `SutraList.txt`（可选） | 同上 `nav/SutraList.txt` | https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/nav/SutraList.txt | — | 与 JSON 等价，Perl 遗留格式，**建议弃用**，仅保留 JSON 减少维护 |
| `file-structure.md` | — | — | — | 已在 `ref/` 备案，描述 `xml-p5` 目录与跨册/卷规则 |

## 2. 作者数据（cbdata.dila.edu.tw）

| 本地文件 | 远端 URL | 备注 |
|----------|----------|------|
| `all-creators-with-alias.json` | https://cbdata.dila.edu.tw/stable/download/all-creators-with-alias.json | 2216 人，`A000009: {regular_name, aliases_all, aliases_byline}`，用于别名搜索 |
| `creators-by-strokes-with-works.json` | https://cbdata.dila.edu.tw/stable/download/creators-by-strokes-with-works.json（待确认）或本地生成 | 笔划->人名->作品，已含 `X0607 法华经科注 (7卷)【明 一如集注】` 等。当前 `ref/` 的副本若非此 URL，请确认源 |
| `catalog`（在线部类目录） | https://cbdata.dila.edu.tw/stable/static_pages/catalog | 官网最新部类，HTML，需抓取后解析为树 |

## 3. XML 经文源

| 类型 | 地址 | 本地 `book/` 镜像 |
|------|------|-------------------|
| GitHub 官方 | https://github.com/cbeta-org/xml-p5 | `book/XML/T/T01/...` |
| 本地硬盘 | 用户配置 `local_xml_root`（如 `D:\cbwork\xml-p5a`） | 同上 |

程序优先级：`local` 与 `github` 可双源，按配置 `source: local|github|auto` 决定。`auto` 时先查本地，缺失或 `remote newer` 则从 GitHub `raw` 拉取 `XML/{canon}/{canon}{vol}/{canon}{vol}n{num}_{juan}.xml`。

## 4. 是否 SutraList.json 就足够？

**结论：是，`SutraList.json` 足够，可删除 `SutraList.txt`。**

- `SutraList.txt:1` 的 Tab 缩进文本与 `SutraList.json:2` 的 JSON 树 **数据等价**（`SutraList.json` 共 6 大组、4899 部；`SutraList.txt` 同数）。JSON 结构更利于 Python `json.load` 直接建树，无需解析 Tab。
- `nav/` 目录下 `SutraList.xlsx` 为 Excel 源，`.txt`/`.json` 均为衍生，保持单一 `json` 可避免三份同步问题。
- 唯一不可替代的是 `sutra_mapping.txt`（8字段），它与 `SutraList` **不同**：前者给出 `first_lb`/`juan`/`file` 映射，用于下载定位；后者仅给 `work->title`。

建议 `ref/` 最终保留：`bulei.txt`、`SutraList.json`、`sutra_mapping.txt`。

## 5. 更新逻辑（供程序实现）

- 每个 `REMOTE_SOURCES` 条目存 `cache/meta.json`：`{url, etag, last_modified, sha, last_check}`。
- `remote_manager.fetch(url)`：`HEAD` 比对 `ETag`，`304` 则跳过，`200` 则下载到 `ref/cache/<name>` 并原子替换 `ref/<name>`。
- 对 GitHub `raw`：可用 `If-None-Match`；对 `cbdata`：用 `Last-Modified`。
- `book/` 的 XML 不走此表，按需 `GET https://raw.githubusercontent.com/cbeta-org/xml-p5/master/XML/...`，同样缓存并记录版本。

---
更新时间：2026-08-27
