# -*- coding: utf-8 -*-
"""校验通过记录库：work×fmt → 上次通过时的校验指纹。

全局 JSON（默认 `config/verify_records.json`，gitignored，不进版本库），
**只记录 pass**：fail/undetermined/error 不写库；环境类失败不删旧记录。
一次“通过”只对一组输入成立，指纹由上游 `pycbeta.verify.verify_fingerprint`
给出；指纹对不上（XML/预设/基线/阈值/实现任一变化）即视为过期重验。

跳过条件（调用方判定，本模块只存取）：
  库中有该 (work, fmt) 的 pass 记录、现算指纹与记录一致、
  库中产物存在、复用开关开。
"""
import json
import os
from datetime import datetime
from pathlib import Path

SCHEMA = 1


def records_path(config=None) -> Path:
    """记录库路径：config/verify_records.json（与 app.json 同目录，可写）。"""
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
    return base / "verify_records.json"


def _empty():
    return {"schema": SCHEMA, "entries": {}}


def load(path) -> dict:
    """读库；缺失/损坏回空库（不抛）。"""
    try:
        p = Path(path)
        if not p.is_file():
            return _empty()
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        if not isinstance(d, dict) or not isinstance(d.get("entries"), dict):
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
        print("verify cache save fail", e)
        return False


def get(path, work: str, fmt: str):
    """取某 (work, fmt) 的通过记录；无则 None。"""
    try:
        e = load(path).get("entries", {}).get(str(work), {}).get(str(fmt))
        return dict(e) if isinstance(e, dict) else None
    except Exception:
        return None


def is_fresh(path, work: str, fmt: str, fingerprint) -> bool:
    """记录存在、指纹一致即新鲜；指纹为空/对不上/库损坏一律不新鲜。"""
    if not fingerprint:
        return False
    e = get(path, work, fmt)
    return bool(e) and e.get("fingerprint") == fingerprint


def record_pass(path, work: str, fmt: str, fingerprint: str, extra=None) -> bool:
    """写入一条通过记录（覆盖旧值）；fingerprint 为空拒绝写入。"""
    if not fingerprint:
        return False
    try:
        d = load(path)
        works = d.setdefault("entries", {})
        fp = str(fingerprint)
        entry = {
            "fingerprint": fp,
            "fp_version": fp.split(":", 1)[0] if ":" in fp else fp,
            "verified_at": datetime.now().isoformat(timespec="seconds"),
        }
        if isinstance(extra, dict):
            entry.update({k: v for k, v in extra.items()
                          if k not in entry})
        works.setdefault(str(work), {})[str(fmt)] = entry
        return _save(path, d)
    except Exception as e:
        print("verify cache record fail", e)
        return False


def drop(path, work: str, fmt: str = None) -> bool:
    """删除记录（fmt 为 None 则删整部书）；用于真实校验失败后的清理。"""
    try:
        d = load(path)
        works = d.get("entries", {})
        if str(work) not in works:
            return True
        if fmt is None:
            works.pop(str(work), None)
        else:
            works[str(work)].pop(str(fmt), None)
            if not works[str(work)]:
                works.pop(str(work), None)
        return _save(path, d)
    except Exception as e:
        print("verify cache drop fail", e)
        return False


def clear(path) -> bool:
    """清空整个通过记录库（缓存页「清理通过记录」用；校验目录不动）。"""
    return _save(path, _empty())


def stats(path) -> dict:
    """返回 {"works": 书数, "entries": 条目数}；读失败回 0。"""
    try:
        entries = load(path).get("entries", {})
        return {"works": len(entries),
                "entries": sum(len(v) for v in entries.values()
                               if isinstance(v, dict))}
    except Exception:
        return {"works": 0, "entries": 0}
