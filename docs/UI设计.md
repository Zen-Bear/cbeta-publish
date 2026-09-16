# CBETA 发布程序 — UI 设计（合并版）

> 2026-08-28 合并 `UI精简版设计方案.md` + `UI框架_主题与语言.md`，去重。范围：转化外置，仅目录/搜索/下载/丛书管理。

## 1. 范围与职责（2026-08-28 新增双链路）

- **做**：目录显示（部类树）、搜索选择（部类/作者/关键词→映射 `sutra_mapping.txt`）、`cbeta_xml/` 与 `cbeta_ebooks/` 双缓存管理、丛书管理、合成。两条成书链路：
  1. **官方电子书→丛书**：下载官方 ebook 到 `cbeta_ebooks/` 直接合成
  2. **XML→电子书→丛书**：`cbeta_xml/XML → E:\dev\cbeta\xml2pdf:1 → ebook → 合成`
- **不做**：转化逻辑在 `xml2pdf`，本程序仅调度 `collections/*.json` → 调 `xml2pdf` 或合并官方 ebook。

## 2. 元数据与缓存

`mulu/` 为官方只读（`bulei.txt`、`SutraList.json`、`sutra_mapping.txt`、`all-creators-with-alias.json` 等），`collections/` 与 `mulu/` 并列。`SutraList.json` 足够（已弃 `SutraList.txt`）。远端源与更新见 `mulu/REMOTE_SOURCES.md:1`、`mulu/cache/meta.json`（`etag/last_modified` 增量），`cbeta_xml/` 按需从 `https://raw.githubusercontent.com/cbeta-org/xml-p5/master/XML/...` 拉取。

`file-structure.md:1` 描述 `T/T01` 目录规则，`mulu/backup/original|last` 仅 2 份（重置点/上一次）。

## 3. 整体布局

单窗三栏 + 状态栏，路径 浏览→勾选→下载→导出：

```
┌──────────────────────────────────────────────────────────────────┐
│ [≡] CBETA 发布管理器   [检查更新] [设置] [book: E:\cbeta\book ▼]   │
├──────────────┬──────────────────────┬──────────────────────────────┤
│ 导航 [部类●][作者][丛书] │ 书籍列表               │ 丛书 [▼ 太虚大师全集]    │
│ 搜索 [____]  │ 筛选 [关键字][已选○] │  45部 最后发布 2026-08-28   │
│ ▼ 01 阿含部类│ [x] T0001 长阿含 22卷│  标签: [author:太虚]       │
│   [x]T0001   │ [ ] T0002 七佛经     │  [新建][改名][删除]        │
│ ▶ 02 本缘   │ 选中 3/25            │  列表（拖拽排序）          │
│ 笔划 [1划▼] │ 详情 T0001 卷22      │  下载队列                   │
│  ▼ 一 一如  │ 路径 T/T01/...       │  ███ T0001 完成            │
├──────────────┴──────────────────────┴──────────────────────────────┤
│ 已缓存 128/4899 | 上次同步 2026-08-27 | 就绪                        │
└──────────────────────────────────────────────────────────────────┘
```

交互：三态勾选、缓存三色点（绿/黄/灰）、批量全选、拖拽排序、`[全部下载][导出]`。丛书管理在右栏（见 §5）。

左栏导航（现行实现要点）：
- 「视图」为单选按钮（部类/三藏/刊本/朝代/作者/丛书），非下拉（`_RadioBar`，接口仿 QComboBox）。
- 目录树配色：**书叶（单本作品）文字黑色**，分组节点（部类/册/朝代/作者/丛书）沿用主题色；
  选中/悬停与中栏书籍列表**完全一致**（选中 `#bbdefb`、悬停 `#fff3c4`、选中+悬停 `#90caf9`）。

## 4. 主题与语言（预留框架，暂不实现）

### 配置 `collections/../app_config.json`（与 `mulu` 分离，避免被覆盖，建议放 `config/app.json`）

```json
{
  "theme": {"mode": "system", "accent": "#8B4513", "available": ["light","dark","system"]},
  "language": "zh-Hans",
  "available_languages": ["zh-Hans","zh-Hant","en"]
}
```

### 主题框架 `cbeta_publish/gui/theme/`

- `theme_manager.py` + `light.qss`/`dark.qss` + `tokens.json`（`--bg/--fg/--accent/--border`），`QStyle` + `qss` 不硬编码颜色，`apply(app)` 时 `setStyleSheet` + `QPalette`，`system` 跟随 OS `paletteChanged`。

```qss
QMainWindow { background: var(--bg); color: var(--fg); }
QTreeView { border: 1px solid var(--border); }
```

### 语言框架 `cbeta_publish/i18n/`

- `i18n.py` + `zh-Hans.json`/`zh-Hant.json`/`en.json`（或 `Qt Linguist .ts→.qm`），所有文案走 `tr("丛书")`，繁简初期 `OpenCC` 自动转。

```json
{"collection": {"zh-Hans":"丛书","zh-Hant":"叢書","en":"Collection"}}
```

### 设置入口（预留）

```
[设置] 外观: 主题 [跟随系统▼] 强调色 [■]  语言: [简体中文▼]（需重启）
```

启动时 `ThemeManager.apply` + `I18nManager.load`，主题即时生效。

## 5. 丛书管理（2026-08-28 已审：`专题/其他` 带悬停，新增双链路）

存储 `collections/author|sect|sutra|theme|custom/<slug>.json` + `categories.json:1`/`tags.json:1` + `index.json`，与 `mulu/` 并列，`docs/设计总案.md:6`。右栏 `[合成]` 自动选源：`cbeta_ebooks/` 优先，否则 `cbeta_xml/XML → xml2pdf`；`last_publish_dir` 指向 `output/<丛书>/`。
标签新增/改名/删除（批量更新），层级 `parent + /` 二级，一丛书多 `tags[]`。

## 6. 精简架构

```
cbeta_publish/
  catalog/bulei_parser.py, sutra_service.py, mapping_service.py
  creators/creator_service.py
  books/source.py, cache_manager.py, remote_manager.py
  collections/collection_model.py, tags_manager.py, export.py
  gui/theme/theme_manager.py, i18n/i18n.py, main_window.py, nav_panel.py, list_panel.py, collection_panel.py
  app.py
```

## 7. 已确认（2026-08-28）

- `book` 默认 `publish/cbeta_xml/`，更新 `每周` + 手动，无需 `GitHub token`。
- 主题/语言仅预留框架，`专题|其他` 已按方案1细化并加 `description` 悬停；`id` 用可读 `slug`。
