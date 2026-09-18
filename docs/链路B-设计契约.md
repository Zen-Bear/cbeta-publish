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
```

- **库调用**，不起子进程：省每本一次 python 启动；进度/取消/错误是直接对象
  （`stop()` 在本与本之间生效；单本内部无更细进度，对面只在完成时落一行）。
- `-i` **只传 work id**：XML 源由 xml2pdf 的 `materialize_work` 解析
  （工作根 → 本地候选源 → 官方下载）。publish 侧**不**自行定位 XML——CBReader
  书库是 P5a（按卷切分），不是对面要的 P5（整部经），拿它去找只会喂错文件。
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
- `-o` = publish 定名的完整产物路径（`{fmt}/{work}.{fmt}` 或校验目录；见 §4）。

**辅助函数**（同在 `xml2pdf_bridge.py`）：
`write_run_wrapper` / `remove_temp_preset`（临时 run.json 生成与删除）/
`_x2p_root` / `_abs`（目录统一绝对，相对按工程根）/
`presets_dir`（= `<仓库>/presets`，由 xml2pdf 决定，publish 不另配）/
`list_presets` / `resolve_preset` / `load_preset_dict` / `save_preset`
（预设读写；优先走上游公开 API，不可用时回退本地）/
`xml_books_dir` / `xml_dest` / `find_built` / `ensure_one`（自制书寻址与复用）/
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
    "merge": ["pdf", "epub"],                          // 初始化右栏格式勾选
    "zip":    {"official": [7种], "xml": ["pdf","docx","epub"]},   // ZIP 弹窗预选
    "export": {"official": [7种], "xml": ["pdf","docx","epub"]}    // 导出弹窗预选
  },
  "xml_to_ebooks_dir": "E:/dev/cbeta/publish/cbeta_xml_ebooks",   // 自制书输出根（可配，绝对路径）
  "xml2pdf": {
    "path": "E:/dev/cbeta/xml2pdf",                    // 自制程序仓库（预设目录=其 presets/）
    "cbeta_ebook": "E:/dev/cbeta/publish/cbeta_xml",   // CBETA XML 目录（--cbeta-ebook；不可空，空则用默认）
    "preset": ""                                     // 默认预设名（presets/ 下 stem）；空=对面默认
  }
}
```
- 目录一律绝对路径；显示与落盘用本地分隔符（Windows 反斜杠）。
- 预设目录固定在 xml2pdf 仓库 `presets/`（上游 `user_presets_dir`），
  publish 不再单独配置目录；`xml2pdf.preset` 存**预设名（stem）**。
- 已删除：`book_dir`、`local_xml_root`（XML 源归 xml2pdf）、
  `xml2pdf.{page,font_lang,engine,vertical}`（preset 为准）、`xml2pdf.preset_dir`、
  `xml2pdf.regen`（合并/ZIP/导出恒「仅缺」，全部重生成用右栏「重制」按钮）。

**`collections/<cat>/<slug>.json`**（只读兼容，不参与决策）
```json
{ "source": "official", "work_sources": {...}, "xml_options": {...} }
```
- 来源**不再**按丛书/逐书配置：一套丛书可按官方或自制合并（右栏按次选，整批统一）。
- 旧字段保留仅为兼容旧 JSON，publish 不写、不用。

**输出目录**（两缓存根同构 `{root}/{fmt}/…`，根分开防复用串源）
- 官方：`cbeta_ebooks/{fmt}/{work}.{fmt}`；目录型 `cbeta_ebooks/{fmt}/{work}/`
  （`official_books_dir` 收敛配置键，`cbeta_ebooks_dir` 优先兼容 `official_ebooks_dir`）。
- 自制：`xml_to_ebooks_dir/{fmt}/{work}.{fmt}`（pdf/epub/docx 分格式目录；
  `find_built` 优先精确名，其次同 `{fmt}/` 下 `{work}*.{fmt}` 通配）。
