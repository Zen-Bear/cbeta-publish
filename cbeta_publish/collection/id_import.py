# -*- coding: utf-8 -*-
"""批量 ID 导入：把粘贴/文件/网页文本解析为规范 work id 行（纯逻辑，无 Qt）。

供 P9「导入ID…」对话框与 P11 卷子集共用：
- `split_token` / `normalize_token`：token → 规范 work id（basename、`_NNN`、`:范围` 归位）；
- `parse_id_lines`：文本 → [(原始 token, 注释)]；
- `classify`：结合 catalog 命中 → 有效/未收录/无效/重复；
- `html_to_text` / `fetch_text`：网页抓取转文本。

卷范围（`:` 后缀 / `_NNN`）本阶段只剥离取 work id；P11 用原始 token 重新解析卷维度
（上游 `pycbeta.juan.split_id_juan` 同义，见 `docs/上游-指纹juan入参提案.md`）。
"""
import html as _html
import re
import urllib.request
from dataclasses import dataclass

from cbeta_publish.catalog.work_id import canonical_work, is_work_id

__all__ = ["IdRow", "STATUS_OK", "STATUS_UNKNOWN", "STATUS_INVALID",
           "STATUS_DUP", "split_token", "normalize_token", "parse_id_lines",
           "classify", "html_to_text", "fetch_text", "juan_token", "token_juan"]

STATUS_OK = "有效"
STATUS_UNKNOWN = "未收录"
STATUS_INVALID = "无效"
STATUS_DUP = "重复"

#: 文件名形态 `T01n0001` / `T05n0220_001`（canon + 册号 + n + 编号[+卷后缀]）
_BASENAME_RE = re.compile(
    r"^([A-Za-z]{1,2})\d{2,3}[nN]([0-9]{3,6}[A-Za-z]?)(?:_\d{1,3})?$")
#: `_NNN` 卷后缀（split_token 未命中时兜底剥离）
_JUAN_SUFFIX_RE = re.compile(r"_\d{1,3}$")
#: 注释首分隔符（剥去）
_NOTE_LEAD = "-—–~～、:：|｜>》 \t"


@dataclass
class IdRow:
    """一行导入记录：原始 token / 规范 work id / 注释 / 状态 / 卷范围 /（可选）目录书名。"""
    raw: str
    work_id: str
    note: str = ""
    status: str = STATUS_OK
    juan: str = ""
    title: str = ""


def split_token(text):
    """token → (head, 卷范围 spec | None)。

    与上游 `pycbeta.juan.split_id_juan` 同义：`:`/`：` 优先于 `_NNN`；
    `T0001_001` → ("T0001", "1")；无分隔符 → (原文, None)。
    head 合法性不校验（交 `normalize_token`）。
    """
    s = (text or "").strip()
    m = re.match(r"^([^:：]+)[:：](.*)$", s)
    if m:
        spec = m.group(2).strip()
        return m.group(1).strip(), (spec or None)
    m2 = re.match(r"^(.+)_(\d{1,3})$", s)
    if m2:
        return m2.group(1), str(int(m2.group(2)))
    return s, None


def normalize_token(token):
    """token → 规范 work id；无效返回 ""。

    - 剥 `:`/`：` 卷范围与 `_NNN` 卷后缀（只取 work id）；
    - basename `T01n0001` / `T05n0220_001` → `T0001` / `T0220`；
    - 去 `.xml`；经 `canonical_work` 归一大小写；非编号形态返回 ""。
    """
    head, _spec = split_token(token)
    s = (head or "").strip()
    if not s:
        return ""
    s = re.sub(r"\.xml$", "", s, flags=re.IGNORECASE)
    m = _BASENAME_RE.match(s)
    if m:
        s = f"{m.group(1)}{m.group(2)}"
    else:
        s = _JUAN_SUFFIX_RE.sub("", s)
    if not is_work_id(s):
        return ""
    return canonical_work(s)


def _clean_note(note):
    return (note or "").strip().lstrip(_NOTE_LEAD).strip()


def juan_token(work_id, spec):
    """work id + 卷范围 → 上游 ids-file/`-i` token（多段用 `+`，避 ids-file 的
    `,`/`、` 分隔冲突）；spec 空则原样返回 work id。"""
    s = re.sub(r"[,，、]", "+", str(spec or "")).strip()
    return f"{work_id}:{s}" if (work_id and s) else str(work_id or "")


