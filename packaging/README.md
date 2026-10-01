# 打包为 Windows 独立程序

## 一键构建

```powershell
# 仓库根
powershell -ExecutionPolicy Bypass -File build_exe.ps1

# 连 Chromium（playwright）一起打包，目标机免安装
powershell -ExecutionPolicy Bypass -File build_exe.ps1 -WithBrowsers

# 只重做数据拷贝/配置改写，不重新 PyInstaller
powershell -ExecutionPolicy Bypass -File build_exe.ps1 -SkipBuild

# 指定 xml2pdf 仓库 / Python
powershell -ExecutionPolicy Bypass -File build_exe.ps1 -X2P D:\xml2pdf -Python py -3

# 代码签名（减少 SmartScreen 拦截）
powershell -ExecutionPolicy Bypass -File build_exe.ps1 -CertThumbprint 1A2B3C4D...
powershell -ExecutionPolicy Bypass -File build_exe.ps1 -PfxPath cert.pfx -PfxPassword ***
```

产物：`dist\cbeta-publish\`（整个目录可拷贝到任意机器，双击 `cbeta-publish.exe`）；
默认同时生成交付压缩包 `dist\cbeta-publish.zip`（`-NoZip` 可跳过）。

## 代码签名（Authenticode）

未签名的 exe，用户首次运行会弹 Windows SmartScreen「未知发布者」。要消除需购买
**代码签名证书**并对 exe 签名（签名须在压缩 zip 前，脚本已内置该步骤）。

证书类型与获取：

| 类型 | 说明 | 价格/年 | SmartScreen |
| --- | --- | --- | --- |
| **Azure Trusted Signing**（微软云签名） | 云 HSM，个人/小团队可申请，按量或低价订阅 | 低 | 逐步积累信誉 |
| **OV 代码签名** | 需企业/组织实名验证；2023 起须硬件 token 或云 HSM | ~$200–400 | 逐步积累信誉 |
| **EV 代码签名** | 同上但扩展验证；须硬件 token | ~$300–600 | **立即**获信誉 |

> 2023 年 6 月起 CA/B 规定：新签发的代码签名证书**不能是裸 .pfx 文件**，
> 须用 **USB 硬件 token** 或 **云签名（HSM）**。常见 CA：DigiCert、Sectigo、
> GlobalSign、SSL.com；云方案：Azure Trusted Signing、DigiCert KeyLocker。

签名命令（脚本自动执行，需安装 Windows SDK 的 `signtool.exe`）：

```bat
rem USB token / 证书库
signtool sign /fd SHA256 /sha1 <证书指纹> /tr http://timestamp.digicert.com /td SHA256 /v cbeta-publish.exe
rem .pfx 文件
signtool sign /fd SHA256 /f cert.pfx /p <口令> /tr http://timestamp.digicert.com /td SHA256 /v cbeta-publish.exe
rem 校验
signtool verify /pa /v cbeta-publish.exe
```

用本脚本：`-CertThumbprint <指纹>`（token/证书库）或 `-PfxPath/-PfxPassword`（文件）。
云签名服务（如 Azure）用各自工具/`signtool /dlib`，可先手动签名 exe，再 `-SkipBuild -NoZip` 或自行压缩。


## 打进包里的内容

### 代码与依赖（进 `_internal\`）
- `cbeta_publish/` 全包（源码运行入口 `cbeta_publish/app.py`）
- 第三方：PySide6、pypinyin、pymupdf(`fitz`)、EbookLib、reportlab、opencc、
  lxml、tinycss2、fontTools、playwright
- `pycbeta`（从 `-X2P` 指定的 xml2pdf 仓库收集：子模块 + `styles/`、`assets/`、`data/`）
- 包内只读资源：`cbeta_publish/gui/theme/tokens.json` 与 `icons/*.png`

### 可写数据（exe 同级，便携）
- `config/app.json`（构建时改写为相对路径）
- `mulu/`（`bulei.txt`、`category.json`、`vol.json`、`dynasty-works.json`、
  `SutraList.json`、`sutra_mapping.txt`、`all-creators-with-alias.json`、
  `creators-by-strokes-with-works.json`、`backup/`；排除 `cache/`）
- `assets/images/`：`B01.jpg`、`B02.jpg`、`1.tif`、`2.tif`（＋备用 `A01/A02.jpg`）
- `xml2pdf/`：从 xml2pdf 仓库拷贝的 `presets/` ＋ `run.json`（供制书选预设）
- `collections/`：**演示丛书**（作者/主题/经/自定义示例 ＋ `categories.json`/`tags.json`），随包分发
- 运行期自建：`collections_books/`、`cbeta_ebooks/`、
  `cbeta_xml_ebooks/`、`cbeta_verify/`、`mulu/cache/`

### 未打入（可在目标机/构建机另行准备）
- **Chromium**（playwright 的 PDF 引擎）：默认不打，目标机需 `python -m playwright install chromium`，
  或用 `-WithBrowsers` 把 `%LOCALAPPDATA%\ms-playwright` 拷到 `exe\ms-playwright`；
  程序冻结时会自动把该目录设为 `PLAYWRIGHT_BROWSERS_PATH`。
- CBETA XML 目录：在「设置」里填（`config` 的 `xml2pdf.cbeta_ebook`）。

## 关键机制

- `cbeta_publish/paths.py: app_root()`：**冻结运行时数据根 = exe 所在目录**；
  源码运行 = 仓库根。所有 `config/mulu/assets/collections/输出目录` 都基于它解析，
  因此打包后放 exe 同级即可读写、便携。
- `config/app.json` 里相关路径构建时改写为**相对路径**（如 `mulu`、`cbeta_ebooks`、
  `xml2pdf`），运行时相对 `app_root()` 解析。
- `packaging/cbeta_publish.spec`：PyInstaller onedir 定义；`excludes` 去掉
  tkinter/numpy/QtWebEngine 等无用大件。

## 注意
- 需 PyInstaller（脚本会自动 `pip install`）。Python 3.14 支持视 PyInstaller 版本而定，
  如遇构建问题可改用 3.12/3.13 解释器（`-Python`）。
- 打包机需已安装全部第三方依赖（见 `requirements.txt` 与 xml2pdf 的 `requirements.txt`）。
