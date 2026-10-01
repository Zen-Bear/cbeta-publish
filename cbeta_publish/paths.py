# -*- coding: utf-8 -*-
"""运行时路径：统一「工程根 / 数据根」，兼容源码运行与 PyInstaller 冻结。

- 源码运行：数据根 = 仓库根（本文件 parents[1]）。
- 冻结运行（onedir/onefile）：数据根 = **exe 所在目录**，便于把 config/mulu/
  collections/输出目录放在 exe 同级，拷走即用（可写、持久）。

包内只读资源（`cbeta_publish/gui/theme/...`）仍用 `Path(__file__).parent` 定位，
PyInstaller 会随包收集，`__file__` 指向包内，不受本函数影响。
"""
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """可写数据根目录（config/、mulu/、assets/、collections/、输出目录等）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]
