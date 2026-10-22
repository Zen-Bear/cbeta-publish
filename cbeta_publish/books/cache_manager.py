# -*- coding: utf-8 -*-
"""缓存统计与清理（cbeta_ebooks / cbeta_xml / 输出中间文件）。"""
import shutil
from pathlib import Path

from cbeta_publish.paths import app_root


def _refuse_reason(p: Path) -> str:
    """危险清理目标：盘根、程序根（或其上级）、用户主目录（或其上级）、程序数据目录。"""
    try:
        rp = p.resolve()
    except OSError:
        return ""
    if rp.parent == rp:
        return "盘根"
    if p.is_file():
        return "文件（不是目录）"
    try:
        root = app_root().resolve()
    except OSError:
        root = None
    if root is not None:
        if rp == root or root.is_relative_to(rp):
            return "程序根或其上级目录"
        # 程序自身数据（配置/目录数据/丛书/资源）绝不允许被「清理缓存」碰到
        for name in ("config", "mulu", "collections", "assets"):
            crit = (root / name).resolve()
            if rp == crit or rp.is_relative_to(crit):
                return f"程序数据目录（{name}/）"
    try:
        home = Path.home().resolve()
    except OSError:
        home = None
    if home is not None and (rp == home or home.is_relative_to(rp)):
        return "用户主目录或其上级目录"
    return ""


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
    """删除目录内容（保留目录本身）；返回 {'removed_files', 'removed_bytes'}。

    危险目标直接拒绝（抛 ValueError）：clean 会清空目录**全部子项**，
    盘根/程序根/用户主目录会删掉整盘或程序本身。
    """
    p = Path(path)
    reason = _refuse_reason(p)
    if reason:
        raise ValueError(f"拒绝清理 {p}：目标是{reason}")
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
    # 按“清理前 - 清理后”统计实际删除量：占用中的文件/权限失败不会虚报
    left = dir_stats(p)
    return {"removed_files": max(0, st["files"] - left["files"]),
            "removed_bytes": max(0, st["bytes"] - left["bytes"])}
