"""SutraList.json 服务"""
import json
from pathlib import Path

from cbeta_publish._vendor import cbeta_fetch as cf

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
            # title like "T0001 长阿含经"；目录节点（"TX 太虛大師全書"）与区间节点
            # （"X01-02 印度撰述 X0001-0207"）首词不是作品编号，跳过——别当作品
            if title and title[0] in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                wid = title.split()[0]
                if cf.is_work_id(wid):
                    self._id_to_title[wid] = title
        for g in self.data:
            dfs(g)

    def title_of(self, work_id: str) -> str:
        return self._id_to_title.get(work_id, work_id)

    def all_ids(self) -> list[str]:
        return list(self._id_to_title.keys())
