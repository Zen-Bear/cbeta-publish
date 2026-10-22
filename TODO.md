# 代办（按优先级）

> 设计文档：`docs/设计总案.md`（总方案）、`docs/UI设计.md`（UI）、
> `docs/链路B-设计契约.md`（与 xml2pdf 的跨仓调用契约）。
> 测试：`python -m unittest discover tests`（当前 861 项通过）。

## 约定（务必遵守）

- **绝不回退真实用户数据**：不要对 `config/app.json`、`mulu/backup/`、`collections/`
  执行 `git checkout` / `git restore` / `git clean`。这些是运行期数据，回退会**覆盖用户设置**。
- `config/app.json` **不进版本库**（见 `.gitignore`）；出厂默认值在跟踪的
  `config/app.default.json`，首启由 `paths.ensure_user_config()` 复制生成。
- `mulu/backup/`（配置与源数据快照）不进版本库；`collections/` 保留跟踪但**永不 clean**。
- 测试必须把 `_config_path`/`collections_dir` 指向临时目录（护栏 `tests/test_no_pollution.py`）；
  若发现真实文件被写脏，**修具体用例**，不要整体回退。

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
  `ensure_products`（合并/ZIP/导出恒仅缺，`重制`=全部重生成；一 work 可对应多个源产物，
  如 TX0011 上/中下，合并/ZIP/导出/打开/校验导入都按产物集合处理）；ZIP/导出弹窗选格式（目录型只打包）；
  PDF 伴生 docx 复用（`reuse_pdf_companion` 默认开，pdf+docx 同跑省一次 docx 渲染）。
- **合并**：PDF（PyMuPDF 书签页顶锚）/EPUB（ebooklib 样式重挂）单一格式、允许分册；
  封面/说明/目录；说明页自制注明；打印/阅读模式；佛像/韦陀。
- **校验重制**：进程内 `VerifyWorker` 逐本生成+校验，跑完自动导入通过项；
  报告兼容独立窗/CLI 两种命名、同一 work 的不同语义产物分别保留与配对；
  同一 work 的多份语义报告聚合判定；独立窗保留为手动工作台。
- **设置/外观**：设置页各页签、按钮语义（确定=本次/保存=落盘）、宋体默认、
  目录行浏览按钮、本地分隔符、单选行（`_RadioBar`）。
- **其它**：进度窗（合并日志/取消/无错自动关闭）、右下「书籍信息/丛书信息」页签、
  E书目录标签链接、产物可点击打开、更新源误报修复（`-gzip` ETag）、
  分隔条单组 ◀/▶（按状态自适应、右栏可收）、二栏→三栏自动加宽。
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

### P0 — 上游跟进（已完成：上游已实现，publish 复用已落地）
- 上游 `pycbeta.verify.verify_fingerprint` + `report.json` 已落地（见上游 `docs/校验report.json说明.md`）。
- publish：全局通过记录库 `config/verify_records.json`（gitignored，只存通过）＋校验前指纹比对跳过
  （自制/重制都跳；重制对跳过项仍重生成但不校验）＋设置开关 `xml2pdf.verify_reuse`（默认开）＋
  缓存页计数/独立清理；无指纹一律重验。`tests/test_verify_reuse.py`。

### P1 — 批量合并（含 ZIP）＋批量更新素材＋官方书刷新（已完成，654 测试通过；设计与步骤见 `docs/批量合并-设计与实施.md`）
- 入口：菜单「制作书籍 → 批量处理…」（`BatchDialog(mode="combined")`，窗口内单选
  「更新素材 / 合并丛书」；**不新开一级菜单、单一入口**）；两者共用备齐实现。
- 批量合并：复选丛书（默认全选非空；全选/全不选）；☑合并 ☑ZIP 打包（格式沿用 `default_formats`）
  ☑合并前自动备齐（默认开，关=只用现有素材）☑报告落盘 → `output_dir/批量合并报告.txt` 覆盖写；
  输出 `output_dir/{丛书名}/`。
- 批量更新素材：只跑备齐（官方缺/过期重下 + 自制源新重制），不合并、不写 `last_publish`；
  报告 `output_dir/批量更新报告.txt`。
- 官方刷新协调：官方书过期判据 = 缺失 ∨ 工作根 XML 源较新 ∨ 本地库版本名（`official_library.root`
  目录名）变化；水位记 `config/official_state.json`（gitignored，按 `(work, fmt)`）。批量默认
  「XML较新则重下」；自制沿用 `sources_newer` 自动重制；单部 合并/ZIP/导出 同步升级。
- 分册配置：丛书 JSON 新增可选 `merge{mode/depth/name_template}`（缺省跟随全局；读入规范化）；
  批量按每部丛书的有效配置合并/ZIP；对话框可设单书配置（含「跟随全局」，确定即落盘）。
  `ask`（全局或单书）不弹框，用 `merge.ask_last`，无记忆回退 `none`。
- 来源/预设/格式整批统一（来源对话框内单选，默认官方；批量对话框默认「更新素材」；丛书不绑定来源；预设/格式取右栏当前）；设置「制作书籍=校验」时批量仍只普通合并。
- 两阶段：备齐（官方缺/过期对一次下载；自制一次生成；备不齐的丛书记失败）→
  逐部 合并+ZIP（空书/空白名/编辑说明有问题记失败；中途失败不影响其余丛书；取消即停，已完成的保留）。
- 报告：进度窗总结（批量合并单窗贯穿，`_Prog` 适配器）＋丛书信息页签逐部清单（成功文件可点开）；
  有产物的部才写 `last_publish`；不切右栏选择、不弹保存提示。
- 实现：`_prepare_official`（水位/force）、`_merge_one_coll`/`_zip_one_coll`（行为保持抽取）、
  `_run_batch_update`/`_run_batch_merge`、`_write_batch_*_report`、`gui/batch_dialogs.py`。
- 测试：`tests/test_official_state.py`（16）、`tests/test_prepare_official.py`（8）、
  `tests/test_batch_update.py`（5）、`tests/test_batch_merge.py`（11）、`tests/test_coll_merge_cfg.py`（7）、
  `tests/test_batch_dialog.py`（6）。

### 分册扩展（已完成）
- [x] ZIP/导出 也按分册模式（`none` 保持单 zip／平铺；其余按可用书分组，命名同合并模板）；
  「合并时选择」与 ZIP/导出共用弹框（共享 `ask_last`/模板）。`tests/test_pack_split.py`。
- [x] 作者/朝代 维度分册（三藏不单列）：`_group_works` 加 `author`/`dynasty` 分支
  （`_work_author_map` 去僧姓/同名归并；`_dynasty_index` + `_dynasty_name` 去「CE 年代」区间）；
  未署名/未詳置末，朝代按朝代序、作者按拼音序；设置页/合并弹框/右栏视图/ ZIP·导出同步。
  `tests/test_by_author_dynasty.py`。
- [x] 模板变量 `{source}`/`{src}`（来源）/`{date}`/`{date8}`（今天）；不分册 ZIP 也走模板。
- [x] 自制书源新重制：源 XML（工作根 `{work} {书名}/*.xml` 最新 mtime）比产物新则「仅缺」也重制；
  官方书按备齐水位判过期（缺失/源较水位新/本地库版本名变化，见 P1）。`tests/test_xml2pdf_bridge.py`。
- [x] 缓存页增加「校验目录」（`verify_dir`）统计与清理。

### P2 — 校验可配置阈值（已完成）
- [x] 全局配置 `xml2pdf.verify_max_diff`（原默认 5；P10 起默认 0）与 `verify_diff_lines`（默认 5）；
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

### P5 — 批量清除上次合并输出＋XML 归属提示（已完成，651 测试通过）
- [x] 批量对话框（合并模式）加复选框「清除所选丛书的上次合并输出（含 ZIP）并清除发布标记」
  （默认不勾，仅 merge 可见，随 `_apply_mode` 显隐；`BatchDialog.purge_enabled()`）。
- [x] `_run_batch_merge` 两阶段前插「阶段零：清除」——删 `output_dir/{丛书名}/`（缺失记「无输出可清」）；
  成功后 `pop last_publish_at/dir`＋复用 `_commit_publish_meta` 落盘＋清内存 `_last_publish`。
- [x] 勾选时执行前二次确认（列出将删目录；取消则整批不跑）；已删不恢复，报告注明；
  根下 `批量合并报告.txt` 不动（下次合并覆盖写）。
- [x] 已核实 ZIP 落点：ZIP 在 `out_dir` 内（`_zip_one_coll: out_dir/f"{base}_{fmt}.zip"`），
  清除 `output_dir/{丛书名}/` 即覆盖合并＋ZIP。
- [x] XML 更新不做（`materialize_work` 缺才下，无强制刷新口；`--update-data` 只管上游自带数据）。
  改为提示：批量对话框更新模式＋来源=自制时，自制策略行下加灰字
  「CBETA XML 源由 xml2pdf 更新和维护，publish 只读不写」（随 `_apply_source` 显隐）；
  设置页「XML 工作根」输入框加同义 tooltip。
- [x] 测试：`test_batch_dialog`（默认关/显隐/getter＋XML 提示显隐）＋ `test_batch_merge`
  `BatchMergePurgeTest`（删目录＋清标记；缺失跳过；未勾/取消不删）；全量通过后同步测试数。
- [x] 文档：`docs/批量合并-设计与实施.md`（清除语义＋XML 归属）＋本 P5 打勾。

### P6 — 批量失败归因＋失败停留（已完成，654 测试通过）
- [x] 部内 `skipped` 名单透出：`r["skipped"]`（之前直接丢掉，报告/页签都看不到缺了哪几部）；
  报告加 `缺素材：…` 行（20 条截断）；页签显示前 3 部＋失败前 2 条。
- [x] `reason` 自动归因：有缺失＋未勾「合并前自动备齐」→指引先跑批量更新或勾选后重试；
  有缺失＋已备齐→"备齐后仍有缺失（见报告明细）"；状态栏同步追加指引。
- [x] 失败停留成功关：有 `failed/partial`/取消调 `finish(总结行)` 手动关（报告先落盘，
  总结行带报告路径）；全 `ok` 仍直接关；批量对话框不重开。
- [x] 测试：`BatchMergeFailureUXTest`（归因文案×2＋失败 finish＋成功 close）；
  全量通过后同步测试数。
