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


if __name__ == "__main__":
    unittest.main()
