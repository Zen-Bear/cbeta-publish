# -*- coding: utf-8 -*-
"""刊本目录：解析官方 scope-selector/vol.json。

结构：单根「選擇全部」→ 刊本（大正藏/卍新續藏/高麗藏/房山石經…）
      → 册（如 `T01 阿含部上 T0001-0098`）→ 经（`T0001 長阿含經…`）。

注意：部分刊本的第二层**直接是经**（无册分组，如 趙城金藏/房山石經），
故每个刊本返回 `vols`（册分组）与 `works`（直属经）两部分。

返回：
[
  {"edition": 刊本名,
   "vols": [{"title": 册名, "works": [(work_id, work_title), ...]}, ...],
   "works": [(work_id, work_title), ...]},   # 直属经（可能为空）
  ...
]
"""
import json
from pathlib import Path


def _children(node) -> list:
    return [c for c in (node.get("children") or []) if isinstance(c, dict)]


def _roots(data) -> list:
    """vol.json 可能是单根「選擇全部」，取其 children 作为刊本层。"""
    if not isinstance(data, list):
        return []
    return _children(data[0]) if (len(data) == 1 and _children(data[0])) else data


def _short_title(title: str) -> str:
    """叶 title 'TXa001 太虛大師全書．編纂說明 (2卷)' → '編纂說明'。

    去 work 前缀 → 去括号说明 → 若含分隔符「．」取末段。
    """
    import re as _re
    t = (title or "").strip()
    t = _re.sub(r"^[A-Z]+[0-9A-Za-z]*\s*", "", t).strip()
    t = _re.sub(r"\s*[（(][^）)]*[）)]\s*", " ", t).strip()
    if "．" in t:
        t = t.split("．")[-1].strip()
    return t or (title or "").strip()


def _leaf_works(node) -> list:
    """收集两级以下的叶（work）。"""
    out = []
    for ch in _children(node):
        if _children(ch):
            out.extend(_leaf_works(ch))
        elif ch.get("key"):
            out.append((ch["key"], ch.get("title", ch["key"])))
    return out


def load_vol(path: str | Path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    # 单根「選擇全部」→ 取其 children 作为刊本层
    roots = _children(data[0]) if (len(data) == 1 and _children(data[0])) else data
    result = []
    for edition in roots:
        if not isinstance(edition, dict):
            continue
        etitle = edition.get("title") or edition.get("key") or ""
        vols = []
        loose = []
        for ch in _children(edition):
            if _children(ch):
                vols.append({"title": ch.get("title") or ch.get("key") or "",
                             "works": _leaf_works(ch)})
            elif ch.get("key"):
                loose.append((ch["key"], ch.get("title", ch["key"])))
        result.append({"edition": etitle, "vols": vols, "works": loose})
    return result


def edition_titles(path: str | Path) -> list:
    return [e["edition"] for e in load_vol(path)]


def count_works(entry: dict) -> int:
    """某刊本的经总数（册内 + 直属）。"""
    return sum(len(v["works"]) for v in entry.get("vols", [])) + len(entry.get("works", []))


def work_vol_map(path: str | Path) -> dict:
    """作品 → 册名（按册分册用）。

    册内的经取册标题；刊本直属经（无册分组）取刊本名。
    同一作品出现在多个刊本时以先出现者为准。
    """
    out = {}
    for e in load_vol(path):
        for vol in e.get("vols", []):
            for wid, _t in vol["works"]:
                out.setdefault(wid, vol["title"])
        for wid, _t in e.get("works", []):
            out.setdefault(wid, e["edition"])
    return out


def work_edition_map(path: str | Path) -> dict:
    """作品 → 刊本名（按刊本分册用）。同一作品出现在多个刊本时以先出现者为准。"""
    out = {}
    for e in load_vol(path):
        for vol in e.get("vols", []):
            for wid, _t in vol["works"]:
                out.setdefault(wid, e["edition"])
        for wid, _t in e.get("works", []):
            out.setdefault(wid, e["edition"])
    return out


def work_file_map(path: str | Path) -> dict:
    """作品 → {"edition": 刊本名, "seq": 刊本内顺序号, "label": 显示名}。

    序号按 vol.json 刊本内原始顺序编号（含直属经）；册取册名，
    直属经取书名（`_short_title`，如「太虛大師全書．編纂說明」→「編纂說明」）。
    同一作品出现在多个刊本时以先出现者为准。
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for edition in _roots(data):
        if not isinstance(edition, dict):
            continue
        etitle = edition.get("title") or edition.get("key") or ""
        seq = 0
        for ch in _children(edition):
            if _children(ch):
                seq += 1
                title = ch.get("title") or ch.get("key") or ""
                for wid, _t in _leaf_works(ch):
                    out.setdefault(wid, {"edition": etitle, "seq": seq, "label": title})
            elif ch.get("key"):
                seq += 1
                out.setdefault(ch["key"], {"edition": etitle, "seq": seq,
                                           "label": _short_title(ch.get("title") or ch["key"])})
    return out
