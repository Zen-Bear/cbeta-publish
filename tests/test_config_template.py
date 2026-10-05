# -*- coding: utf-8 -*-
"""首启配置：config/app.json 缺失时从出厂模板 config/app.default.json 复制。

app.json 是用户运行期配置（不进版本库），模板 app.default.json 跟踪进库；
`paths.ensure_user_config` 负责首启生成，且绝不覆盖已存在的用户配置。
"""
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.paths import ensure_user_config


class EnsureUserConfigTest(unittest.TestCase):
    def test_copies_default_when_missing(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = tmp / "config" / "app.json"
            dflt = tmp / "config" / "app.default.json"
            dflt.parent.mkdir(parents=True, exist_ok=True)
            dflt.write_text('{"a": 1}', encoding="utf-8")
            out = ensure_user_config(cfg, dflt)
            self.assertEqual(out, cfg)
            self.assertTrue(cfg.exists())
            self.assertEqual(cfg.read_text(encoding="utf-8"), '{"a": 1}')
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_does_not_overwrite_existing_user_config(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = tmp / "config" / "app.json"
            dflt = tmp / "config" / "app.default.json"
            dflt.parent.mkdir(parents=True, exist_ok=True)
            dflt.write_text('{"a": 1}', encoding="utf-8")
            cfg.write_text('{"user": true}', encoding="utf-8")
            ensure_user_config(cfg, dflt)
            self.assertEqual(cfg.read_text(encoding="utf-8"), '{"user": true}')
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_default_does_not_create(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg = tmp / "config" / "app.json"
            dflt = tmp / "config" / "app.default.json"
            out = ensure_user_config(cfg, dflt)
            self.assertEqual(out, cfg)
            self.assertFalse(cfg.exists())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
