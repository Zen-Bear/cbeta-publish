# -*- coding: utf-8 -*-
"""CBETA 發佈管理器（publish 侧）。

版本与名称的唯一来源：窗口标题、QApplication 元数据、后续打包/关于框都取这里。
发布流程：功能改动合并后手动升 ``__version__``（语义化版本 MAJOR.MINOR.PATCH），
并在 git 打同名 tag（如 ``v0.1.0``）。
"""

#: 显示名（繁简随界面，标题栏用）
APP_NAME = "CBETA 發佈管理器"

#: 包/可执行文件短名（无空格，用于打包、注册表、路径）
APP_ID = "cbeta-publish"

#: 语义化版本：主.次.补丁；功能迭代升次、修 bug 升补丁、不兼容改动升主
__version__ = "0.5.0"

#: 许可证
__license__ = "GPL-3.0"
__author__ = "Zen Bear"
