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
            # 逐格式判定：全通过=通过；部分通过=部分通过（入库靠 import 逐格式处理）
            fmts_status = b.verify_report_formats(report) if report is not None else {}
            verdict = b.verify_report_pass(report) if report is not None else None
            if fmts_status:
                passed = [f for f, v in fmts_status.items() if v]
                failed_f = [f for f, v in fmts_status.items() if not v]
                if passed and not failed_f:
                    ok += 1
                    self.progress.emit(i, f"{REPLACE_LAST}生成并校验 {w} ...通过", "ok")
                elif passed:
                    ok += 1
                    self.progress.emit(
                        i, f"{REPLACE_LAST}生成并校验 {w} ...部分通过"
                           f"（{'/'.join(passed)} 过，{'/'.join(failed_f)} 未过）", "ok")
                else:
                    failed.append(w)
                    self.progress.emit(i, f"{REPLACE_LAST}生成并校验 {w} ...未通过", "fail")
            elif verdict is True:
                ok += 1
                self.progress.emit(i, f"{REPLACE_LAST}生成并校验 {w} ...通过", "ok")
            elif verdict is False:
                failed.append(w)
                self.progress.emit(i, f"{REPLACE_LAST}生成并校验 {w} ...未通过", "fail")
            else:
                failed.append(w)
                self.progress.emit(i, f"{REPLACE_LAST}生成并校验 {w} ...未判定", "fail")
        self.finished_all.emit(ok, total, failed)