- [x] 文档：`docs/批量合并-设计与实施.md`（§3.8 报告示例＋§3.9 归因/停留规则）＋本 P6 打勾。

### P7 — 上游 `verify_root` 适配（已完成，667 测试通过）
- 背景：上游新增 `source.verify_root`（校验产物总目录，优先级 `--verify-root` ＞ 配置 ＞
  默认 `{输出}/验证`）；报告落 `{输出}/验证/{id 书名}（验证）/{fmt}/` ＋
  `{id}_{书名}_校验报告.txt` ＋ `report.json`（JSON 统一名，见 P8）。校验目录分离决策见
  `docs/链路B-设计契约.md` §9.4。
- **现况影响**：managed 校验写进 `{vdir}/验证/…`，而 `bridge.find_verify_report` 只扫顶层
  `{vdir}/{work}*（验证）/` → 返回 None → `work_verify_reports(primary=None)` 为空 →
  整批判"未判定"不导入。P7 为必须项。
- [x] `find_verify_report` 双层候选：顶层旧版 ＋ `{out}/验证/{work}*（验证）/` 新版，并入现有
  候选集由 `_newest_report` 取最新（并存取新）；新增常量 `VERIFY_ROOT_NAME="验证"`。
- [x] `verify_work` 跑前清理**只清新版** `{out}/验证/{work}*（验证）/`（顶层旧目录保留兼容读取）。
- [x] `verify_work` 显式传 `--verify-root {out_dir}/验证`，把布局钉死（不受预设自定义值劫持）。
- [x] **独立窗**：上游已实现 GUI `--verify-root`（提案 `docs/上游提案归档/上游-GUI校验根参数提案.md` 已归档）；
  `_open_xml2pdf_window` 传 `--verify-root {vdir}/验证` 钉死，与进程内 CLI 一致；
  预设对齐检查扩展到 `source.verify_root`（非空提示可一键清空，作手动运行兜底）。
- [x] 测试：嵌套发现（新/旧/并存取新）；清理只清新版、顶层旧目录保留；argv 含
  `--verify-root` 断言；预设 `verify_root` 对齐提示（有/无两态）。
- [x] 文档：链路B §5/§9（报告布局 `{out}/验证/…`、`report.json`、publish 钉死
  `--verify-root`、独立窗预设对齐）。

### P8 — 校验判读升级：`report.json` 优先（已完成，664 测试通过）
- 背景与原则：上游 `report.json`＝机读结论、txt＝人读（同目录、每次覆盖写、`fail/undetermined/error`
  照写）；publish 现在**只读 txt（正则）**，`report.json` 零引用（上游自身也不消费，`find_verify_reports`
  是给下游的发现接口）。改为 **json 优先、txt 回退**（无 json／损坏／`schema≠1` 回退），
  **消费者零改动**（改造收在 bridge 函数内部）。**比对档≠产物**：`formal_outputs` 仅展示，不入库。
- 契约出处：`docs/校验report.json说明.md`（§1 文件位置、§4 指纹复用契约＋发现接口；
  "上游公开接口"＝`verify_fingerprint`＋`find_verify_reports`）；`docs/第三方调用说明.md` 是
  模块/函数级总览（面向二次开发），本次改动属前者。
- **上游命名变更（2026-10-07）**：机读 JSON **统一名 `report.json`**（CLI/GUI 一致），
  落 `{校验根}/{id 书名}（验证）/report.json`；旧名 `{id}_{书名}_校验报告.json` /
  `*_verify_report.json` 上游 `find_verify_reports` **不再发现**（重跑一次校验即得新名）。
  publish 同口径：**只认 `report.json`**，旧目录 → txt 回退（txt 仍兼容
  `report.txt` / `*_verify_report.txt` / `*_校验报告.txt`）。
- [x] `bridge._paired_json(report_txt)`：**同目录只找 `report.json`**（不再认旧 JSON 名）；
  `_read_verify_json`：utf-8-sig＋`schema==1`＋`fmts` dict，否则 None；
  归一 `{fmts:{fmt:{verdict,missing,extra,reason,diff_scope,formal_outputs}}, coverage}`。
- [x] 四函数 json 优先、txt 回退：`verify_report_formats`（`pass→True、fail→False`，
  `undetermined/error` 不收录）、`verify_report_pending`（reason 映射；pdf 的 reason 缺但
  `coverage` 有时合成 `covered:<src>`）、`verify_report_numbers`（直读）、
  `verify_report_pass`（任一 fail→False、任一 pass→True、否则 None）。
- [x] 新增展示函数：`verify_report_diff_scopes(path)`、`verify_report_comparison_files(path)`
  （均 json-only，txt→空）。
- [x] diff_scope **全链路显示**：`_do_import_verified` 的未通过标签＋"未入"尾注追加
  （含正文差异／差异仅注释／范围未知）；`_review_failed_dialog` 理由附范围＋"打开比对档"链接；
  `VerifyWorker` 进度行（过／部分过／未过）追加范围文案，`finished_all` 签名不变。
- [x] 产物定位（修正版）：json 存在时用其 `fmts` 键限定产物格式（`_verify_products` 加可选
  `fmts` 参数），防顶层旧残留误入；**不用 `formal_outputs` 作导入源**（比对档命名/配置不同）。
- [x] 测试（`tests/test_verify_import.py`，临时目录）：混合 verdict→四函数正确；json 与 txt 矛盾→
  json 胜；损坏／`schema=2`→回退 txt；diff_scope／comparison_files 解析；导入流（pass 入库、
  undet 不入、范围标签上结果页）；格式集过滤；worker 进度含范围；老 txt-only 不回归。
- [x] 文档：链路B §5/§9（判读链"json 优先、txt 回退；比对档仅展示不入库"）＋本 P8 打勾。
- 备注：上游 reason 文案变异→原样透出（同现行为）；schema 升级需人工跟进；不做 json 指纹与
  `verify_records.json` 交叉核对（维度不同）。

### P9 — 批量 ID 建丛书（已完成，696 测试通过）
- 落地：`collection/id_import.py`（`split_token`/`normalize_token`/`parse_id_lines`/
  `classify`/`html_to_text`/`fetch_text`）＋`gui/import_ids_dialog.py`（`ImportIdsDialog`，
  勾选/注释编辑/全选全不选/删除）＋`main_window`「导入ID…」按钮与 `_import_ids_dialog()`；
  模型 `collection_model.py` 加 `work_notes`（键归一、按 work 剪枝、空值丢弃）；
  卷范围并入 `work_ids` **条目键**（`work:卷`，同部多卷各自成条）；
  左/右栏书籍行 tooltip 与「书籍信息」页注释行。测试 `tests/test_id_import.py`（13）＋
  `tests/test_import_ids_dialog.py`（7，含建单集成与模型剪枝）。
- 入口：右侧丛书面板加按钮「导入ID…」（`main_window` 现有按钮批，895–906 接线）→ `_import_ids_dialog()`。
- 对话框 `gui/import_ids_dialog.py` `ImportIdsDialog`：单一 `QPlainTextEdit` 内容区，三种来源灌入并
  可继续手改——粘贴多行 `<work_id> [注释]…`；`从文件载入…`（.txt/.csv，utf-8-sig→gbk 回退）；
  `从网页抓取…`（URL→`fetch_text`→`html_to_text`）。`解析/预览` → 表
  `序号｜原始｜规范ID｜注释(可编辑)｜目录书名｜状态`；状态 `有效/未收录/无效/重复` 全部**保留并标注**，
  可删行/全选/全不选；`OK=创建` → `_ask_name_category("新建丛书")` → 建丛书（内存＋标脏，保存后落盘）。
- 纯逻辑 `collection/id_import.py`（无 Qt，易测）：`normalize_token`（basename `T01n0001`→`T0001`→
  `canonical_work`）、`parse_id_lines`（跳空行/`#`/`//`；行首 id＋余下为注释，剥首分隔符）、
  `classify(rows, work_exists_fn)`（格式→`work_exists`→有效性/未收录/重复）、`html_to_text`、
  `fetch_text(url)`（仅 http(s)、UA、编码猜测、30s 超时）。
- 数据模型（`collection_model.py`）：新增 `work_notes {work_id: 注释}`——`normalize_collection` 键
  `canonical_work`＋按 `work_ids` 剪枝＋空注丢弃（仿 `bulei_groups`）；`Collection.__init__/to_dict/
  create_collection` 透传（非空才写）。
- 显示（仅展示，不参与合并/分册/校验）：左栏丛书树书籍行 tooltip（`_add_coll`/`_work_item` 1675–1681）；
  右栏书单书籍行 tooltip（`_render_coll_rows` 4044+）；「书籍信息」页加注释行（3924）。
- 测试：`tests/test_id_import.py`（分隔符/空行/`#`、basename 规范化、无效/重复、classify、html_to_text、
  编码回退）＋ `tests/test_import_ids_dialog.py`（offscreen：解析→编辑注释→getter；建丛书后 work_notes
  落盘；临时 `_config_path`/`collections_dir`＋`test_no_pollution.py` 护栏）。
- 文档：`docs/UI设计.md`（按钮/对话框）＋`docs/链路B-设计契约.md` §4（`work_notes`）＋本 P9 打勾。
- 风险：网页为通用整页转文本按行解析（不做站点适配/按链接）；抓取在 UI 线程（单页 30s 超时，后续可线程化）。

### P10 — 跨边校验复用＋验收档位（已完成，676 测试通过）
- 背景：上游 P2 提案（`E:/dev/cbeta/xml2pdf/docs/上游提案归档/上游-P2校验结论跨边复用提案.md`）经 publish
  审核，意见见 `docs/上游提案归档/上游-P2复用提案-下游审核意见.md`（同文已就地追加为该提案 §9）；
  指纹入参改进见 `docs/上游提案归档/上游-指纹presets入参提案.md`。目标：上游 `report.json` 的结论可被
  publish 复用（跳过重复校验），并加"注释差异"验收档。
- 上游依赖（待上游落地）：`verify_fingerprint(..., presets=<effective dict>)`——三项
  （`_strip_no_from`/`_theme_css_digest`/`_canon_annotations`）由 presets 派生；
  首选裸预设升为出厂深合并（或公开"取最终生效配置"API），否则验收改为"三形态传同一
  effective 配置"（publish 自包 run 取 dict）；`annotations` 相对路径 publish 绝对化后传；
  预设/`config.user.json` `verify.maxDiff` 改 0（`diff_lines` 保 5）；CLI 文档注明
  `--verify-max-diff 0`；fail 时照写 `diff_scope`（已完成）。
