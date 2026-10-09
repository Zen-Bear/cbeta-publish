# 上游 `verify_fingerprint` 生效配置入参提案

> 状态：**提案，待上游实现**（publish 起草，2026-10-07；下游答复见 §6）。
> 适用：`pycbeta.verify.verify_fingerprint`（可选同及 `build_report_json`）。
> 相关：`docs/上游-P2校验结论跨边复用提案.md` §9.1(2)、`docs/校验report.json说明.md` §4。

## 1 背景与问题

跨边复用要求两端对同一部书算出**逐字相同**的指纹。当前 `verify_fingerprint` 只接受
`config_path`（预设文件路径 / run.json 路径），而两端的"配置形态"不同：

- publish：传**裸预设路径**（`config_path=preset`）。
- GUI/CLI 报告：走**临时 run.json**（`config-json` → 预设 + 5 槽主题）。

`load_effective_presets(config_path)` 对两种形态的解析路径不同（裸预设只取文件本身；
run.json 走 `resolve_effective_config` 与出厂 `config.json` 深合并），而
`canonical_verify_config` 纳入 `theme_css` / `annotations` / `strip_head_no` 等，
导致同一逻辑配置的 `config_digest` 不等 → 跨边永不命中（静默，仅多一次预检）。

## 2 建议

`verify_fingerprint(..., presets: dict | None = None)`：

- `presets` 非空时**直接使用**该 effective 配置 dict（跳过 `load_effective_presets`），
  用于：canonical 摘要、`t2s/engine/vertical` 缺省、`bases` 链、基线根等；
- `presets=None` 时保持现状（由 `config_path` 解析），完全向后兼容；
- 语义：调用方负责传入"生效配置"（即 `theme.resolve_effective_config` 的输出），
  上游不再关心其文件来源形态。
- 建议 `build_report_json` 同样透传（其内部已用 `_ctx` 复用 presets；接线即可）。

publish 侧：以公开 API 取得同一 effective dict 后传入指纹调用；
**不再依赖裸/run 形态一致**（该形态差异随入参消失）。

## 3 验收

- 同一 effective 配置下：`config_path=<预设>`、`config_path=<run.json>`、
  `presets=<dict>` 三种调用指纹**逐字一致**。
- `presets=None` 行为与现状**逐字一致**（回归）。
- 单测：三种调用等价 + 缺省回归。

## 4 publish 影响

- `xml2pdf_bridge.verify_fingerprint` 增加 `presets=` 透传；跳过检查与记录写入
  改用同一 effective dict（来源：上游公开 API）。
- 与阈值统一 0（见 P2 提案 §9.1）配合后，跨边记录可直接互认。

## 5 上游复核（2026-10-07，实测）

同一 effective 配置、三种调用的 `canonical_verify_config` 摘要实测：

| 调用 | sha256 前 16 |
|---|---|
| `config_path=presets/config.user.json` | `565ca069…` |
| `config_path=run.json` | `bb924d1e…` |
| `presets=load_effective_presets(run.json)` + `config_path=None` | `bb924d1e…`（与 run 形态逐字一致） |
| `presets=load_effective_presets(preset)` + `config_path=preset` | `565ca069…`（`config_path` 仍支配三项） |

裸预设 vs run 形态差异键：`annotations / pages / pagination / pre_dedent /
show_close_juan`（裸预设走 `load_effective_presets` 直读、缺出厂 `config.json` 深合并）。

**实现要求（否则 §3 验收不成立）**：

- `presets` 给定时，`canonical_verify_config` 内三项须一并改由 presets 派生：
  `_strip_no_from`（`verify.py:1245`）、`_theme_css_digest`（`2295`）、
  `_canon_annotations`（`2267`；词表相对路径需绝对化或约定 base）。
- 明确「`config_path=<预设>` 形态」是否提升为出厂深合并口径；若不提升，
  §3 验收应改为「三形态传入同一 effective 配置」（`presets=` 为唯一基准）。
- `build_report_json` 透传 `presets=`（其 `_ctx` 已复用；`verify.py:2664` 现为
  `load_effective_presets(config_path)`）。
- 实施前先跑 §3 的三形态等价单测（作为开发中的红/绿判据）。

## 6 下游答复（publish，2026-10-07）

- **接受** §5 实现要求：`presets` 给定时，`_strip_no_from` / `_theme_css_digest` /
  `_canon_annotations` 三项一并由 presets 派生（传了 `presets` 就不再理 `config_path`）。
- `annotations` 相对路径：publish 传入前**绝对化**；上游按绝对路径处理（或约定 base）。
- **首选**：请将「`config_path=<裸预设>`」也提升为**出厂深合并**口径（与 run.json 同口径），
  或公开一个"取最终生效配置"的下游 API——publish 现有裸预设调用点即可直接收敛，
  不必自包 run 包装。
- 若首选不便：验收条件改为「三形态传入同一 effective 配置」；publish 用 run 包装取该
  dict 再传 `presets=`（多一层，可行）。
- `build_report_json` 透传 `presets=`：同意（两端保持同一 effective 配置）。
- 备注：多源口径已另定（P2 提案 §9.7：publish 采用「输入集」模型），与本节无关。

## 7 上游复核（2026-10-07，回应 §6）

- 接受 §6 全部要点；「三项派生 + annotations 绝对化」确认可行
  （`_resolve_asset_path` 已支持绝对路径，`annotate.py:311-312`）。
- **首选「裸预设提升出厂深合并」根因已定位**：分类器以「含任一 `RUN_KEYS` 键」
  判 run.json（`theme.py:248` / `resolve_config_arg:699`），而预设可带主题键——
  本机 `presets/config.user.json` 含顶层 `pdf-docx-user-theme` → 被误判、
  `config-json` 缺省出厂、预设各段被丢弃（实测）。修法：仅当含 `config-json`
  或键集合 ⊆ RUN_KEYS 才按 run.json；否则按基础配置 + 出厂深合并。
  此修复同时修好上游 CLI `--config 裸预设` 的既有 bug。
- 行为变更：裸预设调用生效配置/指纹变化 → 与阈值 0 重跑合并；全量回归 + 文档。
- 最终落地清单见 P2 提案 §9.8(3)。

## 8 下游再确认（publish，2026-10-07，回应 §7）

- 分类器修复（仅当含 `config-json` 或键集合 ⊆ RUN_KEYS 才按 run.json）确认正确，
  与下游首选口径一致；请随修复在 `第三方调用说明.md` / `安装说明.md` 注明裸预设
  `--config` 行为变化（不再丢段）。
- 其余 §7 各点无异议；最终清单见 P2 提案 §9.8(3)。
