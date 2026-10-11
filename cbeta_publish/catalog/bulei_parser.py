"""bulei.txt -> TreeNode(level,title,work_range)  ref: bulei.txt, 格式说明.txt"""
from dataclasses import dataclass, field
from pathlib import Path
import re

@dataclass
class BuleiNode:
    level: int
    title: str
    raw: str
    children: list = field(default_factory=list)

def parse_bulei(path: str | Path) -> list[BuleiNode]:
    path = Path(path)
    roots: list[BuleiNode] = []
    stack: list[BuleiNode] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        level = len(line) - len(line.lstrip("\t"))
        title = line.strip()
        node = BuleiNode(level=level+1, title=title, raw=line)
        # find parent
        while stack and stack[-1].level >= node.level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots

def parse_bulei_json(path: str | Path) -> list[BuleiNode]:
    """解析官方 scope-selector/category.json（嵌套 {title,children,key}）为 BuleiNode 树。
    兼容 buelei.txt 结构：根节点若为单个「選擇全部」，取其 children 为顶层部類。"""
    import json as _json
    data = _json.loads(Path(path).read_text(encoding="utf-8"))

    def conv(obj, level: int) -> BuleiNode:
        title = obj.get("title", "")
        node = BuleiNode(level=level, title=title, raw=title)
        for ch in obj.get("children", []) or []:
            node.children.append(conv(ch, level + 1))
        return node

    roots = [conv(o, 1) for o in data]
    # 单根「選擇全部」时下钻一层，使顶层为 01 阿含部類…
    if len(roots) == 1 and roots[0].children:
        children = roots[0].children
        for c in children:
            c.level = 1
            def renum(n, lv):
                n.level = lv
                for ch in n.children:
                    renum(ch, lv + 1)
            renum(c, 1)
        return children
    return roots

_LEAD_NUM = re.compile(r"^\s*(\d+)\b")


def _lead_num(title: str):
    m = _LEAD_NUM.match(title or "")
    return m.group(1) if m else None


def _norm_title(title: str) -> str:
    """去掉尾部 T/X 范围描述，用于跨源匹配同一分组。"""
    return re.sub(r"\s+[TX]\d.*$", "", (title or "").strip()).strip()


def _copy(node: BuleiNode, level: int) -> BuleiNode:
    n = BuleiNode(level=level, title=node.title, raw=node.raw)
    for c in node.children:
        n.children.append(_copy(c, level + 1))
    return n


def _child_key(title):
    """子节点匹配键：（前导序号或 None，归一标题）。

    数字子节点按序号对齐；无序号（如 `T0220c,21-23 …`）按归一标题对齐，
    使深层叶子也能跨源匹配。
    """
    n = _lead_num(title)
    return (n if (n and n.isdigit()) else None, _norm_title(title))


#: 卷区间 `ID_NNN` / `ID_NNN..MMM`（尾随字母数字即止，`N70_1cont` 不算）
_PAIR_RE = re.compile(r"([A-Z]{1,2}\d+[A-Za-z]?)_(\d{1,4})(?:\.\.(\d{1,4}))?(?![0-9A-Za-z])")


def _title_content(title):
    """标题内容指纹 → ({(work,lo,hi)}, {work})。"""
    t = title or ""
    pairs = set()
    for m in _PAIR_RE.finditer(t):
        pairs.add((m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))))
    return pairs, set(WORK_RE.findall(t))


def _subtree_content(node):
    """子树内容指纹（本节点＋全部后代标题的并集）。"""
    pairs, works = set(), set()
    stack = [node]
    while stack:
        x = stack.pop()
        p, w = _title_content(x.title)
        pairs |= p
        works |= w
        stack.extend(x.children or [])
    return pairs, works


def _is_doc(title):
    """文档/导航节点（非书目）：`help/…htm`、含链接。永不 graft，避免污染书树。"""
    t = (title or "").strip()
    return t.startswith("help/") or ".htm" in t or "http" in t


def _title_work(title):
    """标题首个经号（`T0220_401..537 …` → `T0220`）；无则 ""。"""
    m = WORK_RE.search(title or "")
    return m.group(0) if m else ""


def _work_sort_key(work):
    """经号排序键：藏（字母）＋号（数字）＋后缀（`T0220` < `T0220a` < `T0221`）。"""
    m = re.match(r"^([A-Za-z]+)(\d+)(.*)$", work or "")
    if not m:
        return ("", 0, str(work or ""))
    return (m.group(1).upper(), int(m.group(2)), m.group(3) or "")


def _prune_docs(node):
    """就地剔除文档/导航后代，返回修剪后节点（本节点若为文档返回 None）。

    graft 整棵子树前调用：只带书目内容走，文档链接不进书树。
    （调用方须传 deepcopy 后的节点，勿动 fallback 原树。）
    """
    if node is None or _is_doc(node.title):
        return None
    kept = []
    for c in (node.children or []):
        r = _prune_docs(c)
        if r is not None:
            kept.append(r)
    node.children = kept
    return node