- **旧版平展布局作废**（不迁移、不双读、不自动删）：旧文件需用户手动删除；
  自制书按新布局会视为不存在 → 需重下/重生成。
- **生成策略**：合并/ZIP/导出**恒为「仅缺」**＝已有产物复用、只生成缺少
  （`bridge.ensure_one(regen_all=False)`）。需整体重生成时先点右栏 `[重制]`
  （`regen_all=True`；「调整…」临时预设亦强制重生成）。**不用 mtime/哈希推断过期**。
  两边目录互不混淆；ZIP/导出同样按来源取目录。

## 5. 数据流（合并 / ZIP / 导出）

```
右栏来源 = official → official_ebook_source.download_ebook → cbeta_ebooks/{fmt}/...
右栏来源 = xml      → xml2pdf_bridge.ensure_one(work_id, preset, regen_all) → xml_to_ebooks_dir/{fmt}/{work}.{fmt}
→ ebook_merger 单一格式合并 / ZIP 打包 / 拷贝导出
```
- 说明页：来源=自制时在「说明」标题下一行居中注「E书依 CBETA XML 自制」；官方不加。
- 打包格式（ZIP/导出点后弹窗选，独立于合并格式勾选）：官方源 7 种
 （`PACK_FORMATS`：pdf/epub 单文件＋html/docx/odt/txt/txt_notes 目录型），
  自制源 3 种：pdf/epub/docx。目录型只打包不合并：
  ZIP 按 `部/相对路径` 写入 `{丛书名}_{fmt}.zip`，导出整树拷贝到 `{target}/{work}/`。
  纯 txt 端点（`text/{id}.txt.zip`，不含校注）放 publish 自有 `_EXTRA_DOWNLOADS`，
  vendor 共享层不动。