- 多源口径（再审核定，P2 提案 §9.7）：**上游无需改**——publish 采用「输入集」模型，
  GUI 聚合报告天然支持；CLI 多源报告不导入。
- [x] `verify_cache` schema v2（输入集）：`entries[work][fmt].sets =
  [{fingerprint, inputs:[源基名…], accept, product}]`；`is_fresh`＝存在一个 set 其
  `inputs` 恰为**当前全部源**且指纹逐字命中；旧 schema 1 忽略（本地库尚不存在，零成本）。
- [x] 验收两档（publish 侧，上游不改 verdict 逻辑）：strict＝`missing==0 且 extra==0`；
  notes＝`(missing+extra) ≤ 10` 且 `diff_scope=="notes_only"`；其余人工检验且**放行不记库**；
  常量 `ACCEPT_NOTES_DIFF_MAX=10`；次序＝先按档位得接受集，再做 docx→pdf 覆盖提升。
- [x] 惰性导入（`_send_coll_to_verify`）：按报告 `inputs.xml_files` **同序**映射当前源文件
  算指纹（聚合/单源同一路径；CLI 多源报告不导入；顺序或集合任一不符即不命中；GUI 合并
  临时名无法映射时静默不导入）；stale 时扫 `xml2pdf.verify_reports_dir`
  （默认解析生效 `source.verify_root`，可显式覆盖；解析不到=关）→ 匹配（`schema==1`／
  `work`／指纹相等／`inputs.xml_files` 与 `formal_outputs` 非空）＋两档验收 → 记库；
  一次运行缓存扫描；结果页一行"上游导入 N 条"。
- [x] 判读链：`_do_import_verified` 档位替换"仅 verdict pass"、结果页标注"仅注释差异"；
  `VerifyWorker` 聚合 `nums`、进度行区分通过／通过（仅注释差异）／未通过。
- [x] 阈值 0：`settings_dialog.DEFAULT_CONFIG`、`config/app.default.json` 的
  `verify_max_diff` 5→0（运行期 `config/app.json` 由用户手动改，不动真实数据）。
- [x] 测试：档位真值表（0/0、notes≤10、body≤10、notes>10、数未知）；覆盖提升；输入集模型
  （全源 set 命中/部分源不命中/顺序不符不命中/合并名不导入/CLI 多源不导入/GUI 聚合 TX0011
  用例）；跨边导入四条件＋档位；reports dir 解析与覆盖；阈值 0 默认；隔离护栏照旧。
  上游落地前先以假指纹打桩测导入链。
- [x] 文档：链路B §5（验收档＋逐源复用＋报告根＋阈值 0）＋`docs/设计总案.md` 测试数同步。
- 备注：旧报告（阈值 5）与旧记录全部失效，上游按 0 **重跑一次**后跨边复用生效；
  1–5 字正文差异的书从"自动入库"转为"人工检验"（符合验收档设计）。

### P11 — 卷子集（已完成，708 测试通过）
- 背景：上游已落地卷子集（`--juan`/`-i ID:范围`，2026-10-07）；publish 需让 token 全链
  可走：ID 导入/书单 token → 自制/校验透传 → 子集产物入库与复用。上游指纹/报告卷维度
  （本仓 P11 请求）2026-10-08 已实现。
- [x] 上游指纹/报告卷维度（提案 `docs/上游提案归档/上游-指纹juan入参提案.md`，§8 复核）：`verify_fingerprint(juan=)`
  归一进 payload（`None` 逐字回归）＋`_official_superset` 卷限定（html/docx/txt_notes）＋
  `report.json` 顶层 `juan{segments,label}` 恒输出＋CLI/GUI 全覆盖/无 milestone→`None` 归一
  （顺带修无 milestone 仍加后缀的既有小 bug）；契约见上游 `docs/校验report.json说明.md`
  §3/§4、`docs/校验说明书.md` §4.4。
- [x] P11a 解析/透传：`id_import` token（`split_token`/`normalize_token` 已含 basename/长编号
  `T25n1509`→`T1509`）＋`juan_token`（多段 `,`/`、`→`+`，避 ids-file 分隔冲突）；`xml2pdf_bridge`
  `_id_juan_arg`＋`convert/convert_outputs/ensure_products/ensure_one/verify_work` 加 `juan=` 透传
  （`juan` 非空时 `ensure_products` 恒走输出目录模式，由上游加 `（卷…）` 后缀）；`VerifyWorker`
  加 `works_juan` 逐本透传；`_send_coll_to_verify` 子集项恒重验（复用隔离前）；独立窗 ids 文件写 token。
- [x] P11b 入库/复用：`verify_cache` 集身份扩为 `(inputs, juan)`（`is_fresh`/`record_pass`
  加 `juan`，缺省 `""`＝整本；同 inputs 不同 juan 分集）；`xml2pdf_bridge` `_read_verify_json`
  读顶层 `juan`＋`verify_json_juan`＋`juan_segments`/`juan_label`（上游 `parse_juan_spec`/
  `format_juan_label`，`、`→`,`）＋`verify_fingerprint(juan=)`＋`_verify_stem_matches` 头比对
  （剥 `:范围`/`_NNN`）；`_send_coll_to_verify` 按卷标签算指纹/查库/记库、`_import_upstream_pass`
  校报告 `juan.label`；`works_juan` 传 worker（CLI 用 `,`）。测试：缓存卷隔离、stem 头比对、
  report.json 卷字段、`juan_label` 真值、子集不复用整本记录。
- [x] P11c 文档/测试：契约 §5 卷子集段、UI 设计（导入ID 卷范围并入条目键）；
  子集入库端到端（报告/产物带 `（卷…）` 后缀，导入保留上游名）＋隔离单测；测试数同步
  `docs/设计总案.md`。
- [x] P11d 条目键（每卷独立成书）：卷范围并入 `work_ids`（`work:卷`），同部多卷各自成条——
  `work_id` 加 `split_entry`/`entry_key`/`canonical_entry`；`collection_model` 去 `work_juan`、
  按条目去重/剪枝；「导入ID…」计数/建单按条目（29 行=29 条）；右栏书单/标题/打开按条目拆
  `work`/卷显示；`_send_coll_to_verify`/`VerifyWorker`/`_ensure_xml_batch` 按条目拆 `work`＋卷透传；
  `_do_import_verified` 按 `work`＋`juan.label` 命中条目；`find_all_built_entry` 按卷后缀寻址。
- [x] P11e 官方按卷下载：`official_ebook_source` 按条目拆 `work`/卷——`html`/`txt_notes`/`txt`
  与 `docx`/`odt`（`{canon}/{ID}/{ID}_{NNN}.{ext}`）有单卷端点（实测，docx 例 T0099:1）；
  `pdf`/`epub` 官方无单卷 → **本地拆分**：整部取缓存（保留）再切（pdf 按 TOC 卷号页范围＋
  子集目录重定，epub 取 `juans/{NNN}.xhtml`＋原 OPF/NCX 裁剪＋assets 全留，校验失败回失败通道）。
  `official_state` 水位按条目。测试 `test_download.OfficialJuanTest`＋`OfficialSplitTest`。
- [x] P11f 合并修复：`_prepare_official` 恢复 `autoclose_ok=True`（合并/ZIP/导出前置下载无错
  3 秒自动关闭）；合并标题按条目（`_entry_book_title`＝右栏 `work-id 书名（卷…）`），
  `ensure_products`/`_group_works`/分组标题按 work 部分归位。

### P12 — 部类深层叶子补齐（已完成，742 测试通过）
- 背景：`category.json` 把 `T0220c,21-23` 等当无子节点叶子，深层卷区间叶
  （`T0220_401..537` 等 18 组＋新书叶）只在 `bulei.txt` 有，部类树缺席；
  旧 `merge_missing_children` 只补顶层数字分组。
- [x] 递归 additive 合并：标题命中深入；未命中走新颖门控（文档链接永不 graft；
  含新区卷间对／全新经号整棵接入；余下跳过）；顶层保持旧语义（数字缺失整棵接入），
  两遍式（先整棵补齐再深入门控，跨分支重复天然去重）；`_PAIR_RE` 带词界
  （`N70_1cont` 之类帮助路径不算卷）。 graft 总量 +66 节点（曾裸递归 +5564，已收敛）。
- [x] 定序：深层 graft 无序号时按经号排（`T0220_*` 只看 `T0220`，排到 `T0221` 前，
  不盲追加尾部）；数字仍按值。
- [x] 测试：合成深层 graft＋幂等＋定序；真数据回归 18 组卷区间叶＋文档零 graft＋卷叶序；
  `test_by_catalog` 等目录组全绿。

### P13 — 转换报告开关＋合并（已完成）
- 背景：上游 `output.convert_report`（GUI 默认开）＋CLI 双开关；publish 从未透传，
  实际按预设默认生成、报告堆积且被导入链排除。设置「自制书籍→制作书籍」行加复选，
  默认关。
- [x] 配置 `xml2pdf.convert_report=false`（模板＋DEFAULT_CONFIG）；设置复选＋回写；
  桥接 `_run_cli_convert`/`verify_work` 显式 `--convert-report`／`--no-convert-report`
  （覆盖预设；独立窗不传，用其自有框）。
- [x] 合并：`bridge.convert_reports`（只收每本 `{name}_转换报告.txt`，不收
  `{name}_转换报告_{fmt}.txt` 明细；`总转换报告.txt` 自排除）＋`write_convert_summary`；
  校验流落 `vdir/总转换报告.txt`、普通流落 `xml_out/总转换报告.txt`（覆盖写），
  结果页（`_show_verify_results`／`_show_made_books`）给文件链接。
- [x] 文档：链路B §5/§9、UI设计（设置行）。

### P14 — 自制缺产物清单（已完成）
- 背景：`_ensure_xml_batch` 仅 `outs` 为空记 failed；非空但少于预期源数静默
  （`完成 87/105` 无失败也无清单）。确认为 bug，非行为变更。
- [x] 返回 4 元组 `(ok_map, failed, cancelled, short)`，`short` 记
  `w.fmt 缺n个产物（预期/实得）`；5 调用方解包＋展示（单次/批量更新/批量备齐/
  ZIP/导出）；short 永不阻塞流程（ZIP/导出只提示不取消）。
