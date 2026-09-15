"""mulu 远端增量：ETag/Last-Modified（HTTP 走共享层 cbeta-fetch）"""
import json, re, shutil
from pathlib import Path

from cbeta_publish._vendor import cbeta_fetch as cf

# 服务端对 gzip 表示会给 ETag 加 `-gzip` 后缀（如 cbdata）；
# 发条件头前去掉，否则与实体表示的 ETag 不匹配 → 恒 200、每次都「有更新」
_GZIP_ETAG = re.compile(r'^(W/)?"(.*)-gzip"$')


def _clean_etag(etag: str | None):
    if not etag:
        return etag
    m = _GZIP_ETAG.match(etag)
    return '%s"%s"' % (m.group(1) or "", m.group(2)) if m else etag


class RemoteManager:
    def __init__(self, meta_path: Path):
        self.meta_path = Path(meta_path)
        self.meta = json.loads(self.meta_path.read_text(encoding="utf-8")) if self.meta_path.exists() else {}

    def _save_meta(self):
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _cond(self, url: str):
        m = self.meta.get(url, {}) or {}
        return _clean_etag(m.get("etag") or None), m.get("last_modified") or None

    @staticmethod
    def _local_for(url: str):
        # 由 URL 反查本地文件（SOURCES 单源表）
        from cbeta_publish.books.remote_sources import SOURCES, local_path
        for _key, _cat, u, rel in SOURCES:
            if u == url:
                return local_path(rel)
        return None

    def fetch(self, url: str, dest: Path) -> bool:
        """条件 GET → dest（原子落盘）。返回 True=已更新，False=未变/失败。"""
        etag, lm = self._cond(url)
        status, new_etag, new_lm = cf.fetch_if_changed(
            url, str(dest), etag=etag, last_modified=lm)
        if status == "downloaded":
            self.meta[url] = {"etag": new_etag or "", "last_modified": new_lm or ""}
            self._save_meta()
            return True
        if status == "failed":
            print(f"fetch {url} failed")
        return False

    def check(self, url: str) -> bool:
        """比对是否需要更新（HEAD 条件头 + 远端大小兜底），不下载。返回 True=有新版。

        服务端常不返回 304（cbdata 的 ETag 带 `-gzip` 后缀已失配、GitHub raw 忽略
        条件头），否则会永远误报「有更新」→ 无谓重下。故条件头判「changed」时，
        再用远端 Content-Length 与本地文件大小比对（`probe_info` 即为此设计）：
        大小一致即视为未更新。注意：内容等长的改动不会被检出。
        """
        etag, lm = self._cond(url)
        r = cf.probe_info(url, etag=etag, last_modified=lm)
        status = r.get("status")
        if status == "not-modified":
            return False
        if status == "failed":
            print(f"check {url} failed")
            return False
        dest = self._local_for(url)
        size = r.get("size")
        if dest is not None and size is not None and dest.exists():
            try:
                if dest.stat().st_size == size:
                    return False
            except OSError:
                pass
        return True

    def check_all(self, sources, progress=None) -> list:
        """检查所有源是否需要更新，返回有更新的 key 列表（不下载）。"""
        changed = []
        for key, cat, url, rel in sources:
            if progress:
                progress(f"检查 {key} …")
            if self.check(url):
                changed.append(key)
        self.meta["last_check"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        self._save_meta()
        return changed

    def update_all(self, sources, backup_dir: Path, progress=None) -> dict:
        """按 SOURCES 表批量更新；更新前旧文件快照到 backup_dir/last/。
        sources: [(key, category, url, rel)]
        返回 {key: 'updated'|'unchanged'|'failed'}"""
        from cbeta_publish.books.remote_sources import local_path
        backup_dir = Path(backup_dir)
        last_dir = backup_dir / "last"
        result = {}
        for key, cat, url, rel in sources:
            dest = local_path(rel)
            changed = self.check(url)
            if progress:
                progress(f"检查 {key} … {'有更新' if changed else '已最新'}")
            if not changed:
                result[key] = "unchanged"
                continue
            # 备份旧文件
            try:
                if dest.exists():
                    last_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(dest), str(last_dir / dest.name))
            except Exception as e:
                print(f"backup {dest} fail {e}")
            ok = self.fetch(url, dest)
            result[key] = "updated" if ok else "failed"
            if progress:
                progress(f"{'已更新' if ok else '更新失败'} {dest.name}")
        self.meta["last_check"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        self._save_meta()
        return result
