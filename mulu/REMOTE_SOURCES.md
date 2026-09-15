# 远端更新源（备案）

> 本文件记录所有需定期从网络更新到本地缓存的元数据与 XML。程序启动时通过 `remote_manager` 按此表检查更新，支持 `ETag` / `Last-Modified` 增量。
>
> **URL 单源**：程序不再在本仓写 URL 字面量，统一引用共享层 `src/_vendor/cbeta_fetch.py`
> 的 `REMOTE_URLS`（与 xml2pdf 同源；见 `src/books/remote_sources.py` 的 `_SPEC`）。
> 本文件的 URL 仅作人工备案。上游更新共享层：`python <cbeta-fetch>/tools/sync_into.py src/_vendor`。

## 1. 目录与经录（heavenchou/cbwork-bin）

| 本地文件 | 远端 URL（GitHub） | Raw 直链（程序用） | 更新频率 | 备注 |
|----------|-------------------|-------------------|----------|------|
| `bulei.txt` | https://github.com/heavenchou/cbwork-bin/blob/master/cbreader2X/bulei/bulei.txt | https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/bulei/bulei.txt | 随部类修订，不定期 | `ref/README.md:4` 所指部类总表，UTF-8 Tab 缩进 |
| `sutra_mapping.txt` | https://github.com/heavenchou/cbwork-bin/tree/master/cbreader2X/sutralist | https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/sutralist/sutralist.txt | 随 XML 发布，频繁 | 原 `sutralist.txt`，8字段 `book,vol,num,juan,first_juan,first_lb,name,byline`，决定 `work->file` 映射。本地已重命名为 `sutra_mapping.txt` 以避 Windows 大小写冲突 |
| `SutraList.json` | https://github.com/heavenchou/cbwork-bin/tree/master/cbreader2X/nav | https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/nav/SutraList.json | 同上 | 藏册扁平目录，JSON 结构 `[{title:"T 大正...", children:[...]}]`。`SutraList.txt` 为同数据 TSV 版，已确认 JSON 足够（见 §3） |
| `SutraList.txt`（可选） | 同上 `nav/SutraList.txt` | https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/nav/SutraList.txt | — | 与 JSON 等价，Perl 遗留格式，**建议弃用**，仅保留 JSON 减少维护 |
| `file-structure.md` | — | — | — | 已在 `ref/` 备案，描述 `xml-p5` 目录与跨册/卷规则 |

## 2. 作者数据（cbdata / DILA 权威库）

| 本地文件 | 远端 URL | 备注 |
|----------|----------|------|
| `all-creators-with-alias.json` | https://cbdata.dila.edu.tw/stable/download/all-creators-with-alias.json | 2216 人，`A000009: {regular_name, aliases_all, aliases_byline}`，用于别名搜索 |
| `creators-by-strokes-with-works.json` | https://cbdata.dila.edu.tw/stable/download/creators-by-strokes-with-works.json（待确认）或本地生成 | 笔划->人名->作品，已含 `X0607 法华经科注 (7卷)【明 一如集注】` 等 |
| `catalog` | https://cbdata.dila.edu.tw/stable/static_pages/catalog | 官网最新部类，HTML |
| **人名规范 `A024062`** | https://authority.dila.edu.tw/person/?fromInner=A024062 | 权威库 `search.php?aid=A024062` 返回 `释演培/谛观` 29 部 `YP0001..YP0029`，作参考 |
| **CBData works** | https://cbdata.dila.edu.tw/stable/works?creator_id=A024062 | **新增参考**：同一作者 JSON 接口，返回 21 部 `YP0001..YP0021`（`cjk_chars/file` 等）。与人名规范 **29 vs 21** 差异说明 8 部未入 CBETA XML（如 `YP0022 入中论讲记` 等），UI 需并集展示并标记 `未收录XML` |

> 验证 `A024062`：`authority` 29 部（全），`cbdata works` 21 部（已数字化），差 8 部未扫描。程序对 `collections` 采用并集，缺 `file` 者标灰不可下载。

## 3. XML 经文源

| 类型 | 地址 | 本地 `cbeta_xml/` 镜像 |
|------|------|-------------------|
| GitHub 官方 | https://github.com/cbeta-org/xml-p5 | `cbeta_xml/T/T01/...`（无 `XML/` 前缀，单文件 `T01n0001.xml`，本地 `E:\CBETA\CBReader2X\Bookcase\CBETA\XML:1` 为分卷 `T01n0001_001.xml`） |
| 本地硬盘 | `E:\CBETA\CBReader2X\Bookcase\CBETA\XML:1` | 同上 |

## 4. 官方电子书源（2026-08-28 新增）

> 源 `https://cbdata.dila.edu.tw/stable/static_pages/download_ebooks:1`，URL：`download/{格式}/{藏经}/{编号}.{ext}`

