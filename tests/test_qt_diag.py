# -*- coding: utf-8 -*-
"""Qt 诊断开关：默认关闭；开启后 Qt 警告落盘，野指针类警告附 Python 堆栈。"""
import os
import unittest


class QtDiagTest(unittest.TestCase):
    def test_off_by_default(self):
        from cbeta_publish import qt_diag
        old = os.environ.pop("CBETA_QT_DIAG", None)
        try:
            self.assertIsNone(qt_diag.install())
        finally:
            if old is not None:
                os.environ["CBETA_QT_DIAG"] = old

    def test_on_logs_warning_with_stack(self):
        import io
        from PySide6.QtCore import qInstallMessageHandler, qWarning
        from cbeta_publish import qt_diag
        os.environ["CBETA_QT_DIAG"] = "1"
        try:
            path = qt_diag.install()
            self.assertTrue(path and os.path.isfile(path))
            with open(path, encoding="utf-8") as f:
                before = len(f.read())
            qWarning("shared QObject probe (test)")
            with open(path, encoding="utf-8") as f:
                grown = f.read()[before:]
            self.assertIn("shared QObject probe (test)", grown)
            self.assertIn("python stack at warning", grown)
            self.assertIn("test_qt_diag", grown)  # 堆栈含本测试帧
        finally:
            try:
                qInstallMessageHandler(None)  # 恢复默认，不影响其他测试
            except Exception:
                pass
            try:
                import faulthandler
                faulthandler.disable()
            except Exception:
                pass
            os.environ.pop("CBETA_QT_DIAG", None)


if __name__ == "__main__":
    unittest.main()
