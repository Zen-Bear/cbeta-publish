# 上游校验指纹与 `report.json` 提案

> 状态：**提案，未实现**。
> 适用：`xml2pdf`（`pycbeta`）校验链，以及 publish 的校验复用数据库。
> 顺序：**上游先实现**；publish 的复用实现等待上游落地后再做。
> 相关：publish `docs/链路B-设计契约.md`。

## 1 背景与目标

publish 需要在运行 `--verify` 之前廉价判断：

> 某部书、某格式的上一次“校验通过”结论，在当前输入和当前校验实现下是否仍然有效。

目标是跳过重复校验，但不能把“环境失败”当成“校验结论”，也不能因为
输入变化而沿用旧结论。

为此，上游只需要提供两样能力：

1. **可调用的校验指纹函数**；
2. **校验目录旁的机读结论文件 `report.json`**。

`report.txt` 的现有文本格式保持兼容不变。

## 2 结论枚举

上游与 publish 统一使用以下结论：

- `pass`：真实通过。
- `fail`：真实校验失败（差异超过阈值或结构非法等）。
- `undetermined`：无法判定，例如无基线、被覆盖待定、生成档缺失等。
- `error`：环境或流程失败，例如渲染失败、CLI 异常、IO/权限/占用、报告缺失等。

关键规则：

- 只有 `pass` 可以入库和记入“通过记录”。
- 只有 `fail` 可以称为“校验未通过”。
- `undetermined` 和 `error` 既不入库，也不写入通过记录，更不能因为“没有报告”而删除一条仍然有效的旧记录。
- 环境类失败应当保留失败原因文本，便于区分占用、权限、缺文件等问题。

## 3 上游 API：`verify_fingerprint()`

建议在 `pycbeta/verify.py` 增加公开纯函数，例如：

```python
def verify_fingerprint(
    work_id: str,
    fmt: str,
    *,
    xml_files=None,
    config_path=None,
    max_diff: int = 10,
    diff_lines: int = 5,
) -> str | None:
    ...
```

### 3.1 调用时机

publish 在决定是否调用 `--verify` 之前调用它：

- 返回指纹：publish 与库中记录比较；
- 返回 `None`：表示当前无法计算有效指纹，publish 保守处理为“必须重验”。

因此函数必须：

- 廉价；
- 无副作用；
- 不下载、不渲染、不联网、不写文件；
- 对相同输入返回完全相同的值。

### 3.2 指纹粒度

建议按 **`(work, fmt)`** 计算，而不是整部书一个指纹。

原因：

- 各格式的基线链不同；
- `pdf` 可能由 `docx` 或 `html` 覆盖；
- 只校验 `pdf` 与校验 `pdf+docx` 的结论来源可能不同。

如果请求格式只是 `pdf`，但实际由 `docx` 覆盖，指纹中必须记录该覆盖关系。

### 3.3 必须纳入指纹的输入

1. **实际参与校验的 XML 输入**
   - 建议使用已材料化 XML 的稳定文件标识：
     - 文件名或稳定相对名；
     - `size`；
     - `mtime_ns`。
   - 不建议只用 publish 的工作目录猜测，因为上游 `-i work_id` 可能经过
     `materialize_work`，来源包括 `cbeta_ebook`、本地候选或官方下载。
   - `xml_files=None` 时，如果可以在无副作用的前提下定位输入，则定位；
     否则返回 `None`。

2. **生效配置**
   - 预设链；
   - `run.json` 主题等相关槽；
   - `verify` 段对 `output` 段的覆盖；
   - `pycbeta/config.json` 等相关默认值；
   - `config_path` 指向的临时包装配置应当解析为语义配置后再哈希，
     不要把临时绝对路径本身当作指纹输入。

3. **校验实现版本**
   - `pycbeta.__version__`；
   - `verify.py` 等校验相关实现的版本或源码摘要；
   - 任何影响生成正式比对档或比对规则的代码变化，都必须使旧指纹失效。

4. **实际使用的官方基线**
   - 每个格式实际选用的基线文件标识；
   - 建议用稳定名、`size`、`mtime_ns`；
   - 尚未定位或尚未下载的基线不得参与指纹，应返回 `None`。

5. **校验参数**
   - `max_diff`；
   - `diff_lines`；
   - 相关格式的基线链和覆盖关系。

### 3.4 `None` 的含义

