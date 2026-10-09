from PySide6.QtCore import QThread, Signal
from pathlib import Path


# 进度行前缀：表示“替换上一行”（把「下载 X ...」与「完成 X」合并显示为一行）
REPLACE_LAST = "\r"


class DownloadWorker(QThread):
    progress = Signal(str)
    finished_all = Signal(int, int, list)  # ok, total, failed list

    def __init__(self, works=None, fmts=None, dest_dir=".", pairs=None, config=None,
                 force=False):
        """pairs: 明确的 [(work, fmt), ...]；不传则由 works × fmts 组合。
        config: 透传给 official_ebook_source（本地库），缺省=无本地库（纯下载）。
        force: True 时忽略「未更新」判断与本地库同大小跳过，强制下载/覆盖。"""
        super().__init__()
        if pairs is None:
            pairs = [(w, fmt) for fmt in (fmts or []) for w in (works or [])]
        self.pairs = list(pairs)
        self.works = works if works is not None else [w for w, _ in self.pairs]
        self.fmts = fmts if fmts is not None else sorted({f for _, f in self.pairs})
        self.dest_dir = Path(dest_dir)
        self._config = config
        self.force = bool(force)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        from cbeta_publish.books.official_ebook_source import (
            download_ebook, remote_info, is_unchanged, local_path, local_size_kb,
            copy_from_library, RemoteNotFound, NoJuanEndpoint,
        )
        ok = 0
        total = len(self.pairs)
        failed = []
        try:
            for w, fmt in self.pairs:
                if self._stop:
                    break
                dest = local_path(w, fmt, self.dest_dir)
                existed = dest.exists()
                if existed and not self.force:
                    # 文件存在：先 HEAD 比对，无更新则跳过
                    info = remote_info(w, fmt)
                    if info is not None and is_unchanged(info, dest):
                        ok += 1
                        self.progress.emit(f"跳过 {w}.{fmt}（已是最新）")
                        continue
                self.progress.emit(f"下载 {w}.{fmt} ...")
                got = copy_from_library(w, fmt, self.dest_dir, self._config,
                                        force=self.force)
                kind = "本地库" if got is not None else None
                if got is None:
                    try:
                        got = download_ebook(w, fmt, self.dest_dir, self._config,
                                             force=self.force)
                    except RemoteNotFound:
                        failed.append(f"{w}.{fmt} 不存在")
                        self.progress.emit(f"{REPLACE_LAST}下载 {w}.{fmt} ...不存在")
                        continue
                    except NoJuanEndpoint:
                        failed.append(f"{w}.{fmt} 官方无单卷")
                        self.progress.emit(f"{REPLACE_LAST}下载 {w}.{fmt} ...官方无单卷")
                        continue
                if got and got.exists():
                    ok += 1
                    kb = local_size_kb(got)
                    word = "更新" if existed else "完成"
                    # 与上一行合并：下载 X ...完成 NKB（本地库来源单独标注）
                    self.progress.emit(f"{REPLACE_LAST}{kind or '下载'} {w}.{fmt} ...{word} {kb}KB")
                else:
                    failed.append(f"{w}.{fmt}")
                    self.progress.emit(f"{REPLACE_LAST}下载 {w}.{fmt} ...失败")
        except BaseException as e:
            # 同 VerifyWorker：异常（含 SystemExit）也必须发出 finished_all，
            # 否则主线程嵌套事件循环永不退出（界面挂死）
            print("download worker fail", e)
            for w, fmt in self.pairs:
                if not any(f.startswith(f"{w}.{fmt}") for f in failed):
                    failed.append(f"{w}.{fmt}")
        self.finished_all.emit(ok, total, failed)
