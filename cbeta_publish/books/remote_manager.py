"""mulu 远端增量：ETag/Last-Modified（HTTP 走共享层 cbeta-fetch）"""
import json, shutil
from pathlib import Path

from cbeta_publish._vendor import cbeta_fetch as cf


class RemoteManager:
    def __init__(self, meta_path: Path):
        self.meta_path = Path(meta_path)
        self.meta = json.loads(self.meta_path.read_text(encoding="utf-8")) if self.meta_path.exists() else {}

    def _save_meta(self):
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _cond(self, url: str):
        m = self.meta.get(url, {}) or {}
        return m.get("etag") or None, m.get("last_modified") or None

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
        """仅比对是否需要更新（HEAD + 条件头），不下载。返回 True=有新版。"""
        etag, lm = self._cond(url)
        status, _etag, _lm = cf.probe(url, etag=etag, last_modified=lm)
        if status == "changed":
            return True
        if status == "failed":
            print(f"check {url} failed")
        return False

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
