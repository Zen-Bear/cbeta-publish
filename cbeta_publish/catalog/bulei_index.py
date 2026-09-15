# -*- coding: utf-8 -*-
"""部類索引：从 bulei tree（category.json / bulei.txt）推导 work → 部類/三藏，
并汇总为合并用「说明页」数据。纯内存，CBETA 更新后自动生效。
"""
import re

from cbeta_publish.catalog.tripitaka_service import pitaka_of, PITAKA_ORDER

WORK_RE = re.compile(r"[A-Z]+[0-9A-Za-z]*")


def _iter(nodes, ancestors=None):
    """DFS，产出 (node, [祖先 title...])；ancestors 不含自身。"""
    ancestors = ancestors or []
    for n in nodes:
        title = getattr(n, "title", "") or ""
        yield n, ancestors
        children = getattr(n, "children", []) or []
        if children:
            yield from _iter(children, ancestors + [title])


def build_index(roots) -> dict:
    """返回 {work_id: {"bulei": 顶层部類 title, "pitaka": 经/律/论/藏外, "path": [链]}}。
    顶层 = 根节点（23 部類）；无子节点的叶 title 中提取 work id。"""
    index = {}
    for node, anc in _iter(roots):
        children = getattr(node, "children", []) or []
        if children:
            continue
        title = getattr(node, "title", "") or ""
        for w in WORK_RE.findall(title):
            if len(w) < 4:
                continue
            bulei = anc[0] if anc else title
            index.setdefault(w, {"bulei": bulei, "pitaka": pitaka_of(bulei), "path": anc + [title]})
    return index


def _display_name(title: str) -> str:
    """叶 title 形如 'T0001 長阿含經 (22卷)…'，去掉 work 前缀与括号说明。"""
    t = title or ""
    t = re.sub(r"^[A-Z]+[0-9A-Za-z]*\s*", "", t).strip()
    t = re.sub(r"\s*\([^)]*\)\s*", " ", t).strip()
    return t


def _bulei_label(title: str, with_num: bool = False) -> str:
    """部類标题 '01 阿含部類 T01-02,25,33 etc.' -> '阿含部類'（with_num 时保留序号 '01 阿含部類'）。"""
    t = title or ""
    m = re.match(r"^\s*(\d+)\s*", t)
    num = m.group(1) if m else ""
    body = re.sub(r"^\s*\d+\s*", "", t).strip()
    body = re.split(r"\s+[A-Z]{1,3}\d|\s+etc\.?", body)[0].strip()
    if not body:
        body = re.sub(r"^\s*\d+\s*", "", t).strip() or t
    if with_num and num:
        return f"{num} {body}"
    return body


def summarize(work_ids, roots, title_of=None) -> dict:
    """汇总说明页数据（纯字符串，排版交给渲染层）。

    work_ids: 参与合并的 work id 列表（保序、去重由调用方保证）
    title_of: 可选 work→标题 解析器（如 SutraList 的 title_of）；给出时行标签与
              目录页完全一致（不含作者），否则回退用部類叶标题（含作者）。
    返回 {"title": "说明",
          "summary": ["本丛书共收录 N 部", "三藏：…", "部類：…"],
          "sections": [("01 阿含部類（12 部）", ["T0001 長阿含經", …]), …]}
    """
    index = build_index(roots)
    pitaka_count = {k: 0 for k in PITAKA_ORDER}
    bulei_order = []          # 保持部類树序（按首次出现）
    bulei_map = {}            # bulei -> [work 行...]
    seen = set()
    total = 0
    for w in work_ids or []:
        if not w or w in seen:
            continue
        seen.add(w)
        total += 1
        info = index.get(w)
        bulei = info["bulei"] if info else "未歸類"
        pitaka = info["pitaka"] if info and info["pitaka"] != "其他" else "其他"
        pitaka_count[pitaka] = pitaka_count.get(pitaka, 0) + 1
        if bulei not in bulei_map:
            bulei_map[bulei] = []
            bulei_order.append(bulei)
        bulei_map[bulei].append(w)

    pitaka_txt = "、".join(f"{k} {pitaka_count.get(k, 0)}" for k in PITAKA_ORDER if pitaka_count.get(k))
    summary = [f"本丛书共收录 {total} 部"]
    if pitaka_txt:
        summary.append(f"三藏分布：{pitaka_txt}")
    if bulei_order:
        # 部類分布：名 N
        dist = []
        for b in bulei_order:
            dist.append(f"{_bulei_label(b)} {len(bulei_map[b])}")
        summary.append("部類分布：" + "、".join(dist))

    sections = []
    for b in bulei_order:
        rows = []
        for w in bulei_map[b]:
            if title_of is not None:
                rows.append(title_of(w))
                continue
            info = index.get(w)
            name = ""
            if info and info.get("path"):
                name = _display_name(info["path"][-1])
            rows.append(f"{w} {name}".rstrip())
        sections.append((f"{_bulei_label(b, with_num=True)}（{len(rows)} 部）", rows))
    return {"title": "说明", "summary": summary, "sections": sections}
