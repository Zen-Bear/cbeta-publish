"""mulu 远端增量：ETag/Last-Modified（HTTP 走共享层 cbeta-fetch）"""
import json, re, shutil
from pathlib import Path

from cbeta_publish._vendor import cbeta_fetch as cf
from cbeta_publish.utils.atomic import atomic_write_json

# 服务端对 gzip 表示会给 ETag 加 `-gzip` 后缀（如 cbdata）；
# 发条件头前去掉，否则与实体表示的 ETag 不匹配 → 恒 200、每次都「有更新」
_GZIP_ETAG = re.compile(r'^(W/)?"(.*)-gzip"$')


def _clean_etag(etag: str | None):
    if not etag:
        return etag
    m = _GZIP_ETAG.match(etag)
    return '%s"%s"' % (m.group(1) or "", m.group(2)) if m else etag


class RemoteManager:
    def __init__(self, meta_path: Path, root=None):
        self.meta_path = Path(meta_path)
        #: 目录数据根（相对路径按此解析）；None=默认 app_root/mulu
        self.root = Path(root) if root is not None else None
        self.meta = {}
        if self.meta_path.exists():
            try:
                self.meta = json.loads(self.meta_path.read_text(encoding="utf-8-sig"))
            except Exception as e:
                # meta 损坏不能让更新/检查线程直接死掉；备份后按空库继续
                bak = self.meta_path.with_name(
                    f"{self.meta_path.name}.bad-{__import__('datetime').datetime.now():%Y%m%d-%H%M%S}")
                try:
                    if not bak.exists():
                        shutil.copy2(self.meta_path, bak)
                except Exception as be:
                    print("backup corrupt meta fail", be)
                print("meta corrupt", self.meta_path, e)
                self.meta = {}
        if not isinstance(self.meta, dict):
            self.meta = {}
        self._stop = False
        self._check_failed = 0

    def stop(self):
        """请求在下一个源之前停止（正在进行的单次 HTTP 不中断）。"""
        self._stop = True

    def _save_meta(self):
        atomic_write_json(self.meta_path, self.meta)

    def _cond(self, url: str):
        m = self.meta.get(url, {}) or {}
        return _clean_etag(m.get("etag") or None), m.get("last_modified") or None

    @staticmethod
    def _local_for(url: str, root=None):
        # 由 URL 反查本地文件（SOURCES 单源表）
        from cbeta_publish.books.remote_sources import SOURCES, local_path
        for _key, _cat, u, rel in SOURCES:
            if u == url:
                return local_path(rel, root)
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
            self._check_failed += 1
            print(f"check {url} failed")
            return False
        dest = self._local_for(url, self.root)
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
        self._check_failed = 0
        for key, cat, url, rel in sources:
            if self._stop:
                break
            if progress:
                progress(f"检查 {key} …")
            if self.check(url):
                changed.append(key)
        # 有源检查失败或中途停止时不记 last_check，下次启动继续重试（避免离线一次静默一周）
        if not self._stop and self._check_failed == 0:
            self.meta["last_check"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
            self._save_meta()
        return changed

    def update_all(self, sources, backup_dir: Path, progress=None) -> dict:
        """按 SOURCES 表批量更新；更新前旧文件快照到 backup_dir/last/。
        sources: [(key, category, url, rel)]
        返回 {key: 'updated'|'unchanged'|'failed'}"""
        backup_dir = Path(backup_dir)
        last_dir = backup_dir / "last"
        orig_dir = backup_dir / "original"
        result = {}
        for key, cat, url, rel in sources:
            if self._stop:
                break
            dest = self._local_for(url, self.root)
            self._check_failed = 0
            changed = self.check(url)
            _failed = self._check_failed > 0
            if progress:
                progress(f"检查 {key} … "
                         f"{'有更新' if changed else ('失败' if _failed else '已最新')}")
            if not changed:
                # 网络/HTTP 检查失败不能记成「已最新」，否则界面显示 0 失败
                result[key] = "failed" if _failed else "unchanged"
                continue
            # 备份旧文件：每次更新前存 last；首次更新前存 original（不受后续覆盖）
            try:
                if dest.exists():
                    relp = Path(rel)
                    try:
                        relp = relp.relative_to("mulu")
                    except ValueError:
                        pass
                    for base, overwrite in ((orig_dir, False), (last_dir, True)):
                        target = base / relp
                        if overwrite or not target.exists():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(str(dest), str(target))
            except Exception as e:
                print(f"backup {dest} fail {e}")
            ok = self.fetch(url, dest)
            result[key] = "updated" if ok else "failed"
            if progress:
                progress(f"{'已更新' if ok else '更新失败'} {dest.name}")
        # 中途停止或有失败源时不记 last_check，下次启动/下次检查继续重试
        if not self._stop and not any(v == "failed" for v in result.values()):
            self.meta["last_check"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
            self._save_meta()
        return result
