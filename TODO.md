# 代办（按优先级）

> 设计文档：`docs/设计总案.md`（总方案）、`docs/UI设计.md`（UI）、
> `docs/链路B-设计契约.md`（与 xml2pdf 的跨仓调用契约）。
> 测试：`python -m unittest discover tests`（当前 514 项通过）。

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
  `gui/merge_dialog.py`（「合并时选择」每次弹框，记忆 `merge.ask_last`）；设置页七选一
  （不分册/刊本册/目录部类/手工分册/作者/朝代/合并时选择）+ 深度；右栏书单支持分组
  （平铺/按刊本册/按部类/按作者/按朝代/手工分册，`_CollTree`；后四者为只读视图，可整体拷入手工分册）；
  单测 `tests/test_by_catalog.py`、`tests/test_manual_volumes.py`、`tests/test_by_author_dynasty.py`。

## 待办

### P1 — 批处理合并（所有丛书重新自动合并）
- 入口：批量任务，一次跑完所有丛书（或勾选子集）的合并。
- 按来源分两路：官方来源先下载、自制来源先自制，**先备齐所有文档**再合并
  （复用 `_download_missing` / `_ensure_xml_batch` 的"仅缺"语义；缺书失败即该丛书记失败）。
- 每部丛书按其保存的合并分册配置自动合并（`merge.mode/depth/name_template`；
  「合并时选择」按记忆 `merge.ask_last`，无记忆回退默认）。
- 最后出成功/失败报告（逐丛书：成功文件清单 / 失败原因），可点开。
- 注意：长任务需进度＋取消；中途失败不影响其余丛书；报告落盘可选。

### 分册扩展
- [x] ZIP/导出 也按分册模式（`none` 保持单 zip／平铺；其余按可用书分组，命名同合并模板）；
  「合并时选择」与 ZIP/导出共用弹框（共享 `ask_last`/模板）。`tests/test_pack_split.py`。
- [x] 作者/朝代 维度分册（三藏不单列）：`_group_works` 加 `author`/`dynasty` 分支
  （`_work_author_map` 去僧姓/同名归并；`_dynasty_index` + `_dynasty_name` 去「CE 年代」区间）；
  未署名/未詳置末，朝代按朝代序、作者按拼音序；设置页/合并弹框/右栏视图/ ZIP·导出同步。
  `tests/test_by_author_dynasty.py`。

### P2 — 校验可配置阈值（已完成）
- [x] 全局配置 `xml2pdf.verify_max_diff`（默认 5）与 `verify_diff_lines`（默认 5）；
  设置页「自制E书」以 0–50 数值输入，`bridge.verify_work` 始终透传上游
  `--verify-max-diff`/`--verify-diff-lines`（钳制 0–50）。上游预设 `verify` 段无此二项，仅 CLI 支持。

### P3 — 打包 / 文档（已完成）
- [x] 软件名/版本**单一来源**：`cbeta_publish/__init__.py` 的 `APP_NAME`（显示名）、
  `APP_ID="cbeta-publish"`（包/可执行短名）、`__version__`；窗口标题、`QApplication`
  元数据、**打包产物名**均取此处；发布时手动升版本并打 `vX.Y.Z` tag。
- [x] Windows 打包：`build_exe.ps1` + `packaging/cbeta_publish.spec`（PyInstaller onedir，
  用 `APP_ID` 命名）；`cbeta_publish/paths.py`（冻结时数据根=exe 同级，便携）；
  打进 pycbeta；`-WithBrowsers` 可选连 Chromium。
- [x] `requirements.txt` 固定版本。
- [x] `README.md`（安装/运行/配置/打包/测试）＋ `packaging/README.md`（含/不含清单）。

### P4 — 低优先可选（已完成）
- [x] **丛书导航树结构**：左栏「丛书」视图固定为树 `分类→丛书→书籍`；按 `categories.json`
  顺序分组、空分类也显示、分类节点默认展开（双击仅展开折叠）；分类下拉保留作筛选
  （选中分类只显示该分类，与标签筛选叠加）。`tests/test_by_catalog.py:CollTreeTest`。

## 备注

- 本地 `bulei.txt` 为 CBETA 23 部類；三藏映射 经(01-10)/律(11)/论(12-15)/藏外(16-23)。
- X 续藏按 `bulei.txt` 同名归并，已纳入三藏映射；般若部類 01/09 由 `merge_missing_children` 补。
- 封面字体/颜色/比例在 `cover.styles` 统一（`font` 为字体文件路径；`ratio`/`delta`；
  缺繁体字形回退系统全字库）；字号基准见设置页「封面/版式」。
- 旧版平展缓存布局已作废（不迁移/不双读）：旧目录需手动删、自制书重生成。