返回 `None` 表示“不能证明结论仍然有效”，包括但不限于：

- 找不到可用 XML；
- 基线尚未定位或尚未下载；
- 配置无法解析；
- 不支持的输入或格式；
- 上游版本过旧，没有该能力。

publish 收到 `None` 时一律重验。

## 4 上游输出：`report.json`

### 4.1 位置与命名

对每个 `{id 书名}（验证）/` 目录：

- 已有 `report.txt` 保持不变；
- 新增同目录 `report.json`；
- 每次校验覆盖写入；
- 通过、失败、未判定、环境失败都要写；
- 没有计算机读结论时不得只写文本报告而不写 JSON。

### 4.2 建议结构

```json
{
  "schema": 1,
  "fingerprint_version": "verify-fp-1",
  "tool": {
    "name": "pycbeta",
    "version": "0.1"
  },
  "verify_impl": {
    "module": "pycbeta.verify",
    "digest": "sha256:...",
    "algorithm": "verify-1"
  },
  "work": "T0001",
  "requested_formats": ["pdf"],
  "thresholds": {
    "max_diff": 5,
    "diff_lines": 5
  },
  "inputs": {
    "xml_files": [
      {
        "name": "T01n0001.xml",
        "size": 3093389,
        "mtime_ns": 0
      }
    ],
    "config_digest": "sha256:...",
    "baselines": {
      "docx": [
        {
          "name": "...",
          "size": 0,
          "mtime_ns": 0
        }
      ]
    },
    "coverage": {
      "pdf": "docx"
    }
  },
  "fmts": {
    "pdf": {
      "verdict": "pass",
      "fingerprint": "verify-fp-1:sha256:...",
      "missing": 0,
      "extra": 0,
      "reason": null,
      "formal_outputs": [],
      "report": "report.txt"
    }
  },
  "created_at": "2026-10-03T00:00:00+08:00"
}
```

### 4.3 字段规则

- `verdict` 只能取 `pass`、`fail`、`undetermined`、`error`。
- `fail` 必须给出缺数/多余数或结构原因。
- `undetermined` 必须给出原因，例如：
  - `no_baseline`；
  - `covered:docx`；
  - `gen_not_found`。
- `error` 必须保留可读的失败原因，不得伪装成 `fail`。
- 被覆盖格式（如 `pdf` 由 `docx` 覆盖）应在 `coverage` 和相关条目中写明。
- 新增字段允许向后兼容；改变语义必须升级 `schema` 或 `fingerprint_version`。
- publish 忽略未知字段。

### 4.4 CLI 建议

- `--verify` 和 `--verify-only` 都写 `report.json`。
- 可选增加 `--verify-fingerprint`，用于人工调试和 CLI 批量预判。
- 不得因为新增 JSON 而改变 `report.txt` 的格式和命名。

## 5 publish 侧使用方式

上游实现后，publish 的计划行为如下：

1. 校验前调用上游 `verify_fingerprint(work, fmt)`；
2. 与全局通过记录库中的指纹比较；
3. 全部同时成立才跳过校验：
   - 记录存在且通过；
   - 指纹一致且版本一致；
   - 库中产物存在；
   - 校验复用开关打开。
4. 通过记录只在**产物成功入库之后**写入；
5. 只有真实 `fail` 才可称为“校验未通过”；
6. 环境失败不写入通过记录，也不删除有效记录；
7. 上游没有指纹能力时一律重验，并提示用户。

## 6 上游验收建议

1. 相同输入重复调用指纹完全相同。
2. 分别改变 XML、预设、主题/配置、阈值、基线、格式链、校验实现后，
   指纹发生变化。
3. XML 未材料化或基线缺失时返回 `None`，且没有下载、渲染和写文件副作用。
4. `--verify` 和 `--verify-only` 都会写入合法 `report.json`。
5. `report.txt` 与旧版本解析行为保持兼容。
6. `fail`、`undetermined`、`error` 三类在 JSON 和文本中的表达一致。
7. 新增字段不破坏旧下游解析。

## 7 排期与依赖

1. 本文档为 Phase 0 提案。
2. Phase 1 由上游实现指纹函数和 `report.json`。
3. Phase 2 等上游落地后再实施 publish 的通过记录库与跳过逻辑。
4. 在上游完成前，publish 不实现过渡指纹，不改变现有校验行为。
