import json, uuid, time
from pathlib import Path
from datetime import datetime

from cbeta_publish.catalog.work_id import canonical_work, canonical_entry, split_entry


def _work_of(entry) -> str:
    return split_entry(entry)[0]


def normalize_collection(d: dict) -> dict:
    """就地规范化丛书 JSON 的条目键（work_ids / works[].id / work_sources 键）。

    条目键＝`work`（整本）或 `work:卷范围`（卷子集，如 `T0220:479`）；同一部的
    不同卷是**不同条目**（去重按条目键）。work 级映射（work_sources/work_groups/
    bulei_groups/work_notes）按 work 部分归一。
    迁移策略：读入时规范化（不改磁盘），下次保存自然回写。
    """
    if not isinstance(d, dict):
        return d
    if isinstance(d.get("work_ids"), list):
        seen = set()
        out = []
        for w in d["work_ids"]:
            c = canonical_entry(w)
            if c and c not in seen:
                seen.add(c)
                out.append(c)
        d["work_ids"] = out
    _entries = set(d.get("work_ids") or [])
    _works = {_work_of(e) for e in _entries}
    if isinstance(d.get("work_sources"), dict):
        d["work_sources"] = {canonical_work(_work_of(k)): v
                             for k, v in d["work_sources"].items()}
    if isinstance(d.get("work_groups"), dict):
        d["work_groups"] = {canonical_work(_work_of(k)): v
                            for k, v in d["work_groups"].items()}
    if isinstance(d.get("bulei_groups"), dict):
        # 部类归属：{work_id: [路径段...]}（从部类树拖入时记录；按部类分组优先用它）
        _bg = {}
        for k, v in d["bulei_groups"].items():
            c = canonical_work(_work_of(k))
            if c and isinstance(v, list) and (not _works or c in _works):
                _bg[c] = [str(x) for x in v]
        d["bulei_groups"] = _bg
    if isinstance(d.get("work_notes"), dict):
        # 书籍注释（「导入ID…」带入）：{work_id: 注释}；键归一、按 work 剪枝、
        # 空注丢弃（仅展示，不参与合并/分册/校验）。
        _wn = {}
        for k, v in d["work_notes"].items():
            c = canonical_work(_work_of(k))
            s = str(v or "").strip()
            if c and s and (not _works or c in _works):
                _wn[c] = s
        d["work_notes"] = _wn
    d.pop("work_juan", None)   # 卷范围已并入条目键，旧字段废弃
    if isinstance(d.get("manual_volumes"), list):
        # 手工分册：每卷 {title, work_ids}；条目键规范化、剔除不在 work_ids 的脏项、
        # 跨卷去重（先出现者保留）。空卷保留（可先建卷再移书）。
        _seen = set()
        _vols = []
        for v in d["manual_volumes"]:
            if not isinstance(v, dict):
                continue
            _ids = []
            for w in (v.get("work_ids") or []):
                c = canonical_entry(w)
                if c and c in _entries and c not in _seen:
                    _seen.add(c)
                    _ids.append(c)
            _vols.append({"title": str(v.get("title", "") or ""), "work_ids": _ids})
        d["manual_volumes"] = _vols
    if isinstance(d.get("edit_note"), dict):
        # 丛书特定说明页（设置「封面/版式」编辑，作用于当前丛书）：
        # {file, enabled}；缺省无此键（不写、不插）。
        _en = d["edit_note"]
        d["edit_note"] = {"file": str(_en.get("file", "") or ""),
                          "enabled": bool(_en.get("enabled", False))}
    if isinstance(d.get("merge"), dict):
        # 丛书独立分册配置（批量/单部共用）；缺省无此键 = 跟随全局。
        _m = d["merge"]
        _mode = _m.get("mode") if _m.get("mode") in (
            "none", "volume", "catalog", "manual", "author", "dynasty", "ask") else "none"
        try:
            _depth = int(_m.get("depth", 2))
        except Exception:
            _depth = 2
        d["merge"] = {"mode": _mode, "depth": max(1, min(5, _depth)),
                      "name_template": str(_m.get("name_template", "") or "")}
    if isinstance(d.get("works"), list):
        norm = []
        for x in d["works"]:
            if isinstance(x, dict) and x.get("id"):
                x = dict(x)
                x["id"] = canonical_entry(x["id"])
                norm.append(x)
        d["works"] = norm
    return d


