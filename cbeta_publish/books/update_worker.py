# -*- coding: utf-8 -*-
"""目录更新后台线程：检查 / 下载更新，避免阻塞 UI。"""
from pathlib import Path
from PySide6.QtCore import QThread, Signal


class UpdateWorker(QThread):
    progress = Signal(str)
    checked = Signal(list)   # do_update=False: 有更新的 key 列表
    updated = Signal(dict)   # do_update=True: {key: 状态}

    def __init__(self, meta_path: Path, sources, backup_dir: Path, do_update: bool = False, parent=None):
        super().__init__(parent)
        self.meta_path = Path(meta_path)
        self.sources = sources
        self.backup_dir = Path(backup_dir)
        self.do_update = do_update

    def run(self):
        from cbeta_publish.books.remote_manager import RemoteManager
        rm = RemoteManager(self.meta_path)
        try:
            if self.do_update:
                res = rm.update_all(self.sources, self.backup_dir, progress=self.progress.emit)
                self.updated.emit(res)
            else:
                changed = rm.check_all(self.sources, progress=self.progress.emit)
                self.checked.emit(changed)
        except Exception as e:
            print("update worker fail", e)
            if self.do_update:
                self.updated.emit({})
            else:
                self.checked.emit([])