| 格式 | 单部例 | 全部 | 本地 `cbeta_ebooks/` |
|------|--------|------|--------------------------|
| `epub` | `https://cbdata.dila.edu.tw/stable/download/epub/A/A1057.epub` | `cbeta-epub.zip` | `cbeta_ebooks/epub/A/A1057.epub` |
| `pdf` | `https://cbdata.dila.edu.tw/stable/download/pdf/A/A1057.pdf` | `cbeta-pdf-1/2/3.zip` + `filelist_*.txt` | `cbeta_ebooks/pdf/A/A1057.pdf` |
| `docx` | `https://cbdata.dila.edu.tw/stable/download/docx/T/T0099.zip`（单卷 `T0099_001.docx`） | `cbeta-docx.zip` | `cbeta_ebooks/docx/T/T0099.zip` |
| `odt` | `https://cbdata.dila.edu.tw/stable/download/odt/T/T0099.zip` | `cbeta-odt.zip` | 同上 |

- `docx/odt` 仅大正藏，`pdf/epub` 全藏。
- 用户指定格式单选，下载到 `cbeta_ebooks/{format}/{canon}/`。

## 4. 是否 SutraList.json 就足够？

**结论：是，`SutraList.json` 足够，可删除 `SutraList.txt`。**

- `SutraList.txt:1` 的 Tab 缩进文本与 `SutraList.json:2` 的 JSON 树 **数据等价**（`SutraList.json` 共 6 大组、4899 部；`SutraList.txt` 同数）。JSON 结构更利于 Python `json.load` 直接建树，无需解析 Tab。
- `nav/` 目录下 `SutraList.xlsx` 为 Excel 源，`.txt`/`.json` 均为衍生，保持单一 `json` 可避免三份同步问题。
- 唯一不可替代的是 `sutra_mapping.txt`（8字段），它与 `SutraList` **不同**：前者给出 `first_lb`/`juan`/`file` 映射，用于下载定位；后者仅给 `work->title`。

建议 `ref/` 最终保留：`bulei.txt`、`SutraList.json`、`sutra_mapping.txt`。

## 5. 官方「範圍選擇清單」Scope-Selector（2026-08-30 确认为权威更新源）

> 源说明页：https://cbdata.dila.edu.tw/stable/static_pages/scope_selector  
> 供前端做「範圍選擇」樹狀目錄，含最新部类、作者、朝代，**定版 `cbdata/stable`**，优于 `heavenchou/cbwork-bin` 罐头。

| 本地文件 | 官方 Scope-Selector URL（程序用） | 说明 |
|----------|-----------------------------------|------|
| `SutraList.json` / `bulei.txt` 对应 | https://cbdata.dila.edu.tw/stable/download/scope-selector/category.json | 部类目錄（`選擇全部` -> `01 阿含部類 T01-02...` -> 单经 `T0001 長阿含經...【後漢 安世高譯】`），与本地 `SutraList.json` 同构但为定版全量，**拟切换至此** |
| `creators-by-strokes-with-works.json` | https://cbdata.dila.edu.tw/stable/download/scope-selector/creators-by-strokes-with-works.json | 笔划->人名->作品，已含 `X0607 法华经科注 ...【明 一如集注】` |
| `creators-by-strokes.json` | https://cbdata.dila.edu.tw/stable/download/scope-selector/creators-by-strokes.json | 同上无作品（轻量） |
| `dynasty-works.json` | https://cbdata.dila.edu.tw/stable/download/scope-selector/dynasty-works.json | 朝代期间佛典列表（`東漢 25~220` -> `T0013...【後漢 安世高譯】`），约 718KB，拟用于新增导航 `朝代` |
| `vol.json` | https://cbdata.dila.edu.tw/stable/download/scope-selector/vol.json | **刊本→册→经**（26 刊本 / 465 册 / 5939 部；部分刊本第二层直接是经）；已接入「刊本」导航，约 1.1MB |

> 结论：`category.json` / `dynasty-works.json` / `creators-by-strokes*.json` 均以该页为统一更新源，纳入 `remote_manager` 按 `ETag`/`Last-Modified` 定时拉取（启动检查），替代 GitHub 罐头。
>
> **现状（2026-09）**：`category.json` 已作为「部类」权威源（`bulei.txt` 仅作**补缺**）。
> cbdata 无 `bulei.txt` 端点（`download/bulei/bulei.txt` 等均 404），故 `bulei.txt` 仍取
> `heavenchou/cbwork-bin`（`ref/README.md:4` 所指；GitHub API 的 `download_url` 与本表 raw 直链一致）。
> 实测 `category.json` 缺 般若部類 `01 小品般若經(大般若經第1會) T05-06`、`09 …第11會`
> （远端同一缺），而 `bulei.txt` 完整 → `_load_bulei` 以 category.json 为主、用
> `bulei_parser.merge_missing_children()` 按前导序号补入缺失分组。

## 6. 更新逻辑（供程序实现）

- 每个 `REMOTE_SOURCES` 条目存 `cache/meta.json`：`{url, etag, last_modified, sha, last_check}`。
- `remote_manager.fetch(url)`：`HEAD` 比对 `ETag`，`304` 则跳过，`200` 则下载到 `ref/cache/<name>` 并原子替换 `ref/<name>`。
- 对 GitHub `raw`：可用 `If-None-Match`；对 `cbdata`：用 `Last-Modified`。
- `cbeta_xml/` 的 XML 不走此表，按需 `GET https://raw.githubusercontent.com/cbeta-org/xml-p5/master/XML/...`，同样缓存并记录版本。

---
更新时间：2026-08-27