def slugify(category: str, name: str) -> str:
    try:
        from pypinyin import lazy_pinyin
        py = "".join(lazy_pinyin(name))[:20]
    except:
        py = name[:10]
    ts = datetime.now().strftime("%Y%m%d")
    base = f"{category}_{py}_{ts}"
    return base

def write_index(collections, index_path: Path) -> Path:
    """生成丛书索引（派生缓存，可安全删除；读取仍以扫描分类目录为准）。

    collections: [(path, dict), ...]；输出 [{id,name,category,path,work_count,updated_at}]。
    """
    rows = []
    for p, d in collections:
        if not isinstance(d, dict):
            continue
        rows.append({
            "id": d.get("id") or d.get("slug") or "",
            "name": d.get("name", ""),
            "category": d.get("category", ""),
            "path": str(p),
            "work_count": len(d.get("work_ids", []) or []),
            "updated_at": d.get("updated_at"),
        })
    rows.sort(key=lambda r: (r["category"], r["name"]))
    ip = Path(index_path)
    ip.parent.mkdir(parents=True, exist_ok=True)
    ip.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return ip


class Collection:
    def __init__(self, cid: str, name: str, category: str, tags=None, works=None, source: str="official", work_groups=None, manual_volumes=None, merge=None, work_notes=None):
        self.id = cid
        self.name = name
        self.category = category
        self.tags = tags or []
        self.work_ids = [canonical_entry(w) for w in (works or []) if w]
        self.source = source or "official"     # 集合级默认源: official|xml
        self.work_sources = {}                 # 单书级覆盖 {work_id: official|xml}
        self.work_groups = {canonical_work(_work_of(k)): v for k, v in (work_groups or {}).items()}  # {work_id: 册标签}（按册分册用）
        self.work_notes = {canonical_work(_work_of(k)): str(v) for k, v in (work_notes or {}).items() if str(v or "").strip()}  # 书籍注释（仅展示）
        self.manual_volumes = [                # 手工分册：[{title, work_ids}]，顺序=册序
            {"title": str(v.get("title", "") or ""),
             "work_ids": [canonical_entry(w) for w in (v.get("work_ids") or []) if w]}
            for v in (manual_volumes or []) if isinstance(v, dict)
        ]
        self.merge = dict(merge) if isinstance(merge, dict) else None  # 独立分册配置；None=跟随全局
        self.xml_options = {}                  # 链路B选项 {page,font_lang,engine}
        self.created_at = datetime.utcnow().isoformat()+"Z"
        self.updated_at = self.created_at
        self.last_publish_at = None
        self.last_publish_dir = None

    def to_dict(self):
        d = {
            "id": self.id, "slug": self.id, "name": self.name,
            "category": self.category, "tags": self.tags,
            "work_ids": self.work_ids,
            "works": [{"id": w} for w in self.work_ids],
            "source": self.source, "work_sources": self.work_sources,
            "work_groups": self.work_groups,
            "manual_volumes": self.manual_volumes,
            "xml_options": self.xml_options,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "last_publish_at": self.last_publish_at,
            "last_publish_dir": self.last_publish_dir
        }
        if self.merge:
            d["merge"] = self.merge
        if self.work_notes:
            d["work_notes"] = self.work_notes
        return d

    @staticmethod
    def load(path: Path):
        return normalize_collection(json.loads(path.read_text(encoding="utf-8")))

    def save(self, collections_dir: Path):
        cat_dir = collections_dir / self.category
        cat_dir.mkdir(parents=True, exist_ok=True)
        # filename: name.json, handle duplicate
        fname = f"{self.name}.json"
        target = cat_dir / fname
        if target.exists():
            # add suffix
            base = target.stem
            i=1
            while target.exists():
                target = cat_dir / f"{base}_{i}.json"
                i+=1
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return target

def create_collection(name: str, category: str, tags, work_ids: list[str], source: str="official", work_groups=None, manual_volumes=None, work_notes=None) -> Collection:
    cid = slugify(category, name)
    c = Collection(cid, name, category, tags, work_ids, source=source, work_groups=work_groups, manual_volumes=manual_volumes, work_notes=work_notes)
    return c
