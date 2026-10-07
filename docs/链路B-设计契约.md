# 链路 B 设计契约 — XML → xml2pdf → 丛书（供 publish 与 xml2pdf 双会话复用）

> 状态：**已实现**（publish 侧库调用＋预设制＋分格式目录；UI 见《UI设计.md》）。
> 修订要点：XML 源解析归 xml2pdf；publish 不配置 XML 源、不逐书设来源、
> 不再自行定位 XML（CBReader 是 P5a，非对面要的 P5）。

## 1. 目标与分工

- **xml2pdf**：负责 XML 源解析（本地候选源 → 官方下载）、转换逻辑与
  纸张/字体/引擎等全部渲染参数；对外提供 CLI（`python -m pycbeta`）与
  可复用面板 `pycbeta.gui`。
- **publish**：只做三件事——选**来源**（官方/自制）、选**预设**、
  把一组 work id 交给 xml2pdf；产物落 `xml_to_ebooks_dir` 供合并。
- **会话分工**：渲染参数单一逻辑归属 xml2pdf（以预设文件为界），
  publish 不重复实现，也不再逐项传参。

## 2. 调用方式（publish → xml2pdf，进程内库调用）

```py
# cbeta_publish/books/xml2pdf_bridge.py
def convert(work_id, xml_path, out_file, config, fmt="pdf", preset=None, stop=None) -> Path | None
# 内部：进程内 pycbeta.cli.main(["-i", work_id, "-f", fmt, "-o", out_file,
#                              "--config", preset, "--cbeta-ebook", <工作根>])
def convert_outputs(work_id, fmt, out_dir, config, preset=None, stop=None) -> list[Path]
# 内部：同一调用传输出目录（不是固定文件名），上游按各自标题落盘，
#      publish 再把产物与报告搬回 out_dir。
```

- **库调用**，不起子进程：省每本一次 python 启动；进度/取消/错误是直接对象
  （`stop()` 在本与本之间生效；单本内部无更细进度，对面只在完成时落一行）。
- `-i` **只传 work id**：XML 源由 xml2pdf 的 `materialize_work` 解析
  （工作根 → 本地候选源 → 官方下载）。publish 侧**不**自行定位单个 XML——CBReader
  书库是 P5a（按卷切分），不是对面要的 P5（整部经），拿它去找只会喂错文件；
  需要判断产物是否齐全时，也只数已缓存工作目录根下的 `*.xml`，不解析、不喂单文件。
- `--cbeta-ebook` = XML 工作根，**publish 显式传入**（配置键
  `xml2pdf.cbeta_ebook`；为空则不传，由对面自身配置决定）。这样 xml2pdf 也能
  脱离 publish 独立运行，互不干扰。（契约术语里"XML 源"专指 `source.xml_dir`
  本地候选源，那项 publish 不配。）
- `--config` = **临时 run.json 包装**（`bridge.write_run_wrapper`：5 槽沿用仓库当前
  `run.json`，`config-json` 指本次预设绝对路径；用后删）；上游不可用时回退直传
  预设。`None` = 对面默认。
- **面板选项靠预设即可全项生效**（无需逐个传开关）：`engine` / `output.vertical` /
  `font_lang` 已由对面做**配置回退**（`cli.resolve_engine_vertical_lang`：显式开关 >
  配置 > 默认），所以 publish 只传 `-i / -f / -o / --config / --cbeta-ebook` 即可。
  详见 xml2pdf《第三方调用说明》§8.4 / §8.6 / §8.7 / §9。
- **例外两处**：
  - `formats` 与 `-f`：由命令行 `-f` 决定（publish 用自己的 pdf/epub/docx 勾选）；
    打开「调整…」时已把面板「输出格式」预置为该勾选，避免误导。
  - **CSS 槽（样式表）属 run.json**：已由临时 run.json 包装保留仓库主题
    （命名/临时预设两条路径一致）。
- `-o` = 输出目标：
  - `convert` 传 publish 定名的完整产物路径（`{fmt}/{name}.{fmt}`，
    `name=built_name` 即工作目录名，缺省=work）；
  - `convert_outputs` 传输出目录，让上游按各自源文档标题落盘（`{佛典編號 书名}.{ext}`，
    书名取各源 `title level="m"` 并跟随 `source.title_t2s`，见上游设计规格 §11 输出规则）。
    同一 work id 可能对应多个源 XML（例如 TX0011 的 TX18/TX19 两册）；
    若对多源强制同一个显式 `-o` 文件，后渲染的源会覆盖先渲染的源。
    批量侧发现源集合后按上游默认命名收回全部产物，不再假设一 work 一文件。