- [x] 卷子集按 1 个 tracking unit 计预期（单卷只落在一个源文件里，不误报缺产物）。
- [x] 卷子集复用修复：多源 work 的单卷产物不再按源数判"产物不全"而每轮重制
  （`_outputs_current(subset=bool(juan))`；T0220 三会分档实测）。
- [x] 信息栏本数行：结果页（下载/自制）**首两行**＝本数行 `N 部 x K 格式 (pdf+epub+…) = M 部`
  （各格式数不等则逐格式列出）＋总结行（产物列其后）；自制弹窗首行（计划）＋收尾行前
  （实际）同式；弹窗「完成 …」行全成功绿/否则红；进度日志首行不再空行；结果页总结行同色。
- [x] 新增「自制书籍报告」页签：自制/重制结果写入独立页签（保留最近一次，不被下载/校验覆盖）；
  页签序号改用 `_tab_book/_tab_made/_tab_coll`。
- [x] 书籍信息栏右上角改双箭头三态：`normal`（`△` 收起「发布」栏放大书籍信息 / `▽` 收起书籍信息栏）
  / `pub_collapsed`（仅 `▽`：复原两栏）/ `info_collapsed`（仅 `△`：复原书籍信息栏）；
  tooltip 随状态变化（`_pane_up/_pane_down/_apply_pane_state`）。
- [x] 报告页滚动条：Windows 11 原生滚动条是无轨道细圆点、几乎不可见 →
  「书籍信息」「自制书籍报告」套 `REPORT_SCROLL_QSS` 经典可见滚动条（宽轨道＋明显滑块）。
- [x] 报告产物行按**真实文件名**显示（自制多源作品如 `T0220 大般若經(第1卷-第200卷)` 原
  来三行同名，现各自区分）；官方缓存名（`T0220`）仍补书名标题。

### P15 — 整本不得复用卷子集产物（已完成）
- 背景：手工导入整本 `T0220`（600 卷）后自制，报 `完成 9/9` 却未生成整本——整本寻址
  `find_all_built_entry(juan="")` 的 `or allp` 回退把 3 个卷子集文件（479/523/556）当成
  整本产物；恰好 3 个源 XML＋3 个子集文件，`_outputs_current` 的 `len<len` 不成立 →
  误判"已齐"复用。
- [x] 删回退，整本改用尾缀正则 `_JUAN_SUFFIX_RE=re.compile(r"（卷[^）]*）$")` 排除卷子集；
  整本与子集严格互斥。同步修正校验流"新鲜/缺书"判定（同函数）。
- [x] 测试：整本查询排除子集、书名中间含「（卷」非尾缀仍算整本；整本 3 源＋仅子集文件
  必须重制（`convert_outputs` 被调、`reused=False`）。
- [x] 文档：链路B §5；`_merge_one_coll` 直调处列后续可选。

### P16 — 右栏页签调整＋批处理报告页＋选项记忆（已完成）
- [x] 页签重排：书籍信息 | 丛书信息 | 自制报告 | 批处理报告 | E书目录
  （「自制报告」移到「丛书信息」右侧；新增「批处理报告」页，序号常量加 `_tab_batch`）。
- [x] 「自制书籍报告」页签改名「自制报告」。
- [x] 左栏「丛书」视图右键丛书节点 → 菜单「打开丛书」：在右栏打开该丛书
  （右栏分类筛选不含该丛书时自动切到其分类）；丛书节点存路径角色 `UserRole+1`
  （`_tree_item_coll`/`_open_collection_in_right`）。
- [x] 移动丛书到其他部类：①右键「移动到部类…」（只选部类不改名）；
  ②左栏树内把丛书节点**拖到目标分类节点**（拖到另一分类下的丛书节点亦可）。
  两者共用 `_move_collection_to_category()`（写新分类 JSON、删旧、同步内存/右栏/左栏），
  拖拽起点由 `_tree_mouse_press` 记录（`_tree_move_coll_on_drop`）。
- [x] 丛书右键菜单补「改名…」「删除」：先在右栏打开该丛书，再重用右栏流程
  （`_tree_coll_rename`/`_tree_coll_delete`）。
- [x] 左栏状态行提示：`右键打开本地书` → `右键书籍、丛书打开菜单`。
- [x] 自制/重制 tooltip 随「制作书籍=生成/校验」动态切换（校验时含校验+自动导入语义）。
- [x] 复用旧校验（跳过）可见性：`总验证报告.txt` 增「复用旧校验（跳过） N 部」段
  （`write_verify_summary(skipped=)`，不计入「共 N 部」、不进全文）；
  重制/自制（校验模式）进度日志逐条列出 `书号（格式/格式）`。
- [x] 重制卡顿（点击后很久才弹窗、主窗口无响应）：根因＝指纹比对循环与新鲜项
  重渲染都在弹窗前的主线程里跑（93 部×3 格式实测 6.5s；新鲜项多时重渲染以分钟计），
  全程无事件泵。修法：进度窗先行（`_send_coll_to_verify`/`_ensure_xml_batch` 均先建窗，
  准备/重制逐单元 `update` 泵事件＋可取消，阶段切换 `_progress_reset`）；
  生效预设本轮快照一次复用（`verify_fingerprint(eff=, wrap=)`，调用方管包装生命周期）。
- [x] 询问框文字挤右半边：`_wrap_box` 的无名 `findChild(QLabel)` 先命中图标标签，
  600px 限宽加错地方、消息文本不限 → 长文本撑宽对话框。改按对象名
  `qt_msgbox_label` 取消息文本标签（图标标签不再被误伤）。
- [x] 校验报告摘要行加数字：每条摘要行末附 `[{verify_summary_tokens}]`
  （如 `T0099 通过（docx/epub）[1[docx=OK(0/0)], 2[epub=OK(1/2)]]`）；
  上游总结行原文优先，老报告按判读合成（缺数全未知不带括号、被覆盖记 `COVERED`）。
- [x] 「批处理报告」页：批量更新/合并后写入（首行标题＋落盘报告链接＋逐部状态行）；
  报告落盘时给 `批量更新报告.txt`/`批量合并报告.txt` 可点链接；批量合并完成切到本页。
- [x] 批量处理对话框选项记忆：`BatchDialog.state()`/`apply_state()`；主窗口
  `_remember_batch_options()` 写入 `config/app.json` 的 `batch_options`（内存＋落盘），
  下次打开/下次启动均重用；丛书勾选记「未勾选」集合（新增丛书默认仍选中）。
- [x] 「批处理报告」页产物排版：`N 个文件`＋每个文件独占一行、行首序号（每部从 1 重起）、
  列出全部文件不省略（原 `产物 n：a, b …共 n 个` 单行截断）。
- [x] 测试：`state` 往返/默认/固定模式；批处理报告页标题与链接、切页；
  `_batch_open` 恢复上次选项并落盘本次选项。

### P17 — 卷子集校验报告互删（已完成）
- 背景（2026-10-14 用户报告）：《藏要》第三辑第二次重制，T0279:14/16/17/19/21
  五卷未复用；实测五卷 18:38–18:39 验证过（暂存产物在验证根顶层），但报告目录
  全无、记录库无 juan=14/16/17/19/21（只留卷44；卷49 是更早一轮的幸存者）。
  第一辑同样：T0220 只余卷479 目录（523/556 被删；三卷记录来自三轮、每轮一条）。
- 根因：`verify_work` 跑前清理用 `验证/{work}*（验证）/`（裸经号），对同书多卷
  子集会把**兄弟卷**的报告目录一并删除；批量导入在整批结束后统一扫描，只剩最后
  一卷 → 其余卷不记库 → 永远无法复用；孤儿暂存产物留在验证根顶层。
  `work_verify_reports` 的判定聚合当时也靠这个破坏性清理才不会串卷。
- [x] 清理按卷隔离：卷子集只清 `{work}*（卷{标签}）（验证）/`；整本只清不带卷后缀
  者（`（卷…）` 尾缀目录属其它目标）。
- [x] 判定聚合按卷过滤：`work_verify_reports(..., juan=)` 以 `report_juan_label`
  （report.json 优先、目录后缀回退）与本次卷标签比对；worker 传
  `juan_label(config, spec)`（整本 ""）。
- [x] 测试：清理只动同卷、整本不动卷子集；聚合按卷隔离（含无 json 回退）、
  worker 端到端两卷互不污染。
- [x] 文档：链路B §9.5（按卷隔离为硬要求）。
- 存量自愈：五卷无记录，下次重制会重验并补记（孤儿产物随导入消费）。
- [x] 后续 bug（同日用户报告）：重制"第二次"在指纹扫描后**静默退出弹窗**——
  `works_to_verify` 为空时提前 return，落在新鲜项重生成之前，"重制=全部重新生成"
  落空。修：提前返回只留给自制（`regen_all=False`）；重制全新鲜仍走重生成，
  随后进度窗收尾总结（含目录链接/失败警示）＋「自制报告」页＋书籍信息提示，
  不再静默关窗；测试锁死（全新鲜仍逐 (work,fmt) regen、finish 一次、不启线程）。
- [x] 自制/下载报告排版：输出目录**独占一行**（原挤在总结行尾，如
  `重制完成 27 部（源未变，本次跳过校验） E:\…\cbeta_xml_ebooks`）；
  调用方总结行去掉多余 `→`；测试锁死行序（本数行/总结行/目录行/产物）。

### P18 — 界面字体启动不一致（已完成）
- 背景（2026-10-15 用户报告）：启动时左栏目录树字体比"进设置→确定"后**大**；
  右栏书单却正常（宋体 10）。
- 根因（实测复现）：**无父创建**的控件（`QTreeWidget()`／`QListWidget()`／
  `QComboBox()`／`QTabWidget()`／`QScrollArea()` 等）**不继承 app 字体**，落在
  系统默认字体（Windows=微软雅黑 9，观感比宋体 10 大）；带父创建的
  （如右栏 `_CollTree(self)`）正常继承宋体 10。启动时 `app.py` 只调了一次
  `apply_ui_fonts`（那时还没有控件，靠继承），所以这批控件"要进一次设置"才被
  逐控件显式 setFont 纠正。
- [x] `MainWindow.__init__` 末尾统一 `apply_ui_fonts(config.ui)`：启动即与设置
  「确定」同路径（逐控件显式），不再需要进设置才生效。
- [x] `apply_ui_fonts` 幂等化：已是目标字体则跳过 `setFont`（viewport 单独判断），
  避免重复重排/重绘。
