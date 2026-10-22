# 上游改造提案：TLS 默认校验与分块流式下载

> 提交对象：`cbeta-org/cbeta-fetch`
> 基线版本：`0.1.2`，commit `634b14bb31f1d721aa9bf6521c373b9effc4bc31`，`sha256=c6c779289aba9dc49d6fed581ea2eade2be9fcf5396807f0066ce37a2c71fcaf`
> 提出方：CBETA publish 管理器（下游 vendor 使用方）
> 状态：已实施（cbeta-fetch 0.2.0 / commit `817d207`；已同步 xml2pdf 与 publish）
> 关联：publish `TODO.md` P28 第四批；xml2pdf `pycbeta/_vendor/cbeta_fetch.py` 与 publish `cbeta_publish/_vendor/cbeta_fetch.py` 同源
> 修订：2026-10-21 第 2 版——TLS 改为按主机预选（取消 unverified 回退）；流式补 `Content-Length` 完整性校验；解压原子性/同名策略延后到第二批。

## 0. 一句话

把全局 `ssl._create_unverified_context()` 改为**按主机预选上下文**：默认严格校验，仅对 `cbdata.dila.edu.tw` 放宽 OpenSSL 附加严格检查（缺 Subject Key Identifier），证书链与主机名照常校验；把 `r.read()` 整包入内存改为**分块写入 `.part` 临时文件 + `Content-Length` 完整性校验**，成功后再原子替换。解压原子性与同名策略本批不做。

## 1. 背景与问题

`cbeta-fetch` 同时服务两个下游：

- xml2pdf：`pycbeta/_vendor/cbeta_fetch.py`
- publish：`cbeta_publish/_vendor/cbeta_fetch.py`

当前 0.1.2 的下载层有三个问题：

1. **全局跳过 TLS 校验**
   - `_ctx()` 无条件返回 `ssl._create_unverified_context()`（`cbeta_fetch.py:136-141`）。
   - `download`、`fetch_if_changed`、`probe_info` 都使用它（`:160`、`:215`、`:253`）。
   - 结果：不仅 cbdata，连 `raw.githubusercontent.com` 等所有下载都失去证书校验，存在中间人风险。
2. **整包读入内存**
   - `download` 和 `fetch_if_changed` 都执行 `data = r.read()`（`:165`、`:225`）。
   - 大 PDF/EPUB（几十到上百 MB）会瞬间占用等量内存；并发下载时更明显。
   - 已有的 `.part{pid}` → `os.replace` 原子替换（`:171`、`:229`）只解决了落盘原子性，没有解决内存与中断清理。
3. **解压路径的边界**
   - `download(unzip=True)` 先 `_unzip_bytes(data, dest)`（`:181-189`），仍是整包入内存。
   - `_extract` 按 `basename` 平展写入（`:192-200`）；同名条目后者覆盖前者，不报错。
   - 解压中途失败会留下部分文件；`.part` 也没有统一清理。

## 2. 目标与非目标

### 目标

- 所有主机默认校验证书；仅 cbdata 主机放宽严格附加检查，**证书链与主机名校验保持开启**，不使用 unverified。
- 下载与条件下载改为分块流式写入 `.part`，峰值内存与文件大小无关；以 `Content-Length` 校验完整性，成功后再原子替换。
- 失败、超时、取消时清理本次的 `.part`。
- `unzip=True` 不再把 zip 整包放内存（临时 zip 落盘后平展解压）。
- 公共 API 签名与返回值保持不变，下游无需改业务代码。

### 非目标

- 不改 `catalog_lookup`、`is_work_id`、`parse_work_id`、`REMOTE_URLS` 等非下载逻辑。
- 不新增下载进度回调（如需，另开可选参数，保持向后兼容）。
- 不做全局代理/企业 CA 配置；沿用 Python/系统默认信任库。
- 不在本次改造中更换 cbdata 证书或联系证书签发方。
- 本批不做解压原子化与同名策略（见 §6，延后到第二批）。
- 不引入环境变量或开关来切换 TLS 行为。

## 3. 现状代码（0.1.2 基线）

