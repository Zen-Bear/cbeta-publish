# 链路 B：`engine` / `vertical` / `font_lang` 配置回退说明（供 publish 会话）

> 结论先行：**publish 侧无需改动**。`convert` 只要传
> `--config <preset>` + `--cbeta-ebook <工作根>` + `-f <fmt>` 即可**完整生效**。
> 本说明解释为什么，以及命名预设 / 临时预设两种场景都成立。

## 1. 背景（publish session 的发现，经核对属实）

当时的问题：这三项在预设 JSON 里写了没人读，必须补命令行开关。
经对照 `pycbeta/cli.py` 确认当时为真：

| 面板项 | 预设里的键 | 当时的 CLI 读取处 |
|---|---|---|
| 引擎（管线） | 顶层 `engine` | `cli.py:177` 只读 `args.engine`（`presets["engine"]` 从不读） |
| 竖排 | `output.vertical` | `cli.py:179` 只读 `args.vertical`（`output.vertical` 从不读） |
| 字库语言 | 顶层 `font_lang` | `cli.py:625` 只读 `args.font_lang`（或按 t2s 推） |

注意区分两个键（易混淆）：

| 键 | 在哪 | CLI 读不读 |
|---|---|---|
| `engines.*.chain`（引擎链/单体列表） | `pycbeta/config.json` | ✅ 一直读（`cli.py:554/616/618`） |
| 顶层 `engine`（管线选择 `docx2pdf`/`html2pdf`） | 预设 JSON（面板 `output` 外顶层键） | ❌ 当时不读 |

（当时同样：`formats` 用 `-f`，不读配置。佐证：xml2pdf 自己的 GUI 批量也是把这三项
拼成命令行开关下发，`gui/__main__.py:71/75/78` `build_render_cmd`。）

## 2. 已修复（xml2pdf 侧，`21af635`，全量 715 OK）

`pycbeta/cli.py` 新增纯函数 `resolve_engine_vertical_lang(args, presets)`，
主流程在配置文件解析后统一调用（显式开关 > 配置 > 默认）：

```python
engine = args.engine(开关) or presets["engine"] or None         # 默认 docx2pdf
vertical = args.vertical(开关) or output["vertical"]            # 逻辑或
font_lang = args.font_lang(开关) or (t2s→zh-Hans) or presets["font_lang"] or zh-Hant
```

- 三个开关（`--engine` / `--vertical` / `--font-lang`）全部保留，用于**显式覆盖**；
  help 已补「缺省取 config …」；`--html-epub-user-theme` 仍是占位。
- 测试：`test_cli.TestResolveEngineVerticalLang` 4 项（默认/取配置/开关覆盖/t2s 优先）。

## 3. 为什么 publish 无需改动

`convert` 传 `--config <任意预设>` 后，实际走的是同一条路：

```
--config <文件>
  → theme.resolve_config_arg：run.json / 基础配置 JSON 自动分流
  → resolve_effective_config：出厂 ← 该文件（深合并）
  → presets 字典里已有 engine / font_lang / output.vertical
  → resolve_engine_vertical_lang(args, presets)：开关没给就取配置
```

| 场景 | 预设来源 | 生效情况 |
|---|---|---|
| 选中已保存预设（右栏下拉） | `presets/*.json`（命名文件） | ✅ 全部生效，含 engine/vertical/font_lang |
| 对话框临时调整不保存 | `write_temp_preset(get_preset())` → 系统 temp，用后删 | ✅ 同样全部生效 |

区别只在**文件落哪**（`presets/` vs 系统 temp），不在于生不生效。

## 4. 仍需单独处理的事项（不变）

- `-f/--format`：每本显式给（`formats` 不读配置；缺失即 `ap.error`）。
- `--cbeta-ebook`：publish 显式传（配置键 `xml2pdf.cbeta_ebook`；留空=由预设/对面默认）。
- 主题槽（4 个 CSS）：**不在 base 配置**；要换 CSS 用 run.json 或显式
  `--pdf-docx-theme/--pdf-docx-user-theme`（`--html-epub-user-theme` 占位）。
- 显式覆盖：给了 `--engine` / `--vertical` / `--font-lang` 就优先于配置
  （比如临时换引擎而不改预设）。

## 5. 验收

- xml2pdf 全量 715 OK（skipped=1）。
- publish 侧建议补测（`tests/test_xml2pdf_bridge.py`，可选）：`convert` 不传这三个
  开关、只传 `--config`（预设含 `engine/font_lang/vertical`）时，argv 不含它们
  且渲染结果取预设值。
