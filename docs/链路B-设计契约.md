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
# 内部：进程内 pycbeta.cli.main(["-i", work_id, "-f", fmt, "-o", out_file, "--config", preset])
```

- **库调用**，不起子进程：省每本一次 python 启动；进度/取消/错误是直接对象
  （`stop()` 在本与本之间生效；单本内部无更细进度，对面只在完成时落一行）。
- `-i` **只传 work id**：XML 源由 xml2pdf 的 `materialize_work` 解析
  （本地候选源 → 官方下载）。publish 侧**不**自行定位 XML——CBReader
  书库是 P5a（按卷切分），不是对面要的 P5（整部经），拿它去找只会喂错文件。
- `--config` = 预设文件（run.json 组合单或纯 presets；`None` = 对面默认）。
- `-o` = publish 定名的完整产物路径（平展，见 §4）。

**辅助函数**（同在 `xml2pdf_bridge.py`）：
`_x2p_root` / `_abs`（目录统一绝对，相对按工程根）/
`preset_dir`（缺省 `<仓库>/presets`）/ `list_presets` / `resolve_preset` /
`load_preset_dict`（供 `XmlOptionsDialog` 预填）/
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
  编辑 → 覆盖保存或另存为到预设目录 → 刷新预设下拉。
- `XmlOptions` dataclass 仍是 xml2pdf 内部模型；publish 不直接构造它，
  只传预设文件路径。

## 4. 配置与数据模型

**`config/app.json`**
```json
{
  "default_source": "official",                        // official | xml（右栏来源单选，sticky）
  "xml_to_ebooks_dir": "E:/dev/cbeta/publish/cbeta_ebooks_xml",   // 自制书输出根（可配，绝对路径）
  "xml2pdf": {
    "path": "E:/dev/cbeta/xml2pdf",                    // 自制程序仓库
    "preset_dir": "",                                 // 预设目录；空=仓库下 presets
    "preset": ""                                      // 默认预设文件名；空=对面默认
  }
}
```
- 目录一律绝对路径；显示与落盘用本地分隔符（Windows 反斜杠）。
- 已删除：`book_dir`、`local_xml_root`（XML 源归 xml2pdf）、
  `xml2pdf.{page,font_lang,engine,vertical}`（preset 为准）。

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
- 复用：目标存在且比预设新 → 跳过；否则重生成。两边目录互不混淆。

## 5. 数据流（合成时）

```
右栏来源 = official → official_ebook_source.download_ebook → cbeta_ebooks/{fmt}/...
右栏来源 = xml      → xml2pdf_bridge.convert(work_id, preset) → xml_to_ebooks_dir/{work}.{fmt}
→ ebook_merger 单一格式合并（已支持分册）
```
- 说明页：来源=自制时追加一句「电子书由程序根据官方XML制作。」；官方不加。

## 6. 实施清单

- [x] `publish`：`xml2pdf_bridge.py`（库调用＋预设目录＋平展输出＋复用规则）
- [x] `publish`：右栏来源单选＋预设下拉＋[调整…]；设置页「自制」组（来源/程序路径/自制电子书/预设目录/默认预设）
- [x] `publish`：`[合并]` 整批同源、平展目录、说明页注明
- [x] `xml2pdf`：`pycbeta.gui` 面板/对话框/独立入口（已存在，publish 直接复用）
- [x] 文档：本契约 + 《链路B-UI设计.md》

## 7. 备注

- 三藏/朝代等目录过滤与本链路无关，沿用「启动时内存生成」策略。
- X 续藏按 `bulei.txt` 同名归并，已纳入三藏映射。
