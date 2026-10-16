# -*- coding: utf-8 -*-
"""进程内校验 worker：逐本调 `xml2pdf_bridge.verify_work`（同线程跑会卡 UI）。"""
from pathlib import Path

from PySide6.QtCore import QThread, Signal


class VerifyWorker(QThread):
    # 进度：done, label, level（level: "run"/"ok"/"fail"/""）
    progress = Signal(int, str, str)
    finished_all = Signal(int, int, list)   # ok, total, failed list
    # 逐本格式判定（在 finished_all 之前发出，供收尾按「作品 × 格式」计文件数）：
    # {work: {"passed": [fmt…], "failed": [fmt…], "undet": [fmt…]}}
    # 独立信号：finished_all 仍是 3 参，既有连接点不受影响。
    verdicts = Signal(object)

    def __init__(self, works, fmts, out_dir, config, preset=None,
                 works_fmts=None, works_juan=None):
        super().__init__()
        self.works = list(works or [])
        self.fmts = list(fmts or [])
        # 逐书待验格式（跳过复用时只验 stale 格式）；缺省=全书统一 fmts
        self.works_fmts = dict(works_fmts or {})
        # 逐书卷范围 spec（P11 卷子集）；缺省=整本
        self.works_juan = dict(works_juan or {})
        self.out_dir = Path(out_dir)
        self.config = config
        self.preset = preset
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        from cbeta_publish.books.download_worker import REPLACE_LAST
        from cbeta_publish.catalog.work_id import split_entry
        total = len(self.works)
        ok = 0
        failed = []
        verdicts = {}
        try:
            for i, w in enumerate(self.works, 1):
                if self._stop:
                    break
                _work = split_entry(w)[0]
                self.progress.emit(i - 1, f"生成并校验 {w} ...", "run")
                wf = self.works_fmts.get(w, self.fmts) if self.works_fmts else self.fmts
                _spec = self.works_juan.get(w, "")
                try:
                    _jlab = b.juan_label(self.config, _spec) if _spec else ""
                except Exception:
                    _jlab = ""
                report = b.verify_work(_work, wf, self.out_dir, self.config,
                                       preset=self.preset, stop=lambda: self._stop,
                                       juan=_spec)
                # 同一 work 可能有多个语义产物（如 TX0011 上/中下）：聚合全部相关报告，
                # 避免只看最新一份而漏判另一份；同时按卷隔离——同书多卷子集的报告
                # 目录并存时，只聚合本次卷的（`（卷…）（验证）` 后缀，整本为 ""）。
                reports = b.work_verify_reports(self.out_dir, _work, primary=report,
                                                juan=_jlab)
                fmts_status = {}
                pending_all = {}
                scopes = {}
                nums_all = {}
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
                    # 验收档用缺数/范围：多报告同格式取首个判定报告的
                    for fmt, _ne in b.verify_report_numbers(rp).items():
                        nums_all.setdefault(fmt, _ne)
                    # diff_scope（json-only）：多报告同格式取最保守
                    for fmt, sc in b.verify_report_diff_scopes(rp).items():
                        scopes[fmt] = b.conservative_diff_scope([scopes.get(fmt), sc])
                    one_verdict = b.verify_report_pass(rp)
                    if one_verdict is False or overall is False:
                        overall = False
                    elif one_verdict is None or overall is None:
                        overall = None
                    else:
                        overall = True
                verdict = overall
                # 逐本格式判定（收尾按「作品 × 格式」计文件数用）：
                # 无基线/被覆盖待定的格式不在 formats 表里，同样算未判定
                _passed_f = sorted(f for f, v in fmts_status.items() if v is True)
                if not _passed_f and verdict is True:
                    # 报告无逐格式行（整体判过）：按本次请求格式记，避免文件数漏计
                    _passed_f = sorted(f for f in (wf or []) if f)
                _undet_f = {f for f, v in fmts_status.items()
                            if v is not True and v is not False}
                _undet_f |= {f for f in (pending_all or {})
                             if f and f not in fmts_status}
                verdicts[w] = {
                    "passed": _passed_f,
                    "failed": sorted(f for f, v in fmts_status.items() if v is False),
                    "undet": sorted(_undet_f),
                }
                if fmts_status:
                    passed = [f for f, v in fmts_status.items() if v]
                    failed_f = [f for f, v in fmts_status.items() if not v]
                    def _flab(_f):
                        _mi, _ex = nums_all.get(_f, (None, None))
                        _t = b.accept_tier(False, _mi, _ex, scopes.get(_f))
                        if _t == "notes_only":
                            return f"{_f} 未过（仅注释）"
                        _sct = b.diff_scope_text(scopes.get(_f))
                        return f"{_f} 未过" + (f"（{_sct}）" if _sct else "")
                    _sc = b.diff_scope_text(b.conservative_diff_scope(
                        [scopes.get(f) for f in failed_f]))
                    if passed and not failed_f:
                        ok += 1
                        self.progress.emit(
                            i, f"{REPLACE_LAST}生成并校验 {w} ...通过"
                               f"（{'/'.join(sorted(passed))}）", "ok")
                    elif passed:
                        ok += 1
                        self.progress.emit(
                            i, f"{REPLACE_LAST}生成并校验 {w} ...部分通过"
                               f"（{'/'.join(passed)} 过，{'/'.join(_flab(f) for f in failed_f)}）", "ok")
                    else:
                        failed.append(w)
                        self.progress.emit(
                            i, f"{REPLACE_LAST}生成并校验 {w} ...未通过"
                               + (f"（{_sc}）" if _sc else ""), "fail")
                elif verdict is True:
                    ok += 1
                    _fl = sorted(f for f in (wf or []) if f)
                    self.progress.emit(
                        i, f"{REPLACE_LAST}生成并校验 {w} ...通过"
                           + (f"（{'/'.join(_fl)}）" if _fl else ""), "ok")
                elif verdict is False:
                    failed.append(w)
                    _sc = b.diff_scope_text(b.conservative_diff_scope(scopes.values()))
                    self.progress.emit(
                        i, f"{REPLACE_LAST}生成并校验 {w} ...未通过"
                           + (f"（{_sc}）" if _sc else ""), "fail")
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
        self.verdicts.emit(verdicts)
        self.finished_all.emit(ok, total, failed)
