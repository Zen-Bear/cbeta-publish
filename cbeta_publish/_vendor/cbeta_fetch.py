# -*- coding: utf-8 -*-
"""cbeta_fetch —— CBETA 官方资源下载共享层（纯标准库）。

被 xml2pdf（`pycbeta`）与 publish（`cbeta_publish`）以 **vendored** 方式复用：
URL 模板 / work id 大小写规范化 / catalog 查表 / 文件与 zip 下载 / 条件更新。

约定：
- **只依赖 Python 标准库**（urllib/zipfile/ssl/...），不 import 任何宿主项目。
- **无目录布局假设、无打印**；落盘路径由调用方给。
- work id：canon 大写、编号(no) **保留原大小写**（CBETA XML 文件名与电子书端点
  大小写敏感，如 `TXa001`/`T0128a`/`JB005`）。

同步：本文件是唯一事实源；宿主项目内的副本请用 `tools/sync_into.py` 同步，勿手改。
"""

__version__ = "0.1.2"

import os
import re
import ssl
import time
import zipfile
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

USER_AGENT = "cbeta-fetch/0.1"

# ---------------------------------------------------------------- work id 语法
CANON = r"(?:CC|DA|GA|GB|LC|TX|YP|ZS|ZW|[A-Z])"
WORK_PART = r"(?:\d{4}[a-zA-Z]?|[ABa]\d{3})"
_CANON_RE = re.compile(rf"^({CANON})(.*)$", re.IGNORECASE)
_WORK_ID_RE = re.compile(rf"\A{CANON}{WORK_PART}\Z")


def is_work_id(s: str) -> bool:
    """是否 CBETA 佛典編號（`T0349`/`A1057`/`T0128a`/`TXa001`/`JB005`）。大小写宽容。"""
    return bool(s) and bool(_WORK_ID_RE.match((s or "").strip().upper()))


def parse_work_id(work_id: str) -> Tuple[str, str]:
    """`(canon, no)`：canon **转大写**，no **保留原大小写**。非法抛 ValueError。"""
    m = _CANON_RE.match((work_id or "").strip())
    if not m:
        raise ValueError(f"invalid work id: {work_id!r}")
    return m.group(1).upper(), m.group(2)


# ---------------------------------------------------------------- URL 模板
#: 官方作品文件下载模板（占位：`{id}`=canon+no、`{canon}`、`{vol}`/`{file}` 仅 xml）
DEFAULT_DOWNLOADS = {
    "xml": "https://raw.githubusercontent.com/cbeta-org/xml-p5/master/{canon}/{canon}{vol}/{file}",
    "html": "https://cbdata.dila.edu.tw/stable/download/html/{id}.html.zip",
    "docx": "https://cbdata.dila.edu.tw/stable/download/docx/{canon}/{id}.zip",
    "epub": "https://cbdata.dila.edu.tw/stable/download/epub/{canon}/{id}.epub",
    "odt": "https://cbdata.dila.edu.tw/stable/download/odt/{canon}/{id}.zip",
    "txt_notes": "https://cbdata.dila.edu.tw/stable/download/text-with-notes/{id}.txt.zip",
    "pdf": "https://cbdata.dila.edu.tw/stable/download/pdf/{canon}/{id}.pdf",
}

#: 作品工作格式（不含 pdf —— pdf 是生成物；也不含 xml 基线以外的 figures，figures 属 xml2pdf）
ALL_FORMATS = ("xml", "html", "docx", "epub", "txt_notes", "odt")

