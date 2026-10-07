# 代办（按优先级）

> 设计文档：`docs/设计总案.md`（总方案）、`docs/UI设计.md`（UI）、
> `docs/链路B-设计契约.md`（与 xml2pdf 的跨仓调用契约）。
> 测试：`python -m unittest discover tests`（当前 667 项通过）。

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
- [x] **独立窗**：上游已实现 GUI `--verify-root`（提案 `docs/上游-GUI校验根参数提案.md` 已归档）；
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

### P9 — 批量 ID 建丛书（待办）
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

## 备注

- 本地 `bulei.txt` 为 CBETA 23 部類；三藏映射 经(01-10)/律(11)/论(12-15)/藏外(16-23)。
- X 续藏按 `bulei.txt` 同名归并，已纳入三藏映射；般若部類 01/09 由 `merge_missing_children` 补。
- 封面字体/颜色/比例在 `cover.styles` 统一（`font` 为字体文件路径；`ratio`/`delta`；
  缺繁体字形回退系统全字库）；字号基准见设置页「封面/版式」。
- 旧版平展缓存布局已作废（不迁移/不双读）：旧目录需手动删、自制书重生成。
