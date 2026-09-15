# -*- coding: utf-8 -*-
"""朝代目录：解析官方 scope-selector/dynasty-works.json。
结构：[{title:"選擇全部",children:[{key:"東漢",title:"東漢 25 CE ~ 220 CE",
        children:[{key:"T0013",title:"T0013 長阿含十報法經 (2卷)【後漢 安世高譯】"}, ...]}]}]
返回按朝代顺序的 [(dynasty_title, [(work_id, work_title), ...])]，纯内存解析。"""
import json
from pathlib import Path


def _collect_works(node: dict) -> list:
    """递归收集叶节点（work）的 (key, title)。"""
    out = []
    for ch in node.get("children", []) or []:
        if not isinstance(ch, dict):
            continue
        if ch.get("children"):
            out.extend(_collect_works(ch))
        elif ch.get("key"):
            out.append((ch["key"], ch.get("title", ch["key"])))
    return out


def load_dynasty(path: str | Path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    # 单根「選擇全部」时取其 children
    roots = data[0].get("children", []) if (len(data) == 1 and data[0].get("children")) else data
    result = []
    for dyn in roots:
        if not isinstance(dyn, dict):
            continue
        title = dyn.get("title") or dyn.get("key") or ""
        works = _collect_works(dyn)
        result.append((title, works))
    return result


def dynasty_titles(path: str | Path) -> list:
    return [t for t, _ in load_dynasty(path)]


def work_dynasty_map(roots) -> dict:
    """{work_id: 朝代标题}（同一 work 多朝代时取首个）。"""
    out = {}
    for title, works in roots or []:
        for wid, _t in works:
            out.setdefault(wid, title)
    return out


def dominant_dynasty(work_ids, dmap: dict) -> str:
    """作品的代表朝代：出现最多者；无命中返回 '未詳'。"""
    counts = {}
    for wid in work_ids or []:
        d = dmap.get(wid)
        if d:
            counts[d] = counts.get(d, 0) + 1
    return max(counts, key=counts.get) if counts else "未詳"


def group_authors_by_dynasty(authors, dmap: dict, order) -> list:
    """作者按代表朝代分组，按 `order`（朝代序）排列，'未詳' 置末。

    返回 [(朝代, [作者, ...]), ...]；作者为其原始 dict（含 children=作品）。
    """
    groups = {}
    for a in authors or []:
        ids = [w.get("key") for w in (a.get("children", []) or []) if isinstance(w, dict)]
        groups.setdefault(dominant_dynasty(ids, dmap), []).append(a)
    seq = [t for t in (order or []) if t in groups]
    if "未詳" in groups:
        seq.append("未詳")
    return [(t, groups[t]) for t in seq]

