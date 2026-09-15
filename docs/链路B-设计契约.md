# 链路 B 设计契约 — XML → xml2pdf → 丛书（供 publish 与 xml2pdf 双会话复用）

> 状态：已确认，待 `xml2pdf` 会话实现可复用 UI；本会话负责集成契约。

## 1. 目标与分工

- **xml2pdf 独立窗**：仅单文件/目录转换（`cbeta_xml/{canon}/{vol}/*.xml` → `pdf/epub`），未来可导入 `publish` 导出的 `selection.json` 批量转。
- **publish 集成**：丛书内**每本书默认源非唯一、可配置**（官方 `cbeta_ebooks` ↔ 本地 `cbeta_xml`），通过 `work_sources` 逐书覆盖。
- **会话分工**：纸张/字体/引擎等单一逻辑归属 `xml2pdf`，本会话仅定义接口契约，避免重复实现。

## 2. 接口契约（xml2pdf 产出，publish 消费）

### 2.1 数据结构 `XmlOptions`
```python
@dataclass
class XmlOptions:
    page: str = "a4"          # a4/a5/letter/book/phone/tablet/monitor + config.json:pages 可扩展
    font_set: str = "default" # default:zh-Hans 等，见 pycbeta/config.json:7 font_sets
    engine: str = "docx2pdf"  # docx2pdf[:wps]|html2pdf[:chromium]
    margins: dict = None      # 可选，默认取 pages[page].margins
```

### 2.2 可复用组件 `pycbeta.gui`

| 组件 | 路径 | 职责 |
|------|------|------|
| `XmlOptionsPanel(QWidget)` | `E:/dev/cbeta/xml2pdf/pycbeta/gui/panel.py` | 纸张/字体/引擎选择，复用 `config.json:pages/font_sets`+`theme.py`，暴露 `get_options() -> XmlOptions` / `set_options()` |
| `XmlOptionsDialog(QDialog)` | 同上 | `XmlOptionsPanel` 的对话框包装，`exec() -> XmlOptions|None` |
| 独立主窗 | `python -m pycbeta.gui` | `XmlOptionsPanel` + 输入/输出目录 + 批量转换，`sys.path` 无侵入 |

*publish 侧以 `sys.path += ["E:/dev/cbeta/xml2pdf"]` 引入：`from pycbeta.gui.panel import XmlOptionsPanel`*

## 3. 数据模型与配置

**`config/app.json` 新增**
```json
{
  "default_source": "official",
  "xml2pdf": { "path": "E:/dev/cbeta/xml2pdf", "page": "a4", "font_set": "default", "engine": "docx2pdf" }
}
```
`default_source` 为新建书/丛书的全局默认（`official`|`xml`），用户可在设置页切换，非唯一。

**`collections/<cat>/<slug>.json`**
```json
{
  "source": "official",
  "work_sources": { "T0001": "xml", "T0002": "official" },
  "xml_options": { "page": "a4", "font_set": "default" }
}
```
- `source` 集合级默认（继承全局）
- `work_sources` 单书级覆盖（缺省→继承集合级）
- 兼容旧 JSON（缺字段→ `official`）

## 4. UI 交互

**publish 右栏**
- `来源: (•)跟随集合 ( )官方 ( )本地XML [设置...]` — 单选存 `collection.source`，`[设置...]` 弹 `XmlOptionsDialog` 存 `xml_options`
- 中栏改 `QTableWidget`：`经号 | 经名 | 来源[官方|XML▼]`（默认继承集合级），支持批量“选中多行→设为官方/XML”

**xml2pdf 独立窗**
- 上：输入 `cbeta_xml` 目录/文件 + 输出目录
- 中：`XmlOptionsPanel`
- 下：批量列表 + 进度/取消

## 5. 数据流（合成时）

```
丛书 work_ids + work_sources
  ├─ xml  → xml2pdf_bridge.batch_convert(works_xml, XmlOptions) → cbeta_xml→pdf
  └─ official → official_ebook_source.download_ebook → cbeta_ebooks
→ ebook_merger 单一格式合并（已支持分册）
```

**`cbeta_publish/books/xml2pdf_bridge.py`**
```py
def batch_convert(work_ids: list[str], out_dir: Path, opts: XmlOptions, progress_cb) -> dict[str, Path]
# 内部：cache_manager.ensure_xml(work_id) → subprocess [sys.executable,"-m","pycbeta","-i",xml,"-f",fmt,"--page",opts.page,"-o",out_dir]
```

## 6. 实施清单

- [ ] `xml2pdf` 会话：新建 `pycbeta/gui/` 可复用面板/对话框 + 独立入口
- [ ] `publish` 会话：`collection_model` 新增 `work_sources/xml_options`、`config` 新增 `default_source/xml2pdf`、`xml2pdf_bridge.py`、`main_window` 中栏来源列+右栏嵌入面板、`[合成]` 按 `work_sources` 分流

## 7. 备注

- 三藏/朝代等目录过滤与本链路无关，沿用“启动时内存生成”策略。
- X 续藏按 `bulei.txt` 同名归并，已纳入三藏映射。