| 位置 | 现有行为 | 问题 |
|---|---|---|
| `cbeta_fetch.py:136-141` | `_ctx()` 全局 unverified | 所有主机都不校验证书 |
| `:152-178` | `download` 整包 `r.read()` → `.part{pid}` → `os.replace` | 大文件内存高；同进程多线程 `.part` 撞名 |
| `:181-189` | `_unzip_bytes` 内存解压 | zip 整包入内存 |
| `:192-200` | `_extract` 按 basename 平展写 | 同名覆盖；失败留半成品 |
| `:210-241` | `fetch_if_changed` 整包 `r.read()` → `.part{pid}` | 同 `download` |
| `:244-272` | `probe_info` HEAD，使用 `_ctx()` | HEAD 也不校验证书 |
| `:275-281` | `probe` 包装 `probe_info` | 继承同上 |

## 4. 方案一：按主机预选 TLS 上下文

### 4.1 主机分类

当前 URL 只有两类主机：

- `cbdata.dila.edu.tw`：官方电子书（pdf/docx/epub/html/odt/txt_notes）与 scope-selector JSON。
- `raw.githubusercontent.com`：CBETA XML、gaiji、sanskrit、补充字体、部分目录元数据。

把 cbdata 主机做成模块级常量，便于审计：

```python
CB_DATA_HOSTS = {"cbdata.dila.edu.tw"}
```

### 4.2 上下文选择

把 `_ctx()` 改为按 URL 预选，**不做异常驱动的回退**：

```python
def _context_for(url):
    ctx = ssl.create_default_context()
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if host in CB_DATA_HOSTS and strict:
        ctx.verify_flags &= ~strict
    return ctx
```

要点：

1. cbdata 只清 `VERIFY_X509_STRICT` 这一个附加检查位；`verify_mode=CERT_REQUIRED`、`check_hostname=True` 保持开启（本机实测 `verify_mode=2`、`check_hostname=True`）。
2. `VERIFY_X509_STRICT` 是 Python 3.13 新增常量；用 `getattr` 取 0，可让 Python 3.12 及以下原样使用默认上下文而不抛 `AttributeError`。
3. `download`、`fetch_if_changed`、`probe_info` 三处统一调用 `_context_for(url)`；删除 `ssl._create_unverified_context()`，并新增 `import urllib.parse`（现文件只显式 import 了 `urllib.request`/`urllib.error`）。
4. 上下文可按主机模块级缓存，也可每次现建；一次下载只建一次，开销可忽略，二选一即可。
5. 不写成“先严格、证书失败再放宽重试”：cbdata 始终用放宽上下文，其余主机始终严格。这样不会把证书过期、根不受信等真实问题误当成“可放宽”。

### 4.3 行为矩阵

| 主机 | 证书链 + 主机名 | 严格附加检查 | 校验失败 |
|---|---|---|---|
| `cbdata.dila.edu.tw` | 校验 | 放宽（缺 SKI 可通过） | 返回失败，不降级 |
| `raw.githubusercontent.com` | 校验 | 开启 | 返回失败 |
| 其它 | 校验 | 开启 | 返回失败 |

### 4.4 兼容与风险

- `_ctx()` 是私有函数，改为 `_context_for(url)`；`download`、`fetch_if_changed`、`probe_info` 的公共签名不变。
- 剩余风险：cbdata 若使用“受信 CA 签发但缺 SKI 之类”的证书仍会通过；但证书链与主机名都校验，自签名/不受信证书仍失败，攻击面远小于 unverified。
- 本机实测（Python 3.14 / OpenSSL 3.0.18）：默认上下文带 strict 位，cbdata 报 `Missing Subject Key Identifier` 失败；清掉该位后 200；`raw.githubusercontent.com` 在严格下 200。
- 移除条件：cbdata 证书补上 Subject Key Identifier 后，删除 cbdata 分支，并对 cbdata 跑一次严格验证回归。
- 跟随重定向时沿用同一上下文；若 cbdata 将来 302 到其它受信主机，仍是“链 + 主机名”校验。
- 不引入 `CBETA_FETCH_TLS` 之类环境变量：本批保持单一行为，避免多档位漏测；确需排查再加显式开关。

## 5. 方案二：分块流式下载

### 5.1 `download`

保持签名：

```python
download(url, dest, *, timeout=90, retries=2, unzip=False, headers=None) -> bool
```

实现要点：

1. `urlopen` 后不要 `r.read()`，改为分块写入临时文件：

   ```python
   with open(tmp, "wb") as f:
       shutil.copyfileobj(r, f, length=1024 * 1024)
   ```

