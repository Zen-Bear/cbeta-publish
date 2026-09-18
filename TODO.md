# 代办（按优先级）

> 设计文档：`docs/设计总案.md`（总方案）、`docs/UI设计.md`（UI）、
> `docs/链路B-设计契约.md`（与 xml2pdf 的跨仓调用契约）。
> 测试：`python -m unittest discover tests`（当前 292 项通过）。

## 已完成（里程碑）

- **目录/导航**：六视图（部类/三藏/刊本/朝代/作者/丛书）+ 二级过滤 + 全视图搜索
  （繁简/异体、大小写不敏感）+ 树拖拽 + 刊本 `vol.json` + 朝代排序 + 标签筛选。
- **工作区**：唯一内存书单，中栏与左栏两个视图共享；搜索只写 `_search_results`；
  拖放（目录树/工作区/右栏多向）；二栏/三栏布局切换。
- **丛书**：分类/标签 CRUD、slug id、排序、保存/恢复/另存/删除、派生 `index.json`、
  延迟保存（改动只存内存，点保存落盘）。
- **链路 A（官方电子书）**：`cbeta_fetch` 共享层（URL/规范化/原子下载/解压）；
  7 种格式（pdf/epub 单文件 + html/docx/odt/txt/txt_notes 目录型）；
  ETag+大小兜底增量；缓存统计/清理。
- **链路 B（XML→自制）**：进程内库调用 `pycbeta.cli.main`；预设制（上游公开 API）；
  「调整…」临时预设；CSS 槽临时 run.json 包装；分格式目录 `{root}/{fmt}/…`；
  `ensure_one`（合并/ZIP/导出恒仅缺，`重制`=全部重生成）；ZIP/导出弹窗选格式（目录型只打包）。
- **合并**：PDF（PyMuPDF 书签页顶锚）/EPUB（ebooklib 样式重挂）单一格式、允许分册；
  封面/说明/目录；说明页自制注明；打印/阅读模式；佛像/韦陀。
- **校验重制**：进程内 `VerifyWorker` 逐本生成+校验，跑完自动导入通过项；
  报告兼容独立窗/CLI 两种命名、按 work 取最新；独立窗保留为手动工作台。
- **设置/外观**：设置页各页签、按钮语义（确定=本次/保存=落盘）、宋体默认、
  目录行浏览按钮、本地分隔符、单选行（`_RadioBar`）。
- **其它**：进度窗（合并日志/取消/无错自动关闭）、右下「书籍信息/丛书信息」页签、
  E书目录标签链接、产物可点击打开、更新源误报修复（`-gzip` ETag）。
- **测试隔离**：所有 `MainWindow` 测试覆盖 `_config_path`/`collections_dir` 到临时目录，
  全量不再写脏真实配置/丛书/备份；护栏 `tests/test_no_pollution.py`。
- **软件名/版本**：单一来源 `cbeta_publish/__init__.py`（`APP_NAME`/`APP_ID`/`__version__`），
  窗口标题与 `QApplication` 元数据取此处。
- **分册模式**：`catalog/catalog_path.py`（部类/刊本路径+序+`_` 命名）；`_group_works(mode, depth)`；
  `gui/merge_dialog.py`（「合并时选择」每次弹框，记忆 `merge.ask_last`）；设置页四选一 + 深度；
  单测 `tests/test_by_catalog.py`。右栏不做分组。

## 待办

### 后续可扩展（分册）
- ZIP/导出 也按分册模式（当前仅合并）；「合并时选择」与 ZIP/导出共用弹框；
  作者/朝代维度；三藏不单列。

### P2 — 校验可配置阈值
- 校验的 `maxDiff`/`diffLines` 目前取上游 CLI 默认（10/5），未接预设 `verify` 配置；
  如需按丛书调阈值，评估经 `bridge.verify_work` 透传。

### P3 — 外观/语言（待定）
- 深色/浅色/繁简：`ThemeManager`/`i18n` 现为桩；先用 OpenCC 全文案转 zh-Hant，`en` 后置。

### P3 — 打包 / 文档（待定）
- 软件名/版本**单一来源**：`cbeta_publish/__init__.py` 的 `APP_NAME`（显示名）、
  `APP_ID="cbeta-publish"`（包/可执行短名）、`__version__`（语义化 `MAJOR.MINOR.PATCH`，
  当前 `0.1.0`）。窗口标题、`QApplication` 元数据取此处；发布时手动升版本并打 `vX.Y.Z` tag。
- Windows 启动器/打包（PyInstaller 或快捷方式，用 `APP_ID` 命名）、`requirements.txt` 固定版本。
- README（安装/运行/配置说明）。

### P4 — 低优先可选
- **丛书导航改树结构**（方案二）：「分类 → 丛书」两级（分类节点双击仅展开，丛书节点双击载入中栏）；
  可再加「丛书→书籍」。默认保持扁平。

## 备注

- 本地 `bulei.txt` 为 CBETA 23 部類；三藏映射 经(01-10)/律(11)/论(12-15)/藏外(16-23)。
- X 续藏按 `bulei.txt` 同名归并，已纳入三藏映射；般若部類 01/09 由 `merge_missing_children` 补。
- 封面字体/颜色/比例在 `cover.styles` 统一（`font` 为字体文件路径；`ratio`/`delta`；
  缺繁体字形回退系统全字库）；字号基准见设置页「封面/版式」。
- 旧版平展缓存布局已作废（不迁移/不双读）：旧目录需手动删、自制书重生成。
