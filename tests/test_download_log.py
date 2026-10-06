# -*- coding: utf-8 -*-
"""下载弹窗：以 \\r 前缀的进度行应替换上一行，使「下载 X ...」与「完成 X」合成一行。

原「下载记录」页签已移除：下载/更新按钮改为弹窗进度（`_make_progress`）。
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTextBrowser  # noqa: E402

from cbeta_publish.books.download_worker import REPLACE_LAST  # noqa: E402
from cbeta_publish.gui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _make_window():
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    col = tmp / "collections" / "custom"
    col.mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg.setdefault("xml2pdf", {})["cbeta_ebook"] = str(tmp / "xml")  # 隔离：无真实 XML 源
    cfg.setdefault("merge", {})["mode"] = "none"   # 测试确定性：不随实时配置弹合并框
    cfg.setdefault("cover", {})["enabled"] = True
    cfg["cover"]["edit_note"] = {"file": "", "enabled": False}  # 同上：不弹编辑说明守卫框
    cfg["_config_path"] = str(tmp / "app.json")
    return MainWindow(cfg), tmp


class DownloadLogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _dialog_lines(self, dlg):
        log = dlg.findChildren(QTextBrowser)[0]
        doc = log.document()
        return [doc.findBlockByNumber(i).text()
                for i in range(doc.blockCount()) if doc.findBlockByNumber(i).text()]

    def test_replace_last_merges_into_one_line(self):
        dlg, update, st = self.win._make_progress("下载", 1)
        try:
            update(0, "下载 TX0015.epub ...")
            update(1, REPLACE_LAST + "下载 TX0015.epub ...完成 319KB")
            lines = self._dialog_lines(dlg)
            self.assertEqual(len(lines), 1, lines)
            self.assertIn("完成 319KB", lines[0])
        finally:
            dlg.close()

    def test_replace_without_previous_appends(self):
        dlg, update, st = self.win._make_progress("下载", 1)
        try:
            update(1, REPLACE_LAST + "下载 T0001.pdf ...完成 1KB")
            lines = self._dialog_lines(dlg)
            self.assertEqual(len(lines), 1, lines)
            self.assertIn("完成 1KB", lines[0])
        finally:
            dlg.close()

    def test_several_files_one_line_each(self):
        dlg, update, st = self.win._make_progress("下载", 2)
        try:
            for w in ("T0001", "T0002"):
                update(0, f"下载 {w}.pdf ...")
                update(1, REPLACE_LAST + f"下载 {w}.pdf ...完成 5KB")
            lines = self._dialog_lines(dlg)
            self.assertEqual(len(lines), 2, lines)
        finally:
            dlg.close()

    def test_no_download_record_tab(self):
        # 「下载记录」页签及 log_view 已删除（下载走弹窗）
        win = self.win
        self.assertFalse(hasattr(win, "log_view"))
        names = [win.tab_bottom.tabText(i) for i in range(win.tab_bottom.count())]
        self.assertNotIn("下载记录", names)

    def test_tabs_are_book_info_then_coll_info(self):
        # 右下页签：① 书籍信息 ② 丛书信息 ③ E书目录（原「下载记录」已删除）
        win = self.win
        tb = win.tab_bottom
        self.assertEqual(tb.count(), 3)
        self.assertEqual([tb.tabText(i) for i in range(3)],
                         ["书籍信息", "丛书信息", "E书目录"])
        self.assertTrue(tb.widget(0).isAncestorOf(win.detail))
        self.assertTrue(tb.widget(1).isAncestorOf(win.lbl_coll_info))
        self.assertTrue(tb.widget(2).isAncestorOf(win.lbl_cache_dir))
        self.assertTrue(tb.widget(2).isAncestorOf(win.lbl_xml_dir))
        self.assertTrue(tb.widget(2).isAncestorOf(win.lbl_out_dir))

    def test_click_book_activates_book_tab(self):
        # 三栏点书 → 显示书籍信息并切到「书籍信息」页签；点分组节点 → 清空且不切页签
        win = self.win
        win.tab_bottom.setCurrentIndex(1)
        win.nav_combo.setCurrentText("刊本")
        _ensure_app().processEvents()
        ed = win.tree.topLevelItem(0)
        win._on_tree_preview(ed, 0)
        self.assertEqual(win.detail.text(), "")
        self.assertEqual(win.tab_bottom.currentIndex(), 1)
        vol = next((ed.child(i) for i in range(ed.childCount()) if ed.child(i).childCount()), None)
        if vol is not None:
            win._on_tree_preview(vol.child(0), 0)
            self.assertIn("T", win.detail.text())
            self.assertEqual(win.tab_bottom.currentIndex(), 0)

    def test_download_button_uses_popup(self):
        # 下载/更新按钮 => _download_missing 弹窗（不再切页签、不改按钮文案）
        win = self.win
        col = Path(win.config["collections_dir"]) / "custom" / "下载测.json"
        col.parent.mkdir(parents=True, exist_ok=True)
        col.write_text(json.dumps({"id": "dl", "name": "下载测", "category": "custom",
                                   "tags": [], "work_ids": ["T0001", "T0002"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("下载测.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        calls = []
        win._download_missing = lambda pairs, dest, title="下载": calls.append(
            (list(pairs), title)) or True
        win._prompt_save_collection = lambda *a, **k: None
        win.chk_pdf.setChecked(True)
        win.chk_epub.setChecked(True)
        win.chk_docx.setChecked(False)
        win._on_download_button()
        self.assertEqual(len(calls), 1)
        pairs, title = calls[0]
        self.assertEqual(title, "下载/更新")
        self.assertEqual(sorted(pairs), [("T0001", "epub"), ("T0001", "pdf"),
                                         ("T0002", "epub"), ("T0002", "pdf")])
        self.assertEqual(win.btn_download.text(), "下载/更新")
        col.unlink(missing_ok=True)


class DownloadMissingTest(unittest.TestCase):
    """合并/ZIP/导出 及 下载/更新 共用：弹进度窗下载。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _patch(self, ok_works):
        from cbeta_publish.books import official_ebook_source as oes
        real = oes.download_ebook

        def fake(w, fmt, dest_dir, config=None, force=False):
            if w not in ok_works:
                return None
            p = oes.dest_path(w, fmt, dest_dir)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x" * 2048)
            return p
        oes.download_ebook = fake
        return lambda: setattr(oes, "download_ebook", real)

    def test_all_ok_returns_true(self):
        restore = self._patch({"T0001", "T0002"})
        try:
            ok = self.win._download_missing([("T0001", "pdf"), ("T0002", "pdf")],
                                            self.tmp / "eb", title="下载")
        finally:
            restore()
        self.assertTrue(ok)
        self.assertTrue((self.tmp / "eb" / "pdf" / "T0001.pdf").exists())
        self.assertEqual(self.win._dl_stats["ok"], 2)
        self.assertEqual(self.win._dl_stats["total"], 2)

    def test_partial_failure_returns_false(self):
        restore = self._patch({"T0001"})
        try:
            ok = self.win._download_missing([("T0001", "pdf"), ("T9999", "pdf")],
                                            self.tmp / "eb2", title="下载")
        finally:
            restore()
        self.assertFalse(ok)
        self.assertIn("T9999", " ".join(self.win._dl_stats["failed"]))

    # ---------- 窗口宽度 / 无错自动关闭 ----------
    def test_progress_dialog_is_narrow(self):
        dlg, update, st = self.win._make_progress("下载", 1)
        try:
            self.assertLessEqual(dlg.minimumWidth(), 520)     # 旧值 640 偏宽
            self.assertLessEqual(dlg.minimumHeight(), 360)
        finally:
            dlg.close()

    def _patch_progress(self):
        # 替换进度窗：只记录 finish 的总结与 autoclose_ms（offscreen 下真窗口会直接关闭）
        win = self.win
        real = win._make_progress
        cap = {}

        def fake(title, total):
            st = {"cancel": False, "lines": [], "oncancel": None,
                  "autoclose_ms": 0, "summary": None}

            def update(done, label="", is_html=False):
                if label:
                    st["lines"].append(str(label))
                return True

            def finish(lines=None):
                st["summary"] = list(lines or [])
            st["finish"] = finish
            cap["st"] = st

            class _D:
                pass
            return _D(), update, st
        win._make_progress = fake
        return cap, lambda: setattr(win, "_make_progress", real)

    def test_autoclose_after_ok_download(self):
        cap, restore_pp = self._patch_progress()
        restore_dl = self._patch({"T0001", "T0002"})
        try:
            ok = self.win._download_missing([("T0001", "pdf"), ("T0002", "pdf")],
                                            self.tmp / "eb3", title="下载（合并前）",
                                            autoclose_ok=True)
        finally:
            restore_dl()
            restore_pp()
        self.assertTrue(ok)
        self.assertEqual(cap["st"]["autoclose_ms"], 3000)
        self.assertTrue(any("自动关闭" in x for x in cap["st"]["summary"]), cap["st"]["summary"])

    def test_no_autoclose_on_failure(self):
        cap, restore_pp = self._patch_progress()
        restore_dl = self._patch({"T0001"})
        try:
            ok = self.win._download_missing([("T0001", "pdf"), ("T9999", "pdf")],
                                            self.tmp / "eb4", title="下载（合并前）",
                                            autoclose_ok=True)
        finally:
            restore_dl()
            restore_pp()
        self.assertFalse(ok)
        self.assertEqual(cap["st"]["autoclose_ms"], 0)

    def test_no_autoclose_for_download_button(self):
        # 下载/更新 按钮（autoclose_ok=False）成功也不自动关
        cap, restore_pp = self._patch_progress()
        restore_dl = self._patch({"T0001"})
        try:
            self.win._download_missing([("T0001", "pdf")], self.tmp / "eb5",
                                       title="下载/更新")
        finally:
            restore_dl()
            restore_pp()
        self.assertEqual(cap["st"]["autoclose_ms"], 0)


