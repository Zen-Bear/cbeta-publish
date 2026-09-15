# -*- coding: utf-8 -*-
"""丛书标签：`collections/tags.json` = {"tags":[{id,name,parent,level,description}]}。

标签是**跨分类**的横切维度（一部丛书可有多个标签），与 `category`（单一、决定文件
所在目录）互补。id 由名称生成的 slug（拼音），在文件内唯一。
"""
import json
from pathlib import Path


class TagsManager:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"tags": []}
        self.data.setdefault("tags", [])

    def all(self):
        return self.data["tags"]

    def get(self, tid: str):
        return next((t for t in self.data["tags"] if t["id"] == tid), None)

    def name_of(self, tid: str) -> str:
        t = self.get(tid)
        return t["name"] if t else tid

    def new_id(self, name: str) -> str:
        try:
            from pypinyin import lazy_pinyin
            base = "_".join(lazy_pinyin(name))[:24] or "tag"
        except Exception:
            base = (name or "tag")[:12]
        tid = base
        i = 1
        while self.get(tid):
            tid = f"{base}_{i}"
            i += 1
        return tid

    def add(self, name: str, parent: str = "", description: str = "") -> str:
        tid = self.new_id(name)
        self.data["tags"].append({
            "id": tid, "name": name, "parent": parent,
            "level": 1, "description": description,
        })
        self.save()
        return tid

    def update(self, tid: str, new_name: str = None, new_desc: str = None, parent: str = None):
        t = self.get(tid)
        if not t:
            return
        if new_name is not None:
            t["name"] = new_name
        if new_desc is not None:
            t["description"] = new_desc
        if parent is not None:
            t["parent"] = parent
        self.save()

    def delete(self, tid: str):
        """删除标签及其子标签（按 parent 递归）。"""
        victims = {tid}
        changed = True
        while changed:
            changed = False
            for t in self.data["tags"]:
                if t.get("parent") in victims and t["id"] not in victims:
                    victims.add(t["id"])
                    changed = True
        self.data["tags"] = [t for t in self.data["tags"] if t["id"] not in victims]
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
