# 上游修复需求：WPS COM 僵尸实例导致批量校验第二部必崩

> 发给 xml2pdf 仓。publish 侧已定位、无需改动；基线子目录问题上游已修（`resolve_verify_ebook`），本文只谈 WPS COM 崩溃。

## 一、现象

- publish「自制/重制（校验）」批量跑丛书：第一部通过，第二部转 PDF 时**进程直接退出**，控制台留一句：
  `QObject: shared QObject was deleted directly. The program is malformed and may crash.`
- 同一部书（如 T1859 肇论疏）、同一预设（A5 页面加框），在 xml2pdf 独立跑**完美通过**。
- 「第二部」是稳定复现点：单跑过、批量第二部死。

## 二、复现步骤（publish 侧）

1. 来源切自制、设置「制作书籍」=校验；
2. 点「重制」，跑完（第二部验证失败或通过均可）；
3. 再点一次「重制」，跑到第二部的 PDF 转换时进程退出。

## 三、关键证据（faulthandler 落盘，非推测）

进程内 `VerifyWorker` 线程连续抛出 Windows fatal exception，错误码交替为：

- `0x800706BE` = `RPC_S_CALL_FAILED`
- `0x800706BA` = `RPC_S_SERVER_UNAVAILABLE`

崩溃栈每次都停在同一位置（`pycbeta/render_pdf.py`）：

```
render_pdf.py:153 _com_convert
render_pdf.py:206 _pdf_via_wps
render_pdf.py:344 docx_to_pdf
cli.py:259 render_one
cli.py:373 process_file
cli.py:767 main
```

主线程全程阻塞在校验进度循环，无辜。最后 `Fatal Python error: Aborted`；
`shared QObject…` / `QThreadStorage destroyed…` 是 abort 时线程撕裂的次生噪音，不是死因。

## 四、根因

`_com_convert`（`render_pdf.py:63`）每次现查 `GetActiveObject`、现建 `DispatchEx`，
**命中已有实例后从不验活**（`render_pdf.py:91-97`，`running=True` 即直接附着）：

1. 第一部转完走 `owned → _com_quit → Quit(0)`，WPS 进程异步死亡，但 ROT 条目 lingering；
2. 第二部 `get_active("KWPS.Application")` 捡到**僵尸实例**，附着成功，后续每个 COM 调用全是 RPC 失败；
3. 其中部分失败以 pywin32 翻译不了的 SEH 形态逃逸出 `except Exception`（第 155 行接不住），
   十几次后进程 abort。单跑无前例所以必过——与文档内容无关。

另：全仓无 `CoInitialize`/`com_error` 处理（已 grep 确认），工作线程裸调 Office COM（STA 服务器），
封送全凭运气，这是同类故障的温床。

## 五、修复方案（最小修复，两处 + 回归测试）

**U1 — COM 公寓纪律**（`_com_convert` 入口）：

```python
import pythoncom, threading
_COM_LOCK = threading.Lock()

# _com_convert 开头：
pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
with _COM_LOCK:
    ...  # 原函数体
# finally 配对 CoUninitialize（注意 CoInitializeEx 嵌套计数，引用现有 helper 或按返回值配对）
```

**U2 — 僵尸实例判定**（`get_active` 命中后，`render_pdf.py:91-97`）：

```python
try:
    app_probe = get_active(progid)
    app_probe.Documents.Count  # 活性探针：廉价属性，僵尸必抛（含 RPC 错误）
    running = True
except Exception:
    running = False
```

另建议：`DispatchEx` 新实例若报 RPC 死亡码（0x800706BE/BA），记入进程级 `_DEAD_PROGIDS`，
本进程后续 work 直接跳过该 ProgID，不再鞭尸（现在每部书都会重复踩一次）。

**U3 — 回归测试**（函数已支持 `dispatch/dispatch_ex/get_active` 注入，零侵入）：

- 注入"附着即抛 RPC 死"的假 COM → 断言转用新实例且转换成功；
- 注入"COM 全灭" → 断言返回 `None`（记失败、走引擎链 fallback），而不是把异常抛回 CLI。

`docx_to_pdf` 的 word→wps→libreoffice 链式 fallback 本体不动。

## 六、验证

1. 上游单测全过（含新增 U3 用例）；
2. publish 侧用原丛书连跑两次「重制」（开诊断开关，确认无 RPC fatal、无 abort）。

## 七、publish 侧状态（供上游知悉，不用改）

- 基线"下到旧根找不到"问题：上游 `resolve_verify_ebook`（`cli.py:342`）已修 split-brain，
  publish 传显式 `--cbeta-ebook` 即落在发现目录一侧，publish 不用改。
- publish 已做进程侧加固（worker 异常必发 `finished_all`、线程 `deleteLater`），本次 abort 是引擎层 SEH，
  进程侧接不住，必须在引擎层修。