def token_juan(text):
    """token → 卷范围 spec（`:` 优先；basename `T11n0310_050`／`T11n0310_050.xml`
    的 `_NNN` 亦取，归一为整数串）；无则 ""。"""
    _head, spec = split_token(text)
    if spec:
        return spec
    s = re.sub(r"\.xml$", "", str(text or "").strip(), flags=re.IGNORECASE)
    m = re.match(r"^[A-Za-z]{1,2}\d{2,3}[nN][0-9]{3,6}[A-Za-z]?_(\d{1,3})$", s)
    return str(int(m.group(1))) if m else ""


def _split_line(line):
    """行 → (token, 注释)：优先空白分界；否则逗号/分号分界（head 无卷范围时）。"""
    m = re.match(r"^(\S+)\s+(.*)$", line)
    if m:
        return m.group(1), _clean_note(m.group(2))
    m = re.match(r"^([^,;，；\t]+)[,;，；\t](.*)$", line)
    if m and ":" not in m.group(1) and "：" not in m.group(1) and "-" not in m.group(1):
        return m.group(1).strip(), _clean_note(m.group(2))
    return line, ""


def parse_id_lines(text):
    """文本 → [(原始 token, 注释)]；跳过空行与 `#`/`//` 注释行。

    行首为 token（可含 `:范围`），其后余文为注释（剥首分隔符）。
    """
    out = []
    for raw in (text or "").lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        token, note = _split_line(line)
        if token:
            out.append((token, note))
    return out


def classify(rows, work_exists=None):
    """[(raw, note)] → [IdRow]；状态 有效/未收录/无效/重复。

    去重身份＝(work_id, 卷范围)：同一部的**不同卷**不算重复（如 T0220:1 与 T0220:2）。
    work_exists 为可调用（如 `MappingService.work_exists`）；为空时只做格式与去重，
    一律记「有效」。无效 token 的 work_id 为 ""。
    """
    out = []
    seen = set()
    for raw, note in (rows or []):
        wid = normalize_token(raw)
        juan = token_juan(raw)
        if not wid:
            out.append(IdRow(str(raw), "", str(note or ""), STATUS_INVALID, juan))
            continue
        key = (wid, juan)
        if key in seen:
            out.append(IdRow(str(raw), wid, str(note or ""), STATUS_DUP, juan))
            continue
        seen.add(key)
        status = STATUS_OK
        if callable(work_exists):
            try:
                if not work_exists(wid):
                    status = STATUS_UNKNOWN
            except Exception:
                pass
        out.append(IdRow(str(raw), wid, str(note or ""), status, juan))
    return out


def html_to_text(html):
    """HTML → 纯文本（去 script/style，块级换行，实体解码，压缩空行）。"""
    s = str(html or "")
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|table|section|article|ul|ol)\s*>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", "", s)
    s = _html.unescape(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t\f\v\u00a0\u3000]+", " ", s)
    s = "\n".join(ln.strip() for ln in s.split("\n"))
    s = re.sub(r"\n(?:[ \t]*\n)+", "\n", s)
    return s.strip()


def _guess_encoding(content_type, data):
    m = re.search(r"charset=([\w-]+)", content_type or "", re.IGNORECASE)
    if m:
        return m.group(1)
    head = data[:2048].decode("ascii", errors="ignore")
    m = re.search(r"""charset=["']?([\w-]+)""", head, re.IGNORECASE)
    if m:
        return m.group(1)
    return "utf-8"


def fetch_text(url, timeout=30, user_agent="cbeta-publish/1.0"):
    """抓取 http(s) 网页 → 文本（仅 http(s)、UA、编码猜测、超时）；失败返回 ""。"""
    u = (url or "").strip()
    if not re.match(r"^https?://", u, re.IGNORECASE):
        return ""
    req = urllib.request.Request(
        u, headers={"User-Agent": user_agent,
                    "Accept-Language": "zh-CN,zh;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            enc = _guess_encoding(resp.headers.get("Content-Type", ""), data)
    except Exception:
        return ""
    for cand in (enc, "utf-8", "gbk"):
        try:
            return data.decode(cand)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")
