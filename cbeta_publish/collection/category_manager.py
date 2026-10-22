import json
import shutil
from datetime import datetime
from pathlib import Path

from cbeta_publish.utils.atomic import atomic_write_json

class CategoryManager:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.corrupt = False
        self.data = {"categories": []}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
                if isinstance(raw, list):
                    raw = {"categories": raw}
                if not isinstance(raw, dict) or not isinstance(raw.get("categories"), list):
                    raise ValueError("categories 不是列表")
                self.data = raw
            except Exception as e:
                self.corrupt = True
                print("category file corrupt", self.path, e)
        self.data.setdefault("categories", [])

    def all(self):
        return self.data["categories"]

    def add(self, cid: str, name: str, description: str=""):
        if any(c["id"]==cid for c in self.data["categories"]):
            raise ValueError("exists")
        self.data["categories"].append({"id":cid,"name":name,"description":description,"preset":False})
        self.save()

    def rename(self, cid: str, new_name: str):
        for c in self.data["categories"]:
            if c["id"]==cid:
                c["name"]=new_name
        self.save()

    def update(self, cid: str, new_name: str = None, new_desc: str = None):
        for c in self.data["categories"]:
            if c["id"]==cid:
                if new_name is not None:
                    c["name"]=new_name
                if new_desc is not None:
                    c["description"]=new_desc
        self.save()

    def delete(self, cid: str):
        self.data["categories"]=[c for c in self.data["categories"] if c["id"]!=cid]
        self.save()

    def _backup_bad(self):
        """损坏文件先另存 .bad-<时间戳>，备份失败则拒绝覆盖。"""
        if self.path.exists():
            bak = self.path.with_name(
                f"{self.path.name}.bad-{datetime.now():%Y%m%d-%H%M%S}")
            try:
                if not bak.exists():
                    shutil.copy2(self.path, bak)
            except Exception as e:
                raise RuntimeError(f"分类文件损坏，且备份失败：{e}") from e
        self.corrupt = False

    def save(self):
        if self.corrupt:
            self._backup_bad()
        atomic_write_json(self.path, self.data)
