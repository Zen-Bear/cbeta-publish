import json
from pathlib import Path

class CategoryManager:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"categories":[]}

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

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