2. **必须做完整性校验**：响应带 `Content-Length` 时，比较实际写入字节数与声明值，不一致即视为失败（删除 `tmp`、按 `retries` 重试）。
   - 原因：`shutil.copyfileobj` 遇到短响应**不会抛异常**（实测声明 100 字节、实发 10 字节后断开，写入 10 字节即正常结束）；现状 `r.read()` 会抛 `IncompleteRead`。不补这条，等于把现有的截断保护换掉。
3. `Content-Length` 缺失（chunked/无长度）时放行；这是兜底路径，无法校验。实测两个在用主机都带该头（cbdata 979708 字节、`raw.githubusercontent.com` 191099 字节），主路径有保护。
4. `unzip=False`：`tmp` 是 `dest` 同目录的 `.part` 文件，校验通过后 `os.replace(tmp, dest)`。
5. `unzip=True`：流式写到 `dest` 同级的临时 zip（如 `dest + ".zip.part<pid>.<rand>"`），写完调用 `unzip_flat`，`finally` 删除临时 zip；**不要** `os.replace(tmp, dest)`（`dest` 是目录）。
6. 失败清理本次 `tmp`；网络错误、长度不符按 `retries` 重试；解压错误属确定性失败，直接返回 `False`，不重试。
7. 不把响应内容放进 `bytes`。

### 5.2 `fetch_if_changed`

保持签名与返回值：

```python
fetch_if_changed(url, dest, *, etag=None, last_modified=None,
                 timeout=90, retries=1) -> (status, etag, last_modified)
```

- 304 / 未修改路径不变（`urlopen` 阶段抛 `HTTPError`，body 不会被读取）。
- 200 时同样分块写入 `.part`，并做与 `download` 相同的 `Content-Length` 校验；不符则清理并重试（现有 `retries=1`）。
- 校验通过才 `os.replace`，失败时旧 `dest` 保持不变。
- 失败时清理 `.part`，返回 `("failed", None, None)`。

### 5.3 `.part` 命名与清理

现状 `dest + f".part{os.getpid()}"` 在同进程多线程/多任务下载同一目标时会撞名。建议：

```python
tmp = f"{dest}.part{os.getpid()}.{uuid.uuid4().hex[:8]}"
```

- 每次请求唯一，避免并发覆盖。
- `try/finally` 保证失败清理；成功 `os.replace` 后原临时名自然消失。
- 不做“启动时扫描并删除所有 `.part*`”的全局清理（可能误删另一个正在写的进程）；如需，按修改时间加阈值，另开功能。

### 5.4 解压路径

- `unzip=True` 时先把响应流式写成临时 zip，再调用 `unzip_flat`；不要再用 `_unzip_bytes(data, ...)`。
- 临时 zip 放 `dest` 同级（同盘、删除简单），`finally` 删除；不放系统临时目录，避免跨盘与清理遗漏。
- 解压失败（`BadZipFile`/`OSError`）属确定性失败，直接返回 `False`，不按网络错误重试。
- 保留 `_unzip_bytes` 作为内部兼容函数或删除；公共 `unzip_flat` 本批不改。
- zipfile 需要可 seek 的文件对象，因此“流式下载 + 临时文件 + 解压”是正确组合，不能直接对非 seek 的响应对象解压。

### 5.5 行为与兼容

| 场景 | 现状 | 改造后 |
|---|---|---|
| 大文件下载 | 整包入内存 | 1 MiB 分块，峰值内存有界 |
| 下载失败 | 可能留 `.part{pid}` | 清理本次 `.part` |
| 同进程并发同一目标 | `.part` 撞名 | 每次唯一 `.part` |
| `unzip=True` | 整包入内存再解压 | 临时 zip 文件 + 平展解压 |
| 响应被截断 | `r.read()` 抛 `IncompleteRead` → 重试 | `Content-Length` 比对发现 → 清理并重试 |
| 无 `Content-Length` | 整包读，无法校验 | 放行（无法校验），文档写明 |
| API | `download`/`fetch_if_changed` | 不变 |

## 6. 方案三（第二批，本批不做）：解压原子性与同名冲突

本批只做 TLS 与流式下载，先把风险最小的部分落地；解压原子性与同名策略影响面独立，待流式稳定后单独立项。以下为第二批的设计草稿。

### 6.1 同名条目

`_extract` 目前按 `basename` 平展；zip 内 `a/x.pdf` 与 `b/x.pdf` 会写到同一个 `x.pdf`，后者静默覆盖前者。

建议：

