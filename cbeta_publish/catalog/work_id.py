# -*- coding: utf-8 -*-
"""工作编号规范化（复用 cbeta-fetch：canon 大写 + 编号原样）。

- `canonical_work(w)`：`TXA001 → TXa001`、`T0128A → T0128a`、`jb005 → JB005`；
  依据 `mulu/sutra_mapping.txt` 原始大小写；未命中则原样返回。
- `is_work_id(s)`：共享层作品编号，或本仓文件名形态（`T01n0001`）。
- 条目键：`work`（整本）或 `work:卷范围`（卷子集，如 `T0220:479`）；
  `split_entry`/`entry_key`/`canonical_entry` 供丛书书单与生成按条目处理。
"""
import re
from pathlib import Path

from cbeta_publish._vendor import cbeta_fetch as cf
from cbeta_publish.paths import app_root

ROOT = app_root()

# 文件名形态（`T01n0001`）：共享层只认作品编号，不认这种
_BASENAME_RE = re.compile(r"[A-Za-z]{1,2}[0-9]{2}[nN][0-9]{4,6}[A-Za-z]?")
#: 条目键分隔符（work:卷范围）
_ENTRY_SEP = ":"


def catalog_path() -> Path:
    return ROOT / "mulu" / "sutra_mapping.txt"


def canonical_work(work) -> str:
    return cf.canonical_work_id((work or "").strip(), str(catalog_path()))


def split_entry(s):
    """条目键 → (work, 卷范围)；无 `:` 则 (原文, "")。"""
    s = (s or "").strip()
    if _ENTRY_SEP in s:
        w, lab = s.split(_ENTRY_SEP, 1)
        return w.strip(), lab.strip()
    return s, ""


def entry_key(work, label="") -> str:
    """(work, 卷范围) → 条目键：有卷则 `work:卷`，否则 `work`。"""
    lab = (label or "").strip()
    w = (work or "").strip()
    return f"{w}{_ENTRY_SEP}{lab}" if (w and lab) else w


def canonical_entry(s) -> str:
    """条目键规范化：work 部分按 catalog 归一大小写，卷范围原样保留。"""
    w, lab = split_entry(s)
    return entry_key(canonical_work(w), lab)


def is_work_id(s) -> bool:
    s = (s or "").strip()
    w, _lab = split_entry(s)
    return bool(cf.is_work_id(w)) or bool(_BASENAME_RE.fullmatch(w))