- [x] 分隔条 ◀/▶ 箭头（7pt，仅 setFont）此前会被设置确认放大到 10pt：加
  `app_font_keep` 标记，`apply_ui_fonts` 跳过。
- [x] 测试：`tests/test_ui_fonts.py`（启动即 SimSun 10；apply 后跟随改号；箭头保持 7pt）。

### P19 — 更新源页签：表格定高＋「检查状态」框（已完成）
- 需求（2026-10-15 用户）：中间表格高度缩到合适，空出的位置放检查状态；
  原「立即检查更新」按钮上方的灰字移进新的状态栏。
- [x] 表格高度按内容定（表头 + 各行 + 边框），上限 320px（超出才出纵向滚动条），
  不再参与拉伸（`_reload_update_table` 末尾 `setFixedHeight`）。
- [x] 新增「检查状态」`QGroupBox` + 只读灰字 `QPlainTextEdit`（占满让出的空间）；
  `_check_update` 进度**逐行追加**、自动滚到底、结束写"更新 N/失败 M"汇总行；
  未检查时占位提示"尚未检查（点「立即检查更新」）"；原 `lbl_upd_log` 移除。
- [x] 测试：表格固定高度 ≤320（min==max）；状态框只读、进度与汇总进日志
  （桩 `RemoteManager`）；离屏截图核对比例（表格 202px / 状态框 125px）。
- [x] 顺带修数据依赖用例：`mulu/` 经"立即检查更新"更新后官方 `category.json`
  已含 01 → `test_real_data_restores_banruo_groups` 前提失效，改为
  "合并后恒为 01..13 全序；合并前确实缺时才要求补入带子树"。

### P20 — 自制生成进度口径统一为「作品 × 格式」（已完成）
- 现象（2026-10-15 用户）：32 部 YP 自制批量跑完，进度窗首行「32 部 x 2 格式 = 64 部」，
  末行「完成 80/64」——分子分母不同单位（分子=产出文件 80，分母=计划单元 64）。
- 根因：`_ensure_xml_batch` 计划期按**源 XML 数**预估（首次生成时工作目录/源 XML 由上游
  材料化，跑前不存在 → 每部只算 1）；收尾分子按**文件**数（4 部多册作品：YP0011 两册、
  YP0023 三册、YP0026 五册、YP0029 两册 → 40 文件/格式）。同一批书第二遍跑计划行会变 40 部。
- [x] 进度口径＝作品 × 格式：`total=max(1, len(works)*len(fmts))`，每部每格式 `done += 1`。
- [x] 计划行改 `计划：32 部 x 2 格式 (pdf+docx)`（`_fmt_counts_line(..., with_total=False)`，
  不给总数，免与按文件计的产出混用「部」字）。
- [x] 收尾行改 `完成 32/32 部（产出 80 个文件）`（文件数与作品数不同时才附）；失败/缺产物后缀不变。
- [x] 删掉跑前逐部数源的前置循环（源计数只服务「缺产物」比对，挪到每部转换**后**取数，
  首次运行也能报少产；卷子集不比对）。
- [x] `_on_make_button` 自制报告总结同口径：`生成完成 32 部（80 个文件）`（文件数≠作品数时才附）。
- [x] 测试：`test_ensure_xml_batch_popup_counts_lines` 改断言；新增
  `test_ensure_xml_batch_plan_counts_works_not_sources`（2 部 3 文件：计划 2 部、收尾 2/2 部（产出 3 个文件））；
  用真实 YP 数据端到端核对：计划 32 部、实际 40 部 x 2 = 80 部、收尾 完成 32/32 部（产出 80 个文件）。

### P21 — 更新源：目录变更（当前 vs 上次更新前）＋明细弹窗（已完成）
- 需求（2026-10-15 用户）：「能不能知道当前目录和上一次目录的区别？想知道最新的目录多了什么内容。」
- 可行性：`update_all` 覆盖前会把旧文件快照到 `mulu/backup/last/`（`remote_manager.py:108-114`），
  两份都在本地；实测可比（今日更新：category +1、SutraList +17、sutra_mapping +17、
  bulei +17、vol 无变化）。
- 口径（用户选定）：只列**经**（新增/删除/改名；经号＋书名＋卷＋作者，取源文件原文标题）；
  更新**后**对比（不做更新前预览）；摘要进「检查状态」，明细走弹窗。
- [x] 新模块 `cbeta_publish/books/mulu_diff.py`：`works_of` 按源类型抽经
  （树形 JSON 叶子 key/title；`SutraList` 无 key 取标题首词；`sutra_mapping.txt` 藏+号(+后缀)
  且标题＝「经号 书名（作者）」；`bulei.txt` 只认纯经号行首，`T0220_401..537` 卷叶与
  `T0001-25` 区间标签不计）；`norm_key` 去前导零归一（`T0001`≡`T,05,0001`→`T1`）；
  `diff_source`（新增/删除/改名＋counts）、`merge_works`（跨源去重，标题取优先级
  范围清单>朝代/刊本>经录>部类文本）、`summary_lines`、`detail_text`。
- [x] `settings_dialog.py`：更新完 `_append_mulu_diff` 往「检查状态」追加逐源一行＋合并
  新增经清单（最多 20 条）＋「本次未变（未纳入对比）」/「更新失败（未能对比）」；
  新增按钮 **「查看目录变更…」**→`_mulu_diff_dialog`（按源分组列全部，可滚动可复制，
  标注各源备份时间；无备份时给说明）。`_mulu_diffs(keys/last_dir/new_of)` 可注入路径（测试用）。
- [x] 测试：`tests/test_mulu_diff.py`（10 例：归一化、树/标题/映射/部类文本四类源、
  缺侧返回 None、跨源合并去重与优先级、摘要与明细排版、条数上限）；`test_settings_dialog.py`
  新增 4 例（按钮在、路径可注入、弹窗文本、更新后摘要进状态框）。
- [x] 文档：`docs/UI设计.md` 更新源节；离屏核对真实备份：摘要 5 行＋新增经 18 部（T0220＋17 部 G/YP）。

### P22 — 作者视图「相关（按题名）」子分组（已完成）
- 现象（2026-10-16 用户）：`X1420 楚石梵琦禪師語錄` 在作者目录里找不到——
  源数据 `creators-by-strokes-with-works.json` 把它挂在 15 位门人（中端、文斌、文玹、文晟、
  正隆、正參、良彥、明遠、祖灊、祖光、胤丘、善成、景瓛、曇紹、應訢）名下，主名梵琦
  （A001082）名下只有 B0087、JB283、X1419；`all-creators-with-alias.json` 也没有这部。
  分册（按作者）时取树序首个命中者 → 进「中端」。
- 口径（用户选定）：子分组 + 体裁后缀；误配暂不处理。
- [x] 新模块 `cbeta_publish/creators/related_works.py`：`book_part`（书名段＝`【` 之前去经号）、
  `matches`（名字紧邻体裁后缀才算）、`names_index`、`match_names`、`related_index`
  （倒排名字表，一次扫描全量标题，实测 0.04s／5180 部）。
- [x] 规则细化：**别名若是别人的本名则不参与匹配**（明代無相号太虛 → 不认领《太虛大師全書》
  23 部）；实测该约束只影响 6 位作者、去掉 33 条误配（462→429），梵琦→X1420 保留。
- [x] `main_window.py`：`_related_works`（进程内缓存一次，标题取 SutraList 全量＋作者树叶兜底）、
  `_related_works_of`（含归并成员 `_merged_keys`；已归本作者者剔除）、`_add_author_children`
  （著作叶 + 「相关（按题名）(N部)」灰字子分组）；作者树三种排序（笔画/拼音/朝代）同用。
  分组节点非作品（双击不加书），整组拖拽＝组内全部相关作品；不计部数、不进分册、不改源数据。
- [x] `merge_author_nodes` 增 `_merged_keys`（归并成员的原 author key，供相关作品取名字）。
- [x] 测试：`tests/test_related_works.py` 7 例（书名段/后缀/单字名/撞名不认领/已知误配）；
  `test_right_panel.py` 新增 2 例（子分组渲染与计数不变、已归属不重复且无相关时不出分组）。
- [x] 决策记录：作者搜索保持原样（用户复看后认为搜「太虛」得 22 部正确，不改）。

### P23 — 作者视图搜索结果按命中作者分组并标注命中别名（已完成）
- 背景：搜「太虛」混出 `X0609 法華經大意【明 無相說】`、`X1578 指月錄【明 瞿汝稷集】`，
  只看平铺结果看不出为何命中。用户口径：在搜索结果里标出「無相（別名：太虛）」这类理由，
  匹配规则不动（子串／繁简异体／前 5 位命中作者／前 200 部一律照旧）。
- [x] `_author_search_hits`（`main_window.py`，替代原 `_author_search`）：返回每位命中作者的
  命中方式——`by="name"` 本名命中，`by="alias"` 别名命中并在 `hit` 给出命中的别名
  （多个命中取最短者）。比对与搜索同用繁简/异体变体，故搜「太虚」能标出「太虛」。
- [x] `_author_search_groups`（替代原 `_search_author_works`）：命中作者 → 分组，每部作品只归
  首个命中作者（同旧口径，去重后总数不变）；组内按经号自然序；**本名命中组在前**。
- [x] 新增 `_search_groups`（与 `_search_results` 同步清空于空关键字／`_clear_search`／切导航模式）：
  `_search_results` 仍是平铺列表，`_ws_add_search`「一键加入工作区」不受影响。
- [x] `_add_search_group_nodes`（`_render_search_to_left`）：渲染 `搜索结果（N 部）`→ 作者组 →
  作品叶；组标题 `無相（別名：太虛）（1 部）`，组内作品仍带经号 `X0609　法華經大意`。
  组节点非作品（双击不加书），整组拖拽＝组内全部作品；其它视图与回落搜索仍平铺 `_add_pool_node`。
- [x] 测试：`test_right_panel.py::test_author_search_groups_by_author_with_alias_hint`
  （搜「太虚」三组、标题含别名括注、平铺仍 22 部、一键加入一致、组节点非作品、其它视图不分组）。
- [x] 文档：`docs/UI设计.md` 搜索节补分组与别名括注说明。