- 自制格式勾选（右栏）：pdf/epub/**docx**（docx 默认勾选）；**合并只取 pdf/epub**，
  docx 走 ZIP/导出/校验/打开。`ensure_one`/`find_built`/`xml_dest` 格式通用，无需特判。
- 校验（进程内「校验重制」＋自动/手动导入）：右栏发布行 `[校验重制]`
  （来源=自制时显示）触发 `VerifyWorker` 逐本调 `bridge.verify_work` → 库调用
  `pycbeta.cli.main(["-i", work, "-f", <勾选>, "-o", <vdir>, [--config wrap],
  "--cbeta-ebook", <工作根>, "--verify"])`（上游 `cli.py` 修 work id 校验 `2a10d12`；
  官方基线源目录 `src` 亦按 work id 修正 `16df9cf`：文件→其目录 / 目录→该目录 /
  編號→已材料化 XML 的 work 目录，否则 `find_official`/`auto_fetch` 定位不到）；
  预设经临时 run.json 保主题。**比对档由上游 `generate_formal` 生成**（`verify` 段覆盖
  `output` 段，与 GUI 独立窗一致：`inline_brackets`/`suppress_jhead_dup`/`show_close_juan`
  等生效，`cli.py` `37a864a`），否则会与官方基线误报。正式产物 `{id 书名}.{fmt}` 落校验目录顶层，
  报告落 `{id 书名}（验证）/`（`verify_dir/<丛书>/`，默认 `<工程>/cbeta_verify`，
  与自制书目录分离）。跑完自动导入（可手动重试）：报告兼容
  `{stem}_verify_report.txt` / `report.txt` 两种命名（`bridge.verify_reports`，
  同一 work 只取最新），`bridge.verify_report_pass` 判读（有 `[FAIL]`→不通过；
  ≥1 个 `[OK]` 且无 `[FAIL]`→通过；否则未判定）→ 产物按扩展名全收
  （pdf/epub/docx/odt/md/txt），通过的拷入自制书目录改名
  `{fmt}/{work}.{fmt}`（入库即被 `ensure_one(missing)` 复用）；不通过/未判定不入库。
  临时预设未保存时拒绝执行。手动导入（菜单「导入校验通过E书…」）优先读当前丛书的
  `verify_dir/<丛书>/`；无报告时**弹目录选择**，可指向独立窗输出目录（同样兼容两种报告名），
  便于把独立窗已校验的产物入库。独立窗（「xml2pdf 独立窗…」）保留为手动工作台。

## 6. 实施清单

- [x] `publish`：`xml2pdf_bridge.py`（库调用＋预设（上游 API）＋分格式目录＋`ensure_one` 生成策略）
- [x] `publish`：右栏来源单选＋预设下拉＋[调整…]（生成策略单选已移除：合并/ZIP/导出恒仅缺，「重制」按钮=全部重生成）
- [x] `publish`：`[合并]` 整批同源、分格式目录、说明页注明；**ZIP/导出 亦支持自制**
- [x] `publish`：**校验重制**（进程内 `VerifyWorker`→`verify_work`，跑完自动导入；
  「自制书籍」菜单＋校验目录＋临时预设拦截；见 §5）
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
   `ensure_one` 复用判断）；开关直传要另起一套 argv 装配，调用点更复杂。

故保持临时预设文件方案（`write_temp_preset` + 临时 run.json 包装，用后删）；
开关直传只适合临时调试，不做正式路径。

## 9. 附：独立窗输出目录导入规范

本附录约定"xml2pdf 独立窗输出目录 → publish 自制书目录"的导入规则。
publish 的「校验重制」产物目录天然符合本规范；独立窗手动输出只要同样符合，
即可经「导入校验通过E书…」入库。程序内「自制书籍 → 独立窗输出与导入规则…」
弹窗与本节同文。

### 9.1 独立窗侧输出要求

1. 输出目录（`--out` / 窗内"输出"框）下，每个成功生成的书有**正式产物**：
   `{id 书名}.{ext}`（如 `T0032 四谛经.pdf`、`T0032 四谛经.docx`），放在目录**顶层**。
2. 必须勾选「转换后校验」（`--verify`）：每书在 `{id 书名}（验证）/` 子目录下有一份
   **报告**，命名二选一：
   - `{stem}_verify_report.txt`（独立窗；`stem` = work id，如 `T0032`）；
   - `report.txt`（CLI；work 取父目录名去 `（验证）` 后缀后的首 token，
     如 `T0032 四谛经（验证）` → `T0032`）。
3. 同一书两份报告并存时，以 **mtime 最新者**为准（同刻优先 `report.txt`）。
   只转换、未校验的产物**没有判据，一律不入库**。

### 9.2 publish 侧导入规则

1. 报告发现：递归扫描 `*_verify_report.txt` 与 `report.txt`
  （`bridge.verify_reports`）。
2. 书单匹配：`stem == work`，或 `stem` 以 `work + " "` 开头；匹配不上当前丛书书单的跳过。
3. 判读（`bridge.verify_report_pass`，**入库的唯一质量门**）：
   含 `[FAIL]` → 不通过；≥1 个 `[OK]` 且无 `[FAIL]` → 通过；
   否则未判定（`[--]`/空报告/读失败，需人工看报告）。
4. 产物识别（`MainWindow._verify_products`）：只看目录**顶层** `{stem}*.{ext}`，
   后缀映射 `pdf/epub/docx/odt/md/txt` → fmt；排除 `*_verify_report.txt`、`_ids.txt`；
   每格式取排序后第一个。
5. 入库：`shutil.copy2` 到 `{自制书根}/{fmt}/{work}.{fmt}`（自动建目录、覆盖同名），
   入库即被 `ensure_one(missing)` 复用。
6. 通过但找不到产物 → 记"缺产物"（失败）；不通过/未判定不入库。

### 9.3 入口与目录优先级

1. 「导入校验通过E书…」优先读当前丛书 `verify_dir/<slug>/`；
   无报告则**弹目录选择**，可指向独立窗输出目录（或其任意上层，递归扫描）。
2. 右栏「校验重制」跑完走同一规则（`_do_import_verified`）自动导入。
