# -*- coding: utf-8 -*-
"""进程内校验 worker：逐本调 `xml2pdf_bridge.verify_work`（同线程跑会卡 UI）。"""
from pathlib import Path

from PySide6.QtCore import QThread, Signal


class VerifyWorker(QThread):
    # 进度：done, label, level（level: "run"/"ok"/"fail"/""）
    progress = Signal(int, str, str)
    finished_all = Signal(int, int, list)   # ok, total, failed list

    def __init__(self, works, fmts, out_dir, config, preset=None,
                 works_fmts=None):
        super().__init__()
        self.works = list(works or [])
        self.fmts = list(fmts or [])
        # 逐书待验格式（跳过复用时只验 stale 格式）；缺省=全书统一 fmts
        self.works_fmts = dict(works_fmts or {})
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
        try:
            for i, w in enumerate(self.works, 1):
                if self._stop:
                    break
                self.progress.emit(i - 1, f"生成并校验 {w} ...", "run")
                wf = self.works_fmts.get(w, self.fmts) if self.works_fmts else self.fmts
                report = b.verify_work(w, wf, self.out_dir, self.config,
                                       preset=self.preset, stop=lambda: self._stop)
                # 同一 work 可能有多个语义产物（如 TX0011 上/中下）：聚合全部相关报告，
                # 避免只看最新一份而漏判另一份。
                reports = b.work_verify_reports(self.out_dir, w, primary=report)
                fmts_status = {}
                pending_all = {}
                overall = None
                for rp in reports:
                    one = b.verify_report_formats(rp)
                    one_pending = b.verify_report_pending(rp)
                    # docx通过即pdf通过（pdf由docx校验覆盖，不重复验）
                    one = b.apply_verify_coverage(one, one_pending)
                    for fmt, val in one.items():
                        if fmt not in fmts_status:
                            fmts_status[fmt] = val
                        elif val is False or fmts_status[fmt] is False:
                            fmts_status[fmt] = False
                        elif val is None or fmts_status[fmt] is None:
                            fmts_status[fmt] = None
                        else:
                            fmts_status[fmt] = True
                    for fmt, reason in one_pending.items():
                        pending_all.setdefault(fmt, reason)
                    one_verdict = b.verify_report_pass(rp)
                    if one_verdict is False or overall is False:
                        overall = False
                    elif one_verdict is None or overall is None:
                        overall = None
                    else:
                        overall = True
                verdict = overall
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
                    note = ""
                    if reports:
                        nobase = sorted(
                            f for f, r in pending_all.items()
                            if f and r == "no baseline")
                        if nobase:
                            note = f"（{'/'.join(nobase)} 无基线）"
                    self.progress.emit(i, f"{REPLACE_LAST}生成并校验 {w} ...未判定{note}", "fail")
        except BaseException as e:
            # BaseException：上游 CLI 用 argparse，参数异常抛 SystemExit（不是
            # Exception 子类），会穿透常规 except 导致线程静默死亡、
            # 主线程嵌套事件循环永不退出（界面挂死）。此处吞掉并记失败，
            # 保证 finished_all 发出、界面可继续。
            print("verify worker fail", e)
            for w in self.works:
                if w not in failed:
                    failed.append(w)
        self.finished_all.emit(ok, total, failed)