### P24 — 校验报告口径补全到「部 × 格式 = 文件」（已完成）
- 现象（2026-10-16 用户）：一本书两个格式时，收尾只说「校验完成 1/1」，读不出
  几个格式、几个文件；总报告计数行「共 4 部：通过 2 部 / 未通过 1 部 / 未判定 1 部」
  同样不体现文件数。
- 口径（用户选定）：**文件＝一个「作品 × 格式」判定**；docx 过而连带认定的 pdf 也算一个。
  校验行按判定数、导入行按实际入库数。
- [x] `cbeta_publish/books/verify_worker.py`：通过行加格式（`...通过（pdf/epub）`，含
  报告无逐格式行时按本次请求格式回填）；新增 `verdicts = Signal(object)`（`finished_all`
  之前发出逐本 `{work: {passed, failed, undet}}`，无基线/被覆盖格式计入 undet）；
  `finished_all` 仍 3 参，既有 6 处连接点不受影响。
- [x] `cbeta_publish/gui/main_window.py`：收尾先给产出本数行
  （`1 部 x 2 格式 (pdf+epub) = 2 个文件`，`_fmt_counts_line` 增 `unit` 参数，默认「部」），
  再「校验完成 x/y 部」；`已自动导入 n 部（m 个文件）`；`跳过已通过 n 部（源未变：pdf/epub）`；
  重制全新鲜行改「重制完成 n 部（pdf/epub，源未变、本次跳过校验）」；**无新鲜项不再空打
  「0 部」行、不再空重置进度条**。
- [x] `cbeta_publish/books/xml2pdf_bridge.py`：`write_verify_summary` 计数行先给格式集合，
  再给逐档文件数（`共 4 部（格式 docx/epub/pdf）：通过 2 部（5 个文件） / 未通过 1 部（1 个文件） / 未判定 1 部（1 个文件）`）。
- [x] 测试：`test_verify_import.py` 增 2 例（worker 全过带格式＋`verdicts`；收尾本数行/导入文件数）、
  `test_xml2pdf_bridge.py` 计数行断言更新。
- [x] 文档：`docs/UI设计.md` 自制/校验节、`docs/链路B-设计契约.md` §9.1 总报告。

### P25 — 校验结果页条目显示右栏同款书名（已完成）
- 现象（2026-10-16 用户）：跑完自制/重制后「校验结果」页的「已入库」条目只有裸条目键
  （`・T0099:12（pdf/docx）`），书名与卷名不见了；格式名做成链接这点保留。
- 口径（用户选定）：条目显示**右栏同款** `work-id 书名（卷…）`（`_entry_book_title`，
  条目键里的 `:卷` 收进「（卷…）」，不重复）；**整页四份列表**（已入库／已通过跳过／
  未入库／未判定）都换；尾巴文字（`；未入 epub`、`校验未通过（epub 缺1/多0）`）与
  `（人工放行）` 标记、格式链接一律不动。
- [x] `cbeta_publish/gui/main_window.py` `_show_verify_results`：新增局部 `_titled`
  （按空格/全角括号截出首部条目键 → `_entry_book_title`，取不到书名原样返回），
  四处列表改用它；`ok_files` 查表仍用原条目键；判定/信号/入库逻辑未动。
- [x] 测试：`test_verify_import.py` 增 2 例（四份列表带标题＋卷名收进条目＋尾巴保留；
  目录查不到的条目原样），并给 `test_show_results_links_imported_files` 加标题断言。
- [x] 文档：`docs/UI设计.md` 导入校验节补条目显示口径。

### P26 — 「相关（按题名）」不把 SutraList 目录节点当作品（已完成）
- 现象（2026-10-18 用户）：释太虛「相关（按题名）」里出现 `TX 太虛大師全書`——那是 SutraList 的
  **目录节点**（无作品编号，children 才是 TX0001…TX0020），不是叶子作品。
- 根因：`SutraService._build` 只判「标题首字符是拉丁字母」，把目录节点（`TX`、`T`、`X`、`Y`、
  `LC`、`GA`、`GB`…）与区间节点（`X01-02`、`J32-33`、`N48-62`…共 123 个非标准号）也登记成
  作品编号；相关匹配再按「太虛＋紧邻大師」命中它。全量扫描：受影响的「相关」条目全库仅此一条。
- [x] `cbeta_publish/catalog/sutra_service.py` `_build`：首词过共享层 `cbeta_fetch.is_work_id`
  （字母＋数字，`T0349/TXa001/T0150A/ZW0018b`），目录/区间节点不登记；`title_of('TX')` 随之回退为 `'TX'`。
- [x] `cbeta_publish/gui/main_window.py` `_related_works`：SutraList 全量与作者树叶兜底都加
  `is_work_id` 过滤（双保险）。
- [x] 测试：新增 `tests/test_sutra_service.py`（临时 JSON 夹具：目录/区间节点不入 all_ids、
  `title_of` 回退、真叶子保留）；`test_right_panel.py` 增 `test_author_related_skips_container_ids`
  （桩里塞 `TX` 目录号，相关只留 TXa001）。
- [x] 文档：`docs/UI设计.md` 作者节补「目录/区间节点不算作品」。

### P27 — 「相关（按题名）」后缀补「尊者」（已完成）
- 现象（2026-10-18 用户）：`X1452 紫柏尊者全集`、`X1453 紫柏尊者別集` 源数据挂在德清/錢謙益
  （「閱／纂閱」）名下，真可（紫柏）名下找不到；「相关（按题名）」也不认领——名字后紧跟「尊者」，
  而后缀表没有它。
- 全量扫描（全部作者一遍过，无需逐个指定）：无过滤候选 913 对，绝大多数是词义撞名
  （般若→大般若經 72、心經 58…）；按称呼/体裁词过滤后真例仅 3 条（紫柏全集/別集→真可、
  阿底峽尊者傳→阿底峽）；「集／別集」类 4 条全是已确认错配（空谷集、永光集、唯心集、天竺別集）。
- [x] `cbeta_publish/creators/related_works.py`：`SUFFIXES` 加「尊者」；模块注释记「集／別集」不收的原因。
- [x] 测试：`tests/test_related_works.py` 增 2 例（尊者三正例；天竺別集/空谷集不命中；related_index 归位）。
- [x] 文档：`docs/UI设计.md` 作者节后缀列表加「尊者」。

### P28 — 代码审计：数据安全、并发与性能（2026-10-19 审计完成；第一至第四批已完成）
- 实施进展（2026-10-21）：第一批、第二批（除可选的下载并发）、第三批与第四批已完成；第五批待实施。
  第三批另修正一处：自定义 `mulu_dir` 时更新**落盘目标**也跟随（`remote_sources.local_path`
  增加根参数，`RemoteManager`/`UpdateWorker` 透传），否则更新仍写默认 `mulu/`。
  实测：`MainWindow` 初始化 **2.20 s → 0.74 s**；`canonical_entry`
  **3.5 ms → 0.013 ms**；搜索命中键 **0.265 s → 0.026 s**（首次仍为 0.265 s，逐节点懒缓存）；
  全量测试 **851 项通过**（新增 22 项）。新增文件：`cbeta_publish/utils/atomic.py`、
  `utils/safe_name.py`；测试 `tests/test_atomic_write.py`、`test_safe_name.py`、
  `test_config_paths.py`、`test_verify_worker.py`。
  复核修正（5 项）：清理护栏扩到程序数据目录（config/mulu/collections/assets）并拒绝文件目标；
  配置损坏且模板不可用时给最小默认，避免启动 KeyError；搜索缓存改存「原文＋简体」防原地改字
  命中旧文本；更新进行中禁止保存配置；清洗后为空的丛书名合并到独立输出目录（防互相覆盖）。
  实现差异：搜索缓存挂在节点 data（`0x0100 + 101`），树重建自动失效，未用版本号；
  相对路径归一实际只在 `MainWindow.__init__` 调用（app.py 经构造覆盖、测试同样生效），未重复调用；
  设置页更新改为异步 `UpdateWorker`（相关测试改为等待线程完成）；清理拒绝以 `ValueError`
  抛给界面提示。
- 审计范围：`cbeta_publish/` 44 个业务模块（另有 `_vendor/` 2 个共享层文件不手改）；
  `ebook_merger` 渲染细节与跨仓 `pycbeta` 边界只做重点抽查。审计时仓库未改动。
- 实测（offscreen + 真实 mulu 数据）：
  - `MainWindow` 初始化 **2.20 s**；作品编号规范化每次重读 1978 行/328 KB 索引（**3.5 ms/次**），
    22 部含作品的丛书（569 条 work_ids）归一化 **1.882 s** → 改内存索引后 **0.008 s**（模拟索引实测，启动降到 **0.79 s**）。
  - 搜索每次按键 **0.229–0.271 s**；拆解：遍历 8148 节点取文本仅 **0.008 s**，
    **OpenCC 繁简转换占 0.206 s**，`lower()` 0.002 s → 根因是繁简转换，不是树遍历。
  - 作者树 8148 节点、rebuild **0.375 s**；部类树 rebuild **0.383 s**。
- 口径修正（上一轮口头结论更正，动手时以此为准）：
  - 相对路径问题**只影响打包版**（`build_exe.ps1` 第 6 步把出厂模板改成相对路径；仓库模板是绝对路径，
    源码运行不受影响）。
  - 裸 `except:` 全仓 18 处（main_window 5 处），`except Exception` 360 处、`except BaseException` 2 处。
  - `Collection.save` 不是死代码（`tests/test_merge_mode.py` 在用）；真问题是与主程序写盘**两套逻辑并存**。
- 复核更正（第二轮审核）：先期口头提过的两处不算缺陷——`main_window.py:5684-5689`、
  `:6419-6425` 的 QEventLoop 等待线程是注释在案的有意设计（`:5686`、`:6421`），残留风险仅
  「worker 未捕获异常未发 finished_all 时挂死」，暂不列入实施；`:6064` 的 Popen 是打开
  链路B独立窗，正常。本轮审核未改任何代码。
- 第三轮审核补正：全库写点盘点后，丛书写点实为 7 处（原子写清单已重写）；
  `_write_index` 已有 try（`main_window.py:1953-1958`，best-effort），collections 目录
  不可写时启动不崩，索引仅为派生缓存；`UpdateWorker`（`books/update_worker.py:7`）
  可直接复用，`DownloadWorker` 为单循环串行（`download_worker.py:41`），并发改造面清晰。
