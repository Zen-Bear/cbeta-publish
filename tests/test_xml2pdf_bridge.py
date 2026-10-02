# -*- coding: utf-8 -*-
"""链路B 桥接：库调用 argv 装配、预设目录、平展输出、复用规则。

注：publish 侧不再自行定位 XML（CBReader 是 P5a 按卷切分，不符合
xml2pdf 要的 P5 整部经；XML 源解析归 xml2pdf 的 materialize_work），
一律传 work id。
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.books import xml2pdf_bridge as _b


class BridgeConvertLibTest(unittest.TestCase):
    """库调用：argv 装配（-i 路径/回退传 id、-f/-o/--config）与取消。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.x2p = self.dir / "x2p"
        self.x2p.mkdir()
        self.cfg = {"xml2pdf": {"path": str(self.x2p)}}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _patch_run(self, code=0, touch=True):
        import cbeta_publish.books.xml2pdf_bridge as b
        real = b._run_cli
        calls = []

        def fake(argv):
            calls.append(list(argv))
            if touch:
                try:
                    oi = argv.index("-o")
                    Path(argv[oi + 1]).write_bytes(b"x")
                except Exception:
                    pass
            return code
        b._run_cli = fake
        return calls, lambda: setattr(b, "_run_cli", real)

    def test_argv_with_xml_and_preset(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        xml = self.dir / "T01n0001.xml"
        xml.write_text("<x/>", encoding="utf-8")
        out = self.dir / "T0001.pdf"
        preset = self.dir / "my.json"
        preset.write_text("{}", encoding="utf-8")
        calls, restore = self._patch_run()
        try:
            got = b.convert("T0001", xml, out, self.cfg, fmt="pdf", preset=preset)
        finally:
            restore()
        self.assertEqual(got, out)
        self.assertEqual(len(calls), 1)
        a = calls[0]
        self.assertEqual(a[a.index("-i") + 1], str(xml))
        self.assertEqual(a[a.index("-f") + 1], "pdf")
        self.assertEqual(a[a.index("-o") + 1], str(out))
        self.assertEqual(a[a.index("--config") + 1], str(preset))

    def test_argv_without_preset_omits_config(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = self.dir / "T0001.pdf"
        calls, restore = self._patch_run()
        try:
            b.convert("T0001", None, out, self.cfg, fmt="epub", preset=None)
        finally:
            restore()
        a = calls[0]
        self.assertEqual(a[a.index("-i") + 1], "T0001")   # 无本地 XML 传 id
        self.assertNotIn("--config", a)

    def test_argv_passes_cbeta_ebook_when_configured(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = self.dir / "T0001.pdf"
        ebook = self.dir / "ebook"
        ebook.mkdir()
        cfg = {"xml2pdf": {"path": str(self.x2p), "cbeta_ebook": str(ebook)}}
        calls, restore = self._patch_run()
        try:
            b.convert("T0001", None, out, cfg)
        finally:
            restore()
        a = calls[0]
        self.assertEqual(a[a.index("--cbeta-ebook") + 1], str(ebook))
        # 未配置 → 用默认 CBETA XML 目录（不可空，仍会传）
        calls2, restore2 = self._patch_run()
        try:
            b.convert("T0001", None, out, self.cfg)
        finally:
            restore2()
        self.assertEqual(calls2[0][calls2[0].index("--cbeta-ebook") + 1],
                         str(b.xml_work_dir(self.cfg)))
        self.assertEqual(b.xml_work_dir({}), b.PROJECT_ROOT / "cbeta_xml")

    def test_stop_cancels_before_run(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = self.dir / "T0001.pdf"
        calls, restore = self._patch_run()
        try:
            got = b.convert("T0001", None, out, self.cfg, stop=lambda: True)
        finally:
            restore()
        self.assertIsNone(got)
        self.assertEqual(calls, [])

    def test_nonzero_code_returns_none(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = self.dir / "T0001.pdf"
        calls, restore = self._patch_run(code=1, touch=False)
        try:
            got = b.convert("T0001", None, out, self.cfg)
        finally:
            restore()
        self.assertIsNone(got)

    def test_missing_x2p_dir_returns_none(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = self.dir / "T0001.pdf"
        got = b.convert("T0001", None, out, {"xml2pdf": {"path": str(self.dir / "nope")}})
        self.assertIsNone(got)


class BridgePresetDirTest(unittest.TestCase):
    """预设目录：列出合法预设、解析、平展输出目录。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        # 预设目录固定在 xml2pdf 仓库下 presets/：用临时仓库根模拟
        self.root = self.dir / "x2p"
        (self.root / "presets").mkdir(parents=True)
        (self.root / "presets" / "a.json").write_text("{}", encoding="utf-8")
        (self.root / "presets" / "run.json").write_text('// c\n{"k": 1}', encoding="utf-8")
        (self.root / "presets" / "note.txt").write_text("x", encoding="utf-8")
        self.cfg = {"xml2pdf": {"path": str(self.root)}}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_list_presets(self):
        # 上游 API 不可用（临时仓库根无 pycbeta）时回退本地扫描：stem 名
        import cbeta_publish.books.xml2pdf_bridge as b
        self.assertEqual(b.list_presets(self.cfg), ["a", "run"])

    def test_resolve_preset(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        d = self.root / "presets"
        self.assertIsNone(b.resolve_preset(self.cfg, ""))
        self.assertEqual(b.resolve_preset(self.cfg, "a"), d / "a.json")
        self.assertEqual(b.resolve_preset(self.cfg, "a.json"), d / "a.json")
        self.assertIsNone(b.resolve_preset(self.cfg, "nope"))

    def test_load_and_save_preset(self):
        # load/save 走上游 API（不可用时回退本地读写）
        import cbeta_publish.books.xml2pdf_bridge as b
        self.assertEqual(b.load_preset_dict("a.json", self.cfg), {})
        p = b.save_preset(self.cfg, "我的配置", {"default_page": "a4"})
        self.assertIsNotNone(p)
        self.assertEqual(p, self.root / "presets" / "我的配置.json")
        self.assertEqual(b.load_preset_dict("我的配置", self.cfg), {"default_page": "a4"})
        self.assertIn("我的配置", b.list_presets(self.cfg))

    def test_fmt_dest_and_find_built(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        base = self.dir / "out"
        base.mkdir()
        self.assertEqual(b.xml_dest("T0001", "pdf", base), base / "pdf" / "T0001.pdf")
        self.assertEqual(b.xml_dest("T0001", "pdf", base, name="T0001 中論"),
                         base / "pdf" / "T0001 中論.pdf")
        self.assertIsNone(b.find_built("T0001", "pdf", base))
        (base / "pdf").mkdir()
        (base / "pdf" / "T0001 中論.pdf").write_bytes(b"x")   # 同目录异名通配
        self.assertEqual(b.find_built("T0001", "pdf", base), base / "pdf" / "T0001 中論.pdf")
        (base / "pdf" / "T0001.pdf").write_bytes(b"x")        # 精确名优先
        self.assertEqual(b.find_built("T0001", "pdf", base), base / "pdf" / "T0001.pdf")
        # 旧版顶层平展不再认（不双读）
        (base / "pdf" / "T0001.pdf").unlink()
        (base / "pdf" / "T0001 中論.pdf").unlink()
        (base / "T0001.pdf").write_bytes(b"x")
        self.assertIsNone(b.find_built("T0001", "pdf", base))
        # 边界守卫：T185 不误命中 T1858 书名
        (base / "pdf" / "T1858 肇論疏.pdf").write_bytes(b"x")
        self.assertIsNone(b.find_built("T185", "pdf", base))
        self.assertEqual(b.find_built("T1858", "pdf", base),
                         base / "pdf" / "T1858 肇論疏.pdf")

    def test_ensure_one_missing_vs_all(self):
        # 仅缺：已有产物直接复用（不调 convert）；全部：一律重跑 convert 并覆盖原路径
        import cbeta_publish.books.xml2pdf_bridge as b
        base = self.dir / "out"
        (base / "pdf").mkdir(parents=True)
        calls = []

        def fake_convert(w, xml, out, config, fmt="pdf", preset=None, stop=None):
            calls.append(Path(out))
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(b"x")
            return Path(out)
        real = b.convert
        b.convert = fake_convert
        try:
            # 无产物 → 生成到 {fmt}/{work}.{fmt}
            p, reused = b.ensure_one("T0001", "pdf", base, self.cfg)
            self.assertFalse(reused)
            self.assertEqual(len(calls), 1)
            self.assertEqual(p, base / "pdf" / "T0001.pdf")
            # 已有 → 仅缺模式复用
            p2, reused2 = b.ensure_one("T0001", "pdf", base, self.cfg)
            self.assertTrue(reused2)
            self.assertEqual(p2, p)
            self.assertEqual(len(calls), 1)
            # 全部模式 → 重跑，覆盖同名
            p3, reused3 = b.ensure_one("T0001", "pdf", base, self.cfg, regen_all=True)
            self.assertFalse(reused3)
            self.assertEqual(len(calls), 2)
            self.assertEqual(p3, p)
            # 异名产物在全部模式下也覆盖原路径，不留两份
            (base / "pdf" / "T0001.pdf").unlink()
            gui = base / "pdf" / "T0001 中論.pdf"
            gui.write_bytes(b"x")
            p4, _ = b.ensure_one("T0001", "pdf", base, self.cfg, regen_all=True)
            self.assertEqual(p4, gui)
            self.assertEqual(len(calls), 3)
            self.assertFalse((base / "pdf" / "T0001.pdf").exists())
        finally:
            b.convert = real

    def test_dirs_are_absolute_and_unified(self):
        # 目录统一绝对路径：缺省与相对值都按工程根解析
        import cbeta_publish.books.xml2pdf_bridge as b
        default = b.xml_books_dir({})
        self.assertTrue(default.is_absolute())
        self.assertEqual(b.xml_books_dir({"xml_to_ebooks_dir": "rel/xb"}),
                         b.PROJECT_ROOT / "rel" / "xb")
        abs_p = self.dir / "xb2"
        self.assertEqual(b.xml_books_dir({"xml_to_ebooks_dir": str(abs_p)}), abs_p)
        # 预设目录固定在仓库下 presets/
        self.assertEqual(b.presets_dir({"xml2pdf": {"path": "E:/x"}}),
                         Path("E:/x") / "presets")


class BridgeRunWrapperTest(unittest.TestCase):
    """临时 run.json 包装：5 槽沿用仓库 run.json，config-json 指本次预设，用后删。"""

    def _real_cfg(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        root = b.PROJECT_ROOT.parent / "xml2pdf"
        if not (root / "pycbeta" / "theme.py").is_file():
            self.skipTest("no real xml2pdf sibling repo")
        return {"xml2pdf": {"path": str(root)}}, root

    def test_wrapper_inherits_run_slots(self):
        import json
        import cbeta_publish.books.xml2pdf_bridge as b
        cfg, _root = self._real_cfg()
        preset = Path(tempfile.mkdtemp()) / "p.json"
        try:
            preset.write_text("{}", encoding="utf-8")
            w = b.write_run_wrapper(cfg, preset)
            self.assertIsNotNone(w)
            try:
                d = json.loads(Path(w).read_text(encoding="utf-8"))
                self.assertEqual(d["config-json"], str(preset.resolve()))
                # 5 槽齐全且沿用仓库当前 run.json（pdf 主题槽非空即证明未回出厂）
                self.assertTrue(d.get("pdf-docx-theme"))
                self.assertIn("html-epub-theme", d)
            finally:
                b.remove_temp_preset(w)
            self.assertFalse(Path(w).exists())
        finally:
            shutil.rmtree(preset.parent, ignore_errors=True)

    def test_convert_uses_wrapper_and_deletes_it(self):
        import json
        import cbeta_publish.books.xml2pdf_bridge as b
        cfg, _root = self._real_cfg()
        preset = Path(tempfile.mkdtemp()) / "p.json"
        preset.write_text("{}", encoding="utf-8")
        out = Path(tempfile.mkdtemp()) / "T0001.pdf"
        seen = {}
        real = b._run_cli

        def fake(argv):
            a = list(argv)
            cp = a[a.index("--config") + 1]
            seen["cfg"] = cp
            seen["data"] = json.loads(Path(cp).read_text(encoding="utf-8"))
            Path(a[a.index("-o") + 1]).write_bytes(b"x")
            return 0
        b._run_cli = fake
        try:
            got = b.convert("T0001", None, out, cfg, fmt="pdf", preset=preset)
        finally:
            b._run_cli = real
            shutil.rmtree(preset.parent, ignore_errors=True)
            shutil.rmtree(out.parent, ignore_errors=True)
        self.assertEqual(got, out)
        self.assertNotEqual(seen["cfg"], str(preset))   # 传的是包装，不是预设本身
        self.assertEqual(seen["data"]["config-json"], str(preset.resolve()))
        self.assertTrue(seen["data"].get("pdf-docx-theme"))
        self.assertFalse(Path(seen["cfg"]).exists())    # 用后删除

    def test_convert_falls_back_to_preset_without_upstream(self):
        # 上游不可用（假仓库根）→ 回退直传预设（旧行为不断）
        import cbeta_publish.books.xml2pdf_bridge as b
        d = Path(tempfile.mkdtemp())
        try:
            fake_root = d / "x2p"
            fake_root.mkdir()
            cfg = {"xml2pdf": {"path": str(fake_root)}}
            preset = d / "my.json"
            preset.write_text("{}", encoding="utf-8")
            out = d / "T0001.pdf"
            calls = []
            real = b._run_cli

            def fake(argv):
                calls.append(list(argv))
                Path(argv[argv.index("-o") + 1]).write_bytes(b"x")
                return 0
            b._run_cli = fake
            try:
                got = b.convert("T0001", None, out, cfg, fmt="pdf", preset=preset)
            finally:
                b._run_cli = real
            self.assertEqual(got, out)
            self.assertEqual(calls[0][calls[0].index("--config") + 1], str(preset))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class BridgeVerifyWorkTest(unittest.TestCase):
    """进程内校验：argv 装配（-i work/-f 逗号/-o/--verify/--cbeta-ebook）与报告定位。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.x2p = self.dir / "x2p"
        self.x2p.mkdir()
        self.cfg = {"xml2pdf": {"path": str(self.x2p)}}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _patch(self, touch_report=True):
        import cbeta_publish.books.xml2pdf_bridge as b
        real = b._run_cli
        calls = []

        def fake(argv):
            calls.append(list(argv))
            if touch_report:
                out = Path(argv[argv.index("-o") + 1])
                vd = out / "T0001 大般若經（验证）"
                vd.mkdir(parents=True, exist_ok=True)
                (vd / "report.txt").write_text(
                    "=== T0001\n  [OK]  docx 缺0 多0\n", encoding="utf-8")
            return 0
        b._run_cli = fake
        return calls, lambda: setattr(b, "_run_cli", real)

    def test_argv_and_report_found(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = self.dir / "v"
        calls, restore = self._patch()
        try:
            rp = b.verify_work("T0001", ["pdf", "epub"], out, self.cfg)
        finally:
            restore()
        self.assertIsNotNone(rp)
        self.assertTrue(rp.is_file())
        self.assertTrue(b.verify_report_pass(rp))
        a = calls[0]
        self.assertEqual(a[a.index("-i") + 1], "T0001")
        self.assertEqual(a[a.index("-f") + 1], "pdf,epub")
        self.assertEqual(a[a.index("-o") + 1], str(out))
        self.assertIn("--verify", a)
        self.assertEqual(a[a.index("--cbeta-ebook") + 1], str(b.xml_work_dir(self.cfg)))
        self.assertNotIn("--config", a)   # 出厂默认不传
        # 校验阈值：缺省透传 5/5
        self.assertEqual(a[a.index("--verify-max-diff") + 1], "5")
        self.assertEqual(a[a.index("--verify-diff-lines") + 1], "5")

    def test_argv_verify_thresholds(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        self.cfg["xml2pdf"]["verify_max_diff"] = 3
        self.cfg["xml2pdf"]["verify_diff_lines"] = 7
        calls, restore = self._patch()
        try:
            b.verify_work("T0001", ["pdf"], self.dir / "vt", self.cfg)
        finally:
            restore()
        a = calls[0]
        self.assertEqual(a[a.index("--verify-max-diff") + 1], "3")
        self.assertEqual(a[a.index("--verify-diff-lines") + 1], "7")

    def test_argv_verify_thresholds_clamped(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        self.cfg["xml2pdf"]["verify_max_diff"] = 999
        self.cfg["xml2pdf"]["verify_diff_lines"] = -3
        calls, restore = self._patch()
        try:
            b.verify_work("T0001", ["pdf"], self.dir / "vc", self.cfg)
        finally:
            restore()
        a = calls[0]
        self.assertEqual(a[a.index("--verify-max-diff") + 1], "50")
        self.assertEqual(a[a.index("--verify-diff-lines") + 1], "0")

    def test_no_report_returns_none(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        calls, restore = self._patch(touch_report=False)
        try:
            rp = b.verify_work("T0001", ["pdf"], self.dir / "v2", self.cfg)
        finally:
            restore()
        self.assertIsNone(rp)

    def test_verify_reports_both_namings(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        d = self.dir / "v3"
        vd1 = d / "T0001 涅槃（验证）"
        vd1.mkdir(parents=True)
        (vd1 / "T0001_verify_report.txt").write_text("=== T0001\n [OK]\n", encoding="utf-8")
        vd2 = d / "T0002 般若（验证）"
        vd2.mkdir(parents=True)
        (vd2 / "report.txt").write_text("=== T0002\n [FAIL]\n", encoding="utf-8")
        got = dict((stem, rp.name) for rp, stem in b.verify_reports(d))
        self.assertEqual(got.get("T0001"), "T0001_verify_report.txt")
        self.assertEqual(got.get("T0002"), "report.txt")

    def test_verify_reports_dedupes_same_stem_newest(self):
        # 同一书旧（独立窗）与新（CLI）报告并存：只取最新一份，不重复计数
        import os
        import cbeta_publish.books.xml2pdf_bridge as b
        d = self.dir / "v4"
        vd = d / "T0003 法華（验证）"
        vd.mkdir(parents=True)
        old = vd / "T0003_verify_report.txt"
        new = vd / "report.txt"
        old.write_text("=== T0003\n [OK]\n", encoding="utf-8")
        new.write_text("=== T0003\n [FAIL]\n", encoding="utf-8")
        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))
        got = b.verify_reports(d)
        self.assertEqual(len(got), 1)
        rp, stem = got[0]
        self.assertEqual((stem, rp.name), ("T0003", "report.txt"))
        self.assertFalse(b.verify_report_pass(rp))    # 取的是新的 FAIL


class BridgeTempTrackingTest(unittest.TestCase):
    """临时 run/preset 登记与退出兜底：正常删除即注销；残留由 cleanup 删光。"""

    def setUp(self):
        import os
        import sys
        from types import ModuleType
        import cbeta_publish.books.xml2pdf_bridge as b
        self._b = b
        self._saved_live = set(b._LIVE_TEMP_FILES)
        b._LIVE_TEMP_FILES.clear()
        self.dir = Path(tempfile.mkdtemp())
        self.root = self.dir / "x2p"
        (self.root / "pycbeta").mkdir(parents=True)
        theme_py = self.root / "pycbeta" / "theme.py"
        theme_py.write_text("# stub", encoding="utf-8")

        def _load_run_config(*a, **k):
            return {"a": "1"}

        pkg = ModuleType("pycbeta")
        pkg.__path__ = [str(self.root / "pycbeta")]
        mod = ModuleType("pycbeta.theme")
        mod.__file__ = str(theme_py)
        mod.load_run_config = _load_run_config
        mod.RUN_KEYS = ("a",)
        self._saved_mods = {k: sys.modules.get(k) for k in ("pycbeta", "pycbeta.theme")}
        sys.modules["pycbeta"] = pkg
        sys.modules["pycbeta.theme"] = mod
        self.cfg = {"xml2pdf": {"path": str(self.root)}}
        self.preset = self.dir / "p.json"
        self.preset.write_text("{}", encoding="utf-8")

    def tearDown(self):
        import sys
        import cbeta_publish.books.xml2pdf_bridge as b
        for k, v in self._saved_mods.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        b._LIVE_TEMP_FILES.clear()
        b._LIVE_TEMP_FILES.update(self._saved_live)
        shutil.rmtree(self.dir, ignore_errors=True)

    def _key(self, p):
        import os
        return os.path.normcase(os.path.abspath(str(p)))

    def test_wrapper_tracked_and_untracked_on_remove(self):
        b = self._b
        w = b.write_run_wrapper(self.cfg, self.preset)
        self.assertIsNotNone(w)
        self.assertTrue(w.exists())
        self.assertIn(self._key(w), b._LIVE_TEMP_FILES)
        b.remove_temp_preset(w)
        self.assertFalse(w.exists())
        self.assertNotIn(self._key(w), b._LIVE_TEMP_FILES)

    def test_cleanup_deletes_leftovers(self):
        b = self._b
        w = b.write_run_wrapper(self.cfg, self.preset)
        self.assertTrue(w.exists())
        left = b.cleanup_live_wrappers()
        self.assertIn(self._key(w), [self._key(p) for p in left])
        self.assertFalse(w.exists())
        self.assertEqual(b._LIVE_TEMP_FILES, set())

    def test_cleanup_empty_is_noop(self):
        self.assertEqual(self._b.cleanup_live_wrappers(), [])


class BridgeReportFormatsTest(unittest.TestCase):
    """逐格式报告解析：CLI（标记行+【源】行）与独立窗（标记行含格式）两种。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_cli_report(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        p = self.dir / "report.txt"
        p.write_text(
            "=== T01n0032.xml\n"
            "  [OK] (缺0/多0 ≤阈值10)\n"
            "  pdf→docx 【源】a.docx\n"
            "  pdf→docx 【新】b.docx\n"
            "  [FAIL] (缺3/多1 >阈值10)\n"
            "  epub 【源】c.epub\n"
            "  epub 【新】d.epub\n",
            encoding="utf-8")
        self.assertEqual(b.verify_report_formats(p), {"pdf": True, "epub": False})

    def test_gui_report(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        p = self.dir / "T0001_verify_report.txt"
        p.write_text(
            "=== T0001\n"
            "  [OK]  docx 缺0 多0\n"
            "  [FAIL] epub 缺3 多1\n",
            encoding="utf-8")
        self.assertEqual(b.verify_report_formats(p), {"docx": True, "epub": False})

    def test_covered_marker_ignored(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        p = self.dir / "r.txt"
        p.write_text("=== T1\n  [--] pdf 已覆盖（已由 docx 校验）\n"
                     "  [OK] (缺0/多0)\n  docx 【源】a\n", encoding="utf-8")
        self.assertEqual(b.verify_report_formats(p), {"docx": True})


class BridgeReportPendingTest(unittest.TestCase):
    """[--] 行解析与覆盖规则：docx通过即pdf通过、无基线原因。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _rp(self, text):
        p = self.dir / "r.txt"
        p.write_text(text, encoding="utf-8")
        return p

    def test_covered(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        p = self._rp("=== T45n1852.xml\n"
                     "  [--]  pdf 已覆盖（已由 docx 校验）\n"
                     "  [OK] (docx→docx 缺0/多0 ≤阈值10)\n")
        self.assertEqual(b.verify_report_pending(p), {"pdf": "covered:docx"})

    def test_no_baseline(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        p = self._rp("=== T0001\n"
                     "  [--]  epub no baseline\n"
                     "  [--]  docx no baseline\n")
        self.assertEqual(b.verify_report_pending(p),
                         {"epub": "no baseline", "docx": "no baseline"})

    def test_gen_not_found(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        p = self._rp("=== T0001\n  [--]  pdf→docx gen not found: \n")
        self.assertEqual(b.verify_report_pending(p), {"pdf": "gen not found"})

    def test_missing_file(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        self.assertEqual(b.verify_report_pending(self.dir / "nope.txt"), {})

    def test_coverage_docx_pass_covers_pdf(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = b.apply_verify_coverage({"docx": True}, {"pdf": "covered:docx"})
        self.assertEqual(out, {"docx": True, "pdf": True})

    def test_coverage_docx_fail_covers_nothing(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = b.apply_verify_coverage({"docx": False}, {"pdf": "covered:docx"})
        self.assertEqual(out, {"docx": False})

    def test_coverage_explicit_entry_wins(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = b.apply_verify_coverage({"docx": True, "pdf": False},
                                      {"pdf": "covered:docx"})
        self.assertEqual(out, {"docx": True, "pdf": False})

    def test_coverage_no_pending_is_identity(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        st = {"docx": True}
        out = b.apply_verify_coverage(st, {})
        self.assertEqual(out, {"docx": True})
        self.assertIsNot(out, st)


class BridgeWorkSummaryTest(unittest.TestCase):
    """上游总结行 `[id] N format: 1[docx=OK(0/0)], 2[pdf=1], …` 解析：优先于 trial 行。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _rp(self, text):
        p = self.dir / "report.txt"
        p.write_text(text, encoding="utf-8")
        return p

    def test_summary_ok_fail_numbers(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        p = self._rp("[T45n1859] 3 format: 1[docx=OK(0/0)], 2[pdf=1], 3[epub=FAIL(48/97)]\n"
                     "=== T45n1859.xml\n")
        self.assertEqual(b.verify_report_formats(p),
                         {"docx": True, "pdf": True, "epub": False})
        self.assertEqual(b.verify_report_numbers(p),
                         {"docx": (0, 0), "pdf": (0, 0), "epub": (48, 97)})
        self.assertFalse(b.verify_report_pass(p))
        self.assertEqual(b.verify_report_pending(p), {"pdf": "covered:docx"})

    def test_summary_ref_to_failed(self):
        # 被覆盖项结论跟随第 M 条：源失败则同样失败
        import cbeta_publish.books.xml2pdf_bridge as b
        p = self._rp("[T1] 2 format: 1[docx=FAIL(3/1)], 2[pdf=1]\n")
        self.assertEqual(b.verify_report_formats(p), {"docx": False, "pdf": False})
        self.assertFalse(b.verify_report_pass(p))

    def test_summary_bare_covered(self):
        # 无 ref 的 COVERED：pending 记 covered，沿用 pdf←docx 启发式
        import cbeta_publish.books.xml2pdf_bridge as b
        p = self._rp("[T1] 2 format: 1[docx=OK(0/0)], 2[pdf=COVERED]\n")
        self.assertEqual(b.verify_report_formats(p), {"docx": True})
        self.assertEqual(b.verify_report_pending(p), {"pdf": "covered"})
        out = b.apply_verify_coverage(b.verify_report_formats(p),
                                      b.verify_report_pending(p))
        self.assertEqual(out, {"docx": True, "pdf": True})
        self.assertTrue(b.verify_report_pass(p))

    def test_summary_pending_reasons(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        p = self._rp("[T1] 4 format: 1[epub=NO_BASELINE], 2[docx=NOGEN], "
                     "3[pdf=ERROR], 4[md=???]\n")
        self.assertEqual(b.verify_report_formats(p), {})
        pending = b.verify_report_pending(p)
        self.assertEqual(pending["epub"], "no baseline")
        self.assertEqual(pending["docx"], "gen not found")
        self.assertEqual(pending["pdf"], "error")
        self.assertIsNone(b.verify_report_pass(p))

    def test_summary_arrow_fmt_and_unknown_numbers(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        p = self._rp("[T1] 2 format: 1[pdf→docx=OK(0/0)], 2[epub=FAIL(?/?)]\n")
        self.assertEqual(b.verify_report_formats(p), {"pdf": True, "epub": False})
        self.assertEqual(b.verify_report_numbers(p), {"pdf": (0, 0)})

    def test_no_summary_falls_back_to_trials(self):
        # 老报告无总结行：trial 解析照常，numbers 为空
        import cbeta_publish.books.xml2pdf_bridge as b
        p = self._rp("=== T0001\n  [OK]  docx 缺0 多0\n  [FAIL] epub 缺3 多1\n")
        self.assertEqual(b.verify_report_formats(p), {"docx": True, "epub": False})
        self.assertFalse(b.verify_report_pass(p))
        self.assertEqual(b.verify_report_numbers(p), {})
        self.assertEqual(b.verify_report_pending(p), {})


class BridgeBuiltNamingTest(unittest.TestCase):
    """L2 命名：工作根目录名推导带书名；更长編號不误命中。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.root = self.dir / "x2p"
        (self.root / "presets").mkdir(parents=True)
        self.work = self.dir / "xml"
        (self.work / "T0001 中論").mkdir(parents=True)
        (self.work / "T0001 中論" / "T01n0001.xml").write_bytes(b"x")
        (self.work / "T0001a 别传").mkdir(parents=True)
        self.cfg = {"xml2pdf": {"path": str(self.root), "cbeta_ebook": str(self.work)}}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_built_name_from_work_dir(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        self.assertEqual(b.built_name(self.cfg, "T0001"), "T0001 中論")
        self.assertEqual(b.built_name(self.cfg, "T0001a"), "T0001a 别传")
        self.assertEqual(b.built_name(self.cfg, "T9999"), "T9999")  # 无目录退回 id

    def test_work_dir_skips_longer_ids(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        self.assertEqual(b.work_dir_of(self.cfg, "T0001").name, "T0001 中論")
        self.assertIsNone(b.work_dir_of(self.cfg, "T000"))  # 前缀不算

    def test_ensure_one_with_name(self):
        # name 透传：直生目标用带书名（L2），复用仍命中
        import cbeta_publish.books.xml2pdf_bridge as b
        base = self.dir / "out"
        (base / "pdf").mkdir(parents=True)

        def fake_convert(w, xml, out, config, fmt="pdf", preset=None, stop=None):
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(b"x")
            return Path(out)

        real = b.convert
        b.convert = fake_convert
        try:
            p, reused = b.ensure_one("T0001", "pdf", base, self.cfg, name="T0001 中論")
            self.assertFalse(reused)
            self.assertEqual(p, base / "pdf" / "T0001 中論.pdf")
            p2, reused2 = b.ensure_one("T0001", "pdf", base, self.cfg, name="T0001 中論")
            self.assertTrue(reused2)
            self.assertEqual(p2, p)
        finally:
            b.convert = real

    def _touch(self, path, ts):
        import os as _os
        _os.utime(path, (ts, ts))

    def test_source_mtime_ignores_subdirs(self):
        import os as _os
        import cbeta_publish.books.xml2pdf_bridge as b
        xml = self.work / "T0001 中論" / "T01n0001.xml"
        self._touch(xml, 1000)
        # html/ 下的派生物不算源
        (self.work / "T0001 中論" / "html").mkdir(parents=True, exist_ok=True)
        (self.work / "T0001 中論" / "html" / "x.xml").write_bytes(b"x")
        self._touch(self.work / "T0001 中論" / "html" / "x.xml", 999999)
        self.assertEqual(b.source_mtime(self.cfg, "T0001"), 1000.0)
        self.assertIsNone(b.source_mtime(self.cfg, "T9999"))

    def test_ensure_one_regens_when_source_newer(self):
        # 源 XML 比产物新 → 仅缺模式也重制并覆盖原路径；源旧/无源仍复用
        import cbeta_publish.books.xml2pdf_bridge as b
        base = self.dir / "out"
        (base / "pdf").mkdir(parents=True)
        calls = []

        def fake_convert(w, xml, out, config, fmt="pdf", preset=None, stop=None):
            calls.append(Path(out))
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(b"x")
            return Path(out)

        real = b.convert
        b.convert = fake_convert
        xml = self.work / "T0001 中論" / "T01n0001.xml"
        try:
            self._touch(xml, 5000)
            p, reused = b.ensure_one("T0001", "pdf", base, self.cfg, name="T0001 中論")
            self.assertFalse(reused)
            self.assertEqual(len(calls), 1)
            # 产物置为新、源置为旧 → 复用
            self._touch(p, 9000)
            self._touch(xml, 1000)
            p2, reused2 = b.ensure_one("T0001", "pdf", base, self.cfg, name="T0001 中論")
            self.assertTrue(reused2)
            self.assertEqual(len(calls), 1)
            # 源比产物新 → 重制覆盖
            self._touch(xml, 12000)
            p3, reused3 = b.ensure_one("T0001", "pdf", base, self.cfg, name="T0001 中論")
            self.assertFalse(reused3)
            self.assertEqual(len(calls), 2)
            self.assertEqual(p3, p2)
            # 无工作目录的 work：始终复用（无源可比）
            (base / "pdf" / "T9999.pdf").write_bytes(b"x")
            _, reused4 = b.ensure_one("T9999", "pdf", base, self.cfg)
            self.assertTrue(reused4)
        finally:
            b.convert = real


class BridgeVerifySummaryTest(unittest.TestCase):
    """总验证报告：合并单本报告为固定名文件（摘要＋全文），二次扫描不认它。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _reports(self):
        (self.dir / "T0001_verify_report.txt").write_text(
            "=== T0001\n  [OK]  docx 缺0 多0\n  [OK]  pdf 缺0 多0\n",
            encoding="utf-8")
        (self.dir / "T0002_verify_report.txt").write_text(
            "[T0002] 2 format: 1[docx=OK(0/0)], 2[epub=FAIL(3/1)]\n"
            "=== T0002\n  [OK]  docx 缺0 多0\n  [FAIL] epub 缺3 多1\n",
            encoding="utf-8")
        (self.dir / "T0003_verify_report.txt").write_text(
            "=== T0003\n  [--]  epub 无基线（no baseline）\n",
            encoding="utf-8")
        (self.dir / "T0004_verify_report.txt").write_text(
            "=== T0004\n  [OK]  docx 缺0 多0\n"
            "  [--]  pdf 已覆盖（已由 docx 校验）\n",
            encoding="utf-8")

    def test_write_and_reread(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        self._reports()
        out = b.write_verify_summary(self.dir, "测丛书")
        self.assertEqual(out.name, "总验证报告.txt")
        text = out.read_text(encoding="utf-8")
        self.assertIn("共 4 部：通过 2 部 / 未通过 1 部 / 未判定 1 部", text)
        self.assertIn("T0002 校验未通过（epub 缺3/多1）", text)
        self.assertIn("T0004 通过（docx/pdf）", text)
        self.assertIn("T0003 未判定（epub无基线）", text)
        for stem in ("T0001", "T0002", "T0003", "T0004"):
            self.assertIn(f"===== {stem}（{stem}_verify_report.txt）=====", text)
        # 总报告不参与导入扫描；覆盖写更新内容
        self.assertEqual(len(b.verify_reports(self.dir)), 4)
        (self.dir / "T0001_verify_report.txt").write_text(
            "=== T0001\n  [FAIL] docx 缺1 多0\n", encoding="utf-8")
        out2 = b.write_verify_summary(self.dir, "测丛书")
        self.assertEqual(out2, out)
        text2 = out2.read_text(encoding="utf-8")
        self.assertIn("T0001 校验未通过（docx）", text2)

    def test_no_reports_returns_none(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        self.assertIsNone(b.write_verify_summary(self.dir, "空丛书"))
        self.assertFalse((self.dir / "总验证报告.txt").exists())


if __name__ == "__main__":
    unittest.main()
