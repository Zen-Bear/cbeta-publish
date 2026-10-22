# -*- coding: utf-8 -*-
"""文件名清洗：非法字符替换、空白压缩、去首尾点/空格；空则兜底。

与 `main_window._safe_name` 原行为一致（该方法是本函数的薄包装）。
只用于**文件名**；显示名保持用户原文。
"""
import re

_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_SPACES = re.compile(r"\s+")


def safe_name(label, fallback="未分册") -> str:
    s = _ILLEGAL.sub("_", (label or "").strip())
    s = _SPACES.sub(" ", s).strip(" ._")
    return s or fallback
