# -*- coding: utf-8 -*-
"""Qt 诊断开关：环境变量 `CBETA_QT_DIAG=1` 时，把 Qt 警告（含
"shared QObject was deleted directly" 这类野指针提示）连同触发时的
Python 堆栈写入 `%TEMP%/cbeta_publish_qt_diag.log`，并打开 faulthandler
（崩溃时同样落盘）。默认关闭，对正常运行零影响。
"""
import datetime
import os
import tempfile
import traceback

LOG_NAME = "cbeta_publish_qt_diag.log"


def log_path():
    return os.path.join(tempfile.gettempdir(), LOG_NAME)


def install():
    """安装 Qt 消息钩子 + faulthandler；返回日志路径（未开启返回 None）。"""
    if os.environ.get("CBETA_QT_DIAG") != "1":
        return None
    path = log_path()
    try:
        f = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    try:
        f.write(f"\n===== diag start "
                f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} "
                f"pid={os.getpid()} =====\n")
    except Exception:
        pass
    try:
        import faulthandler
        faulthandler.enable(file=f)
    except Exception:
        pass
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        def _handler(mode, context, message):
            try:
                msg = str(message)
                f.write(f"[{datetime.datetime.now():%H:%M:%S}] "
                        f"{mode.name if hasattr(mode, 'name') else mode} {msg}\n")
                if ("shared QObject" in msg or "deleted directly" in msg
                        or mode in (QtMsgType.QtFatalMsg, QtMsgType.QtCriticalMsg)):
                    f.write("--- python stack at warning ---\n")
                    f.write("".join(traceback.format_stack()))
                    f.write("--- end stack ---\n")
            except Exception:
                pass

        qInstallMessageHandler(_handler)
    except Exception:
        pass
    return path
