# -*- coding: utf-8 -*-
"""三藏映射：本地 bulei.txt 为 CBETA 23 部類，按名/序号归入 经/律/论/藏外。
参考 docs/设计总案.md 与 https://archive2.cbeta.org/en/node/6595（大正三藏划分）。
纯内存重分组，无衍生文件；CBETA 更新源后自动生效。
"""
import re

# 三藏固定顺序
PITAKA_ORDER = ["經", "律", "論", "藏外"]

# 部類名（去数字前缀）关键字 -> 三藏；最长/最具体优先（列表顺序即匹配顺序）
PITAKA_KEYWORDS = [
    ("經", ["阿含", "本緣", "般若", "法華", "華嚴", "寶積", "涅槃", "大集", "經集", "密教"]),
    ("律", ["律"]),
    ("論", ["毘曇", "中觀", "瑜伽", "論集"]),
    ("藏外", ["淨土宗", "禪宗", "史傳", "事彙", "敦煌", "國圖", "南傳", "新編"]),
]

# 序号兜底区间
PITAKA_BY_NUM = [
    (1, 10, "經"),
    (11, 11, "律"),
    (12, 15, "論"),
    (16, 23, "藏外"),
]


def strip_num(title: str) -> str:
    return re.sub(r"^\s*\d+\s+", "", title or "").strip()


def num_of(title: str):
    m = re.match(r"^\s*(\d+)", title or "")
    return int(m.group(1)) if m else None


def pitaka_of(title: str) -> str:
    """部類标题 -> 三藏（经/律/论/藏外）；无法判定返回 '其他'。"""
    name = strip_num(title)
    for pitaka, kws in PITAKA_KEYWORDS:
        for kw in kws:
            if kw in name:
                return pitaka
    n = num_of(title)
    if n is not None:
        for lo, hi, pitaka in PITAKA_BY_NUM:
            if lo <= n <= hi:
                return pitaka
    return "其他"


def group_by_pitaka(roots) -> list[tuple[str, list]]:
    """将 bulei 顶层节点（部類）按三藏分组，返回固定顺序的 [(三藏, [部類节点...])]。
    CBETA 23 部類外的新增部類归入 '其他' 并追加在末尾。"""
    bucket: dict[str, list] = {k: [] for k in PITAKA_ORDER}
    for r in roots:
        p = pitaka_of(getattr(r, "title", ""))
        bucket.setdefault(p, []).append(r)
    order = list(PITAKA_ORDER)
    for k in bucket:
        if k not in order and bucket[k]:
            order.append(k)
    return [(k, bucket[k]) for k in order if bucket.get(k)]