- 第四轮审核（错漏与过度设计）：`last_publish_dir` **不能**作为批量清除目标（ZIP `:8916`、
  导出 `:9137` 也会写它）；相对路径归一键缩到 4 个（其余已有 `_abs`/`_font_path`/`_out_dir`
  解析）；剔除 4 项过度设计（见下）。
- 过度设计剔除（不实施，理由留档）：
  - 作者树作品叶懒加载：`_search_current_tree`（`main_window.py:3565-3572`）靠遍历已建子节点
    收集作品，懒加载会让搜索漏掉未展开的作者；收益仅 rebuild 0.375 s→约 0.1 s，风险大于收益。
  - `collections/index.json` 原子化：全仓无读取方，半截文件也无影响。
  - 归一键扩到六个目录 + `cover.images`/`supplement_ttf`：多数已有工程根解析，重复处理无收益。
  - 整体拆 `main_window.py`：见第五批，改为「新代码进模块、旧文件只在改动时顺手抽离」。
  - Windows 保留设备名（`CON`/`NUL`/`AUX`）与超长名**不额外处理**：实测本机可正常创建
    `CON.json`/`NUL.json`/`aux.json`/`COM1.json`；超长名写盘失败有可见报错，收益低于规则复杂度。
- 第五轮审核（打根验证）：三处 `PROJECT_ROOT` 均为 `app_root()`（`settings_dialog.py:17`、
  `xml2pdf_bridge.py:22`、`ebook_merger.py:115`），冻结（onedir）解析正确——**勿改回 `__file__`
  推导**；`xml2pdf.path` 的全部消费经 `_x2p_root` 漏斗（`xml2pdf_bridge.py:44-45`），条目行号
  等价覆盖；清理入口唯一（设置页 `_clean_cache` → `cache_manager.clean`），护栏放
  `cache_manager.clean` 内即覆盖未来入口；下载主机实为 cbdata + `raw.githubusercontent.com`
  两类，TLS 白名单方案与之吻合。新发现两处（已并入第一批/第三批清单）：设置页缓存统计对
  相对值受 cwd 影响、设置页 mulu/meta 与主窗两套来源。
- 第六轮审核（实测验证）：`_safe_name` 现状（`main_window.py:7216-7220`）实测已能中和路径穿越
  与非法字符——`..`/`.`/`...`/纯空白/换行 → 兜底名，`a/b`·`a:b`·`a\b` → `a_b`，`阿含/地藏` →
  `阿含_地藏`，尾点/尾空格去掉；**无需再加规则**。打包入口确认是 `cbeta_publish/app.py`
  （`packaging/cbeta_publish.spec:60`），故 app.py 层的「配置损坏恢复」与「相对路径归一」
  对打包版确实生效。新增一条实施约束：构造期提示不可用模态框（见第一批对应条目）。
- 第七轮审核（终审）：更正一处数字——`main_window.py` 实际 **8738 行**（此前记 9147，已改）。
  复核「忽略返回值」的 3 个调用点语义均成立：用户点「立即保存」（`:5876`）、设置页保存后写说明页
  （`:7037`）、分册「确定即落盘」（`:8183`）；补一条时机约束——`app.py:18` 的配置读取早于
  `QApplication`（`:24`），损坏提示必须延后。其余条目、行号、数字与方案经全量复核无新错漏。
  终审结论：P28 定稿，可实施。
- 动手前的约束：
  - 共享层 `_vendor/cbeta_fetch.py` **不可本地手改**（`tests/test_vendor_sync.py` 校验 sha256）；
    TLS 与流式下载须在 cbeta-fetch 上游改（`cbeta-org/cbeta-fetch`），再用其
    `tools/sync_into.py` 同步到 xml2pdf `pycbeta/_vendor` 与 publish
    `cbeta_publish/_vendor`，两处都更新 `SOURCE.txt`；不要只改 xml2pdf 或手改 vendor。
    （publish 仓里**没有** `tools/sync_into.py`——`test_vendor_sync.py:24` 报错文案引用了它，
    属误导，工程化批可补脚本或改文案。）
  - 已有文件名清洗器：`_safe_name`（`main_window.py:7216`）、`_safe_stem`（`xml2pdf_bridge.py:409`）、
    `_safe_seg`（`catalog_path.py:46`）——**复用/上提，不新造**。
  - 原子写现成范例 `official_state.py:60`、`verify_cache.py:64` 用固定 tmp 名（双开两实例会撞名），
    新 helper 的 tmp 名要带进程号/随机后缀。
- 第一批（数据安全，publish 内）：
  - [x] 统一原子写 helper（同目录 tmp 名带 pid＋随机后缀 + `os.replace`），覆盖**用户数据写点**：
    丛书文件 7 处（`main_window.py:3853/4118/4223/4379/5771/5805/4263`、`collection_model.py:196`）、
    config 及本地状态 4 处（`main_window.py:2306/2328/2590`、`settings_dialog.py:2006`）、分类/标签/远程 meta
    （`category_manager.py:38`、`tags_manager.py:76`、`remote_manager.py:26`）、preset 回退
    （`xml2pdf_bridge.py:437`）。派生索引 `collection_model.py:132` **不改造**（`index.json` 全仓无读取方，
    grep 只有写点）。报告/临时文件写点同样不改造（`main_window.py:6015/8337/8597`、
    `xml2pdf_bridge.py:285/467`）。`official_state.py:60`、`verify_cache.py:64` 已顺带换用共享 helper。
  - [x] 存盘失败保留脏标记并提示：批量保存无条件清脏（`main_window.py:4268-4269`）；
    单册 `_save_one_collection`（`:5790` 失败 `return False`）有 3 个调用点忽略返回值
    （`:5876/7037/8183`）→ 统一「失败＝脏保留＋提示，成功才清」。多文件失败时**合并成一次提示**
    （逐个弹窗会连环打断）。
  - [x] 丛书名/分类名走 `_safe_name`：文件名构造 4 处（`main_window.py:3879` 新建、`:4107` 另存为、
    `:4209` 移动、`:4291` 空白丛书保存）、合并输出目录 `7850`、批量清除目标 `8359/8383`
    （**不要用 `last_publish_dir`**——它也被 ZIP `:8916` 与导出 `:9137` 覆盖成用户选的目录；
    改为 `out_root / safe_name(name)` 并加 `is_relative_to` 越界校验；名字为 `..` 时现会删到
    输出根的父目录）。显示名保持用户原文，只清洗文件名部分。`collection_model.py:187`
    （仅测试调用的 `Collection.save`）同规则顺手改。
  - [x] 配置损坏自动恢复：`app.py:18` 捕获后备份 `app.json.bak-<时间戳>`、回退出厂模板并提示。
    注意读取发生在 `QApplication` 创建（`:24`）之前，**提示须延后**到主窗显示后（或先写日志），
    不能在此处直接弹窗。
  - [x] 目录数据缺失/损坏：**不阻断启动**，在构造函数末尾检查服务是否齐全，提示并引导到
    「设置→更新源」（否则用户进不了设置页修）。**提示用非模态**（状态栏/左栏角标），
    不要在构造函数里弹 `QMessageBox`——测试与离屏环境会被模态框挂起。
    现 `main_window.py:419-425` 吞异常留半残状态，
    且 `:419` 的 `config["mulu_dir"]` 在 try 外、键缺失直接崩；`1948` 裸 `except` 让损坏丛书静默消失
    （改为收集文件清单，在左栏/状态栏提示跳过后数量）。
  - [x] 打包版相对路径归一：只处理**实际按原样消费**的 4 个键——`mulu_dir`（`main_window.py:419`）、
    `collections_dir`（`:3877` 等）、`official_ebooks_dir`（或别名 `cbeta_ebooks_dir`，
    `official_ebook_source.py:95` 直接 `Path`）、`xml2pdf.path`（`main_window.py:5991/6249`、
    `xml2pdf_bridge.py:45` 均未走 `_abs`；空值时主窗回退写死的开发机路径 `E:/dev/cbeta/xml2pdf`，
    属既有行为，归一只对有值配置生效）；**又一 cwd 敏感点**：设置页缓存统计/清理对
    「官方电子书缓存」用原始值直接 `Path`（`settings_dialog.py:1182/1229`），归一必须在
    构造 `SettingsDialog` 前生效才顺带修好它；做成**幂等函数放 `paths.py`**，
    `app.py` 与 `MainWindow.__init__` 都调用（测试与其它入口不经过 `app.py`），只改内存，
    不改用户磁盘配置。其余键**无需处理**（已有工程根解析）：`output_dir` 走 `_out_dir`（`:5946-5950`）、
    `verify_dir`/`xml_to_ebooks_dir`/`xml2pdf.cbeta_ebook` 走 `_abs`（`xml2pdf_bridge.py:35-37/48-50/489/728`）、
    `cover.images` 走 `_font_path`（`ebook_merger.py:108-112`）；`ui.supplement_ttf` 打包默认空。
- 第二批（性能，publish 内）：
  - [x] `work_id.py` 惰性建 `{canon+no → 原始大小写}` 索引（首次出现者胜，与 `catalog_lookup` 同语义；
    按文件 mtime/size 失效——`sutra_mapping` 本身是更新源，`remote_sources.py:27`，更新后文件被替换）
    → 启动省约 1.4 s。
  - [x] 搜索简体兜底缓存：现状已是「原文子串优先→简体兜底」（`main_window.py:3556-3563`），
    但未命中节点每次按键都重算 OpenCC 简体（8148 节点 0.206 s）；节点简体文本按树版本缓存后
    常态按键约 26 ms（实测；首次 0.265 s）；未使用的 `_title_s2`（`main_window.py:1060`，白花 0.154 s）删除——
    **但要保留 `text_util.init()`（`:1059`）**：那是全仓唯一初始化点（grep 仅此一处），
    删掉后 `to_simplified` 静默不转换（`utils/text_util.py:19-25`），繁简搜索会无声失效。
  - [x] 刊本树缓存：每次刷新都重新解析 1.1 MB 的 vol.json（`main_window.py:1458` 调
    `vol_service.load_vol`），按 mtime 缓存（`vol.json` 也是更新源 `remote_sources.py:21`）；
    朝代索引已有内存缓存（`:1563`），仅缺更新源替换文件后的失效。
  - [ ] 批量下载 2–4 并发（可选，非必需；保留取消与重试语义）。
