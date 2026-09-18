# -*- coding: utf-8 -*-
"""目录路径：work → 分册路径段（部类 / 刊本册），供合并分册与命名。

- dim="bulei"：部类树（`bulei.txt`/`category.json`）路径，段名清洗掉经号范围与
  `etc.`，保留序号前缀（如 `01 阿含部類`）；order 为 DFS 序号元组（树序稳定）。
- dim="volume"：`mulu/vol.json` 的 [刊本名, 册/编 显示名]；order 为 (刊本内序号,)。
- 未命中：部类「未歸類」、刊本「未分冊」，order 置末。

深度 `depth` 截断路径前 N 段；volume 路径最多 2 段（depth>2 按实际段数）。
纯内存；CBETA 更新后下次启动重建。
"""
import re
from pathlib import Path

from cbeta_publish.catalog.bulei_index import _bulei_label

WORK_RE = re.compile(r"[A-Z]+[0-9A-Za-z]*")

#: 未归类分组用的排序权重（置末）
_LAST = 10 ** 6


def _clean_bulei_seg(title: str) -> str:
    """部类树节点标题 → 干净段名（去序号外的经号范围、`etc.`）。"""
    t = _bulei_label(title or "", with_num=True) or (title or "")
    t = re.sub(r"\betc\.?", "", t)
    t = re.sub(r"^(\d+)\s+[A-Z]+\d+[-\dA-Za-z]*\s*", r"\1 ", t)   # "01 T01-02 阿含部類" → "01 阿含部類"
    t = re.sub(r"^[A-Z]+\d+[-\dA-Za-z]*\s*", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _safe_seg(seg: str) -> str:
    """文件名段清洗（下划线拼接用）。"""
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f\r\n\t]+', "_", (seg or "").strip())
    s = re.sub(r"\s+", " ", s).strip(" ._")
    return s


def build_bulei_map(roots) -> dict:
    """{work: {"path": [标题...], "order": (索引...), "unclassified": False}}。"""
    index = {}

    def dfs(nodes, ancestors, indices):
        for i, n in enumerate(nodes or []):
            title = getattr(n, "title", "") or ""
            children = getattr(n, "children", []) or []
            if children:
                dfs(children, ancestors + [title], indices + [i])
                continue
            for w in WORK_RE.findall(title):
                if len(w) < 4:
                    continue
                index.setdefault(w, {"path": ancestors + [title],
                                     "order": tuple(indices + [i]),
                                     "unclassified": False})

    dfs(roots, [], [])
    return index


def build_volume_map(vol_path) -> dict:
    """{work: {"edition","seq","label"}}（薄封装 vol_service.work_file_map）。"""
    try:
        from cbeta_publish.catalog.vol_service import work_file_map
        return work_file_map(Path(vol_path))
    except Exception:
        return {}


def resolve(work, dim, depth=2, *, bulei_map=None, volume_map=None) -> dict:
    """返回 {"segments":[段...], "label", "stem", "order", "unclassified"}。"""
    depth = max(1, int(depth or 1))
    unclassified = False
    if dim == "volume":
        info = (volume_map or {}).get(work)
        parts = []
        order = (_LAST,)
        if info:
            parts = [str(info.get("edition") or ""), str(info.get("label") or "")]
            order = (int(info.get("seq") or 0),)
        if not any(parts):
            parts = ["未分册"]
            unclassified = True
    else:  # bulei
        info = (bulei_map or {}).get(work)
        order = (_LAST,)
        parts = []
        if info:
            parts = [_clean_bulei_seg(t) for t in info.get("path") or []]
            order = tuple(info.get("order") or (_LAST,))
        if not parts:
            parts = ["未歸類"]
            unclassified = True
    parts = [p for p in parts if p][:depth]
    if not parts:
        parts = ["未歸類" if dim != "volume" else "未分册"]
        unclassified = True
    label = " / ".join(parts)
    stem = "_".join(_safe_seg(p) for p in parts) or label
    return {"segments": parts, "label": label, "stem": stem,
            "order": order, "unclassified": unclassified}