#: 元数据/字库更新源（**单源**）：两端 source 表只引用 key，不写 URL 字面量
REMOTE_URLS = {
    "sutra_mapping":
        "https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/sutralist/sutralist.txt",
    "bulei":
        "https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/bulei/bulei.txt",
    "sutralist_json":
        "https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/nav/SutraList.json",
    "sutralist_txt":
        "https://raw.githubusercontent.com/heavenchou/cbwork-bin/master/cbreader2X/nav/SutraList.txt",
    "category_json":
        "https://cbdata.dila.edu.tw/stable/download/scope-selector/category.json",
    "dynasty_works":
        "https://cbdata.dila.edu.tw/stable/download/scope-selector/dynasty-works.json",
    "vol_json":
        "https://cbdata.dila.edu.tw/stable/download/scope-selector/vol.json",
    "creators_by_strokes":
        "https://cbdata.dila.edu.tw/stable/download/scope-selector/creators-by-strokes-with-works.json",
    "all_creators":
        "https://cbdata.dila.edu.tw/stable/download/all-creators-with-alias.json",
    "gaiji":
        "https://raw.githubusercontent.com/cbeta-org/cbeta_gaiji/master/cbeta_gaiji.json",
    "sanskrit":
        "https://raw.githubusercontent.com/cbeta-org/cbeta_gaiji/master/cbeta_sanskrit.json",
    "supplement_ttf":
        "https://raw.githubusercontent.com/cbeta-org/cbeta-fonts/main/CBETASupplement.ttf",
}


# ---------------------------------------------------------------- catalog
def catalog_lookup(catalog: str, canon: str, no: str) -> List[Dict]:
    """查 `sutra_mapping.txt`（8 列：`canon,vol,no,juan,first_juan,first_lb,name,byline`）。

    canon/no **大小写不敏感**匹配（catalog 里字母后缀大小写不统一：`TX,00,a001`、
    `T,02,0128a`、`J,15,B005`），返回项**保留 catalog 原始大小写**：
    `[{"vol","no","file","title"}]`（同一编号多册全返）。文件缺失/非法 → `[]`。
    """
    if not catalog or not os.path.isfile(catalog):
        return []
    cu, nl = (canon or "").upper(), (no or "").lower()
    out: List[Dict] = []
    try:
        f = open(catalog, encoding="utf-8")
    except OSError:
        return []
    with f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 3 and parts[0].upper() == cu \
                    and parts[2].lower() == nl:
                vol, stored_no = parts[1], parts[2]
                title = parts[6].strip() if len(parts) >= 7 else ""
                out.append({"vol": vol, "no": stored_no,
                            "file": f"{parts[0]}{vol}n{stored_no}.xml",
                            "title": title})
    return out


def canonical_work_id(work_id: str, catalog: Optional[str] = None) -> str:
    """按 catalog 原始大小写规范化 work id（`canon` 大写 + `no` 原样）。
    catalog 未命中（离线/本地/未知）→ 原样返回。"""
    try:
        canon, no = parse_work_id(work_id)
    except ValueError:
        return work_id
    recs = catalog_lookup(catalog, canon, no) if catalog else []
    if recs and recs[0].get("no"):
        return f"{canon}{recs[0]['no']}"
    return work_id


# ---------------------------------------------------------------- HTTP
def _ctx():
    """cbdata 证书缺 Subject Key Identifier：公共数据集用 unverified context。"""
    try:
        return ssl._create_unverified_context()
    except Exception:  # noqa: BLE001
        return None


def _request(url: str, headers: Optional[Dict[str, str]] = None,
             method: Optional[str] = None):
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    return urllib.request.Request(url, headers=h, method=method)


def download(url: str, dest: str, *, timeout: int = 90, retries: int = 2,
             unzip: bool = False, headers: Optional[Dict[str, str]] = None) -> bool:
    """下载 `url` → `dest`。文件写入为**原子替换**（`.part` → `os.replace`）。

    - `unzip=False`：`dest` 是**文件路径**（父目录自动创建）。
    - `unzip=True`：`dest` 是**目录**，下载 zip 后平展解压（zip 不留）。
    失败返回 False（重试 `retries` 次）。
    """
    ctx = _ctx()
    for attempt in range(max(1, retries + 1)):
        try:
            with urllib.request.urlopen(
                    _request(url, headers), timeout=timeout, context=ctx) as r:
                data = r.read()
            if unzip:
                return _unzip_bytes(data, dest)
            d = os.path.dirname(os.path.abspath(dest))
            if d:
                os.makedirs(d, exist_ok=True)
            tmp = dest + f".part{os.getpid()}"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
            return True
        except Exception:  # noqa: BLE001
            time.sleep(min(1.0 * (attempt + 1), 3.0))
    return False


