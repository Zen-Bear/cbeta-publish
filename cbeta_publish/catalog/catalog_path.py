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

WORK_RE = re.compile(r"[A-Z]+[0-9A-Za-z]*")

#: 未归类分组用的排序权重（置末）
_LAST = 10 ** 6


def _clean_bulei_seg(title: str) -> str:
    """部类树节点标题 → 干净段名：去经号 token 及其逗号连带的卷号列表
    （`T30a,42,45`/`X46,54`/`T1564-67`/`K1482`…；续号同样可带字母后缀，
    如 `T11-12a,26a,37,40b`，否则残留孤立 `a`/`b` 进文件名）、`etc.`、列表标点；
    保留顶层序号前缀、全角 `／`（如 `中觀部／疏`）与作者等正文（`【隋 吉藏撰】`）。
    """
    t = title or ""
    m = re.match(r"^\s*(\d+)\s+", t)
    num = m.group(1) if m else ""
    if m:
        t = t[m.end():]
    # 经号 token（含其后逗号分隔的裸卷号列表，续号可带字母后缀）
    # 经号 token（含其后逗号分隔的裸卷号列表，续号可带字母后缀）
    t = re.sub(r"[A-Za-z]{1,3}\d+[-\dA-Za-z]*(?:\s*[,，、;；]\s*\d+[-\dA-Za-z]*)*", " ", t)
    # 残留的「逗号+裸卷号」（其前导经号已先被去掉；同样可带字母后缀）
    t = re.sub(r"[,，、;；]\s*\d+[-\dA-Za-z]*", " ", t)
    t = re.sub(r"\betc\.?", " ", t, flags=re.I)
    t = re.sub(r"[,，、;；/]+", " ", t)          # 去列表标点与半角斜杠
    t = re.sub(r"\s*／\s*", "／", t)             # 全角斜杠两侧不留空格
    t = re.sub(r"\s+", " ", t).strip()
    if not re.search(r"[\u4e00-\u9fffA-Za-z]", t):
        t = ""
    return (f"{num} {t}".strip() if num else t).strip()


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
    parts = [p for p in parts if p]
    full = list(parts)   # 未截断全路径（封面显示可取更深；文件名仍用截断后 segments）
    parts = parts[:depth]
    if not parts:
        parts = ["未歸類" if dim != "volume" else "未分册"]
        unclassified = True
    label = " / ".join(parts)
    stem = "_".join(_safe_seg(p) for p in parts) or label
    return {"segments": parts, "label": label, "stem": stem,
            "order": order, "unclassified": unclassified,
            "full_segments": full or parts}