- 解压前扫描 `namelist()`，按 `basename` 检测重复。
- 发现重复时：
  - 方案 A（推荐，数据正确优先）：整个 `download` 返回 `False`，日志列出冲突名；不写入半成品。
  - 方案 B（兼容优先）：保留最后一个，记 warning；需要下游显式接受覆盖语义。
- 需要上游确认选 A 还是 B；下游 publish 目前更希望 A（避免混书）。

### 6.2 原子解压

建议：

1. 在 `dest` 同文件系统下建临时目录 `dest/.extract-<pid>-<uuid>/`。
2. 逐条目写入临时目录（仍按 basename 平展）。
3. 全部成功后，把临时目录中的文件逐个 `os.replace` 到 `dest`。
4. 任一步失败：删除临时目录，返回 `False`。解压阶段不留半成品；替换阶段是逐个 `os.replace`，若中途失败或进程被杀，已替换的文件会留在 `dest`，属 best-effort，不承诺整体原子。
5. 同名冲突检测在写入前完成，避免写到一半才失败。

`unzip_flat(zip_path, dest_dir)` 的签名保持不变，内部改为上述流程。

## 7. API 兼容与下游影响

保持以下公共接口不变：

- `download(url, dest, *, timeout, retries, unzip, headers) -> bool`
- `fetch_if_changed(url, dest, *, etag, last_modified, timeout, retries) -> (status, etag, last_modified)`
- `probe_info(url, *, etag, last_modified, timeout) -> dict`
- `probe(url, *, etag, last_modified, timeout) -> (status, etag, last_modified)`
- `unzip_flat(zip_path, dest_dir) -> None`

下游影响：

- publish：`official_ebook_source` 用 `cbeta_fetch.download`；`remote_manager` 用 `probe_info`/`fetch_if_changed`；签名不变即可。
- xml2pdf：`pycbeta/fetch.py` 委托共享层；签名不变即可。
- 若新增可选参数（如 `chunk_size`、`progress`），必须带默认值，且放在关键字参数区。

## 8. 测试

在 cbeta-fetch 现有测试（0.1.2 实际 15 项；本文档早前写 13 项，已更正）基础上增加：

### TLS

- cbdata 上下文：`verify_mode == CERT_REQUIRED`、`check_hostname is True`、`verify_flags` 不含 `VERIFY_X509_STRICT`（即不是 unverified）。
- 其它主机上下文与 `ssl.create_default_context()` 一致（Python 支持时含 strict 位）。
- 模拟没有 `VERIFY_X509_STRICT` 常量的环境，确认构造上下文不抛 `AttributeError`（`getattr` 兼容路径）。
- `probe_info` 的 HEAD 也走 `_context_for`。
- 证书真失败（不受信/过期）时返回失败，不降级、不回退 unverified。

### 流式

- 用假响应对象断言按块读取（`read(n)`），不调用无参 `read()`。
- `Content-Length` 与实际字节不一致：`download` 与 `fetch_if_changed` 各一条，断言失败、无 `.part` 残留、旧 `dest` 未被覆盖。
- 无 `Content-Length` 的响应：成功落盘（兜底路径）。
- 大文件（可用 `file://` 夹具或伪造流）下载时，峰值内存不随文件大小线性增长（`tracemalloc` 或粗略断言）。
- 失败/超时后 `.part` 不存在；旧 `dest` 保持原内容。
- 同进程两次下载同一目标使用不同 `.part` 名。
- `unzip=True` 成功后临时 zip 已删除。

### 解压（第二批）

- 正常 zip 平展解压；文件名大小写、目录层级与现状一致。
- 同名 basename：按选定策略返回 False 或 warning。
- 坏 zip：返回 False，临时目录/临时 zip 清理干净。
- 解压中途失败：解压阶段不留半成品；替换阶段已替换的文件会留在 `dest`（best-effort）。

### 回归

- `fetch_if_changed` 304 路径不读 body、不写 `.part`。
- `probe_info` 的 304/失败/Content-Length 行为不变。
- `catalog_lookup`、`is_work_id`、`parse_work_id`、`REMOTE_URLS` 不受影响。

## 9. 版本、提交与同步

1. 版本号建议 `0.2.0`（行为有变化、API 兼容）；`USER_AGENT` 同步从 `cbeta-fetch/0.1` 改为 `cbeta-fetch/0.2`。
2. 在 cbeta-fetch 提交后，运行其 `tools/sync_into.py` 分别同步到：
   - xml2pdf：`pycbeta/_vendor/`
   - publish：`cbeta_publish/_vendor/`
