from PySide6.QtCore import QThread, Signal
from pathlib import Path


# 进度行前缀：表示“替换上一行”（把「下载 X ...」与「完成 X」合并显示为一行）
REPLACE_LAST = "\r"


class DownloadWorker(QThread):
    progress = Signal(str)
    finished_all = Signal(int, int, list)  # ok, total, failed list

    def __init__(self, works=None, fmts=None, dest_dir=".", pairs=None):
        """pairs: 明确的 [(work, fmt), ...]；不传则由 works × fmts 组合。"""
        super().__init__()
        if pairs is None:
            pairs = [(w, fmt) for fmt in (fmts or []) for w in (works or [])]
        self.pairs = list(pairs)
        self.works = works if works is not None else [w for w, _ in self.pairs]
        self.fmts = fmts if fmts is not None else sorted({f for _, f in self.pairs})
        self.dest_dir = Path(dest_dir)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        from cbeta_publish.books.official_ebook_source import (
            download_ebook, remote_info, is_unchanged, local_path, local_size_kb,
        )
        ok = 0
        total = len(self.pairs)
        failed = []
        for w, fmt in self.pairs:
            if self._stop:
                break
            dest = local_path(w, fmt, self.dest_dir)
            existed = dest.exists()
            if existed:
                # 文件存在：先 HEAD 比对，无更新则跳过
                info = remote_info(w, fmt)
                if info is not None and is_unchanged(info, dest):
                    ok += 1
                    self.progress.emit(f"跳过 {w}.{fmt}（已是最新）")
                    continue
            self.progress.emit(f"下载 {w}.{fmt} ...")
            got = download_ebook(w, fmt, self.dest_dir)
            if got and got.exists():
                ok += 1
                kb = local_size_kb(got)
                word = "更新" if existed else "完成"
                # 与上一行合并：下载 X ...完成 NKB
                self.progress.emit(f"{REPLACE_LAST}下载 {w}.{fmt} ...{word} {kb}KB")
            else:
                failed.append(f"{w}.{fmt}")
                self.progress.emit(f"{REPLACE_LAST}下载 {w}.{fmt} ...失败")
        self.finished_all.emit(ok, total, failed)
