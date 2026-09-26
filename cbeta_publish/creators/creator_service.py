"""作者服务：all-creators + creators-by-strokes"""
import json
from pathlib import Path

class CreatorService:
    def __init__(self, alias_path: str | Path, strokes_path: str | Path):
        self.alias_path = Path(alias_path)
        self.strokes_path = Path(strokes_path)
        self.alias = json.loads(self.alias_path.read_text(encoding="utf-8"))
        self.strokes = json.loads(self.strokes_path.read_text(encoding="utf-8"))
        self._index = {}
        self._build()

    def _build(self):
        for aid, info in self.alias.items():
            names = [info["regular_name"]] + info.get("aliases_all",[])
            for n in names:
                self._index.setdefault(n, []).append(aid)

    def search(self, keyword: str) -> list[dict]:
        res=[]
        for aid, info in self.alias.items():
            if keyword in info["regular_name"] or any(keyword in a for a in info.get("aliases_all",[])):
                res.append({"id": aid, "name": info["regular_name"], "aliases": info.get("aliases_all",[])})
        return res[:50]

    def works_of(self, creator_id: str) -> list[dict]:
        # 同一作者 id 可出现在多个 strokes 节点（别名/异称分立，如 A001019 窺基
        # 同时挂在 窺基/釋窺基/慈恩法師/大乘 名下）：全部收集（旧逻辑首个命中即停，
        # 作者视图搜“窥基”只返回 X0352 一部）。同 id 即同人，去重后返回。
        out=[]
        seen=set()
        def dfs(node):
            if not isinstance(node, dict):
                return
            if node.get("key")==creator_id:
                for c in node.get("children",[]) or []:
                    k=c.get("key") if isinstance(c, dict) else None
                    if k and k in seen:
                        continue
                    seen.add(k)
                    out.append(c)
            for c in node.get("children",[]) or []:
                dfs(c)
        for g in self.strokes or []:
            dfs(g)
        return out