**辅助函数**（同在 `xml2pdf_bridge.py`）：
`write_run_wrapper` / `remove_temp_preset`（临时 run.json 生成与删除）/
`_x2p_root` / `_abs`（目录统一绝对；相对按 `cbeta_publish/paths.app_root()`——
源码=仓库根、打包=exe 同级目录）/
`presets_dir`（= `<仓库>/presets`，由 xml2pdf 决定，publish 不另配）/
`list_presets` / `resolve_preset` / `load_preset_dict` / `save_preset`
（预设读写；优先走上游公开 API，不可用时回退本地）/
`xml_books_dir` / `xml_dest` / `find_built` / `find_all_built` /
`work_source_files` / `ensure_products`（自制书寻址、批量生成与复用；
`ensure_one` 只保留旧调用兼容，返回代表产物）/
`verify_work` / `find_verify_report` / `verify_reports` / `verify_report_pass`
（校验，见 §5）。官方侧：`official_ebook_source.official_books_dir`（收敛官方缓存根键）。

## 3. 可复用 UI 组件 `pycbeta.gui`

| 组件 | 路径 | 用途 |
|------|------|------|
| `XmlOptionsPanel(QWidget)` | `E:/dev/cbeta/xml2pdf/pycbeta/gui/panel.py` | 渲染参数编辑面板，`get_options() -> XmlOptions` / `set_options()`；自带保存用户配置 |
| `XmlOptionsDialog(QDialog)` | 同上 | 面板对话框包装，`exec()` 确定返回 `XmlOptions` |
| 独立主窗 | `python -m pycbeta.gui` | 面板 + 输入/输出 + 批量转换 |

- publish 以 `sys.path` 引入（`bridge._ensure_path`）：
  `from pycbeta.gui.panel import XmlOptionsDialog`。
- publish 的**预设[调整…]**入口即调 `XmlOptionsDialog`：读取当前预设 →
  编辑 → `exec()` Accepted 后取 `dlg.get_preset(base)`（合并后的预设 dict）→
  覆盖保存或另存为（写盘经 xml2pdf 公开函数 `save_config_preset`，见下）。
- 上游 `CssEditorDialog` 曾在构造时往 `QApplication` 追加全局样式
  （`ensure_tooltip_style`），触发全应用 repolish，左栏最小值 346→1272 级别
  抬高且粘住回不来，导致分栏锁死、主窗口无法缩小；上游已修（规则下到
  对话框实例，`test_upstream_dialog_no_app_pollution` 构造真对话框锁定），
  publish 侧无残留 workaround。
- **公开 API（不碰私有名）**：`XmlOptionsPanel.get_options()/set_options()`、
  `XmlOptionsPanel.merged_preset(base=None)`（面板值+base → 预设 dict）、
  `XmlOptionsDialog.get_options()/get_preset(base=None)`、
  `list_config_presets/load_config_preset/save_config_preset/delete_config_preset`
  （`presets/` 读写；非法名/越界删除抛 `ValueError`）。
- `XmlOptions` dataclass 仍是 xml2pdf 内部模型；publish 不直接构造它，
  只传预设文件路径。

## 4. 配置与数据模型

**`config/app.json`**
```json
{
  "default_source": "official",                        // official | xml（右栏/设置来源单选，sticky）
  "default_formats": {                                 // 默认勾选格式（设置页「E书默认来源和格式」）
    "merge": ["pdf", "epub"],                          // 初始化右栏格式勾选（合并只取 pdf/epub）
    "official": ["pdf","epub","html","docx","txt"],    // 官方 ZIP/导出 预选（默认去 odt/txt_notes）
    "xml": ["pdf","docx"]                              // 自制 ZIP/导出 预选（默认不勾 epub）
  },
  "xml_to_ebooks_dir": "E:/dev/cbeta/publish/cbeta_xml_ebooks",   // 自制书输出根（可配，绝对路径）
  "xml2pdf": {
    "path": "E:/dev/cbeta/xml2pdf",                    // cbeta-xml2pdf 仓库（预设目录=其 presets/）
    "cbeta_ebook": "E:/dev/cbeta/publish/cbeta_xml",   // CBETA XML 目录（--cbeta-ebook；不可空，空则用默认）
    "preset": "",                                    // 默认预设名（presets/ 下 stem）；空=对面默认
    "verify_build": false                            // 制作书籍：true=自制/重制后校验并仅导入通过项
  }
}
```
- 目录一律绝对路径；显示与落盘用本地分隔符（Windows 反斜杠）。
  （可为相对路径，按 `paths.app_root()` 解析；打包脚本会把 dev 绝对路径改写为
  便携相对路径，见 `packaging/README.md`。）
