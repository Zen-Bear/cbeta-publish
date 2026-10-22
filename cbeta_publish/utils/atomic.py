# -*- coding: utf-8 -*-
"""原子写：同目录临时文件 + `os.replace`，避免进程中断留下半截 JSON。

用户数据（丛书、分类、标签、配置）一律经这里落盘；续写失败时抛异常，
由调用方决定「保留脏标记 + 提示」，不要吞掉。
"""
import json
import os
import tempfile
from pathlib import Path


def atomic_write_text(path, text, encoding="utf-8") -> Path:
    """写文本：`.<名>.<随机>.tmp` → `os.replace` 覆盖目标；失败清理 tmp 后抛出。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp 带随机后缀：同进程/双开多实例都不会撞名（对比固定 name.tmp）
    fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp",
                               dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return p


def atomic_write_json(path, data, **dumps_kw) -> Path:
    """写 JSON（默认 `ensure_ascii=False, indent=2`）。"""
    kw = {"ensure_ascii": False, "indent": 2}
    kw.update(dumps_kw)
    return atomic_write_text(path, json.dumps(data, **kw))
