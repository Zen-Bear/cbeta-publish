# -*- coding: utf-8 -*-
"""目录源差异：当前 mulu 文件 vs 上次更新前快照（mulu/backup/last/）。

只做**经**的新增/删除/改名（经号 → 原文标题，标题自带卷与作者）。各源的经号抽取：

- 树形 JSON（`category` / `dynasty` / `vol`）与 `SutraList.json`：叶子 `key`/`title`；
  `SutraList` 叶子无 key，经号取标题首词（`G2352 楞伽阿跋多羅寶經科解`）。
- `sutra_mapping.txt`：`G,127,2352,10,1,0257a01,楞伽…,明 真貴述`——经号＝藏+号（含小写
  后缀），标题＝「经号 书名（作者）」。
- `bulei.txt`：部类树文本，行首经号（`T0001 長阿含經22卷`）；`T0220_401..537` 这类
  卷叶行不计（不是经级条目）。

经号匹配用**归一化式**（去前导零：`T0001` ≡ `T,05,0001` → `T1`，`B0001` ≡ `B1`），
展示仍用原文经号。
"""
import json
import re
from pathlib import Path

#: 源 key → 解析方式（"json"＝树形/标题 JSON；其余为文本源）
KIND_OF = {
    "category": "json", "dynasty": "json", "vol": "json",
    "sutralist": "json", "sutra_mapping": "mapping", "bulei_txt": "bulei",
}

#: 跨源合并时标题的优先级（数字小者优先：范围清单 > 朝代/刊本 > 经录 > 部类文本）
PRIORITY = {"category": 0, "dynasty": 1, "vol": 2,
            "sutralist": 3, "sutra_mapping": 4, "bulei_txt": 5}

_KEY_RE = re.compile(r"^([A-Z]{1,4})0*(\d+)([a-z]?)")
_SORT_RE = re.compile(r"^([A-Z]+)(\d+)([a-z]?)$")


def norm_key(raw: str) -> str:
    """归一化经号：去前导零（`T0001`→`T1`），保留小写后缀（`T0128a`→`T128a`）。"""
    m = _KEY_RE.match(str(raw or "").strip())
    return (m.group(1) + m.group(2) + m.group(3)) if m else ""


def _sort_key(k: str):
    m = _SORT_RE.match(str(k or ""))
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (str(k), 0, "")


def _leaves(nodes, out):
    for x in nodes or []:
        if isinstance(x, dict) and x.get("children"):
            _leaves(x["children"], out)
        elif isinstance(x, dict):
            out.append(x)
    return out


def works_of(path, kind) -> dict:
    """{归一化经号: 原文标题}；文件缺失/解析失败返回 {}。"""
    p = Path(path)
    try:
        if kind == "mapping":
            out = {}
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                f = line.split(",")
                if len(f) < 7 or not f[0] or not f[2]:
                    continue
                k = norm_key(f[0] + f[2])
                if not k:
                    continue
                name = f[6].strip()
                author = f[7].strip() if len(f) > 7 else ""
                title = f"{f[0]}{f[2]} {name}"
                out[k] = (title + (f"（{author}）" if author else "")).strip()
            return out
        if kind == "bulei":
            out = {}
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                tok = s.split(" ")[0] if s else ""
                # 只认纯经号行首（`T0001 …`）；`T0220_401..537` 卷叶、
                # `T0001-25` 区间标签都不是经级条目。
                if not re.fullmatch(r"[A-Z]{1,4}\d+[a-z]?", tok):
                    continue
                k = norm_key(tok)
                if k:
                    out[k] = re.sub(r"\s+", " ", s)
            return out
        data = json.loads(p.read_text(encoding="utf-8"))
        out = {}
        for x in _leaves(data, []):
            title = str(x.get("title") or "").strip()
            key = x.get("key") or (title.split(" ")[0] if title else "")
            k = norm_key(key)
            if k and title:
                out[k] = title
        return out
    except Exception:
        return {}


def diff_source(key, old_path, new_path):
    """单源差异；任一侧缺失/解析为空返回 None。

    返回 {"key", "added", "removed", "renamed", "counts"}：
    added/removed＝[(经号, 标题)]；renamed＝[(经号, 旧标题, 新标题)]；
    counts＝(新增, 删除, 改名)。
    """
    kind = KIND_OF.get(key)
    if kind is None:
        return None
    if not (Path(old_path).is_file() and Path(new_path).is_file()):
        return None
    a = works_of(old_path, kind)
    b = works_of(new_path, kind)
    if not a and not b:
        return None
    added = [(k, b[k]) for k in sorted(set(b) - set(a), key=_sort_key)]
    removed = [(k, a[k]) for k in sorted(set(a) - set(b), key=_sort_key)]
    renamed = [(k, a[k], b[k]) for k in sorted(set(a) & set(b), key=_sort_key)
               if a[k] != b[k]]
    return {"key": key, "added": added, "removed": removed, "renamed": renamed,
            "counts": (len(added), len(removed), len(renamed))}


