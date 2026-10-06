# -*- coding: utf-8 -*-
"""官方书备齐水位库 `books/official_state.py` 与官方辅助函数。

覆盖过期判据：缺失 / 源较水位新 / 本地库版本名变化 / 无水位回退产物 mtime；
以及水位写入、损坏回空库、`_config_path` 隔离。
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.books import official_state as st
from cbeta_publish.books import official_ebook_source as oes


def _cfg(tmp: Path):
    xroot = tmp / "xml"
    cfgdir = tmp / "config"
    xroot.mkdir(parents=True, exist_ok=True)
    cfgdir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "_config_path": str(cfgdir / "app.json"),
        "xml2pdf": {"cbeta_ebook": str(xroot)},
        "official_library": {"root": str(tmp / "CBETA" / "2026r2")},
    }
    return cfg, xroot


def _make_src(xroot: Path, work: str, mtime: float, title: str = "經"):
    d = xroot / f"{work} {title}"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{work}.xml"
    f.write_text("<x/>", encoding="utf-8")
    os.utime(f, (mtime, mtime))
    return f


def _make_prod(dest_dir: Path, work: str, fmt: str, mtime: float):
    p = oes.dest_path(work, fmt, dest_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


class OfficialStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg, self.xroot = _cfg(self.tmp)
        self.dest = self.tmp / "cbeta_ebooks"
        self.path = st.state_path(self.cfg)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_state_path_isolated_by_config_path(self):
        self.assertEqual(self.path, self.tmp / "config" / "official_state.json")

    def test_missing_is_stale(self):
        self.assertTrue(st.stale(self.cfg, "T0001", "pdf", self.dest, self.path))

    def test_source_newer_than_watermark_is_stale(self):
        _make_prod(self.dest, "T0001", "pdf", 1000.0)
        st.record(self.path, "T0001", "pdf", 1000.0, "2026r2")
        _make_src(self.xroot, "T0001", 2000.0)
        self.assertTrue(st.stale(self.cfg, "T0001", "pdf", self.dest, self.path))

    def test_source_not_newer_than_watermark_is_fresh(self):
        _make_prod(self.dest, "T0001", "pdf", 1000.0)
        st.record(self.path, "T0001", "pdf", 2000.0, "2026r2")
        _make_src(self.xroot, "T0001", 1500.0)
        self.assertFalse(st.stale(self.cfg, "T0001", "pdf", self.dest, self.path))

    def test_version_change_is_stale(self):
        _make_prod(self.dest, "T0001", "pdf", 2000.0)
        st.record(self.path, "T0001", "pdf", 2000.0, "2026r2")
        _make_src(self.xroot, "T0001", 1000.0)   # 源不新
        self.cfg["official_library"]["root"] = str(self.tmp / "CBETA" / "2026r3")
        self.assertTrue(st.stale(self.cfg, "T0001", "pdf", self.dest, self.path))

    def test_fresh_after_mark_checked(self):
        _make_prod(self.dest, "T0001", "pdf", 1000.0)
        _make_src(self.xroot, "T0001", 2000.0)
        self.assertTrue(st.mark_checked(self.cfg, "T0001", "pdf", self.path))
        self.assertFalse(st.stale(self.cfg, "T0001", "pdf", self.dest, self.path))
        self.assertEqual(st.get(self.path, "T0001", "pdf")["lib_version"], "2026r2")

    def test_no_watermark_fallback_to_product_mtime(self):
        _make_prod(self.dest, "T0001", "pdf", 1000.0)
        _make_src(self.xroot, "T0001", 2000.0)
        self.assertTrue(st.stale(self.cfg, "T0001", "pdf", self.dest, self.path))
        _make_src(self.xroot, "T0001", 500.0)
        self.assertFalse(st.stale(self.cfg, "T0001", "pdf", self.dest, self.path))

    def test_no_xml_no_watermark_not_stale(self):
        _make_prod(self.dest, "T0001", "pdf", 1000.0)
        self.assertFalse(st.stale(self.cfg, "T0001", "pdf", self.dest, self.path))

    def test_record_none_src_omits_src_mtime(self):
        st.record(self.path, "T0001", "pdf", None, "2026r2")
        e = st.get(self.path, "T0001", "pdf")
        self.assertNotIn("src_mtime", e)
        self.assertEqual(e["lib_version"], "2026r2")

    def test_load_corrupt_returns_empty(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(st.load(self.path).get("works"), {})
        self.assertEqual(st.stats(self.path), {"works": 0, "entries": 0})

    def test_clear(self):
        st.record(self.path, "T0001", "pdf", 1.0, "2026r2")
        self.assertEqual(st.stats(self.path)["entries"], 1)
        st.clear(self.path)
        self.assertEqual(st.stats(self.path)["entries"], 0)


class OfficialHelpersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_library_version(self):
        self.assertEqual(oes.library_version({}), "")
        self.assertEqual(
            oes.library_version({"official_library": {"root": r"E:\CBETA\2026r2\\"}}),
            "2026r2")

    def test_product_mtime_file(self):
        p = self.tmp / "a.pdf"
        p.write_text("x", encoding="utf-8")
        os.utime(p, (1234.0, 1234.0))
        self.assertAlmostEqual(oes.product_mtime(p), 1234.0, places=1)

    def test_product_mtime_dir_takes_latest(self):
        d = self.tmp / "T0001"
        d.mkdir()
        (d / "a.docx").write_text("x", encoding="utf-8")
        (d / "b.docx").write_text("y", encoding="utf-8")
        os.utime(d / "a.docx", (100.0, 100.0))
        os.utime(d / "b.docx", (200.0, 200.0))
        self.assertAlmostEqual(oes.product_mtime(d), 200.0, places=1)

    def test_product_mtime_empty_dir_zero(self):
        d = self.tmp / "empty"
        d.mkdir()
        self.assertEqual(oes.product_mtime(d), 0.0)

    def test_product_mtime_missing_zero(self):
        self.assertEqual(oes.product_mtime(self.tmp / "nope"), 0.0)


if __name__ == "__main__":
    unittest.main()
