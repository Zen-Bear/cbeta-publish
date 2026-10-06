# -*- coding: utf-8 -*-
"""官方书「备齐水位」库：work×fmt → 上次备齐时看到的源 mtime + 本地库版本。

全局 JSON（默认 `config/official_state.json`，gitignored，不进版本库），
用于判断官方电子书是否过期（合并/ZIP/导出前「缺/过期」备齐）：

  过期 = 产物缺失
        ∨ 工作根 XML 源较「水位」新
        ∨ 本地库版本名（`official_library.root` 目录名）变化

水位按 `(work, fmt)` 记录：某格式下载失败不影响其它格式；换库后成功的项更新版本，
失败项保持旧版本 → 下次只重试失败项。无水位（升级后首跑）回退「源 mtime > 产物 mtime」，
不触发版本判定（避免首跑全量重下）。
"""
import json
import os
from datetime import datetime
from pathlib import Path

SCHEMA = 1


def state_path(config=None) -> Path:
    """水位库路径：`config/official_state.json`（与 app.json 同目录，可写）。"""
    from cbeta_publish.paths import app_root
    base = None
    try:
        cp = (config or {}).get("_config_path") if isinstance(config, dict) else None
        if cp:
            base = Path(cp).parent
    except Exception:
        base = None
    if base is None:
        base = Path(app_root()) / "config"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return base / "official_state.json"


def _empty():
    return {"schema": SCHEMA, "works": {}}


def load(path) -> dict:
    """读库；缺失/损坏回空库（不抛）。"""
    try:
        p = Path(path)
        if not p.is_file():
            return _empty()
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        if not isinstance(d, dict) or not isinstance(d.get("works"), dict):
            return _empty()
        return d
    except Exception:
        return _empty()


def _save(path, data: dict) -> bool:
    """原子写（同目录 tmp + os.replace）；失败返回 False。"""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(str(tmp), str(p))
        return True
    except Exception as e:
        print("official state save fail", e)
        return False


def get(path, work: str, fmt: str):
    """取某 (work, fmt) 的水位；无则 None。"""
    try:
        e = load(path).get("works", {}).get(str(work), {}).get(str(fmt))
        return dict(e) if isinstance(e, dict) else None
    except Exception:
        return None


def record(path, work: str, fmt: str, src_mtime=None, lib_version="") -> bool:
    """写入一条水位（覆盖旧值）。src_mtime 为 None 时不写该键（仅记版本）。"""
    try:
        d = load(path)
        works = d.setdefault("works", {})
        entry = {
            "lib_version": str(lib_version or ""),
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        if src_mtime is not None:
            entry["src_mtime"] = float(src_mtime)
        works.setdefault(str(work), {})[str(fmt)] = entry
        return _save(path, d)
    except Exception as e:
        print("official state record fail", e)
        return False


def mark_checked(config, work: str, fmt: str, path=None) -> bool:
    """备齐成功后记水位：现算源 mtime 与本地库版本，写入该 (work, fmt)。"""
    src = None
    ver = ""
    try:
        from cbeta_publish.books import xml2pdf_bridge as _xb
        src = _xb.source_mtime(config, work)
    except Exception:
        src = None
    try:
        from cbeta_publish.books import official_ebook_source as _oes
        ver = _oes.library_version(config)
    except Exception:
        ver = ""
    return record(path or state_path(config), work, fmt, src, ver)


def stale(config, work: str, fmt: str, dest_dir, path=None) -> bool:
    """该 (work, fmt) 官方产物是否过期（需下载/更新）。"""
    from cbeta_publish.books import official_ebook_source as _oes
    p = path or state_path(config)
    dest = _oes.local_path(work, fmt, dest_dir)
    try:
        if not Path(dest).exists():
            return True
    except Exception:
        return True
    cur_ver = _oes.library_version(config)
    cur_src = None
    try:
        from cbeta_publish.books import xml2pdf_bridge as _xb
        cur_src = _xb.source_mtime(config, work)
    except Exception:
        cur_src = None
    entry = get(p, work, fmt)
    if entry:
        ev = entry.get("lib_version")
        if ev is not None and ev != cur_ver:
            return True
        wm = entry.get("src_mtime")
        if cur_src is not None and wm is not None and cur_src > float(wm) + 1e-6:
            return True
        return False
    # 无水位：回退「源 mtime > 产物 mtime」，不触发版本判定
    if cur_src is not None:
        return cur_src > _oes.product_mtime(dest) + 1e-6
    return False


def clear(path) -> bool:
    """清空水位库。"""
    return _save(path, _empty())


def stats(path) -> dict:
    """返回 {"works": 书数, "entries": 条目数}；读失败回 0。"""
    try:
        works = load(path).get("works", {})
        return {"works": len(works),
                "entries": sum(len(v) for v in works.values()
                               if isinstance(v, dict))}
    except Exception:
        return {"works": 0, "entries": 0}