def merge_works(diffs, field="added") -> list:
    """跨源合并去重（按归一化经号），取优先级最高源的条目；按经号排序。

    条目原样保留（added/removed＝`(经号, 标题)`；renamed＝`(经号, 旧标题, 新标题)`）。
    """
    best = {}
    for skey, d in (diffs or {}).items():
        if not d:
            continue
        pri = PRIORITY.get(skey, 9)
        for item in d.get(field) or []:
            k = item[0]
            cur = best.get(k)
            if cur is None or pri < cur[0]:
                best[k] = (pri, tuple(item[1:]))
    return [(k, *best[k][1]) for k in sorted(best, key=_sort_key)]


def _label(key, label_of) -> str:
    if label_of is None:
        return key
    try:
        return label_of[key]
    except Exception:
        return label_of(key) if callable(label_of) else key


def summary_lines(diffs, limit=20, label_of=None) -> list:
    """状态框摘要：逐源一行（新增/删除/改名）＋合并新增经清单（最多 limit 条）。"""
    if not diffs:
        return ["目录变更：无可对比项（没有上次备份，或本次没有更新）。"]
    lines = ["—— 目录变更（对比上次更新前的备份）——"]
    for skey, d in diffs.items():
        a, r, c = d.get("counts") or (0, 0, 0)
        lines.append(f"{_label(skey, label_of)}：新增 {a}、删除 {r}、改名 {c}"
                     if (a or r or c) else f"{_label(skey, label_of)}：无变化")
    added = merge_works(diffs, "added")
    removed = merge_works(diffs, "removed")
    renamed = merge_works(diffs, "renamed")
    if added:
        head = "、".join(t for _k, t in added[:limit])
        more = f"…（共 {len(added)} 部，点「查看目录变更…」看全部）" if len(added) > limit else ""
        lines.append(f"新增经 {len(added)} 部：{head}{more}")
    if removed:
        lines.append("删除经 %d 部：%s%s" % (
            len(removed), "、".join(t for _k, t in removed[:limit]),
            "…" if len(removed) > limit else ""))
    if renamed:
        lines.append("改名经 %d 部：%s%s" % (
            len(renamed), "、".join(f"{t0} → {t1}" for _k, t0, t1 in renamed[:limit]),
            "…" if len(renamed) > limit else ""))
    if not (added or removed or renamed):
        lines.append("本次更新没有经的新增/删除/改名。")
    return lines


def detail_text(diffs, label_of=None, times=None) -> str:
    """弹窗明细：按源分组列出全部新增/删除/改名（可滚动、可复制）。"""
    if not diffs:
        return ("没有可对比的备份。\n\n"
                "说明：每次「立即检查更新」覆盖前，旧文件会快照到 mulu/backup/last/；\n"
                "该目录为空（或当前文件缺失）时无法比较。先更新一次再回来查看。")
    out = []
    added = merge_works(diffs, "added")
    removed = merge_works(diffs, "removed")
    renamed = merge_works(diffs, "renamed")
    out.append(f"合计（跨源去重）：新增经 {len(added)} 部、删除经 {len(removed)} 部、"
               f"改名经 {len(renamed)} 部")
    for skey, d in diffs.items():
        a, r, c = d.get("counts") or (0, 0, 0)
        t = ""
        if times:
            try:
                t = f"（备份：{times[skey]}）"
            except Exception:
                t = ""
        out.append("")
        out.append(f"== {_label(skey, label_of)}{t}：新增 {a}、删除 {r}、改名 {c} ==")
        if d.get("added"):
            out.append("新增：")
            out.extend(f"  + {title}" for _k, title in d["added"])
        if d.get("removed"):
            out.append("删除：")
            out.extend(f"  - {title}" for _k, title in d["removed"])
        if d.get("renamed"):
            out.append("改名：")
            out.extend(f"  ~ {t0}  →  {t1}" for _k, t0, t1 in d["renamed"])
        if not (a or r or c):
            out.append("  （无变化）")
    return "\n".join(out)
