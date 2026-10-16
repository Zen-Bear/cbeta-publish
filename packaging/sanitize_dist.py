# -*- coding: utf-8 -*-
"""发布包出厂化：清掉不该随包分发的「打包机本机信息」。

用法（``build_exe.ps1`` 第 6.5 步自动调用；也可单独跑）：

```bat
python packaging\\sanitize_dist.py <dist_app_dir>
```

做三件事（幂等，重复跑无副作用）：

1. ``config/app.default.json`` 的 ``official_library.root`` 置空——``build_exe.ps1`` 只改写
   「目录类」键，这个键会残留打包机的本地官方库路径（如 ``E:\\CBETA\\2026r2``），
   新用户首启就会带上一台不存在的本地库。
2. 删 ``mulu/backup/{last,original}/app.json``——那是打包机自己的 ``config/app.json``
   快照；随包发出会让新用户点「恢复原始」恢复成打包机的配置（含打包机路径）。
   目录内其它 mulu 数据快照保留（「恢复」「目录变更对比」仍可用；用户首启后
   自己保存配置时会生成自己的 ``app.json`` 快照）。
3. 清空包内预设 ``xml2pdf/presets/*.json`` 里**指向本机的绝对路径**
   （``source.xml_dir``/``cbeta_ebook``/``baselines.*``/``baselines_root``/``out_dir``/
   ``verify_root``、``annotations.file``）：相对路径与其它值一律不动；
   带注释等非 JSON 的预设（如 ``config.factory.json``）不猜、原样保留。
"""
import json
import re
import sys
from pathlib import Path

#: 「本机绝对路径」判据：盘符（``C:\\`` / ``D:/``）、UNC（``\\\\server``）、根（``/``）
ABS_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/)")

#: ``source`` 下可能指向本机的键（``baselines`` 逐键另判）
SOURCE_KEYS = ("xml_dir", "cbeta_ebook", "baselines_root", "out_dir", "verify_root")


def _clear_abs_paths(mapping, keys):
    """``mapping`` 中 ``keys`` 里值为本机绝对路径的置空；返回改动条数。"""
    n = 0
    for k in keys:
        v = mapping.get(k)
        if isinstance(v, str) and v.strip() and ABS_PATH_RE.match(v.strip()):
            mapping[k] = ""
            n += 1
    return n


def sanitize_config_default(dist):
    """``config/app.default.json`` 的 ``official_library.root`` 置空；返回 True＝改过。"""
    p = Path(dist) / "config" / "app.default.json"
    if not p.is_file():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except ValueError:
        return False
    lib = data.get("official_library") if isinstance(data, dict) else None
    if not isinstance(lib, dict) or not lib.get("root"):
        return False
    lib["root"] = ""
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def remove_backup_config(dist):
    """删包内 ``mulu/backup/{last,original}/app.json``；返回被删的 Path 列表。"""
    removed = []
    for sub in ("last", "original"):
        p = Path(dist) / "mulu" / "backup" / sub / "app.json"
        if p.is_file():
            p.unlink()
            removed.append(p)
    return removed


def sanitize_preset(path):
    """清一个预设文件里的本机绝对路径；返回改动条数（非 JSON／不可读→0）。"""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError:
        return 0
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return 0
    if not isinstance(data, dict):
        return 0
    n = 0
    src = data.get("source")
    if isinstance(src, dict):
        n += _clear_abs_paths(src, SOURCE_KEYS)
        bl = src.get("baselines")
        if isinstance(bl, dict):
            n += _clear_abs_paths(bl, tuple(bl))
    ann = data.get("annotations")
    if isinstance(ann, dict):
        n += _clear_abs_paths(ann, ("file",))
    if n:
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8-sig" if had_bom else "utf-8")
    return n


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    dist = Path(argv[1]).resolve()
    if not (dist / "config").is_dir():
        print(f"[sanitize] 不是发布包目录（缺 config/）：{dist}")
        return 1
    if sanitize_config_default(dist):
        print("[sanitize] config/app.default.json: official_library.root 已置空")
    for p in remove_backup_config(dist):
        print(f"[sanitize] 删除本机配置快照：{p.relative_to(dist)}")
    presets = dist / "xml2pdf" / "presets"
    if presets.is_dir():
        for p in sorted(presets.glob("*.json")):
            n = sanitize_preset(p)
            if n:
                print(f"[sanitize] 清本机绝对路径 {n} 处："
                      f"{(Path('xml2pdf') / 'presets' / p.name)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
