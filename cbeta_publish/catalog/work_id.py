# -*- coding: utf-8 -*-
"""工作编号规范化（复用 cbeta-fetch：canon 大写 + 编号原样）。

- `canonical_work(w)`：`TXA001 → TXa001`、`T0128A → T0128a`、`jb005 → JB005`；
  依据 `mulu/sutra_mapping.txt` 原始大小写；未命中则原样返回。
- `is_work_id(s)`：共享层作品编号，或本仓文件名形态（`T01n0001`）。
"""
import re
from pathlib import Path

from cbeta_publish._vendor import cbeta_fetch as cf

ROOT = Path(__file__).resolve().parents[2]

# 文件名形态（`T01n0001`）：共享层只认作品编号，不认这种
_BASENAME_RE = re.compile(r"[A-Za-z]{1,2}[0-9]{2}[nN][0-9]{4,6}[A-Za-z]?")


def catalog_path() -> Path:
    return ROOT / "mulu" / "sutra_mapping.txt"


def canonical_work(work) -> str:
    return cf.canonical_work_id((work or "").strip(), str(catalog_path()))


def is_work_id(s) -> bool:
    s = (s or "").strip()
    return bool(cf.is_work_id(s)) or bool(_BASENAME_RE.fullmatch(s))
