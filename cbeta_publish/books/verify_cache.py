# -*- coding: utf-8 -*-
"""校验通过记录库：work×fmt → 上次通过时的校验指纹（输入集模型）。

全局 JSON（默认 `config/verify_records.json`，gitignored，不进版本库），
**只记录自动接受项**（人工放行不记库）：fail/undetermined/error 不写库；
环境类失败不删旧记录。

每条记录挂一组输入集（XML 源基名有序列表）：
`entries[work][fmt] = {"accept": "strict"|"notes_only",
"sets": [{"fingerprint": fp, "inputs": [xml基名…],
"verified_at": ..., "product": ...}]}`。
一次"通过"只对一组输入成立；指纹由上游 `pycbeta.verify.verify_fingerprint`
给出；指纹对不上（XML/预设/基线/阈值/实现任一变化）或输入集变化即视为过期重验。

跳过条件（调用方判定，本模块只存取）：
  库中有该 (work, fmt) 的某输入集记录、现算指纹与记录一致且输入集相同、
  库中产物存在、复用开关开。
"""
import json
import os
from datetime import datetime
from pathlib import Path

SCHEMA = 2


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


def _entry_sets(entry) -> list:
    """记录内的输入集列表；兼容 schema1 遗留（{"fingerprint": …} 视为单集）。

    每集补 `juan`（卷标签，缺省 ""＝整本），供子集/整本隔离。
    """
    if not isinstance(entry, dict):
        return []
    sets = entry.get("sets")
    if isinstance(sets, list):
        out = []
        for s in sets:
            if isinstance(s, dict):
                s = dict(s)
                s.setdefault("juan", "")
                out.append(s)
        return out
    if entry.get("fingerprint"):
        return [{"fingerprint": entry.get("fingerprint"), "inputs": [], "juan": ""}]
    return []


def is_fresh(path, work: str, fmt: str, fingerprint, inputs=None, juan="") -> bool:
    """记录中存在输入集一致且指纹一致即新鲜；否则不新鲜。

    - fingerprint 为空一律不新鲜；
    - inputs 为 None 时只比指纹（兼容旧调用与 schema1 记录）；
    - inputs 为列表时，要求某集的 inputs 与之**有序相等**且指纹一致；
    - juan（卷标签，`""`＝整本）须相等：子集与整本、不同子集互不命中。
    """
    if not fingerprint:
        return False
    j = str(juan or "")
    e = get(path, work, fmt)
    for s in _entry_sets(e):
        if s.get("fingerprint") != fingerprint:
            continue
        if str(s.get("juan") or "") != j:
            continue
        if inputs is None:
            return True
        try:
            if [str(x) for x in (s.get("inputs") or [])] == [str(x) for x in inputs]:
                return True
        except Exception:
            continue
    return False


def record_pass(path, work: str, fmt: str, fingerprint: str, extra=None) -> bool:
    """写入一条通过记录（按输入集合并旧值）；fingerprint 为空拒绝写入。

    extra 可带 `inputs`（XML 源基名有序列表）、`accept`（"strict"/"notes_only"，
    缺省 strict）、`product`、`juan`（卷标签，缺省 ""＝整本）。集身份＝(inputs, juan)：
    同 inputs 同 juan 的集被覆盖，不同 inputs 或不同 juan 追加。
    """
    if not fingerprint:
        return False
    try:
        fp = str(fingerprint)
        inputs = []
        accept = "strict"
        juan = ""
        if isinstance(extra, dict):
            try:
                inputs = [str(x) for x in (extra.get("inputs") or [])]
            except Exception:
                inputs = []
            if extra.get("accept") in ("strict", "notes_only"):
                accept = extra.get("accept")
            juan = str(extra.get("juan") or "")
        d = load(path)
        works = d.setdefault("entries", {})
        entry = works.setdefault(str(work), {}).setdefault(str(fmt), {})
        entry["accept"] = accept
        sets = entry.setdefault("sets", [])
        if not isinstance(sets, list):
            sets = entry["sets"] = []
        rec = {
            "fingerprint": fp,
            "inputs": inputs,
            "juan": juan,
            "verified_at": datetime.now().isoformat(timespec="seconds"),
        }
        prod = (extra or {}).get("product") if isinstance(extra, dict) else None
        if prod:
            rec["product"] = str(prod)
        for i, s in enumerate(sets):
            if isinstance(s, dict) and [str(x) for x in (s.get("inputs") or [])] == inputs \
                    and str(s.get("juan") or "") == juan:
                sets[i] = rec
                break
        else:
            sets.append(rec)
        entry["fp_version"] = fp.split(":", 1)[0] if ":" in fp else fp
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
