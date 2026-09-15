# -*- coding: utf-8 -*-
# 繁简转换工具：OpenCC 可用时统一转简体匹配；不可用时原样返回（降级）
_t2s=None
_s2t=None
_available=False

def init():
    global _t2s, _s2t, _available
    try:
        from opencc import OpenCC
        _t2s=OpenCC("t2s")
        _s2t=OpenCC("s2t")
        _available=True
    except Exception:
        _t2s=None
        _s2t=None
        _available=False

def to_simplified(text):
    if _t2s and text:
        try:
            return _t2s.convert(text)
        except Exception:
            return text
    return text

def to_traditional(text):
    if _s2t and text:
        try:
            return _s2t.convert(text)
        except Exception:
            return text
    return text

def available():
    return _available