- `config/ui_state.json`：上次工作的丛书路径（`last_collection`），切换右栏丛书即写此文件
  （与 `app.json` 同级、**gitignored，不进版本库**），下次启动按其选中（缺失则回退空白/首项）。
  旧配置里的 `ui.last_collection` 仅在迁移时读到即移除，不再回写 `app.json`。
- 预设目录固定在 xml2pdf 仓库 [cbeta-xml2pdf](https://github.com/Zen-Bear/cbeta-xml2pdf) `presets/`（上游 `user_presets_dir`），
  publish 不再单独配置目录；`xml2pdf.preset` 存**预设名（stem）**。
- 已删除：`book_dir`、`local_xml_root`（XML 源归 xml2pdf）、
  `xml2pdf.{page,font_lang,engine,vertical}`（preset 为准）、`xml2pdf.preset_dir`、
  `xml2pdf.regen`（合并/ZIP/导出恒「仅缺」，全部重生成用右栏「重制」按钮）。

**`collections/<cat>/<slug>.json`**（只读兼容，不参与决策）
```json
{ "source": "official", "work_sources": {...}, "xml_options": {...},
  "manual_volumes": [ {"title": "法藏", "work_ids": ["T0001","T0002"]} ],
  "bulei_groups": { "T0001": ["16 淨土部類", "T0001 淨土經"] } }
```
- `bulei_groups`：从部类树拖入时记录的来源部类**全路径**（`{work_id: [段...]}`）。
  「按部类」分组/合并时按当前深度截断、`_clean_bulei_seg` 清洗后优先采用，
  解决同书多部类被首个命中抢走的问题（如 16 淨土的书同时在 06/10）。
  读入规范化：key 归一、剔除不在 `work_ids` 的项。无记录的书走自动解析（旧行为）。
- `manual_volumes`：右栏「手工分册」的卷定义（顺序=册序；`work_ids` 仍是全书单真相，
  卷内顺序不独立存放）。读入规范化：id 归一、剔除不在 `work_ids` 的脏 id、跨卷去重（先出现者保留）、
  空卷保留。`merge.mode=manual` 时按此分册（无卷则回退不分册）。
- 来源**不再**按丛书/逐书配置：一套丛书可按官方或自制合并（右栏按次选，整批统一）。
- 旧字段保留仅为兼容旧 JSON，publish 不写、不用。

**输出目录**（两缓存根同构 `{root}/{fmt}/…`，根分开防复用串源）
- 官方：`cbeta_ebooks/{fmt}/{work}.{fmt}`；目录型 `cbeta_ebooks/{fmt}/{work}/`
  （`official_books_dir` 收敛配置键，`cbeta_ebooks_dir` 优先兼容 `official_ebooks_dir`）。
- 自制：`xml_to_ebooks_dir/{fmt}/` 下按上游默认命名落盘（pdf/epub/docx 分格式目录；
  `find_all_built` 找同一 work 的全部产物；`find_built` 返回其中第一项）。
  同一 work 的多个源文档分别生成各自产物（如 TX0011 上/中下两个 docx），
  目录型输出同样保留各自文件。复用按“产物齐全＋源不比产物新”判定。
- **旧版平展布局作废**（不迁移、不双读、不自动删）：旧文件需用户手动删除；
  自制书按新布局会视为不存在 → 需重下/重生成。
- **生成策略**：合并/ZIP/导出**恒为「仅缺」**＝已有产物复用、只生成缺少
  （`bridge.ensure_products(regen_all=False)`）。需整体重生成时先点右栏 `[重制]`
  （`regen_all=True`；「调整…」临时预设亦强制重生成）。**不用 mtime/哈希推断过期**。
  两边目录互不混淆；ZIP/导出同样按来源取目录。
- **PDF 伴生 docx 复用**（`xml2pdf.reuse_pdf_companion`，默认开；设置页「自制E书」）：
  `docx2pdf` 管线在 PDF 成功产出时，必在输出根附一份同内容、同 stem 的 docx
  （上游唯一目的是给 `--verify-only` 定位；无条件覆盖写）。publish 从不用 verify-only，
  故 pdf+docx 同跑时由 `bridge.adopt_pdf_companions` 直接把该伴生搬进 `docx/`
  当作 docx 产物（重制路径同时清理同 work 过期异名残留），**省一次完整 docx 渲染**；
  html2pdf/竖排管线无伴生则照常渲染；仅选 pdf 时不动该文件。仅在本轮 PDF
  真实渲染（非复用）后认领，历史遗留伴生不会被误用。

## 5. 数据流（合并 / ZIP / 导出）

```
右栏来源 = official → official_ebook_source.download_ebook → cbeta_ebooks/{fmt}/...
  （本地库优先：`official_library.root` 非空时先拷贝，缺失回退下载；
  下载前 HEAD 探针（10s）：404/410 确定不存在即抛 `RemoteNotFound` 快失败
  （失败项记 `不存在`，跳过 90s×3 重试），超时/其它异常照常下载；
  校验基线同库 `seed` 进工作根 `{id 书名}/docx|txt|epub/`，只补缺失）
右栏来源 = xml      → xml2pdf_bridge.ensure_products(work_id, preset, regen_all) → xml_to_ebooks_dir/{fmt}/ 上游默认命名产物（同一 work 可能多个文件）
→ ebook_merger 单一格式合并 / ZIP 打包 / 拷贝导出
```
- 说明页：来源=自制时在「说明」标题下一行居中注 `intro["note"]`（设置「自制书说明」，
  默认「依 CBETA XML 自制」，其后空一行）；官方不加。简介三行默认仿宋单行距
  （`styles.intro_summary`），部类/刊本分组信息按 ` / ` 每段一行、沿用目录条目字体。
- 打包格式（ZIP/导出点后弹窗选，独立于合并格式勾选）：官方源 7 种
 （`PACK_FORMATS`：pdf/epub 单文件＋html/docx/odt/txt/txt_notes 目录型），
  自制源 3 种：pdf/epub/docx。目录型只打包不合并：
  ZIP 按 `部/相对路径` 写入 `{丛书名}_{fmt}.zip`，导出整树拷贝到 `{target}/{work}/`。
  纯 txt 端点（`text/{id}.txt.zip`，不含校注）放 publish 自有 `_EXTRA_DOWNLOADS`，
  vendor 共享层不动。
- **ZIP/导出 按分册**：读全局 `merge.mode`（`ask` 弹合并设置框，共享 `ask_last`/模板）；
  `none` 保持单 zip／平铺；分册模式按**可用书**分组，每组每格式 ZIP
  `{基名}_{fmt}.zip`、导出 `{target}/{基名}_{fmt}/`（`基名=_merge_basename`，同合并命名），
  组名重名自动 `_2` 去重；空组/缺书跳过记失败。
- **缺书确认（官方源；合并/ZIP/导出一致）**：是=先下载（下完仍缺再问
  「是否继续（仅打已有）」）、否=跳过缺书继续（缺的记失败）、取消=不打。
- 自制格式勾选（右栏）：pdf/epub/**docx**（docx 默认勾选）；**合并只取 pdf/epub**，
  docx 走 ZIP/导出/校验/打开。`ensure_products`/`find_all_built`/`xml_dest` 格式通用，无需特判。
- 校验（进程内「自制/重制」＋自动/手动导入）：设置「制作书籍」=`校验`
  （`xml2pdf.verify_build`）时，右栏 `[自制]/[重制]` 转为校验式——`[自制]` 只处理
  自制书目录里**缺少**的书，`[重制]` 整批全部重做；触发 `VerifyWorker` 逐本调
- **校验复用**（`xml2pdf.verify_reuse`，默认开；需上游 `pycbeta.verify.verify_fingerprint`
  可用，否则全部重验并提示）：跑校验前先算每部书每格式的上游指纹，
  库（`config/verify_records.json`，gitignored，只存通过）中有同指纹且产物在库
  即跳过（自制/重制都跳；重制对跳过项仍重生成产物但不校验）；
  指纹对不上/无记录/产物缺失才真校验，通过且入库成功后写库。
  跳过项不进导入扫描与总报告，单独列「已通过（跳过）」。
  `bridge.verify_work` → 库调用
  `pycbeta.cli.main(["-i", work, "-f", <勾选>, "-o", <vdir>, [--config wrap],
  "--cbeta-ebook", <工作根>, "--verify",
  "--verify-max-diff", N, "--verify-diff-lines", M])`
  （阈值取全局 `xml2pdf.verify_max_diff`（默认 5）与 `verify_diff_lines`（默认 5），钳制 0–50；
  上游预设 `verify` 段无此二项、仅 CLI 支持，故 publish 始终透传。`VerifyWorker`
  聚合该 work 的全部语义产物报告：任一失败即该 work 失败，只有全部通过才算通过；
  上游 `cli.py` 修 work id 校验 `2a10d12`；
  官方基线源目录 `src` 亦按 work id 修正 `16df9cf`：文件→其目录 / 目录→该目录 /
  編號→已材料化 XML 的 work 目录，否则 `find_official`/`auto_fetch` 定位不到）；
  预设经临时 run.json 保主题。**比对档由上游 `generate_formal` 生成**（`verify` 段覆盖
  `output` 段，与 GUI 独立窗一致：`inline_brackets`/`suppress_jhead_dup`/`show_close_juan`
  等生效，`cli.py` `37a864a`），否则会与官方基线误报。正式产物 `{id 书名}.{fmt}` 落校验目录顶层，
  报告落 `{id 书名}（验证）/`（`verify_dir/<丛书>/`，默认 `<工程>/cbeta_verify`，
     与自制书目录分离）。跑完自动导入（可手动重试）：报告兼容
   `{stem}_verify_report.txt` / `{id}_{书名}_校验报告.txt` / `report.txt` 三种命名
   （`bridge.verify_reports`，同一语义产物只取最新；同一 work 的不同语义产物分别保留）。**判读按格式**：优先读每 work 段首的上游总结行
   （`bridge.parse_work_summary_line`：`[id] N format: 1[docx=OK(0/0)], 2[pdf=1],
   3[epub=FAIL(48/97)]`；`pdf=数字` 为被覆盖、结论跟随同行第 M 条；`COVERED` 无 ref、
   `NO_BASELINE`/`NOGEN`/`ERROR` 为未判定原因；`→` 左侧为产物格式）；
   无总结行（老报告）时回退 trial 解析（`bridge.verify_report_formats`）：
   把报告里 `[OK]/[FAIL]` 逐 trial 映射回产物格式（`pdf→docx` 记在 pdf 名下；
   独立窗标记行直接带格式），得 {fmt: 通过}；`[--]`（覆盖/无基线）另由
   `bridge.verify_report_pending` 解析为 {fmt: 原因}（`covered:<src>` / `no baseline` /
   `gen not found`）。缺数/多余数由 `bridge.verify_report_numbers` 取
   （`FAIL(48/97)`→`缺48/多97`，`?`→未知）。
   **docx通过即pdf通过**（`bridge.apply_verify_coverage`）：pdf 被报告记为
   「已由 src 校验覆盖」且 src 逐格式通过 → pdf 视为通过（不重复验；src 未过则不套用）。
   缺逐格式信息时退回整体判定
   （`bridge.verify_report_pass`：有 `[FAIL]`→不通过；≥1 `[OK]` 无 `[FAIL]`→通过；否则未判定）。
   **逐格式入库**：通过的格式 **move** 入 `{fmt}/{id 书名}.{fmt}`（L2 带书名，
    保留上游产物名；入库即被 `ensure_products` 的产物齐全检查复用），
    未通过的格式跳过、不拖累通过者（如 docx 过、epub 没过 → 入 docx＋被覆盖的 pdf）。
    上/中下等多源语义产物按各自报告目录精确入库，不互相覆盖或误套报告。
   未判定标注原因（如 `T1858 未判定（epub无基线）`）；失败标签带数
   （如 `T1859 校验未通过（epub 缺48/多97）`）。结果页每部书列出入库了哪个格式文件
   （可点开；人工放行的标"人工放行"）。
   **人工检验**：导入（自动/手动）后，未通过＋未判定项弹框询问，可看报告后勾选放行入库
   （左勾选列表＋右报告预览＋"打开产物/报告/校验目录"链接；本 session 放行过的不再重复询问）。
   未放行项在**托管校验目录**内删除（外部目录只导入不删）。
   worker 异常（含上游 argparse 的 `SystemExit`）也必发 `finished_all`
   （否则嵌套事件循环挂死）；线程跑完断开信号＋`deleteLater`（野指针防护）。
   临时预设未保存时拒绝执行。手动导入（菜单「导入校验通过E书…」）**每次都弹目录选择**
  （默认指向当前丛书 `verify_dir/<丛书>/`，可改选独立窗输出目录，同样兼容两种报告名），
   便于把独立窗已校验的产物入库（菜单「制作书籍 → 运行 xml2pdf 制作书籍…」
   会把当前丛书直接带过去）。独立窗保留为手动工作台。

## 6. 实施清单

- [x] `publish`：`xml2pdf_bridge.py`（库调用＋预设（上游 API）＋分格式目录＋`ensure_products` 生成策略，支持一 work 多产物）
- [x] `publish`：右栏来源单选＋预设下拉＋[调整…]（生成策略单选已移除：合并/ZIP/导出恒仅缺，「重制」按钮=全部重生成）
- [x] `publish`：`[合并]` 整批同源、分格式目录、说明页注明；**ZIP/导出 亦支持自制**
- [x] `publish`：**自制/重制（设置=校验）**（进程内 `VerifyWorker`→`verify_work`，跑完自动导入；
  「制作书籍」菜单＋校验目录＋临时预设拦截；见 §5）
- [x] `xml2pdf`：`--verify` 支持 work id 输入（`2a10d12`：改用已 materialize 的 `xmls`；
  `16df9cf`：官方基线源目录 `src` 按 work 目录修正，编号输入可定位官方基线）
- [x] `xml2pdf`：`-i` 输入分类健壮性（`25eccb8`：cwd 下有同名**非 XML** 目录时不再
  劫持合法編號，改按編號材料化；避免 `no XML files under <id>`）
- [x] `xml2pdf`：独立窗启动参数预填（`7258b65`：`--ids-file/--out/--preset/--formats/
  --verify/--autostart`，`parse_known_args`＋Qt 透传；保留为手动工作台）
- [x] `xml2pdf`：`pycbeta.gui` 面板/对话框/独立入口（已存在，publish 直接复用）
- [x] `xml2pdf`：`--config` 兼容 run.json 与基础配置 JSON（`theme.resolve_config_arg`）；
  `--html-epub-user-theme` 占位开关；公开 `merged_preset`/`get_preset`/`*_config_preset`
- [x] `publish`：`convert` 传 `--cbeta-ebook`（配置键 `xml2pdf.cbeta_ebook`，设置页「XML 工作根」行）
- [x] `publish`：预设读写改用公开 API（`list_config_presets`/`load_config_preset`/
  `save_config_preset`；`[调整…]` 用 `get_preset`），不再碰私有名或自写盘
- [x] 文档：本契约 + 《UI设计.md》
- [x] `publish`：Windows 打包（`build_exe.ps1` + `packaging/cbeta_publish.spec`：onedir、
  便携数据根 `paths.app_root()`、打进 pycbeta、可选 Chromium/代码签名；见 §4 相对路径）
- [x] `publish`：GPL-3.0 许可（`LICENSE`，Zen Bear）、`README.md`、示例输出 `demo/`；发布 GitHub

## 7. 备注

- 三藏/朝代等目录过滤与本链路无关，沿用「启动时内存生成」策略。
- X 续藏按 `bulei.txt` 同名归并，已纳入三藏映射。

## 8. 问答

**Q1：何时要包一层临时 run.json，何时直接传？**

根因是上游 `theme.resolve_config_arg` 的分流：`--config` 直接传预设（base 配置
JSON）时只当 `config-json` 单槽，其余 CSS 槽回出厂，不取仓库当前 `run.json`。

- 要包（`preset` 非空）：命名预设或「调整…」临时预设，且要保留仓库主题 →
  `bridge.write_run_wrapper`（5 槽照抄仓库当前 `run.json`，`config-json` 指本次
  预设），`--config` 传包装，用后删。`convert` 内已统一做，两条路径一致。
- 不包：`preset=None`（出厂默认，`--config` 整个不传）；或上游不可用时回退
  直传预设（降级：能跑，但 CSS 槽回出厂，与包装前旧行为一致）。
- 只读类调用（`list_presets`/`resolve_preset`/`load_preset_dict`）不走
  `--config`，不涉及。

**Q2：「调整…」不保存时，为何用临时预设文件，而不用 CLI 开关直传？**

上游 CLI 确实有不少开关（`--theme`、4 个 CSS 槽、`--font-lang`、`--t2s`、
`--font-scale`、`--notes`、`--page`、`--vertical`、`--engine` 等），且 publish
是进程内调 `pycbeta.cli.main(argv)`，技术上加开关无障碍。但：

1. 覆盖不全：预设是整棵配置树（`output/pages/source/engines/annotations/…`），
   CLI 只覆盖部分叶子，无开关的项会丢；走文件是面板产出 dict → CLI 消费
    文件的无损直通。
2. 耦合回流：上游每加一个面板选项，publish 就要手写一条映射；预设制正是
    为清掉这类逐项耦合。
3. 路径分叉：命名/临时预设共用一条 `--config` 路径（`_run_preset` 透传、
    `ensure_products` 复用判断）；开关直传要另起一套 argv 装配，调用点更复杂。

故保持临时预设文件方案（`write_temp_preset` + 临时 run.json 包装，用后删）；
开关直传只适合临时调试，不做正式路径。

## 9. 附：独立窗输出目录导入规范

本附录约定"xml2pdf 独立窗输出目录 → publish 自制书目录"的导入规则。
publish 的「自制/重制（校验）」产物目录天然符合本规范；独立窗手动输出只要同样符合，
即可经「导入校验通过E书…」入库。程序内「制作书籍 → 导入说明…」
弹窗是本节的简化版（操作口径）。

### 9.1 独立窗侧输出要求

1. 输出目录（`--out` / 窗内"输出"框）下，每个成功生成的书有**正式产物**：
   `{id 书名}.{ext}`（如 `T0032 四谛经.pdf`、`T0032 四谛经.docx`），放在目录**顶层**。
2. 必须勾选「转换后校验」（`--verify`）：每书在 `{id 书名}（验证）/` 子目录下有一份
   **报告**，命名三选一（新版上游用第一种，旧版两种仍兼容读）：
   - `{id}_{书名}_校验报告.txt`（如 `T0001_长阿含经_校验报告.txt`；无书名时 `{id}_校验报告.txt`）；
   - `{stem}_verify_report.txt`（独立窗旧命名；`stem` = work id，如 `T0032`）；
   - `report.txt`（CLI 旧命名；work 取父目录名去 `（验证）` 后缀后的首 token，
     如 `T0032 四谛经（验证）` → `T0032`）。
   另有**转换报告** `{name}_转换报告.txt`（及 `{fmt}/` 下按格式的同名文件，
   `output.convert_report` 控制，默认开）：只记录渲染特殊处理，**不是校验判据**，
   不参与导入扫描、不算产物。
3. 同一书多份报告并存时，以 **mtime 最新者**为准（同刻优先 `report.txt`）。
   只转换、未校验的产物**没有判据，一律不入库**。
4. 总报告 `总验证报告.txt`（`bridge.write_verify_summary`，固定名覆盖写）：
   头＋摘要（行文同导入标签）＋全文（按 stem 拼接原文）；刻意避开两种发现模式，
   不参与导入扫描；自制/重制跑完与手动导入均写一份，链接进进度总结与结果页。

### 9.2 publish 侧导入规则

1. 报告发现：递归扫描 `*_verify_report.txt`、`*_校验报告.txt` 与 `report.txt`
  （`bridge.verify_reports`）。同一 work 的不同语义产物各保留最新的一份报告
  （例如 TX0011 上/中下），同一语义产物的新旧命名仍只取最新。
2. 书单匹配：`stem == work`，或 `stem` 以 `work + " "` / `work + "_"` 开头
  （新命名用下划线分隔，仍要求分隔符对齐，`T185` 不误命中 `T1858`）；
  匹配不上当前丛书书单的跳过。
3. 判读**按格式**：优先读每 work 段首的上游总结行
   （`[id] N format: 1[docx=OK(0/0)], 2[pdf=1], 3[epub=FAIL(48/97)]`；
   `pdf=数字` 为被覆盖、结论跟随同行第 M 条；`COVERED` 无 ref、`NO_BASELINE`/
   `NOGEN`/`ERROR` 为未判定原因；无总结行的老报告回退 trial 解析）。
   把报告 `[OK]/[FAIL]` 逐 trial 映射回产物格式（`pdf→docx` 记在 `pdf`；
   独立窗标记行直接带格式），得 `{fmt: 通过}`。
   缺逐格式信息时退回整体判定（`bridge.verify_report_pass`：含 `[FAIL]`→不通过；
   ≥1 `[OK]` 无 `[FAIL]`→通过；否则未判定）。缺数/多余数取自总结行
   （`FAIL(48/97)`→`缺48/多97`），用于失败标签与人工检验。
4. 产物识别（`MainWindow._verify_products`）：有报告时优先用该报告所在
  `(验证)` 目录名派生的产物名精确匹配；其余只看目录**顶层** `{stem}*.{ext}`，
  后缀映射 `pdf/epub/docx/odt/md/txt` → fmt；排除 `*_verify_report.txt`、
  `*_校验报告.txt`、`_ids.txt` 与 `*转换报告*`；
  同一 work 的多个语义产物分别入库。
5. 入库（**逐格式**）：某格式判通过 → `shutil.move` 到 `{自制书根}/{fmt}/{上游产物名}.{fmt}`
  （L2 带书名，保留上游产物名；自动建目录、同名覆盖），入库即被 `ensure_products` 的
  产物齐全检查复用；
   未通过/未判定的格式跳过，**不拖累**通过的格式（如 docx 过、epub 没过 → 只入 docx）。
    `find_built` 先精确 `{fmt}/{work}.{fmt}`、再 `{fmt}/{work} *.{fmt}`（边界空格，
    防 `T185` 误命中 `T1858`）；`built_name`（工作目录名 `{id} {书名}`）只用于
    单源精确路径与复用查找，不作为多源产物的命名来源——多源各产物名取各自源文档
    的 `title level="m"`（如 TX0011 的上/中下，目录名只反映其中之一）。
6. 无任何产物 → 记"缺产物"（失败）；全部格式都未通过 → 记"校验未通过"；
   都未判定 → "未判定"。
7. **人工检验**：导入（自动/手动）后，未通过＋未判定项弹框询问，可看报告后勾选放行入库
   （左勾选列表＋右报告预览＋"打开产物/报告/校验目录"链接；结果页标"人工放行"；
   本 session 放行过的不再重复询问）。
8. **删除未放行**：托管校验目录（`verify_dir` 内）中未放行的暂存产物在检验后删除；
   外部目录（手动导入选的独立窗输出等）只导入不删。

### 9.3 入口与目录优先级

1. 「导入校验通过E书…」**每次都弹目录选择**（默认当前丛书 `verify_dir/<slug>/`，
   可改选独立窗输出目录或其任意上层，递归扫描）。
2. 右栏「自制/重制（设置=校验）」跑完走同一规则（`_do_import_verified`）自动导入。

### 9.4 校验目录分离（用户决策：保持分离，不共用）

publish 的 `verify_dir`（默认 `<工程>/cbeta_verify`）与 xml2pdf 校验输出
（独立窗每轮指定的输出目录／`source.verify_root`）**保持分离**，不并成同一个文件夹。
publish「运行独立窗」预填 `--out=<丛书校验目录>` 的单次任务制共用保留（用完即导入/清理），
全局并目录不做。理由：

- **托管判定是路径判定**（`_is_managed_verify_dir`）：并目录后独立窗产物全落托管区，
  人工检验"不放行"的会被 publish 直接删除——删的是独立窗唯一的一份；外部目录只导入不删。
- 通过项入库是 **`move` 搬走**，独立窗侧被掏空。
- 双方都写 `总验证报告.txt`（互相覆盖）；递归扫描"同 work 取最新"会跨来源取到对方旧报告。
- 缓存页"校验目录"统计虚高、清理不敢下手（与官方缓存/XML 共用目录同构）。
- 上游面板已有 `verify_root` 行，独立窗侧一设全局 publish 侧无感知；
  publish 调用上游校验时显式钉死 `--verify-root {vdir}/验证`（见 §5），预设对齐检查同步覆盖。
