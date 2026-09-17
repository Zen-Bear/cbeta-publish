# -*- coding: utf-8 -*-
"""进程内校验 worker：逐本调 `xml2pdf_bridge.verify_work`（同线程跑会卡 UI）。"""
from pathlib import Path

from PySide6.QtCore import QThread, Signal


class VerifyWorker(QThread):
    # 进度：done, label, level（level: "run"/"ok"/"fail"/""）
    progress = Signal(int, str, str)
    finished_all = Signal(int, int, list)   # ok, total, failed list

    def __init__(self, works, fmts, out_dir, config, preset=None):
        super().__init__()
        self.works = list(works or [])
        self.fmts = list(fmts or [])
        self.out_dir = Path(out_dir)
        self.config = config
        self.preset = preset
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        from cbeta_publish.books.download_worker import REPLACE_LAST
        total = len(self.works)
        ok = 0
        failed = []
        for i, w in enumerate(self.works, 1):
            if self._stop:
                break
            self.progress.emit(i - 1, f"生成并校验 {w} ...", "run")
            report = b.verify_work(w, self.fmts, self.out_dir, self.config,
                                   preset=self.preset, stop=lambda: self._stop)
            verdict = b.verify_report_pass(report) if report is not None else None
            if verdict is True:
                ok += 1
                self.progress.emit(i, f"{REPLACE_LAST}生成并校验 {w} ...通过", "ok")
            elif verdict is False:
                failed.append(w)
                self.progress.emit(i, f"{REPLACE_LAST}生成并校验 {w} ...未通过", "fail")
            else:
                failed.append(w)
                self.progress.emit(i, f"{REPLACE_LAST}生成并校验 {w} ...未判定", "fail")
        self.finished_all.emit(ok, total, failed)