def _merge_deep(p_children, f_children, level, have_pairs, have_works):
    """深层递归合并（顶层直属子节点之下各层）：标题命中则递归；未命中走新颖门控。

    门控（只增不改）：文档链接跳过；含新卷区间对 → 整棵接入；
    无区间但含全新经号 → 整棵接入；余下（重复/无书目导航）跳过。
    定序：数字按值；无序号按经号（只看 work 部分，如 `T0220_*` 排到 `T0221` 前）；
    无经号追加尾部。
    返回新增 graft 根数（接入后同步更新 have_*）。
    """
    pmap = {}
    for c in p_children:
        pmap.setdefault(_child_key(c.title), c)
    added = 0
    for fc in f_children:
        pc = pmap.get(_child_key(fc.title))
        if pc is not None:
            added += _merge_deep(pc.children, fc.children, pc.level + 1,
                                 have_pairs, have_works)
            continue
        if _is_doc(fc.title):
            continue
        node = _copy(fc, level)
        node = _prune_docs(node)
        if node is None:
            continue
        pairs, works = _subtree_content(node)
        if pairs:
            if pairs <= have_pairs:
                continue
        elif works:
            if works <= have_works:
                continue
        else:
            continue
        num = _lead_num(fc.title)
        if num and num.isdigit():
            pos = len(p_children)
            for i, ex in enumerate(p_children):
                en = _lead_num(ex.title)
                if en and en.isdigit() and int(en) > int(num):
                    pos = i
                    break
            p_children.insert(pos, node)
        else:
            # 无序号：按经号定序（`T0220_*` 只看 `T0220`，排到 `T0221` 前）；
            # 无经号追加尾部
            wk = _work_sort_key(_title_work(fc.title))
            pos = len(p_children)
            if wk[0]:
                for i, ex in enumerate(p_children):
                    ew = _title_work(ex.title)
                    if ew and _work_sort_key(ew) > wk:
                        pos = i
                        break
            p_children.insert(pos, node)
        pmap[_child_key(fc.title)] = node
        npairs, nworks = _subtree_content(node)
        have_pairs |= npairs
        have_works |= nworks
        added += 1
    return added


def merge_missing_children(primary: list, fallback: list) -> int:
    """把 fallback 里 primary 缺失的同级分组补进 primary（按前导序号插入）。

    背景：官方 `category.json` 偶尔缺分组（实测 般若部類 缺 01/09），
    而 `bulei.txt` 仍完整。顶层部類按标题对齐后递归到任意深度：
    只在「顶层部類 → 直接子分组」这一层按序号补齐已不够——`category.json`
    另有深层叶子缺失（如 `T0220c,21-23` 下的 `T0220_401..537` 等卷区间叶，
    主源将其当无子节点叶子）。递归只增不改主源已有节点。返回新增 graft 根数。

    两遍式：先按旧语义整棵补齐缺失数字子分组，再深入门控补深层。
    深层门控（只增不改）：文档链接跳过；含新卷区间对 → 整棵接入；
    无区间但含全新经号 → 整棵接入；余下（重复/无书目导航）跳过。
    跨分支重复由全局新颖索引天然去重。
    """
    added = 0
    by_name = {}
    for top in fallback:
        by_name.setdefault(_norm_title(top.title), top)
    # 全局新颖索引（主源全部节点标题；graft 时同步追加，保证跨分组去重）
    have_pairs, have_works = set(), set()
    stack = list(primary)
    while stack:
        x = stack.pop()
        p, w = _title_content(x.title)
        have_pairs |= p
        have_works |= w
        stack.extend(x.children or [])
    for top in primary:
        src = by_name.get(_norm_title(top.title))
        if src is None:
            continue
        # 两遍式：先按旧语义整棵补齐缺失数字子分组（含子树，不做新颖判断），
        # 再对标题命中的深入递归门控补深层——后者能看到前者已带入的内容，
        # 跨分支重复天然跳过。
        # 第一遍：旧语义（数字缺失整棵接入、非数字跳过；子树内文档链接剪掉）
        have = {_lead_num(c.title) for c in top.children}
        for c in src.children:
            num = _lead_num(c.title)
            if not num or num in have:
                continue
            node = _prune_docs(_copy(c, top.level + 1))
            if node is None:
                continue
            # 按前导序号放进正确位置
            pos = len(top.children)
            for i, ex in enumerate(top.children):
                en = _lead_num(ex.title)
                if en and en.isdigit() and int(en) > int(num):
                    pos = i
                    break
            top.children.insert(pos, node)
            have.add(num)
            npairs, nworks = _subtree_content(node)
            have_pairs |= npairs
            have_works |= nworks
            added += 1
        # 第二遍：标题命中的深入递归（旧实现到此为止）
        pmap = {}
        for c in top.children:
            pmap.setdefault(_child_key(c.title), c)
        for c in src.children:
            pc = pmap.get(_child_key(c.title))
            if pc is None:
                continue
            added += _merge_deep(pc.children, c.children, pc.level + 1,
                                 have_pairs, have_works)
    return added


def flatten_bulei(nodes: list[BuleiNode]) -> list[tuple[int,str]]:
    out = []
    def dfs(n):
        out.append((n.level, n.title))
        for c in n.children:
            dfs(c)
    for r in nodes:
        dfs(r)
    return out

# work id extraction e.g. T0001, T0220_576
WORK_RE = re.compile(r"[A-Z]+[0-9A-Za-z]*")
def extract_works(title: str) -> list[str]:
    return WORK_RE.findall(title)
