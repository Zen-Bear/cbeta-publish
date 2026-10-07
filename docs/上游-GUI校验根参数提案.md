# 上游 GUI `--verify-root` 参数提案

> 状态：**已实现**（上游 GUI `--verify-root`：`_pick_verify_root`／`_apply_launch_args`；
> 校验根优先级 显式 ＞ 预设 `source.verify_root` ＞ `{输出}/验证`）。
> 适用：`xml2pdf`（`pycbeta`）GUI 独立窗（`python -m pycbeta.gui`）。
> publish 侧已收尾：`_open_xml2pdf_window` 传 `--verify-root {vdir}/验证` 钉死，与进程内 CLI 一致。
> 相关：publish `docs/链路B-设计契约.md` §9.4／§9.5；
> 上游 `docs/校验report.json说明.md` §1（校验根与 `report.json` 布局）。

## 1 背景与目标

publish 的校验链分两条：

- **进程内 CLI**（`bridge.verify_work` → `pycbeta.cli.main`）：可以显式传
  `--verify-root`，已把托管产物钉死在 `{输出}/验证/`。
- **独立窗**（菜单「运行 xml2pdf 制作书籍…」→ `python -m pycbeta.gui`，publish 预填
  `--out=<丛书校验目录>`）：**无法传 `--verify-root`**，校验根只能来自预设
  `source.verify_root` 或默认 `{--out}/验证`。

问题：若所选预设带非空 `source.verify_root`，独立窗的校验产物会**静默落到 publish
托管区之外**，下游扫不到、也无法从命令行钉死。下游只能在预设里做「清空 `verify_root`」
的对齐提示来兜底，属于绕过，非根治。

目标：给 GUI 独立窗一个与 CLI **同名同语义**的 `--verify-root`，使下游能把独立窗
产物钉进托管目录，与 `--verify` 的 CLI 行为完全一致。

## 2 现状

- CLI：`cli.py` 已定义 `--verify-root`（`vg.add_argument("--verify-root", default="", …)`），
  经 `_cli_verify_custom(args)`／`verify.resolve_verify_root` 生效；优先级
  `--verify-root` ＞ 配置 `source.verify_root` ＞ 默认 `{输出}/验证`。
- GUI：`pycbeta/gui/__main__.py` 的 argparse 只有
  `--ids-file / --out / --preset / --formats / --verify / --autostart`，
  **没有 `--verify-root`**。
- GUI 当前校验根来源：`source.verify_root`（预设，非空优先），否则
  `default_verify_root(out_dir)`（＝`{输出}/验证`）；落点见
  `_effective_verify_root()`／`_verify_dir(out_dir, wid, title, verify_root="")`。
- 报告布局：`{校验根}/{id 书名}（验证）/{fmt}/` ＋ `{id}_{书名}_校验报告.txt`
  ＋ `report.json`（JSON 统一名，2026-10-07）。

## 3 建议改动（最小）

1. `pycbeta/gui/__main__.py` argparse 增加：
   ```python
   _ap.add_argument("--verify-root", default=None,
                    help="校验根预填（为空=跟随预设 source.verify_root 或 {输出}/验证）")
   ```
2. 生效优先级与 CLI 对齐：**显式 `--verify-root` ＞ 预设 `source.verify_root` ＞
   默认 `{输出}/验证`**。即：
   - `_effective_verify_root()` 先取显式值；为空再取预设；再为空走 `default_verify_root`。
   - `_verify_dir(...)` 使用同一生效值（当前已接受 `verify_root` 形参，接线即可）。
3. 只影响校验产物落点，不改渲染输出目录（渲染仍在 `--out` 顶层）。

## 4 验收建议

- 传 `--verify-root <abs>` 时，`report.json` 与 `{id}_{书名}_校验报告.txt` 落
  `<abs>/{id 书名}（验证）/`；不传时行为与现状一致（预设/默认）。
- 显式值能覆盖预设里的 `source.verify_root`（与 CLI 同断言）。
- 单测：无参回退、预设回退、显式优先三条；不改渲染输出路径。

## 5 publish 侧影响

上游落地后，publish 的 `_open_xml2pdf_window` 增加
`--verify-root <丛书校验目录>/验证`，与进程内 CLI 路径一致；预设对齐提示可保留作兜底，
但不再是唯一手段。
