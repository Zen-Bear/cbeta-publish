# 上游 `verify_fingerprint`／`report.json` 卷维度提案

> 状态：**已实现**（2026-10-08 上游；publish 起草，上游复核与实现清单见 §8）。
> 落地：`juan.normalize_segments` + `verify_fingerprint(juan=)`（payload 仅子集入键，
> `None` 逐字回归）+ `_official_superset` 卷限定 + `build_report_json` 顶层
> `juan{segments,label}` 恒输出 + CLI/GUI 归一传参（full/无 milestone → None）。
> 适用：`pycbeta.verify.verify_fingerprint`（可选同及 `build_report_json`＋CLI/GUI 校验流）。
> 相关：`docs/上游-P2校验结论跨边复用提案.md`（P10 已落地，指纹跨边互认）、上游 `pycbeta/juan.py`（`parse_juan_spec`／`split_id_juan` 语义基准）。

## 1 背景与问题

publish P11 将支持卷子集（`-i ID:范围` token，如 `T0349:2-3`；见 §4 用法）。
子集与整本用**同一组 XML 输入**，当前指纹对其算出**逐字相同**的值，
跨边复用会把"子集 pass"误认为"整本 pass"（或反之）——** correctness 缺口**，
比 P10 的"静默不命中"严重一档（那是多验一次，这是少验一次）。

另：子集跑完的 `report.json` 无任何卷自描述（目录名后缀 `（卷…）` 人眼可辨、
机读无字段），publish 无法机读区分，`_paired_json` 同口径亦无法区分。

## 2 现状核实（上游侧，publish 只读核对）

- `verify_fingerprint(work_id, fmt, *, xml_files, config_path, max_diff, diff_lines,
  t2s, engine, vertical, baseline_roots, baseline, presets, _ctx)`：**无 `juan`
  形参**；payload 键＝`fp_version/work/requested/coverage/xml/config_digest/
  baselines/thresholds/t2s/engine/vertical/baseline/impl`，**无卷维度**。
- `build_report_json(...)`（`verify.py:2659`）：**无 `juan` 形参**；顶层返回
  `schema/fingerprint_version/tool/verify_impl/work/requested_formats/
  thresholds/inputs/fmts/created_at`，**无卷字段**；每 fmt 指纹经 `_ctx`
  复算（`:2792`），与独立 `verify_fingerprint` 同口径（同样无卷）。
- 基线口径：report 内 `official` 超集按 `juan=None` 计算（`:2725` 注释"只增不减
  方向安全"）；而实际校验（`verify_one(juan=…)`）走卷限定基线。两者对子集的
  "比对依据"本就不同，指纹若继续无视卷，会把两种不同比对判为同一结论。
- CLI 已有：`-i ID:spec` 拆分＋`--juan` 互斥报错、`args.juan_segments`／
  `juan_label`／`juan_suffix`、报告/校验目录自动加后缀——**传参与落盘已通，
  缺的只是指纹与 report.json 机读层**。

## 3 建议

### 3.1 `verify_fingerprint(..., juan=None)`

- `juan` 为 `[(lo, hi)]`（`verify_one` 同形）或 `None`；非空时按 `parse_juan_spec`
  语义归一（排序、合并重叠/相邻；非法抛 `ValueError` 交给调用方，与 CLI 双 parse
  点行为一致），空列表视为 `None`。
- payload 新增 `"juan"`＝归一 segments（`[[lo,hi],…]`）或 `None`。
- `juan=None` 时 payload 与现状**逐字一致**（回归基准；旧记录继续有效）。
- 不同 `juan`（含 `None` vs 非空）指纹**必须互异**（归一后 `34-36,40` 与
  `40,34-36` 同值，属同一选择，值相等为正确）。

### 3.2 基线口径（与 §2 注释配套）

- `juan` 给定时，`_official_superset` 按 `find_official(..., juan=所选卷集)`
  取卷限定超集（与 `verify_one` 实际比对口径一致，fp 随"该子集基线"变化而变化）；
  `None` 时保持现状。
- 若上游倾向保持"超集 juan=None"（少验不错验的保守方向），亦可接受，
  但须两端统一（report 内与独立调用一致）——见 §6 Q2。