3. 两处 `SOURCE.txt` 更新 `repo`/`commit`/`version`/`sha256`。
4. 两边分别运行 `test_vendor_sync`（xml2pdf、publish 各有一套）。
5. publish 再跑全量测试（当前 861 项基线）。
6. **不要手改下游 vendor 文件**；所有改动只进 cbeta-fetch，再由同步工具落盘。

## 10. 验收与回滚

### 验收

- cbdata 的 pdf/docx/epub/html/odt/txt_notes 全部能下载；scope-selector JSON 正常。
- `raw.githubusercontent.com` 的 XML/gaiji/字体/元数据正常，且 TLS 校验未被绕过。
- 100 MB 级文件下载峰值内存明显低于文件大小（约 1 MiB 缓冲 + 解释器开销）。
- 失败/超时/.part 清理符合预期；本地假服务器返回“声明长度大于实发”时下载被拒绝，不落正式文件。
- cbdata 在 Python 3.13+ 下载成功，同时上下文为 `CERT_REQUIRED` + `check_hostname=True`；代码中不再出现 `ssl._create_unverified_context()`。

### 回滚

- 回退 cbeta-fetch 的提交，按旧 commit/sha 重新同步两个下游的 `_vendor` 与 `SOURCE.txt`。
- 下游业务代码无需改动；回滚只涉及 vendor 与同步记录。

## 11. 决策记录

1. 采用“cbdata 只放宽 `VERIFY_X509_STRICT`、证书链与主机名照常校验”，不再使用 unverified 上下文。
2. 已在 Python 3.14 / OpenSSL 3.0.18 复现：cbdata 默认失败于 Missing Subject Key Identifier，清 strict 位后 200；GitHub 严格 200。
3. 版本号采用 `0.2.0`。
4. 本批不加下载进度回调（公共签名不变）。
5. 本批只做 TLS + 流式；解压原子性与同名策略放到第二批。
6. 同名策略第二批再定；本版保持旧行为（后者覆盖）。

## 12. 实施清单

- [x] `_context_for(url)` + `CB_DATA_HOSTS`（cbdata 清 `VERIFY_X509_STRICT`，`getattr` 兼容，无异常回退）
- [x] `download` 分块写 `.part` + `Content-Length` 校验 + 失败清理；`unzip=True` 走临时 zip
- [x] `fetch_if_changed` 分块写 `.part` + 同校验；304/失败路径不变
- [x] `probe_info` 使用同一套 TLS 上下文；新增 `probe_status` 供 404/410 快判
- [x] `.part` 命名加随机后缀
- [x] 新增 TLS/流式/截断/`.part` 测试（解压原子性测试随第二批）
- [x] 版本号、`USER_AGENT`、`SOURCE.txt` 更新
- [x] 同步 xml2pdf 与 publish，跑两边 `test_vendor_sync` 与 publish 全量测试
- [ ] 第二批：解压原子化 + 同名策略（待上游确认后另起）

## 13. 实施结果（2026-10-21）

- 上游 `cbeta-fetch` 本地 commit `817d207`，版本 `0.2.0`；`API.md`、`CHANGELOG.md`、`README.md`、`pyproject.toml` 已更新。
- 代码：默认严格校验；cbdata 仅清 `VERIFY_X509_STRICT`（`CERT_REQUIRED` + `check_hostname` 保持）；分块流式 + `Content-Length` 校验；`.part` 唯一名；`unzip=True` 临时 zip + `unzip_flat`；新增 `probe_status`。
- 测试：上游 23 项通过；publish 全量 861 项通过；xml2pdf `test_fetch` 51 项 + `test_update_data` 20 项 + vendor sync 3 项通过。
- 实测：cbdata `probe_status` 200（默认上下文仅因 Missing SKI 失败，清 strict 位后成功）；GitHub 严格 200。
- 同步：publish `cbeta_publish/_vendor` 与 xml2pdf `pycbeta/_vendor` 均为 `version=0.2.0`、`commit=817d207`、`sha256=353a6004984815e5afe2923fc59432ef9f7a7d8b043ad8d10bb294976fd5a2c7`。
- 下游：publish `official_ebook_source._head_absent_404` 改用 `cf.probe_status`，保留 404/410 快判。
- 未做：解压原子性/同名策略（第二批）、可选下载进度回调。上游 commit 未推送。