- 第三批（并发与安全，publish 内）：
  - [x] 设置页「检查更新」改用现成 `UpdateWorker`（`books/update_worker.py:7`，已带
    progress/checked/updated 信号；现 `settings_dialog.py:1487-1492` 在 UI 线程调
    `rm.update_all` 靠 `processEvents()` 续命）；运行期间禁用「关闭」防半途中断；
    完成后沿用主窗口径提示「重启后生效」（`main_window.py:1144`），`result` 仍供
    `_reload_update_table`/`_append_mulu_diff` 使用。
  - [x] `verify_worker.py:161-169` 异常时只把**未处理**作品记失败：现异常分支把 `self.works`
    全部补进 `failed`（已通过的也算失败）；改以 `verdicts` 是否已含该作品为界，只补未处理者。
    保留现有捕获 BaseException 防 SystemExit 穿透的意图（`:162-165` 注释）。
  - [x] 设置页更新源的 meta/备份目录与主窗**两套来源**：设置页硬编码 `PROJECT_ROOT/mulu`（`:19`、
    `:1375`、`:1480`），主窗用 `config["mulu_dir"]`（`main_window.py:1120/1136`）；用户自设
    mulu 目录时两边读写不同的 meta.json 与 backup/。改用 worker 时顺带统一为
    `self._cfg["mulu_dir"]` 派生。**实现时发现落盘目标也写死 app_root**（`remote_sources.local_path`），
    已一并加根参数随 `mulu_dir`。
  - [x] `collection/id_import.py:208-209` 抓取加大小/类型上限（现 `resp.read()` 无上限）。
  - [x] 缓存清理护栏：`cache_manager.clean` 会逐个删除目标目录下的**全部子项**
    （`cache_manager.py:38-44`），目标若被设成盘根/程序根/用户主目录＝删整盘、删程序本身；
    硬拒绝这三类目标（现 `settings_dialog.py:174-191` 只提示与 XML 根重叠）。
- 第四批（跨仓轨：cbeta-fetch 改完同步到 xml2pdf/publish；已完成）：
  - [x] TLS：所有主机默认 `ssl.create_default_context()`；cbdata 只清
    `VERIFY_X509_STRICT` 附加位（`CERT_REQUIRED` + `check_hostname` 保持开启），
    不使用 `ssl._create_unverified_context()`；其它主机严格。实测 Python 3.14 /
    OpenSSL 3.0.18：cbdata 默认报 Missing SKI，清 strict 位后 200；GitHub 严格 200。
  - [x] 下载分块流式：`download`/`fetch_if_changed` 1 MiB 分块写 `.part`；
    `Content-Length` 与实际字节数不一致即失败重试（`copyfileobj` 短读不抛异常，
    必须显式校验）；`.part` 名加 pid+随机后缀；`unzip=True` 临时 zip + `unzip_flat`。
  - [x] 新增 `probe_status(url) -> int|None`（HEAD 状态码，共用同一套 TLS 上下文），
    publish `_head_absent_404` 改用它，保留 404/410 快判。
  - [ ] 解压原子性与同名策略：延后第二批（临时目录解压后替换；同名整单失败 vs 后者覆盖）。
  - 实施：cbeta-fetch `817d207` / v0.2.0（本地 commit，未推送；该仓库未配置 remote）；已同步 xml2pdf `pycbeta/_vendor` 与
    publish `cbeta_publish/_vendor`（两边 `SOURCE.txt` 已更新）。上游 23 项、
    publish 861 项、xml2pdf `test_fetch` 51 项 + `test_update_data` 20 项 + vendor sync 3 项通过。
  - 方案与测试清单见 `docs/上游-cbeta-fetch-TLS与分块下载.md`。
- 第五批（工程化）：
  - [ ] 加 ruff（先只开 E722/F841/E501）；CI 可选。
  - [x] **不整体拆** `main_window.py`（8738 行，拆分收益低于回归风险）：新代码进独立模块，
    旧文件只在改动时顺手抽离（如本次原子写、名称清洗、搜索缓存）。
- 测试计划：原子写、名称越界（`..` 与非法字符）、不同工作目录下启动、配置损坏回退、编号索引缓存、
  搜索缓存失效、盘根清理被拒、校验异常只记未处理作品——每项一条回归测试。

### 第九轮：状态机与跨文件一致性（2026-10-21）

- 审查角度：脏状态、跨次残留、线程退出、目录切换、界面过滤、富文本；审查阶段只读，结论确认后实施。
- 新增结论（已复核）：
  1. 退出保存失败仍关闭；空白丛书改名先删旧文件，随后写新文件失败会丢已保存内容（`main_window.py` 的 `closeEvent`、`_save_collections`、`_finalize_blank_save`）。
  2. 官方书备齐失败/取消后，旧文件存在时合并/ZIP/导出静默用旧版；取消还会误写「备齐水位」。影响 5 个调用点（单册合并、批量更新、批量合并、ZIP、导出）。
  3. 启动目录更新线程无进度、不可取消、退出不等待；设置页可再起一个更新线程，同进程两线程撞同一个 `.part` 临时文件，表现为假失败。
  4. 设置改「丛书数据/目录数据」即时生效但不重建内存；`_save_config` 整份写回会撤销目录修改，并把归一化后的绝对路径写回 `app.json`，破坏打包版便携相对路径。
  5. `_dl_stats` 跨次残留；删除当前分类后右侧过滤显示「全部」但实际仍按已删分类过滤；左栏丛书树刷新不沿用当前分类/标签过滤。
  6. 人工放行后汇总仍把该作品列在「未入库」；放行记录只按（作品，格式）记，文件变化后再失败不会重新询问。
  7. `detail` 富文本未转义收藏名（低危，需点击；他人分享的丛书 JSON 可注入链接）。
  8. 小项：批量保存取消空白丛书改名仍按临时名落盘、`check_all` 失败也写 `last_check`、发布元数据写失败静默、`_name_taken` 大小写敏感、设置页固定写默认配置路径（生产不受影响，测试/自定义路径才有差异）。
- 修法要点：
  - 退出：`_save_collections` 返回是否全部成功；失败弹「取消/仍退出」默认取消；空白丛书改名改为先写新文件、成功后再删旧文件。
  - 官方备齐：取消不写水位；下载尝试后重算 `stale`，仍有「文件存在但过期」时询问「是否用旧版继续」，默认否；批量更新把仍过期项计入失败。
  - 更新线程：`RemoteManager`/`UpdateWorker` 增加停止标志与进度；关闭时停止并等待；与设置页更新互斥。
  - 目录：本次会话固定旧目录并提示重启；`_save_config` 只覆盖运行时键、保留文件里的路径键；设置页下次打开显示文件里的待生效目录。
  - 界面：重建过滤下拉后用实际 `currentData()`；树刷新沿用当前过滤；放行后从 `fail`/`undet` 剔除；富文本只转义用户名。
- 测试计划：退出保存失败、取消/失败备齐、配置目录保留、过滤状态、放行汇总、名称大小写、设置页配置路径；`MainWindow` 测试全部用临时 `_config_path`/`collections_dir`。
- 实施结果（2026-10-21，全部完成）：
  - 退出保存：`_save_collections` 返回是否全部成功；`closeEvent` 失败时弹「取消/仍退出」默认取消；空白丛书改名改为先写新文件、成功后再删旧文件（`_finalize_blank_save` 用副本写入，失败不动内存）。
  - 官方备齐：`_download_missing` 入口重置 `_dl_stats`；取消不写水位；新增 `_official_stale_pairs`/`_confirm_use_old_official`，单册合并、批量更新、批量合并、ZIP、导出五处按仍过期项提示或计入失败。
  - 更新线程：`RemoteManager`/`UpdateWorker` 增加停止标志；主窗口连接 progress，关闭时先停并最多等 20 秒，超时拒绝关闭；设置页更新与主窗口更新互斥。
  - 目录/配置：设置改 `collections_dir`/`mulu_dir` 本次会话固定旧值并提示重启；`_save_config` 改为保留文件里的目录键与 `xml2pdf.path`，不再把归一化绝对路径写回；设置页按传入 `_config_path` 保存/备份。
  - 界面：`_sync_combo` 用重建后的实际分类；`_refresh_coll_tree` 校验过滤值并在三个刷新点沿用当前过滤；`_manual_approved` 改按（作品，格式）＋文件大小/修改时间；放行后从 `fail`/`undet` 剔除对应行。
  - 富文本：右栏 `detail` 改用 `_DetailLabel`（默认纯文本，校验汇总走 `setHtml`）；直接进 QMessageBox 的用户名/分类名/标签名按 `_esc_ui` 转义。
  - 小项：批量保存取消空白改名不再按临时名落盘；`check_all` 有失败/停止不写 `last_check`；发布元数据写失败保留脏标记；`_name_taken` 大小写不敏感（原有路径归一测试改用尾部空格，继续覆盖避让逻辑）。
  - 上一轮遗留 P0/P1：更新页「恢复原始/上一次」只恢复 SOURCES 目录数据，配置快照移到 `backup/config/`（恢复原始优先用出厂模板）；分类/标签文件损坏时先另存 `.bad-<时间戳>` 再写；清理报告按「清理前－清理后」统计实际删除量并提示残留；`meta.json` 损坏先备份再按空库继续。
  - P2/P3：`_replace_staged_path` 残留目录返回 False；EPUB `full-path` 反斜杠/`./..` 归一；新建分类 id 经 `safe_name` 清洗；14 处裸 `except:` 改 `except Exception:`。
  - 测试：全量 **861 项通过**（原 851 + 新增 10 项）；`tests/test_state_regressions.py` 覆盖退出保存失败、取消不写水位、配置目录保留、名称大小写、放行指纹、设置页配置路径、分类/标签/meta 损坏、恢复只还原目录数据。
  - 未做：第四批之二（解压原子性/同名策略）、空服务替身（测试辅助）。

## 备注

- 本地 `bulei.txt` 为 CBETA 23 部類；三藏映射 经(01-10)/律(11)/论(12-15)/藏外(16-23)。
- X 续藏按 `bulei.txt` 同名归并，已纳入三藏映射；般若部類 01/09 由 `merge_missing_children` 补。
- 封面字体/颜色/比例在 `cover.styles` 统一（`font` 为字体文件路径；`ratio`/`delta`；
  缺繁体字形回退系统全字库）；字号基准见设置页「封面/版式」。
- 旧版平展缓存布局已作废（不迁移/不双读）：旧目录需手动删、自制书重生成。
