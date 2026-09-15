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
        # search in strokes tree
        out=[]
        def dfs(node):
            if node.get("key")==creator_id:
                out.extend(node.get("children",[]))
                return True
            for c in node.get("children",[]):
                if dfs(c):
                    return True
            return False
        for g in self.strokes:
            dfs(g)
        return out
