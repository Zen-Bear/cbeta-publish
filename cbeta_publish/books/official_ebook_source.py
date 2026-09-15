"""官方电子书下载（复用 cbeta-fetch 共享层：URL 模板 / id 规范化 / 原子下载 / zip 解压）。

- URL、id 大小写规范化、下载与解压均由 `cbeta_publish/_vendor/cbeta_fetch` 提供（勿改）。
- 目录布局（publish 自有，不共享）：`{dest_dir}/{fmt}/{canon}/{work}.{fmt}`；
  docx/odt 端点为 zip，解压到目录 `{dest_dir}/{fmt}/{canon}/{work}/`。
"""
from email.utils import parsedate_to_datetime
from pathlib import Path

from cbeta_publish._vendor import cbeta_fetch as cf
from cbeta_publish.catalog.work_id import canonical_work, catalog_path

_ZIP_FORMATS = {"docx", "odt", "html", "txt_notes"}


def canonical(work: str) -> str:
    """按 catalog 原始大小写规范化（`TXA001 → TXa001`、`T0128A → T0128a`）。"""
    return canonical_work(work)


def canon_of(work: str) -> str:
    """藏经代号（大写）：`T0001 → T`、`TXa001 → TX`、`JB005 → J`。"""
    try:
        return cf.parse_work_id(canonical(work))[0]
    except ValueError:
        return (work or "?")[0].upper()


def ebook_url(fmt: str, canon: str, work: str) -> str:
    tmpl = cf.DEFAULT_DOWNLOADS.get(fmt)
    if not tmpl:
        raise ValueError(f"unknown ebook format: {fmt}")
    return tmpl.format(canon=canon, id=work)


def dest_path(work: str, fmt: str, dest_dir) -> Path:
    """单文件格式落盘路径（布局 publish 自有）。"""
    return Path(dest_dir) / fmt / canon_of(work) / f"{canonical(work)}.{fmt}"


def zip_dest_dir(work: str, fmt: str, dest_dir) -> Path:
    """zip 型格式（docx/odt）解压目录。"""
    return Path(dest_dir) / fmt / canon_of(work) / canonical(work)


def local_path(work: str, fmt: str, dest_dir) -> Path:
    return zip_dest_dir(work, fmt, dest_dir) if fmt in _ZIP_FORMATS else dest_path(work, fmt, dest_dir)


def remote_info(work: str, fmt: str) -> dict | None:
    """HEAD 探针（复用共享层），返回 {url,size,mtime,etag}；失败/zip 型返回 None。"""
    if fmt in _ZIP_FORMATS:
        return None   # 端点为 zip，本地是目录，大小不可比 → 总是下载
    work = canonical(work)
    url = ebook_url(fmt, canon_of(work), work)
    r = cf.probe_info(url)
    if r.get("status") != "changed":
        return None
    mtime = None
    lm = r.get("last_modified")
    if lm:
        try:
            mtime = parsedate_to_datetime(lm).timestamp()
        except Exception:
            mtime = None
    return {"url": url, "size": r.get("size"), "mtime": mtime, "etag": r.get("etag")}


def is_unchanged(info: dict | None, dest) -> bool:
    # 本地存在且远端大小一致、远端不比本地新 -> 视为未更新，可跳过
    if info is None:
        return False
    try:
        st = Path(dest).stat()
    except OSError:
        return False
    if not Path(dest).is_file():
        return False
    if info.get("size") is not None and info["size"] != st.st_size:
        return False
    if info.get("size") is None and info.get("mtime") is None:
        return False   # 远端无任何可比元信息：无法判断，下载
    if info.get("mtime") is not None and info["mtime"] > st.st_mtime + 1:
        return False
    return True


def download_ebook(work: str, fmt: str, dest_dir) -> Path | None:
    work = canonical(work)
    url = ebook_url(fmt, canon_of(work), work)
    if fmt in _ZIP_FORMATS:
        out_dir = zip_dest_dir(work, fmt, dest_dir)
        return out_dir if cf.download(url, str(out_dir), unzip=True) else None
    dest = dest_path(work, fmt, dest_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest if cf.download(url, str(dest)) else None