class MergeXmlSourceTest(unittest.TestCase):
    """合并来源=自制：整批走库调用生成（平展目录），说明页加一句注明。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _select_coll(self, work_ids):
        win = self.win
        col = Path(win.config["collections_dir"]) / "custom" / "合测.json"
        col.write_text(json.dumps({"id": "m", "name": "合测", "category": "custom",
                                   "tags": [], "work_ids": list(work_ids)},
                                  ensure_ascii=False), encoding="utf-8")
        self._coll_file = col
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("合测.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()

    def test_xml_merge_uses_preset_and_flat_dir(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        import cbeta_publish.books.ebook_merger as em
        win = self.win
        self._select_coll(["T0001"])
        win.config["default_source"] = "xml"
        win.config["xml_to_ebooks_dir"] = str(self.tmp / "xb")
        # 预设目录固定在 xml2pdf 仓库 presets/：用临时仓库根模拟
        root = self.tmp / "x2p"
        (root / "presets").mkdir(parents=True, exist_ok=True)
        preset = root / "presets" / "my.json"
        preset.write_text("{}", encoding="utf-8")
        win.config["xml2pdf"]["path"] = str(root)
        win.config["xml2pdf"]["preset"] = "my"
        # 工作根隔离到 tmp：直生命名取工作目录名（L2 带书名）
        _old_ebook = (win.config.get("xml2pdf") or {}).get("cbeta_ebook")
        (self.tmp / "xml" / "T0001 测经").mkdir(parents=True, exist_ok=True)
        (self.tmp / "xml" / "T0001 测经" / "T01n0001.xml").write_bytes(b"<x/>")
        win.config["xml2pdf"]["cbeta_ebook"] = str(self.tmp / "xml")
        win.chk_pdf.setChecked(True)
        win.chk_epub.setChecked(False)
        win.chk_docx.setChecked(True)     # 勾了 docx：合并应过滤掉，只合 pdf
        calls = []
        real_convert, real_merge = b.convert, em.merge_pdfs

        def fake_convert(w, xml, out, config, fmt="pdf", preset=None, stop=None):
            calls.append((w, xml, fmt, preset, str(out)))
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(b"x")
            return Path(out)

        def fake_merge(sources, out, **kw):
            Path(out).write_bytes(b"PDF")
            return [Path(out)]
        b.convert, em.merge_pdfs = fake_convert, fake_merge
        try:
            win._merge()
            _ensure_app().processEvents()
        finally:
            b.convert, em.merge_pdfs = real_convert, real_merge
            if _old_ebook is None:
                win.config["xml2pdf"].pop("cbeta_ebook", None)
            else:
                win.config["xml2pdf"]["cbeta_ebook"] = _old_ebook
        self.assertEqual(len(calls), 1)
        w, xml, fmt, preset_arg, out = calls[0]
        self.assertEqual((w, fmt), ("T0001", "pdf"))
        self.assertIsNone(xml)   # 只传 work id，XML 解析归 xml2pdf（P5a≠P5，不再自行定位）
        self.assertEqual(Path(preset_arg), preset)          # 预设透传
        self.assertEqual(out, str(self.tmp / "xb" / "pdf" / "T0001 测经.pdf"))  # {fmt}/分层+L2带书名
        self._coll_file.unlink(missing_ok=True)

    def test_merge_only_docx_warns(self):
        # 只勾 docx：合并不支持，直接警告，不进入合成
        from PySide6.QtWidgets import QMessageBox
        win = self.win
        self._select_coll(["T0001"])
        win.chk_pdf.setChecked(False)
        win.chk_epub.setChecked(False)
        win.chk_docx.setChecked(True)
        warned = []
        real = QMessageBox.warning
        QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a))
        try:
            win._merge()
        finally:
            QMessageBox.warning = real
            win.chk_pdf.setChecked(True)
        self.assertTrue(warned, "只勾 docx 应弹警告")
        self._coll_file.unlink(missing_ok=True)

    def test_intro_note_only_for_made(self):
        win = self.win
        cfg = {"enabled": True, "intro": {"enabled": True}}
        made = win._intro_for(["T0001"], cfg, made_by_xml=True)
        self.assertEqual(made.get("note"), "依 CBETA XML 自制")   # 默认文案
        off = win._intro_for(["T0001"], cfg, made_by_xml=False)
        self.assertIsNone(off.get("note"))
        # 设置里可改注明文字
        cfg2 = {"enabled": True, "intro": {"enabled": True, "note": "自訂註記"}}
        self.assertEqual(win._intro_for(["T0001"], cfg2, made_by_xml=True).get("note"), "自訂註記")

    def _xml_env(self):
        win = self.win
        win.config["default_source"] = "xml"
        win.config["xml_to_ebooks_dir"] = str(self.tmp / "xb_env")
        return Path(win.config["xml_to_ebooks_dir"])

    def test_merge_reuses_existing_in_missing_mode(self):
        # 合并恒「仅缺」：已有产物 → 不再调用 convert
        import cbeta_publish.books.xml2pdf_bridge as b
        import cbeta_publish.books.ebook_merger as em
        win = self.win
        self._select_coll(["T0001"])
        out_dir = self._xml_env()
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "pdf").mkdir(exist_ok=True)
        (out_dir / "pdf" / "T0001.pdf").write_bytes(b"old")
        calls = []
        real_convert, real_merge = b.convert, em.merge_pdfs
        b.convert = lambda *a, **k: (calls.append(a) or a[2])
        em.merge_pdfs = lambda sources, out, **kw: (Path(out).write_bytes(b"PDF"), [Path(out)])[1]
        try:
            win._merge()
            _ensure_app().processEvents()
        finally:
            b.convert, em.merge_pdfs = real_convert, real_merge
        self.assertEqual(calls, [])          # 复用，未重生成
        self._coll_file.unlink(missing_ok=True)

    def test_ensure_xml_batch_generates_and_reports(self):
        # ZIP/导出 共用的批量生成助手：ok_map/failed 结构
        import cbeta_publish.books.xml2pdf_bridge as b
        win = self.win
        out_dir = self._xml_env()
        calls = []
        real = b.convert

        def fake_convert(w, xml, out, config, fmt="pdf", preset=None, stop=None):
            calls.append((w, fmt))
            if w == "T9999":
                return None
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(b"x")
            return Path(out)
        b.convert = fake_convert
        try:
            ok_map, failed, cancelled = win._ensure_xml_batch(["T0001", "T9999"], ["pdf"])
        finally:
            b.convert = real
        self.assertFalse(cancelled)
        self.assertIn("T0001", ok_map["pdf"])
        self.assertEqual(len(failed), 1)
        self.assertIn("T9999", failed[0])

    def test_ensure_xml_batch_flattens_multi_products(self):
        # 同一 work 的多个自制产物都要进入 ok_map，不能只留第一项。
        import cbeta_publish.books.xml2pdf_bridge as b
        win = self.win
        out_dir = self._xml_env()
        one = out_dir / "pdf" / "TX0011 上.pdf"
        two = out_dir / "pdf" / "TX0011 中下.pdf"
        one.parent.mkdir(parents=True, exist_ok=True)
        one.write_bytes(b"a")
        two.write_bytes(b"b")
        real = b.ensure_products
        b.ensure_products = lambda *a, **k: ([one, two], True)
        try:
            ok_map, failed, cancelled = win._ensure_xml_batch(["TX0011"], ["pdf"])
        finally:
            b.ensure_products = real
        self.assertFalse(cancelled)
        self.assertEqual(failed, [])
        self.assertEqual(ok_map["pdf"]["TX0011"], [one, two])

    def test_expand_group_files_preserves_all_products(self):
        # 分组合并时，一个 work 的多个自制产物都要进入同一个分组。
        first = Path("TX0011 上.pdf")
        second = Path("TX0011 中下.pdf")
        group = {"ok": [first], "titles": ["T0001"], "works": ["T0001"]}
        expanded = MainWindow._expand_group_files(
            group, {"T0001": [first, second]})
        self.assertEqual(expanded["ok"], [first, second])
        self.assertEqual(expanded["titles"], ["T0001", "TX0011 中下"])
        self.assertEqual(expanded["works"], ["T0001"])

    def _patch_render_with_companion(self, with_companion=True):
        """假渲染：pdf 产物旁边按需写伴生 docx；记录调用 (work, fmt)。"""
        import cbeta_publish.books.xml2pdf_bridge as b
        calls = []
        real = b.ensure_products

        def fake(w, fmt, base, config, preset=None, regen_all=False, name=None):
            calls.append((w, fmt))
            d = Path(base) / fmt
            d.mkdir(parents=True, exist_ok=True)
            out = d / f"{w}.{fmt}"
            out.write_bytes(b"x")
            if fmt == "pdf" and with_companion:
                (d / f"{w}.docx").write_bytes(b"D")
            return [out], False
        b.ensure_products = fake
        return calls, lambda: setattr(b, "ensure_products", real)

    def test_ensure_xml_batch_reuses_pdf_companion(self):
        # pdf+docx 同跑：docx 直接用 pdf 伴生，跳过 docx 渲染
        win = self.win
        out_dir = self._xml_env()
        shutil.rmtree(out_dir, ignore_errors=True)
        old = (win.config.get("xml2pdf", {}) or {}).get("reuse_pdf_companion")
        win.config.setdefault("xml2pdf", {})["reuse_pdf_companion"] = True
        calls, restore = self._patch_render_with_companion(True)
        try:
            ok_map, failed, cancelled = win._ensure_xml_batch(["T0001"], ["pdf", "docx"])
        finally:
            restore()
            if old is None:
                win.config["xml2pdf"].pop("reuse_pdf_companion", None)
            else:
                win.config["xml2pdf"]["reuse_pdf_companion"] = old
        self.assertFalse(cancelled)
        self.assertEqual(failed, [])
        self.assertEqual(calls, [("T0001", "pdf")])       # docx 未渲染
        docx = ok_map["docx"]["T0001"]
        self.assertEqual([p.name for p in docx], ["T0001.docx"])
        self.assertTrue(docx[0].is_file())

    def test_ensure_xml_batch_companion_off_renders_docx(self):
        # 开关关：docx 照常渲染（不看伴生）
        win = self.win
        out_dir = self._xml_env()
        shutil.rmtree(out_dir, ignore_errors=True)
        win.config.setdefault("xml2pdf", {})["reuse_pdf_companion"] = False
        calls, restore = self._patch_render_with_companion(True)
        try:
            win._ensure_xml_batch(["T0001"], ["pdf", "docx"])
        finally:
            restore()
            win.config["xml2pdf"]["reuse_pdf_companion"] = True
        self.assertEqual(sorted(calls), [("T0001", "docx"), ("T0001", "pdf")])

    def test_ensure_xml_batch_no_companion_renders_docx(self):
        # 无伴生（html 管线等）：docx 回退正常渲染
        win = self.win
        out_dir = self._xml_env()
        shutil.rmtree(out_dir, ignore_errors=True)
        win.config.setdefault("xml2pdf", {})["reuse_pdf_companion"] = True
        calls, restore = self._patch_render_with_companion(False)
        try:
            win._ensure_xml_batch(["T0001"], ["pdf", "docx"])
        finally:
            restore()
        self.assertIn(("T0001", "docx"), calls)


class MergeEditNoteGuardTest(unittest.TestCase):
    """编辑说明前置检查：启用但无文件/文件无效/封面总开关关闭 → 弹框问是否继续。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _select_coll(self, work_ids):
        win = self.win
        col = Path(win.config["collections_dir"]) / "custom" / "合测.json"
        col.write_text(json.dumps({"id": "m", "name": "合测", "category": "custom",
                                   "tags": [], "work_ids": list(work_ids)},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("合测.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()

    def _run_merge_no(self, cover, coll_note=None):
        # 返回 (boxes, generated_calls)
        import cbeta_publish.books.xml2pdf_bridge as b
        from PySide6.QtWidgets import QMessageBox
        win = self.win
        self._select_coll(["T0001"])
        _d = win._coll_dict(win.coll_combo.currentData())
        if coll_note is not None:
            _d["edit_note"] = coll_note
        else:
            _d.pop("edit_note", None)
        win.config["default_source"] = "xml"
        win.config["xml_to_ebooks_dir"] = str(self.tmp / "xb")
        root = self.tmp / "x2p"
        (root / "presets").mkdir(parents=True, exist_ok=True)
        win.config["xml2pdf"]["path"] = str(root)
        win.config["xml2pdf"]["preset"] = ""
        win.config["cover"] = cover
        win.chk_pdf.setChecked(True)
        win.chk_epub.setChecked(False)
        win.chk_docx.setChecked(False)
        boxes = []
        real_box = win._wrap_box
        win._wrap_box = lambda *a, **k: boxes.append(a) or QMessageBox.No
        calls = []
        real_convert = b.convert

        def fake_convert(*a, **k):
            calls.append(a)
            raise AssertionError("should not generate after abort")

        b.convert = fake_convert
        try:
            win._merge()
            _ensure_app().processEvents()
        finally:
            win._wrap_box = real_box
            b.convert = real_convert
        return boxes, calls

    def test_no_file_asks_and_aborts(self):
        boxes, calls = self._run_merge_no(
            {"enabled": True, "edit_note": {"file": "", "enabled": True}})
        self.assertTrue(any("未选择说明文件" in str(a) for a in boxes), boxes)
        self.assertEqual(calls, [])
        self.assertIn("已取消合成", self.win.detail.text())

    def test_cover_off_asks_and_aborts(self):
        f = self.tmp / "n.txt"
        f.write_text("<title>T\n正文\n", encoding="utf-8")
        boxes, calls = self._run_merge_no(
            {"enabled": False, "edit_note": {"file": str(f), "enabled": True}})
        self.assertTrue(any("封面总开关" in str(a) for a in boxes), boxes)
        self.assertEqual(calls, [])

    def test_collection_specific_note_guard(self):
        # 丛书特定说明页：启用但无文件 → 前置检查弹框（作用于当前丛书）
        boxes, calls = self._run_merge_no(
            {"enabled": True, "edit_note": {"file": "", "enabled": False}},
            coll_note={"file": "", "enabled": True})
        self.assertTrue(any("加丛书说明页" in str(a) for a in boxes), boxes)
        self.assertEqual(calls, [])

    def test_ok_proceeds_without_question(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        import cbeta_publish.books.ebook_merger as em
        win = self.win
        self._select_coll(["T0001"])
        win.config["default_source"] = "xml"
        win.config["xml_to_ebooks_dir"] = str(self.tmp / "xb")
        win.config["cover"] = {"enabled": True,
                               "edit_note": {"file": "", "enabled": False}}
        win.chk_pdf.setChecked(True)
        win.chk_epub.setChecked(False)
        win.chk_docx.setChecked(False)
        boxes = []
        real_box = win._wrap_box
        win._wrap_box = lambda *a, **k: boxes.append(a) or None
        real_convert, real_merge = b.convert, em.merge_pdfs

        def fake_convert(w, xml, out, config, fmt="pdf", preset=None, stop=None):
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(b"x")
            return Path(out)

        def fake_merge(sources, out, **kw):
            Path(out).write_bytes(b"PDF")
            return [Path(out)]
        b.convert, em.merge_pdfs = fake_convert, fake_merge
        try:
            win._merge()
            _ensure_app().processEvents()
        finally:
            win._wrap_box = real_box
            b.convert, em.merge_pdfs = real_convert, real_merge
        self.assertFalse(any("编辑说明" in str(a) for a in boxes), boxes)


if __name__ == "__main__":
    unittest.main()
