"""SutraList.json 服务"""
import json
from pathlib import Path

class SutraService:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        self._id_to_title = {}
        self._build()

    def _build(self):
        def dfs(node):
            if "children" in node:
                for c in node["children"]:
                    dfs(c)
            title = node.get("title","")
            # title like "T0001 长阿含经"
            if title and title[0] in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                wid = title.split()[0]
                self._id_to_title[wid] = title
        for g in self.data:
            dfs(g)

    def title_of(self, work_id: str) -> str:
        return self._id_to_title.get(work_id, work_id)

    def all_ids(self) -> list[str]:
        return list(self._id_to_title.keys())
