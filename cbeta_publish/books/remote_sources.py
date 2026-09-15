# -*- coding: utf-8 -*-
"""远端更新源表（mulu 元数据）。权威源见 mulu/REMOTE_SOURCES.md。

URL **单源**：不在本文件写 URL 字面量，统一引用共享层 `cbeta_fetch.REMOTE_URLS`
（与 xml2pdf 同源）。供 RemoteManager 批量检查/更新；更新前旧文件快照到
mulu/backup/last/。
"""
from pathlib import Path

from cbeta_publish._vendor import cbeta_fetch as cf

ROOT = Path(__file__).resolve().parents[2]

# (key, 分类, 本地相对路径, REMOTE_URLS 键)
# 分类用于备份/展示：部类 / 作者 / 经录 / 朝代 / 刊本
_SPEC = [
    # 官方范围清单（scope-selector，cbdata/stable 定版）——权威
    ("category", "部类", "mulu/category.json", "category_json"),
    ("dynasty", "朝代", "mulu/dynasty-works.json", "dynasty_works"),
    ("vol", "刊本", "mulu/vol.json", "vol_json"),
    ("creators_strokes", "作者", "mulu/creators-by-strokes-with-works.json", "creators_by_strokes"),
    ("creators_alias", "作者", "mulu/all-creators-with-alias.json", "all_creators"),
    # GitHub 罐头（备用/兼容）
    ("bulei_txt", "部类", "mulu/bulei.txt", "bulei"),
    ("sutralist", "经录", "mulu/SutraList.json", "sutralist_json"),
    ("sutra_mapping", "经录", "mulu/sutra_mapping.txt", "sutra_mapping"),
]


def url_of(key: str) -> str:
    """按 SOURCES key 取共享层单源 URL。"""
    for k, _cat, _rel, shared in _SPEC:
        if k == key:
            return cf.REMOTE_URLS[shared]
    raise KeyError(key)


# 展开成现有 4 元组 (key, 分类, url, 本地相对路径)，下游无需改动
SOURCES = [(key, cat, cf.REMOTE_URLS[shared], rel) for key, cat, rel, shared in _SPEC]


def local_path(rel: str) -> Path:
    return ROOT / rel
