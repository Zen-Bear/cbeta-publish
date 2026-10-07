# -*- coding: utf-8 -*-
"""S8：批量合并 `_run_batch_merge`（逐部/失败隔离/取消/报告/隔离/单书配置）。"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from cbeta_publish.gui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _write_coll(dirp, name, works, extra=None):
    d = {"id": name, "name": name, "category": "custom", "tags": [], "work_ids": works}
    if extra:
        d.update(extra)
    p = dirp / f"{name}.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return p


def _make_window():
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    cdir = tmp / "collections" / "custom"
    cdir.mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    _write_coll(cdir, "甲", ["T0001", "T0002"])
    _write_coll(cdir, "乙", ["T0003"])
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["output_dir"] = str(tmp / "out")
    cfg["update_interval"] = "manual"
    cfg["xml2pdf"]["cbeta_ebook"] = str(tmp / "xml")
    cfg["official_library"] = {"root": ""}
    cfg["cbeta_ebooks_dir"] = str(tmp / "eb")
    cfg["_config_path"] = str(tmp / "app.json")
    cfg["default_formats"] = {"merge": ["pdf", "epub"],
                              "official": ["pdf", "epub"], "xml": ["pdf", "docx"]}
    cfg.setdefault("cover", {})["edit_note"] = {"file": "", "enabled": False}
    win = MainWindow(cfg)
    win._load_collections()
    return win, tmp, cdir


def _opts(run_source="official", **kw):
    o = {"merge": True, "zip": True, "auto_prepare": False,
         "official_policy": "stale", "self_policy": "missing", "save_report": True,
         "merge_fmts": ["pdf"], "zip_fmts": ["epub"], "run_source": run_source}
    o.update(kw)
    return o


class BatchMergeTest(unittest.TestCase):
    def setUp(self):
        self.win, self.tmp, self.cdir = _make_window()
        self.win.chk_pdf.setChecked(True)
        self.win.chk_epub.setChecked(True)
        self.win.chk_docx.setChecked(False)
        self.merge_calls = []
        self.zip_calls = []
        self.win._merge_one_coll = lambda data, d, works, **kw: (
            self.merge_calls.append((str(data), kw.get("mode"), kw.get("skip_missing")))
            or {"success": ["/tmp/x/a.pdf"], "skipped": [], "failed": [],
                "cancelled": False, "out_dir": "/tmp/x"})
        self.win._zip_one_coll = lambda d, works, **kw: (
            self.zip_calls.append((d.get("name"), kw.get("mode")))
            or {"success": ["/tmp/x/a_epub.zip"], "failed": [], "cancelled": False})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _selected(self):
        return [(p, d) for p, d in self.win._collections
                if (d.get("work_ids") or [])]

    def test_merge_and_zip_per_coll_report_and_last_publish(self):
        self.win.config["default_source"] = "official"
        self.win._run_batch_merge(self._selected(), _opts())
        names = [c[0] for c in self.merge_calls]
        self.assertEqual(len(names), 2)
        self.assertEqual(len(self.zip_calls), 2)
        rep = Path(self.win.config["output_dir"]) / "批量合并报告.txt"
        self.assertTrue(rep.is_file())
        # last_publish 写入有产物的部
        for _p, d in self._selected():
            self.assertTrue(d.get("last_publish_at"))
            self.assertEqual(d.get("last_publish_dir"),
                             str(Path(self.win.config["output_dir"]) / d["name"]))

    def test_auto_prepare_off_does_not_prepare(self):
        self.win.config["default_source"] = "official"
        called = []
        self.win._prepare_official = lambda *a, **k: called.append(1) or ({}, [])
        self.win._run_batch_merge(self._selected(), _opts(auto_prepare=False))
        self.assertEqual(called, [])

    def test_auto_prepare_on_official(self):
        self.win.config["default_source"] = "official"
        called = []
        self.win._prepare_official = lambda works, fmts, dest, policy="stale": (
            called.append((list(fmts), policy)) or ({}, []))
        self.win._run_batch_merge(self._selected(),
                                  _opts(auto_prepare=True, official_policy="all"))
        self.assertEqual(len(called), 1)
        self.assertEqual(called[0][1], "all")

    def test_editnote_problem_fails_merge_but_zip_runs(self):
        self.win.config["default_source"] = "official"
        for p, d in self._selected():
            if d["name"] == "甲":
                d["edit_note"] = {"file": "no_such_note.txt", "enabled": True}
        self.win._run_batch_merge(self._selected(), _opts())
        merged_names = [c[0] for c in self.merge_calls]
        self.assertNotIn(str(self.cdir / "甲.json"), merged_names)
        zipped = [c[0] for c in self.zip_calls]
        self.assertIn("甲", zipped)

    def test_ask_uses_ask_last(self):
        self.win.config["default_source"] = "official"
        self.win.config.setdefault("merge", {})["ask_last"] = {"mode": "none", "depth": 1}
        for p, d in self._selected():
            if d["name"] == "甲":
                d["merge"] = {"mode": "ask", "depth": 2, "name_template": ""}
        self.win._run_batch_merge(self._selected(), _opts())
        modes = {c[0]: c[1] for c in self.merge_calls}
        self.assertEqual(modes[str(self.cdir / "甲.json")], "none")

    def test_cancel_marks_rest(self):
        self.win.config["default_source"] = "official"
        state = {"n": 0}
        def fake(data, d, works, **kw):
            state["n"] += 1
            return {"success": [], "skipped": [], "failed": [], "cancelled": True,
                    "out_dir": "/tmp/x"}
        self.win._merge_one_coll = fake
        self.win._run_batch_merge(self._selected(), _opts(zip=False))
        self.assertEqual(state["n"], 1)

    def test_blank_name_skipped(self):
        self.win.config["default_source"] = "official"
        _write_coll(self.cdir, "空白丛书", ["T0009"])
        self.win._load_collections()
        self.win._run_batch_merge(self._selected(), _opts(zip=False))
        merged_names = [c[0] for c in self.merge_calls]
        self.assertNotIn(str(self.cdir / "空白丛书.json"), merged_names)

    def test_isolation_global_state(self):
        self.win.config["default_source"] = "official"
        before = {k: self.win.config.get(k) for k in
                  ("default_source", "xml2pdf", "merge", "ui")}
        self.win._run_batch_merge(self._selected(), _opts())
        after = {k: self.win.config.get(k) for k in
                 ("default_source", "xml2pdf", "merge", "ui")}
        self.assertEqual(before, after)

    def test_right_panel_merge_button_saves_to_json(self):
        from cbeta_publish.gui import merge_dialog as md

        win = self.win
        self.assertEqual(win.btn_coll_merge.text(), "分册…")
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("甲.json"):
                win.coll_combo.setCurrentIndex(i)
                break

        class FakeMD:
            def __init__(self, *a, **k):
                pass
            def exec(self):
                from PySide6.QtWidgets import QDialog
                return QDialog.Accepted
            def result_merge(self):
                return {"mode": "dynasty", "depth": 1, "name_template": "D"}
            def _refresh(self):
                pass

        real = md.MergeDialog
        md.MergeDialog = FakeMD
        try:
            win._edit_coll_merge()
        finally:
            md.MergeDialog = real
        txt = (self.cdir / "甲.json").read_text(encoding="utf-8")
        self.assertIn('"merge"', txt)
        self.assertIn("dynasty", txt)


class BatchMergePurgeTest(unittest.TestCase):
    def setUp(self):
        self.win, self.tmp, self.cdir = _make_window()
        self.win.chk_pdf.setChecked(True)
        self.win.chk_epub.setChecked(True)
        self.win.chk_docx.setChecked(False)
        self.merge_calls = []
        self.win._merge_one_coll = lambda data, d, works, **kw: (
            self.merge_calls.append(str(data))
            or {"success": ["/tmp/x/a.pdf"], "skipped": [], "failed": [],
                "cancelled": False, "out_dir": "/tmp/x"})
        self.win._zip_one_coll = lambda d, works, **kw: (
            {"success": [], "failed": [], "cancelled": False})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _selected(self):
        return [(p, d) for p, d in self.win._collections
                if (d.get("work_ids") or [])]

    def _report_text(self):
        rep = next(Path(self.win.config["output_dir"]).glob("*报告.txt"))
        return rep.read_text(encoding="utf-8")

    def _qbox(self, answer):
        m = mock.patch("cbeta_publish.gui.main_window.QMessageBox")
        box = m.start()
        self.addCleanup(m.stop)
        box.question.return_value = answer
        box.Yes = QMessageBox.Yes
        box.No = QMessageBox.No
        return box

    def test_purge_off_by_default(self):
        sel = self._selected()
        out_d = Path(self.win.config["output_dir"]) / sel[0][1]["name"]
        out_d.mkdir(parents=True)
        (out_d / "old.pdf").write_text("x")
        self.win._run_batch_merge(sel, _opts(zip=False))
        self.assertTrue((out_d / "old.pdf").is_file())

    def test_purge_yes_clears_outputs_and_marks(self):
        sel = self._selected()
        name = sel[0][1]["name"]
        out_d = Path(self.win.config["output_dir"]) / name
        out_d.mkdir(parents=True)
        (out_d / "old.pdf").write_text("x")
        sel[0][1]["last_publish_at"] = "2020-01-01T00:00:00Z"
        sel[0][1]["last_publish_dir"] = str(out_d)
        # 本用例合并零产出 → 合并阶段不写标记；末态无标记即证明清除阶段清过
        self.win._merge_one_coll = lambda data, d, works, **kw: (
            self.merge_calls.append(str(data))
            or {"success": [], "skipped": [], "failed": [],
                "cancelled": False, "out_dir": "/tmp/x"})
        self._qbox(QMessageBox.Yes)
        self.win._run_batch_merge(sel, _opts(zip=False, purge=True))
        self.assertFalse(out_d.exists())
        self.assertNotIn("last_publish_at", sel[0][1])
        self.assertNotIn("last_publish_dir", sel[0][1])
        self.assertTrue(self.merge_calls)  # 清除后合并照常跑
        self.assertIn("清除", self._report_text())

    def test_purge_no_cancels_whole_run(self):
        sel = self._selected()
        out_d = Path(self.win.config["output_dir"]) / sel[0][1]["name"]
        out_d.mkdir(parents=True)
        (out_d / "old.pdf").write_text("x")
        self._qbox(QMessageBox.No)
        self.win._run_batch_merge(sel, _opts(zip=False, purge=True))
        self.assertTrue((out_d / "old.pdf").is_file())
        self.assertEqual(self.merge_calls, [])

    def test_purge_missing_dir_reports_and_continues(self):
        sel = self._selected()
        self._qbox(QMessageBox.Yes)
        self.win._run_batch_merge(sel, _opts(zip=False, purge=True))
        self.assertTrue(self.merge_calls)
        self.assertIn("无输出可清", self._report_text())


class BatchMergeFailureUXTest(unittest.TestCase):
    """备齐关＋缺素材：skipped 透出、reason 归因、失败停留。"""

    def setUp(self):
        self.win, self.tmp, self.cdir = _make_window()
        self.win.chk_pdf.setChecked(True)
        self.win.chk_epub.setChecked(True)
        self.win.chk_docx.setChecked(False)
        self.finished = []
        self.closed = []
        win = self.win
        finished, closed = self.finished, self.closed

        class _FakeDlg:
            def close(self):
                closed.append(1)

        def _fake_progress(title, total):
            return _FakeDlg(), lambda *a, **k: True, \
                {"finish": lambda lines: finished.append(list(lines))}
        win._make_progress = _fake_progress

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _selected(self):
        return [(p, d) for p, d in self.win._collections
                if (d.get("work_ids") or [])]

    def _report_text(self):
        rep = next(Path(self.win.config["output_dir"]).glob("*报告.txt"))
        return rep.read_text(encoding="utf-8")

    def _stub_merge(self, skipped=(), failed=(), success=()):
        self.win._merge_one_coll = lambda data, d, works, **kw: {
            "success": list(success), "skipped": list(skipped),
            "failed": list(failed), "cancelled": False, "out_dir": "/tmp/x"}
        self.win._zip_one_coll = lambda d, works, **kw: {
            "success": [], "failed": [], "cancelled": False}

    def test_prepare_off_missing_points_to_prepare(self):
        self._stub_merge(skipped=["T0001.pdf"], failed=["pdf 无文件"])
        self.win._run_batch_merge(self._selected(), _opts(zip=False))
        rep = self._report_text()
        self.assertIn("缺素材", rep)
        self.assertIn("自动备齐", rep)  # reason 归因进报告
        self.assertIn("缺素材", self.win.lbl_coll_info.text())  # 页签可见
        self.assertTrue(self.finished)  # 失败停留（调了 finish）
        self.assertEqual(self.closed, [])

    def test_prepare_on_missing_says_still_missing(self):
        self._stub_merge(skipped=["T0001.pdf"], failed=["pdf 无文件"])
        self.win._prepare_official = lambda *a, **k: ({}, [])
        self.win._run_batch_merge(
            self._selected(), _opts(zip=False, auto_prepare=True))
        self.assertIn("备齐后仍有缺失", self._report_text())
        self.assertTrue(self.finished)

    def test_all_ok_still_closes(self):
        self._stub_merge(success=["/tmp/x/a.pdf"])
        self.win._run_batch_merge(self._selected(), _opts(zip=False))
        self.assertEqual(self.finished, [])
        self.assertTrue(self.closed)  # 成功仍直接关


class BatchDialogTest(unittest.TestCase):
    def setUp(self):
        self.win, self.tmp, self.cdir = _make_window()
        self.items = [(p, d) for p, d in self.win._collections]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_checklist_default_all_nonempty(self):
        from cbeta_publish.gui.batch_dialogs import CollectionChecklist
        cl = CollectionChecklist(self.items, self.win._coll_merge_cfg)
        sel = cl.selected_items()
        names = sorted(d["name"] for _p, d in sel)
        self.assertEqual(names, ["乙", "甲"])

    def test_merge_dialog_defaults(self):
        from cbeta_publish.gui.batch_dialogs import BatchMergeDialog
        dlg = BatchMergeDialog(self.items, self.win._coll_merge_cfg, self.win,
                               merge_fmts=["pdf"], zip_fmts=["epub"], can_merge=True)
        self.assertTrue(dlg.merge_enabled())
        self.assertTrue(dlg.zip_enabled())
        self.assertTrue(dlg.auto_prepare())
        self.assertEqual(dlg.official_policy(), "stale")

    def test_merge_edit_follow_and_custom(self):
        from cbeta_publish.gui.merge_dialog import MergeDialog
        d = MergeDialog(self.win, allow_follow=True, allow_ask=True, follow=True,
                        global_cfg=("none", 2, "T"))
        self.assertIsNone(d.result_merge())   # 默认跟随全局
        d._chk_follow.setChecked(False)
        d._select("author")
        d.sp_depth.setValue(3)
        d.ed_template.setText("X")
        self.assertEqual(d.result_merge(),
                         {"mode": "author", "depth": 3, "name_template": "X"})

    def test_merge_edit_prefills_collection_or_global(self):
        from cbeta_publish.gui.merge_dialog import MergeDialog
        own = MergeDialog(self.win, allow_follow=True, allow_ask=True, follow=False,
                          default_mode="catalog", default_depth=2,
                          default_template="C", global_cfg=("none", 4, "G"))
        self.assertFalse(own.follow_global())
        self.assertEqual(own.chosen()[0], "catalog")
        self.assertEqual(own.sp_depth.value(), 2)
        self.assertEqual(own.template(), "C")
        gl = MergeDialog(self.win, allow_follow=True, allow_ask=True, follow=True,
                         global_cfg=("author", 4, "G"))
        self.assertTrue(gl.follow_global())
        self.assertEqual(gl.chosen()[0], "author")   # 显示全局值
        self.assertEqual(gl.sp_depth.value(), 4)
        self.assertEqual(gl.template(), "G")

    def test_merge_edit_allows_ask(self):
        from cbeta_publish.gui.merge_dialog import MergeDialog
        d = MergeDialog(self.win, allow_follow=True, allow_ask=True, follow=False)
        d._select("ask")
        self.assertEqual(d.result_merge()["mode"], "ask")
        self.assertFalse(d.sp_depth.isEnabled())

    def test_edit_merge_saves_immediately(self):
        from cbeta_publish.gui import batch_dialogs as bd
        from cbeta_publish.gui import merge_dialog as md

        saved = []

        class FakeMD:
            def __init__(self, *a, **k):
                pass
            def exec(self):
                from PySide6.QtWidgets import QDialog
                return QDialog.Accepted
            def result_merge(self):
                return {"mode": "author", "depth": 3, "name_template": "X"}
            def _refresh(self):
                pass

        real = md.MergeDialog
        md.MergeDialog = FakeMD
        try:
            dlg = bd.BatchMergeDialog(self.items, self.win._coll_merge_cfg, self.win,
                                      merge_fmts=["pdf"], zip_fmts=["epub"],
                                      can_merge=True,
                                      save_merge_fn=lambda k, m: saved.append((k, m)))
            it = dlg.list.topLevelItem(0)
            dlg._edit_merge(it)
        finally:
            md.MergeDialog = real
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0][1]["mode"], "author")
        self.assertEqual(dlg.list.item_pair(it)[1]["merge"]["mode"], "author")

    def test_prepare_checkbox_text_plain(self):
        from cbeta_publish.gui.batch_dialogs import BatchMergeDialog
        dlg = BatchMergeDialog(self.items, self.win._coll_merge_cfg, self.win,
                               merge_fmts=["pdf"], zip_fmts=["epub"], can_merge=True)
        self.assertNotIn("水位", dlg.chk_prepare.text())
        self.assertIn("自动备齐", dlg.chk_prepare.text())

    def test_update_dialog_hides_merge_column_and_is_wide(self):
        from cbeta_publish.gui.batch_dialogs import BatchUpdateDialog
        dlg = BatchUpdateDialog(self.items, self.win._coll_merge_cfg, self.win)
        self.assertTrue(dlg.list.isColumnHidden(2))   # 无「分册」列
        self.assertGreaterEqual(dlg.minimumWidth(), 600)
        self.assertLessEqual(dlg.minimumWidth(), 800)

    def test_merge_dialog_has_merge_column_and_is_wide(self):
        from cbeta_publish.gui.batch_dialogs import BatchMergeDialog
        dlg = BatchMergeDialog(self.items, self.win._coll_merge_cfg, self.win,
                               merge_fmts=["pdf"], zip_fmts=["epub"], can_merge=True)
        self.assertEqual(dlg.list.columnCount(), 3)
        self.assertFalse(dlg.list.isColumnHidden(2))
        self.assertGreaterEqual(dlg.minimumWidth(), 600)
        self.assertLessEqual(dlg.minimumWidth(), 800)

    def test_combined_dialog_switches_mode(self):
        from cbeta_publish.gui.batch_dialogs import BatchDialog
        dlg = BatchDialog(self.items, self.win._coll_merge_cfg, self.win,
                          mode="combined", merge_fmts=["pdf"], zip_fmts=["epub"],
                          can_merge=True)
        self.assertEqual(dlg.effective_mode(), "update")   # 默认更新素材
        self.assertTrue(dlg.list.isColumnHidden(2))
        self.assertTrue(dlg.chk_merge.isHidden())
        dlg.rb_merge.setChecked(True)
        self.assertEqual(dlg.effective_mode(), "merge")
        self.assertFalse(dlg.list.isColumnHidden(2))
        self.assertFalse(dlg.chk_merge.isHidden())

    def test_click_merge_column_opens_editor(self):
        from cbeta_publish.gui.batch_dialogs import BatchMergeDialog
        dlg = BatchMergeDialog(self.items, self.win._coll_merge_cfg, self.win,
                               merge_fmts=["pdf"], zip_fmts=["epub"], can_merge=True)
        calls = []
        dlg._edit_merge = lambda item=None: calls.append(item)
        it = dlg.list.topLevelItem(0)
        dlg._on_list_clicked(it, 0)          # 非「分册」列：不触发
        self.assertEqual(calls, [])
        dlg._on_list_clicked(it, 2)          # 「分册」列：进入编辑
        self.assertEqual(calls, [it])


if __name__ == "__main__":
    unittest.main()
