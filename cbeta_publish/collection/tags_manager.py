# -*- coding: utf-8 -*-
"""丛书标签：`collections/tags.json` = {"tags":[{id,name,parent,level,description}]}。

标签是**跨分类**的横切维度（一部丛书可有多个标签），与 `category`（单一、决定文件
所在目录）互补。id 由名称生成的 slug（拼音），在文件内唯一。
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

from cbeta_publish.utils.atomic import atomic_write_json


class TagsManager:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.corrupt = False
        self.data = {"tags": []}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
                if isinstance(raw, list):
                    raw = {"tags": raw}
                if not isinstance(raw, dict) or not isinstance(raw.get("tags"), list):
                    raise ValueError("tags 不是列表")
                self.data = raw
            except Exception as e:
                self.corrupt = True
                print("tags file corrupt", self.path, e)
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

    def _backup_bad(self):
        """损坏文件先另存 .bad-<时间戳>，备份失败则拒绝覆盖。"""
        if self.path.exists():
            bak = self.path.with_name(
                f"{self.path.name}.bad-{datetime.now():%Y%m%d-%H%M%S}")
            try:
                if not bak.exists():
                    shutil.copy2(self.path, bak)
            except Exception as e:
                raise RuntimeError(f"标签文件损坏，且备份失败：{e}") from e
        self.corrupt = False

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.corrupt:
            self._backup_bad()
        atomic_write_json(self.path, self.data)