### 3.3 全覆盖归一（与命名行为对齐）

- 上游现有行为：选择覆盖全部卷 → `filter_work_juan` 回 `full`、不裁剪、不加后缀
  （与整本产物字节一致）。建议 CLI/GUI 在 `status == "full"` 时把往下传的
  `juan` 归一为 `None`（指纹函数本身不知全集，只能调用方做），则全覆盖子集的
  fp 与整本一致——与"字节一致、不加后缀"同一口径。见 §6 Q3。

### 3.4 `build_report_json(..., juan=None)`

- 顶层新增 `"juan": {"segments": [[lo,hi],…], "label": "34-36、40"} | None`
 （`label` 用 `format_juan_label`，与目录后缀同源；`None`＝整本）。
- 透传给每 fmt 的 `verify_fingerprint` 调用（`_ctx` 复用不变）。
- CLI/GUI 校验流把已解析的 `args.juan_segments` 传入（`None` 保持现状）。
- `schema` 保持 `1`（只增字段；publish `_read_verify_json` 未知字段忽略，
  已确认向前兼容）。

## 4 publish 侧用法（上游落地后）

- 记录 key 扩展为 `(work, fmt, juan_label)`（`""`＝整本）；跳过检查比较同 label
  指纹；`accept_tier` 不变（档位与卷正交）。
- 传参形态：`-i "ID:spec"`（与独立窗 `--ids-file` token 形态统一；`--juan`
  与 `-i` 形态二选一，publish 用前者，CLI 现已支持）。
- 入库命名：子集产物/报告后缀沿用上游 `resolve_juan_suffix`（模板键
  `output.juan_suffix_template`，publish 读生效预设，不新增配置键）。

## 5 验收

- `juan=None`：`verify_fingerprint` 与现状逐字一致；`report.json` 仅多
  `"juan": None`（或缺省，定一种），旧 publish 照读。
- 同 `(work, fmt, xml, presets, juan)` 两端（report 内 vs 独立调用）指纹一致。
- `None` vs 任一子集、不同子集之间互异；`40,34-36` vs `34-36,40` 同值。
- 子集报告 `juan.segments/label` 与本次 `--juan` 一致；`full` 归一后为 `None`。
- 单测：归一等价＋互异＋`None` 回归＋report 自描述。

## 6 上游待确认

- **Q1**：payload `juan` 表示偏好（`[[lo,hi]]` vs 归一串 `"34-36,40"`）？
- **Q2**：§3.2 基线口径二选一（卷限定 vs 保持超集），以哪个为准？
- **Q3**：全覆盖→`None` 归一放在 CLI/GUI 调用方（建议，§3.3），上游是否接受？
  若不接受，`full` 子集 fp 与整本互异（每次多验，可接受但须写明）。
- **Q4**：长编号册号（`vol`，如 `T25n1509` 的 `25`）是否需要进 payload？
  publish 理解：`vol` 只影响 XML 集合（已体现在 `xml` file identity 中），
  无需单独字段，请确认。
- **Q5**：`_NNN` 形态（`T0001_001`）在指纹/report 层是否一律视为 `:N`
  归一（CLI `-i` 已拆，report `work` 字段是否保持短 id）？publish 将统一存
  `:N` 形，`work` 保持短 id 可使 `_verify_stem_matches`  head 比对成立。

## 7 publish 绕行（上游落地前，P11 内置，不等上游）

- 记录按 `(work, fmt, juan_label)` 隔离；`juan_label` 非空的项**跳过复用、
  恒做真实校验**（多验不错验）；整本复用路径不变。
- 上游本提案落地＋联调通过后，publish 放开子集复用（即本提案 §4）。

## 8 上游复核（2026-10-08）

> 结论：**核心采纳**（correctness 缺口属实）；Q1–Q5 答复见 §8.2；
> 实现清单 §8.3。上游副本与 publish `docs/上游-指纹juan入参提案.md` 同文。

### 8.1 对代码复核

