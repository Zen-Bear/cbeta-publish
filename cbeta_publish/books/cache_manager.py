# -*- coding: utf-8 -*-
"""缓存统计与清理（cbeta_ebooks / cbeta_xml / 输出中间文件）。"""
import shutil
from pathlib import Path


def dir_stats(path) -> dict:
    """返回 {'files': n, 'bytes': total}；目录不存在返回 0。"""
    p = Path(path)
    if not p.exists():
        return {"files": 0, "bytes": 0}
    files = 0
    total = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                files += 1
                total += f.stat().st_size
        except OSError:
            continue
    return {"files": files, "bytes": total}


def human(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


def clean(path) -> dict:
    """删除目录内容（保留目录本身）；返回 {'removed_files', 'removed_bytes'}。"""
    p = Path(path)
    st = dir_stats(p)
    if not p.exists():
        return {"removed_files": 0, "removed_bytes": 0}
    for child in list(p.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except OSError:
            continue
    return {"removed_files": st["files"], "removed_bytes": st["bytes"]}
