# -*- coding: utf-8 -*-
"""按题名关联作品：书名里出现作者本名/别名，且紧邻体裁后缀。

源数据 `creators-by-strokes-with-works.json` 只把作品挂在「编者/译者」名下：例如
`X1420 楚石梵琦禪師語錄` 只挂在它的 15 位门人下，主名梵琦名下没有它。本模块按题名
兜底找出「相关」作品，**仅供作者视图的「相关（按题名）」子分组使用**——不计部数、
不进分册、不改源数据。

规则（2026-10-16 用户选定）：
- 取作品**书名段**（`【` 之前、去掉开头经号）匹配，不含卷数与译作者；
- 作者本名或任一别名出现在书名段，且**紧邻**一个体裁后缀（禪師/大師/語錄/文集/傳…）；
  加后缀这一档是为了滤掉「般若→大般若經」「自在→觀自在」「功德→功德莊嚴經」这类同名噪声；
- **别名若是别人的本名，则不参与匹配**：明代無相号太虛（别名表记「太虛」），若拿它匹配就会把
  民國太虛大師的《太虛大師全書》认领过来（实测 23 部）；这类撞名一律不比（本名照比）；
- 命中即算相关。已知仍有零星误配（如 傳燈→《續傳燈錄》《景德傳燈錄》），用户暂不处理。
"""
import re

#: 体裁后缀：名字后紧跟这些词才算命中
SUFFIXES = (
    "禪師", "大師", "法師", "和尚", "律師", "國師",
    "語錄", "錄", "文集", "全集", "詩集", "著述",
    "聖傳", "傳", "年譜", "行實",
)

#: 标题开头的经号（`X1420 ` / `T0001a `）——书名段匹配时去掉
_KEY_RE = re.compile(r"^\s*[A-Za-z]+\d+[a-z]?\s*")

#: 参与匹配的名字最短长度（单字噪声太大，直接不用）
_MIN_NAME = 2


def book_part(title: str) -> str:
    """书名段：`【` 之前、去掉开头经号。

    `X1420 楚石梵琦禪師語錄 (20卷)【(門人)…等編】` → `楚石梵琦禪師語錄 (20卷)`
    """
    s = str(title or "").split("【")[0]
    return _KEY_RE.sub("", s).strip()


def matches(book: str, names, suffixes=SUFFIXES):
    """书名段 `book` 里命中（且紧邻体裁后缀）的名字；命中多个取最长者，无则 None。"""
    hit = ""
    for nm in names or ():
        nm = (nm or "").strip()
        if len(nm) < _MIN_NAME or len(nm) <= len(hit):
            continue
        i = book.find(nm)
        while i >= 0:
            tail = book[i + len(nm):]
            if any(tail.startswith(s) for s in suffixes):
                hit = nm
                break
            i = book.find(nm, i + 1)
    return hit or None


def names_index(alias: dict) -> dict:
    """{作者id: [本名, 别名…]}：去空、去重、去单字。"""
    out = {}
    for aid, info in (alias or {}).items():
        names, seen = [], set()
        for n in [info.get("regular_name") or ""] + list(info.get("aliases_all") or []):
            n = (n or "").strip()
            if len(n) >= _MIN_NAME and n not in seen:
                seen.add(n)
                names.append(n)
        if names:
            out[aid] = names
    return out


def match_names(alias: dict) -> dict:
    """{作者id: [可用于按题名匹配的名字]}：别名里凡是他人的本名者剔除（本名自留）。"""
    reg = {}
    for aid, info in (alias or {}).items():
        rn = (info.get("regular_name") or "").strip()
        if rn:
            reg.setdefault(rn, set()).add(aid)
    out = {}
    for aid, names in names_index(alias).items():
        keep = []
        for n in names:
            owners = reg.get(n)
            if owners and aid not in owners:
                continue        # 该别名是别人的本名（如 無相 的别名「太虛」）→ 不参与匹配
            keep.append(n)
        if keep:
            out[aid] = keep
    return out


def related_index(alias: dict, works: dict, suffixes=SUFFIXES) -> dict:
    """{作者id: [(作品id, 标题, 命中名)]}。

    `works` = {作品id: 标题}（来自 SutraList 等目录源）。只按书名段匹配；
    命中后不再过滤「是否已归该作者」（由调用方按需剔除），排序交给调用方。
    """
    name2ids = {}
    for aid, names in match_names(alias).items():
        for n in names:
            name2ids.setdefault(n, []).append(aid)
    if not name2ids:
        return {}
    maxlen = max(len(n) for n in name2ids)
    out = {}
    for wid, title in (works or {}).items():
        book = book_part(title)
        if not book:
            continue
        best = {}          # 作者id → 命中名（同书同作者取最长）
        n = len(book)
        for i in range(n):
            for L in range(_MIN_NAME, min(maxlen, n - i) + 1):
                sub = book[i:i + L]
                ids = name2ids.get(sub)
                if not ids:
                    continue
                tail = book[i + L:]
                if not any(tail.startswith(s) for s in suffixes):
                    continue
                for aid in ids:
                    if len(sub) > len(best.get(aid, "")):
                        best[aid] = sub
        for aid, nm in best.items():
            out.setdefault(aid, []).append((wid, title, nm))
    return out
