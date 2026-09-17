# 链路 B 设计契约 — XML → xml2pdf → 丛书（供 publish 与 xml2pdf 双会话复用）

> 状态：**已实现**（publish 侧库调用＋预设制＋平展目录；UI 见《链路B-UI设计.md》）。
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
  - `formats` 与 `-f`：由命令行 `-f` 决定（publish 用自己的 pdf/epub 勾选）；
    打开「调整…」时已把面板「输出格式」预置为该勾选，避免误导。
  - **CSS 槽（样式表）属 run.json**：已由临时 run.json 包装保留仓库主题
    （命名/临时预设两条路径一致）。
- `-o` = publish 定名的完整产物路径（平展，见 §4）。

**辅助函数**（同在 `xml2pdf_bridge.py`）：
`write_run_wrapper` / `remove_temp_preset`（临时 run.json 生成与删除）/
`_x2p_root` / `_abs`（目录统一绝对，相对按工程根）/
`presets_dir`（= `<仓库>/presets`，由 xml2pdf 决定，publish 不另配）/
`list_presets` / `resolve_preset` / `load_preset_dict` / `save_preset`
（预设读写；优先走上游公开 API，不可用时回退本地）/
`xml_books_dir` / `xml_dest` / `find_built` / `is_fresh`。

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
  "default_source": "official",                        // official | xml（右栏来源单选，sticky）
  "xml_to_ebooks_dir": "E:/dev/cbeta/publish/cbeta_ebooks_xml",   // 自制书输出根（可配，绝对路径）
  "xml2pdf": {
    "path": "E:/dev/cbeta/xml2pdf",                    // 自制程序仓库（预设目录=其 presets/）
    "cbeta_ebook": "E:/dev/cbeta/publish/cbeta_xml",   // CBETA XML 目录（--cbeta-ebook；不可空，空则用默认）
    "preset": "",                                     // 默认预设名（presets/ 下 stem）；空=对面默认
    "regen": "missing"                                // 生成策略：missing=仅缺｜all=全部重生成
  }
}
```
- 目录一律绝对路径；显示与落盘用本地分隔符（Windows 反斜杠）。
- 预设目录固定在 xml2pdf 仓库 `presets/`（上游 `user_presets_dir`），
  publish 不再单独配置目录；`xml2pdf.preset` 存**预设名（stem）**。
- 已删除：`book_dir`、`local_xml_root`（XML 源归 xml2pdf）、
  `xml2pdf.{page,font_lang,engine,vertical}`（preset 为准）、`xml2pdf.preset_dir`。

**`collections/<cat>/<slug>.json`**（只读兼容，不参与决策）
```json
{ "source": "official", "work_sources": {...}, "xml_options": {...} }
```
- 来源**不再**按丛书/逐书配置：一套丛书可按官方或自制合并（右栏按次选，整批统一）。
- 旧字段保留仅为兼容旧 JSON，publish 不写、不用。

**输出目录**
- 官方：`cbeta_ebooks/{fmt}/{canon}/{work}.{fmt}`（`cbeta_ebooks_dir`）。
- 自制：`xml_to_ebooks_dir/{work}.{fmt}`（**完全平展**，pdf/epub 同目录，
  扩展名区分；`find_built` 兼容 GUI 产出的 `{id 书名}.pdf` 形式）。
- **生成策略**（`config.xml2pdf.regen`，右栏「生成」单选，用户决定）：
  `missing`（默认）＝已有产物复用、只生成缺少（`bridge.ensure_one(regen_all=False)`）；
  `all`＝全部重新生成、覆盖原路径（`regen_all=True`）。**不用 mtime/哈希推断过期**。
  两边目录互不混淆；ZIP/导出同样按来源取目录。

## 5. 数据流（合并 / ZIP / 导出）

```
右栏来源 = official → official_ebook_source.download_ebook → cbeta_ebooks/{fmt}/...
右栏来源 = xml      → xml2pdf_bridge.ensure_one(work_id, preset, regen_all) → xml_to_ebooks_dir/{work}.{fmt}
→ ebook_merger 单一格式合并 / ZIP 打包 / 拷贝导出
```
- 说明页：来源=自制时追加一句「电子书由程序根据官方XML制作。」；官方不加。
- 打包格式（ZIP/导出点后弹窗选，独立于合并格式勾选）：官方源 7 种
 （`PACK_FORMATS`：pdf/epub 单文件＋html/docx/odt/txt/txt_notes 目录型），
  自制源仅 pdf/epub。目录型只打包不合并：
  ZIP 按 `部/相对路径` 写入 `{丛书名}_{fmt}.zip`，导出整树拷贝到 `{target}/{work}/`。
  纯 txt 端点（`text/{id}.txt.zip`，不含校注）放 publish 自有 `_EXTRA_DOWNLOADS`，
  vendor 共享层不动。

## 6. 实施清单

- [x] `publish`：`xml2pdf_bridge.py`（库调用＋预设（上游 API）＋平展输出＋`ensure_one` 生成策略）
- [x] `publish`：右栏来源单选＋预设下拉＋生成策略（仅缺/全部）＋[调整…]
- [x] `publish`：`[合并]` 整批同源、平展目录、说明页注明；**ZIP/导出 亦支持自制**
- [x] `xml2pdf`：`pycbeta.gui` 面板/对话框/独立入口（已存在，publish 直接复用）
- [x] `xml2pdf`：`--config` 兼容 run.json 与基础配置 JSON（`theme.resolve_config_arg`）；
  `--html-epub-user-theme` 占位开关；公开 `merged_preset`/`get_preset`/`*_config_preset`
- [x] `publish`：`convert` 传 `--cbeta-ebook`（配置键 `xml2pdf.cbeta_ebook`，设置页「XML 工作根」行）
- [x] `publish`：预设读写改用公开 API（`list_config_presets`/`load_config_preset`/
  `save_config_preset`；`[调整…]` 用 `get_preset`），不再碰私有名或自写盘
- [x] 文档：本契约 + 《链路B-UI设计.md》

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