- 缺口属实：`_verify_fingerprint_inner` payload（`verify.py:2570-2585`）无卷维度；
  子集与整本同 XML 文件、同超集基线、同生效配置 → 指纹**逐字相同**。P10 输入集
  记录按 `(work, fmt)` 存，确会互串（子集 pass 被当整本 pass）。
- 行号校正：report 超集调用实为 `verify.py:2732`（提案写 `:2725`，其余
  `build_report_json:2659`、每 fmt 复算 `:2792` 正确）。
- 落点：CLI 报告写入 `cli.py:1499`；GUI `gui/__main__.py:435`；
  GUI `_juan_plan` `:609`。

### 8.2 Q1–Q5 答复

- **Q1**：用 `[[lo,hi],…]`（归一整数对；`None`＝整本）。`label` 只进 report
  顶层，不进指纹 payload（可派生，避免双源）。
- **Q2**：**卷限定**（§3.2 前案）。`find_official` 卷过滤"过滤后为空回退不过滤"
  天然保守；卷限定与实际比对依据一致、更精确（无关卷基线变动不误伤子集复用）。
  即便选超集也不会错复用（payload 已有 juan 区分），故若实现成本敏感超集亦可
  接受；按卷限定实施。
- **Q3**：**接受**调用方归一（`full`→`None`）。补充两处必须一并改（GUI 侧）：
  - `_juan_plan` 现在 `full` 返回 `(segs, "")`（`gui/__main__.py:620-621`）→
    须改返回 `(None, "")`，否则 GUI 子集指纹永远 ≠ 整本；
  - `not all_juans`（无 milestone）也须 `(None, "")`——当前会加后缀，与 CLI
    "无卷 milestone → 警告忽略、不加后缀"不一致，属既有小 bug，随本项一并修。
- **Q4**：**确认不需要** vol 字段。vol 只决定取哪个 XML 文件，已体现在 `xml`
  文件身份（name+sha256）；跨册重复编号（`G114n2302` vs `G118n2302`）文件名不同
  → 身份不同。
- **Q5**：**确认**。`_NNN` 在 `split_id_juan` 已归一为 `:N`；report `work` 恒短 id
  （`w.id` 来自 `get_work_id_from_basename`），`_verify_stem_matches` head 比对成立。
- **附**：report 顶层**恒输出** `"juan": None`（稳定 schema、自描述；不采用
  "缺省省略"）。

### 8.3 实现清单（上游）

1. `verify_fingerprint(..., juan=None)`：归一（排序、合并重叠/相邻；非法输入经
   现有 try/except **返回 None**——公开契约"绝不抛异常"，且 CLI/GUI 入口已各自
   parse 报错，无需二次抛）→ payload 增 `"juan"`。
2. `_official_superset(source, stem, roots_cfg, juan=None)`：
   `find_official(..., juan=所选卷集)`（仅 html/docx/txt_notes；epub/odt 照旧）。
3. `build_report_json(..., juan=None)`：顶层
   `"juan": {"segments": [[lo,hi],…], "label": "34-36、40"} | None`
   （label 用 `format_juan_label`）；透传每 fmt 指纹（`_ctx` 复用不变）。
4. CLI 校验流：`_juan_status == "filtered"` 时传 `args.juan_segments`，否则 None
   （`cli.py:1499` 的 `_v_json` 调用）。
5. GUI：`_juan_plan` full/无 milestone → `(None, "")`；`_v_json`（`:435`）传
   归一 juan。
6. 文档：`校验report.json说明.md` §3（顶层 `juan`）+ §4（`verify_fingerprint(juan=)`）；
   `校验说明书.md` §4.4 一句（指纹/报告含卷维度）。
7. 测试：`juan=None` 逐字回归；归一等价（`40,34-36` ≡ `34-36,40`）；
   None/子集/不同子集互异；full 归一后与整本一致；report 自描述；
   卷限定基线发现。
8. 兼容：`schema` 保持 1（只增字段）；旧记录（无 juan 键）在 `juan=None` 路径
   逐字有效。

### 8.4 优先级

**中**：P2 的 correctness 补丁（少验一次 > 多验一次）；publish 已有 §7
"子集恒验"绕行，不阻塞。上游改动集中、`None` 路径零行为变化。