def _unzip_bytes(data: bytes, dest_dir: str) -> bool:
    import io as _io
    try:
        os.makedirs(dest_dir, exist_ok=True)
        with zipfile.ZipFile(_io.BytesIO(data)) as z:
            _extract(z, dest_dir)
        return True
    except (zipfile.BadZipFile, OSError):
        return False


def _extract(zf: "zipfile.ZipFile", dest_dir: str) -> None:
    for n in zf.namelist():
        if n.endswith("/") or n.endswith("\\"):
            continue
        base = os.path.basename(n.replace("\\", "/"))
        if not base:
            continue
        with zf.open(n) as src, open(os.path.join(dest_dir, base), "wb") as dst:
            dst.write(src.read())


def unzip_flat(zip_path: str, dest_dir: str) -> None:
    """平展解压：忽略 zip 自带目录层次，所有文件按 basename 写入 `dest_dir`（防 zip-slip）。"""
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        _extract(z, dest_dir)


def fetch_if_changed(url: str, dest: str, *, etag: Optional[str] = None,
                     last_modified: Optional[str] = None, timeout: int = 90,
                     retries: int = 1) -> Tuple[str, Optional[str], Optional[str]]:
    """条件 GET → `dest`（原子）。返回 `(status, etag, last_modified)`，
    `status ∈ {"downloaded","not-modified","failed"}`。"""
    ctx = _ctx()
    headers: Dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    for attempt in range(max(1, retries + 1)):
        try:
            with urllib.request.urlopen(
                    _request(url, headers), timeout=timeout, context=ctx) as r:
                data = r.read()
            d = os.path.dirname(os.path.abspath(dest))
            if d:
                os.makedirs(d, exist_ok=True)
            tmp = dest + f".part{os.getpid()}"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
            return ("downloaded", r.headers.get("ETag"),
                    r.headers.get("Last-Modified"))
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return ("not-modified", etag, last_modified)
            time.sleep(min(1.0 * (attempt + 1), 3.0))
        except Exception:  # noqa: BLE001
            time.sleep(min(1.0 * (attempt + 1), 3.0))
    return ("failed", None, None)


def probe_info(url: str, *, etag: Optional[str] = None,
               last_modified: Optional[str] = None,
               timeout: int = 20) -> Dict:
    """不落盘探针（HEAD + 条件头），返回详情 dict（比 `probe` 多 `size`）。

    返回 `{"status": "changed"|"not-modified"|"failed", "etag", "last_modified",
    "size"}`；`size` 为远端 `Content-Length`（int，缺失为 None）。
    供宿主做「大小一致即跳过」类判断；`probe` 保持三元组兼容。
    """
    ctx = _ctx()
    headers: Dict[str, str] = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    try:
        req = urllib.request.Request(url, headers=headers, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            cl = r.headers.get("Content-Length")
            return {"status": "changed", "etag": r.headers.get("ETag"),
                    "last_modified": r.headers.get("Last-Modified"),
                    "size": int(cl) if (cl and cl.isdigit()) else None}
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return {"status": "not-modified", "etag": etag,
                    "last_modified": last_modified, "size": None}
        return {"status": "failed", "etag": None, "last_modified": None, "size": None}
    except Exception:  # noqa: BLE001
        return {"status": "failed", "etag": None, "last_modified": None, "size": None}


def probe(url: str, *, etag: Optional[str] = None,
          last_modified: Optional[str] = None,
          timeout: int = 20) -> Tuple[str, Optional[str], Optional[str]]:
    """不落盘探针（HEAD + 条件头）。返回 `(status, etag, last_modified)`，
    `status ∈ {"changed","not-modified","failed"}`。需要 `size` 时用 `probe_info`。"""
    r = probe_info(url, etag=etag, last_modified=last_modified, timeout=timeout)
    return (r["status"], r["etag"], r["last_modified"])
