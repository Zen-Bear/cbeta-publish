# -*- coding: utf-8 -*-
"""S2：官方备齐 `_prepare_official`（策略/水位/返回）与 `DownloadWorker(force=)`。

- policy=missing/stale/all 的 pairs 选择与 force 传递；
- 成功（含跳过未变）写 official_state 水位，失败不写；
- force=True 绕过「未更新」判断，强制重新下载。
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cbeta_publish.books import official_ebook_source as oes  # noqa: E402
from cbeta_publish.books import official_state as ost  # noqa: E402
from cbeta_publish.books.download_worker import DownloadWorker  # noqa: E402
from cbeta_publish.gui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _prod(dest_dir: Path, work: str, fmt: str, mtime: float):
    p = oes.dest_path(work, fmt, dest_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def _src(xroot: Path, work: str, mtime: float, title: str = "經"):
    d = xroot / f"{work} {title}"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{work}.xml"
    f.write_text("<x/>", encoding="utf-8")
    os.utime(f, (mtime, mtime))
    return f


class PrepareOfficialTest(unittest.TestCase):
    def setUp(self):
        _ensure_app()
        self.tmp = Path(tempfile.mkdtemp())
        col = self.tmp / "collections" / "custom"
        col.mkdir(parents=True)
        (self.tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
        (self.tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
        cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
        cfg["mulu_dir"] = str(ROOT / "mulu")
        cfg["collections_dir"] = str(self.tmp / "collections")
        cfg["update_interval"] = "manual"
        cfg["xml2pdf"]["cbeta_ebook"] = str(self.tmp / "xml")
        cfg["official_library"] = {"root": str(self.tmp / "CBETA" / "2026r2")}
        cfg["_config_path"] = str(self.tmp / "app.json")
        self.win = MainWindow(cfg)
        self.dest = self.tmp / "cbeta_ebooks"
        self.xroot = self.tmp / "xml"
        self.xroot.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch(self, rec, failed=None, force_rec=None):
        def fake(pairs, dest_dir, title="下载", autoclose_ok=False, force=False):
            rec.extend(list(pairs))
            if force_rec is not None:
                force_rec.append(force)
            self.win._dl_stats = {"ok": 0, "total": len(pairs),
                                  "failed": list(failed or []), "cancel": False}
            return not failed
        self.win._download_missing = fake

    def test_missing_policy(self):
        _prod(self.dest, "T0001", "pdf", 2000.0)
        rec = []
        self._patch(rec)
        src_map, failed = self.win._prepare_official(["T0001", "T0002"], ["pdf"],
                                                     self.dest, policy="missing")
        self.assertEqual(rec, [("T0002", "pdf")])
        self.assertEqual(failed, [])
        self.assertEqual(src_map["pdf"]["T0001"], oes.dest_path("T0001", "pdf", self.dest))

    def test_stale_policy_includes_source_newer(self):
        _prod(self.dest, "T0001", "pdf", 1000.0)   # 源较新 → 过期
        _src(self.xroot, "T0001", 2000.0)
        _prod(self.dest, "T0002", "pdf", 2000.0)   # 无源、产物在 → 不过期
        rec = []
        self._patch(rec)
        self.win._prepare_official(["T0001", "T0002"], ["pdf"], self.dest, policy="stale")
        self.assertEqual(rec, [("T0001", "pdf")])

    def test_all_policy_forces(self):
        rec, frec = [], []
        self._patch(rec, force_rec=frec)
        self.win._prepare_official(["T0001", "T0002"], ["pdf"], self.dest, policy="all")
        self.assertEqual(sorted(rec), [("T0001", "pdf"), ("T0002", "pdf")])
        self.assertEqual(frec, [True])

    def test_watermark_written_on_success(self):
        rec = []
        self._patch(rec, failed=[])
        self.win._prepare_official(["T0002"], ["pdf"], self.dest, policy="all")
        e = ost.get(ost.state_path(self.win.config), "T0002", "pdf")
        self.assertIsNotNone(e)
        self.assertEqual(e["lib_version"], "2026r2")

    def test_failure_not_marked(self):
        rec = []
        self._patch(rec, failed=["T0002.pdf"])
        self.win._prepare_official(["T0002"], ["pdf"], self.dest, policy="all")
        self.assertIsNone(ost.get(ost.state_path(self.win.config), "T0002", "pdf"))

    def test_no_pairs_no_download(self):
        _prod(self.dest, "T0001", "pdf", 2000.0)
        rec = []
        self._patch(rec)
        self.win._prepare_official(["T0001"], ["pdf"], self.dest, policy="missing")
        self.assertEqual(rec, [])


class WorkerForceTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "pdf").mkdir(parents=True)
        (self.dir / "pdf" / "T0001.pdf").write_bytes(b"x" * 100)
        self._real_remote = oes.remote_info
        self._real_dl = oes.download_ebook

    def tearDown(self):
        oes.remote_info = self._real_remote
        oes.download_ebook = self._real_dl
        shutil.rmtree(self.dir, ignore_errors=True)

    def _run(self, force):
        calls = []

        def fake_dl(work, fmt, dest_dir, config=None, force=False):
            calls.append(force)
            p = oes.dest_path(work, fmt, dest_dir)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"z" * 10)
            return p

        oes.remote_info = lambda work, fmt: {"url": "u", "size": 100,
                                             "mtime": 1.0, "etag": None}
        oes.download_ebook = fake_dl
        w = DownloadWorker(["T0001"], ["pdf"], self.dir, force=force)
        w.run()
        return calls

    def test_unchanged_skipped_without_force(self):
        self.assertEqual(self._run(False), [])

    def test_force_redownloads(self):
        self.assertEqual(self._run(True), [True])


if __name__ == "__main__":
    unittest.main()
