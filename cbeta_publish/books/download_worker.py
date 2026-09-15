from PySide6.QtCore import QThread, Signal
from pathlib import Path

class DownloadWorker(QThread):
    progress = Signal(str)
    finished_all = Signal(int, int, list)  # ok, total, failed list
    def __init__(self, works, fmts, dest_dir):
        super().__init__()
        self.works=works
        self.fmts=fmts
        self.dest_dir=Path(dest_dir)
        self._stop=False
    def stop(self):
        self._stop=True
    def run(self):
        from cbeta_publish.books.official_ebook_source import download_ebook, remote_info, is_unchanged, local_path
        ok=0
        total=len(self.works)*len(self.fmts)
        failed=[]
        for fmt in self.fmts:
            for w in self.works:
                if self._stop:
                    break
                dest=local_path(w, fmt, self.dest_dir)
                existed=dest.exists()
                if existed:
                    # 文件存在：先 HEAD 比对，无更新则跳过
                    info=remote_info(w, fmt)
                    if info is not None and is_unchanged(info, dest):
                        ok+=1
                        self.progress.emit(f"跳过 {w}.{fmt}（已是最新）")
                        continue
                self.progress.emit(f"下载 {w}.{fmt} ...")
                got=download_ebook(w, fmt, self.dest_dir)
                if got and got.exists():
                    ok+=1
                    try:
                        kb = got.stat().st_size//1024 if got.is_file() else sum(
                            f.stat().st_size for f in got.rglob("*") if f.is_file())//1024
                    except OSError:
                        kb = 0
                    self.progress.emit(f"更新 {w}.{fmt} {kb}KB" if existed else f"完成 {w}.{fmt} {kb}KB")
                else:
                    failed.append(f"{w}.{fmt}")
                    self.progress.emit(f"失败 {w}.{fmt}")
            if self._stop:
                break
        self.finished_all.emit(ok, total, failed)
