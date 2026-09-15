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


def merge_missing_children(primary: list, fallback: list) -> int:
    """把 fallback 里 primary 缺失的同级分组补进 primary（按前导序号插入）。

    背景：官方 `category.json` 偶尔缺分组（实测 般若部類 缺 01/09），
    而 `bulei.txt` 仍完整。只在「顶层部類 → 直接子分组」这一层按序号补齐，
    不改动 primary 既有节点。返回补入的节点数。
    """
    added = 0
    by_name = {}
    for top in fallback:
        by_name.setdefault(_norm_title(top.title), top)
    for top in primary:
        src = by_name.get(_norm_title(top.title))
        if src is None:
            continue
        have = {_lead_num(c.title) for c in top.children}
        for c in src.children:
            num = _lead_num(c.title)
            if not num or num in have:
                continue
            node = _copy(c, top.level + 1)
            # 按前导序号放进正确位置
            pos = len(top.children)
            for i, ex in enumerate(top.children):
                en = _lead_num(ex.title)
                if en and en.isdigit() and num.isdigit() and int(en) > int(num):
                    pos = i
                    break
            top.children.insert(pos, node)
            have.add(num)
            added += 1
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
