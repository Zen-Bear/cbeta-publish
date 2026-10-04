<#
.SYNOPSIS
  把 CBETA publish 打包成 Windows 独立运行程序（PyInstaller onedir）。

.DESCRIPTION
  产物目录：dist\<APP_ID>\
    - <APP_ID>.exe            主程序（名字取自 cbeta_publish/__init__.py 的 APP_ID）
    - _internal\               依赖/包内资源（含 pycbeta、主题图标）
    - config\ mulu\ assets\    可写数据（放 exe 同级，便携：拷走整个目录即用）
    - xml2pdf\                 预设与 run.json（供制书；pycbeta 已打进 _internal）
    - collections\ collections_books\ cbeta_ebooks\ cbeta_xml_ebooks\ cbeta_verify\  运行期自建

.PARAMETER X2P
  cbeta-xml2pdf 仓库路径（https://github.com/Zen-Bear/cbeta-xml2pdf；收集 pycbeta 与预设）。
  默认 E:\dev\cbeta\xml2pdf。

.PARAMETER Python
  构建用 Python 解释器。默认 python。

.PARAMETER WithBrowsers
  一并拷贝 playwright 的 Chromium（%LOCALAPPDATA%\ms-playwright -> exe\ms-playwright），
  使 PDF 引擎在无网/无 playwright 安装的机器上也能跑（体积 +数百 MB）。

.PARAMETER SkipBuild
  跳过 PyInstaller，只重做数据拷贝/配置改写（调试用）。

.PARAMETER CertThumbprint
  代码签名：证书指纹（USB token/证书库），如 1A2B3C...（signtool /sha1）。

.PARAMETER PfxPath
  代码签名：.pfx/.p12 证书文件（配合 -PfxPassword）。

.PARAMETER PfxPassword
  代码签名：.pfx 口令。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File build_exe.ps1
  powershell -ExecutionPolicy Bypass -File build_exe.ps1 -WithBrowsers
  powershell -ExecutionPolicy Bypass -File build_exe.ps1 -CertThumbprint 1A2B3C4D...
#>
[CmdletBinding()]
param(
    [string]$X2P = "E:\dev\cbeta\xml2pdf",
    [string]$Python = "python",
    [switch]$WithBrowsers,
    [switch]$SkipBuild,
    [switch]$NoZip,
    # 代码签名（可选）：给 exe 加 Authenticode 签名，减少 SmartScreen 拦截
    [string]$CertThumbprint = "",                       # 证书指纹（USB token/证书库，推荐）
    [string]$PfxPath = "",                              # 或 .pfx/.p12 文件
    [string]$PfxPassword = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Spec = Join-Path $Repo "packaging\cbeta_publish.spec"

# 可执行/产物名取自唯一来源 cbeta_publish/__init__.py 的 APP_ID
$initFile = Join-Path $Repo "cbeta_publish\__init__.py"
$appId = (Select-String -Path $initFile -Pattern 'APP_ID\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if (-not $appId) { throw "未从 $initFile 解析到 APP_ID" }
$Dist = Join-Path $Repo "dist\$appId"

function Info($m) { Write-Host "[build] $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[build] $m" -ForegroundColor Yellow }

# ---------- 1. 检查构建环境 ----------
Info "仓库根: $Repo"
if (-not (Test-Path (Join-Path $Repo "cbeta_publish\app.py"))) {
    throw "未找到 cbeta_publish\app.py，请在仓库根运行。"
}
if (-not (Test-Path (Join-Path $X2P "pycbeta"))) {
    Warn "未找到 cbeta-xml2pdf 仓库: $X2P（pycbeta 将无法打包，制书功能不可用）"
}

# ---------- 2. PyInstaller 打包（onedir）----------
if (-not $SkipBuild) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & $Python -c "import PyInstaller" 2>&1 | Out-Null
    $hasPyI = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev
    if (-not $hasPyI) {
        Info "安装 PyInstaller …"
        & $Python -m pip install --upgrade pyinstaller
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller 安装失败" }
    }

    Info "PyInstaller 打包中（首次较慢）…"
    $env:PUBLISH_ROOT = $Repo
    $env:X2P_ROOT = $X2P
    & $Python -m PyInstaller --clean --noconfirm `
        --distpath (Join-Path $Repo "dist") `
        --workpath (Join-Path $Repo "build") $Spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败" }
} else {
    Info "跳过 PyInstaller（-SkipBuild）"
}

if (-not (Test-Path $Dist)) { throw "未生成 $Dist" }

# ---------- 3. 拷贝可写数据（exe 同级）----------
Info "拷贝可写数据到 exe 同级 …"
New-Item -ItemType Directory -Force -Path (Join-Path $Dist "config") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Dist "mulu") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Dist "assets\images") | Out-Null

Copy-Item (Join-Path $Repo "config\app.json") (Join-Path $Dist "config\app.json") -Force

# mulu 数据（整目录，排除 cache；含 backup/original、backup/last 以支持「恢复」）
robocopy (Join-Path $Repo "mulu") (Join-Path $Dist "mulu") /E /XD cache /NFL /NDL /NJH /NJS /NP | Out-Null

# 封面图：仅程序实际引用的最小集（B01/B02 与 1.*/2.* 回退）＋备用 A01/A02
foreach ($img in @("B01.jpg", "B02.jpg", "1.tif", "2.tif", "A01.jpg", "A02.jpg")) {
    $src = Join-Path $Repo "assets\images\$img"
    if (Test-Path $src) { Copy-Item $src (Join-Path $Dist "assets\images\$img") -Force }
}

# 封面标题字体（assets/fonts/*，config 里 cover.styles.title.font 相对引用）
New-Item -ItemType Directory -Force -Path (Join-Path $Dist "assets\fonts") | Out-Null
if (Test-Path (Join-Path $Repo "assets\fonts")) {
    robocopy (Join-Path $Repo "assets\fonts") (Join-Path $Dist "assets\fonts") /E /NFL /NDL /NJH /NJS /NP | Out-Null
}

# 说明文件示例（assets/notes/sample.txt；用户私有说明不入包）
New-Item -ItemType Directory -Force -Path (Join-Path $Dist "assets\notes") | Out-Null
$sampleNote = Join-Path $Repo "assets\notes\sample.txt"
if (Test-Path $sampleNote) {
    Copy-Item $sampleNote (Join-Path $Dist "assets\notes\sample.txt") -Force
}

# ---------- 4. 拷贝制书预设（xml2pdf/presets + run.json）----------
$X2PDist = Join-Path $Dist "xml2pdf"
New-Item -ItemType Directory -Force -Path $X2PDist | Out-Null
foreach ($f in @("run.json", "config.json")) {
    $src = Join-Path $X2P $f
    if (Test-Path $src) { Copy-Item $src (Join-Path $X2PDist $f) -Force }
}
if (Test-Path (Join-Path $X2P "presets")) {
    robocopy (Join-Path $X2P "presets") (Join-Path $X2PDist "presets") /E /NFL /NDL /NJH /NJS /NP | Out-Null
} else {
    Warn "未找到 $X2P\presets，制书将无预设可选"
}

# ---------- 5. 演示丛书 + 运行期自建目录 ----------
# 演示用丛书（collections/，含作者/主题/经/自定义示例）随包分发
if (Test-Path (Join-Path $Repo "collections")) {
    robocopy (Join-Path $Repo "collections") (Join-Path $Dist "collections") /E /NFL /NDL /NJH /NJS /NP | Out-Null
} else {
    New-Item -ItemType Directory -Force -Path (Join-Path $Dist "collections") | Out-Null
}
foreach ($d in @("collections_books", "cbeta_ebooks",
                 "cbeta_xml_ebooks", "cbeta_verify", "mulu\cache")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Dist $d) | Out-Null
}

# ---------- 6. 改写 config 为「便携相对路径」----------
Info "改写 config/app.json 为便携相对路径 …"
$cfgPath = Join-Path $Dist "config\app.json"
$cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Set-Prop($obj, $name, $value) {
    if ($null -ne $obj.PSObject.Properties[$name]) { $obj.$name = $value }
    else { $obj | Add-Member -NotePropertyName $name -NotePropertyValue $value }
}

Set-Prop $cfg "official_ebooks_dir" "cbeta_ebooks"
Set-Prop $cfg "verify_dir"           "cbeta_verify"
Set-Prop $cfg "mulu_dir"             "mulu"
Set-Prop $cfg "collections_dir"      "collections"
Set-Prop $cfg "output_dir"           "collections_books"
Set-Prop $cfg "xml_to_ebooks_dir"    "cbeta_xml_ebooks"

if ($null -ne $cfg.xml2pdf) {
    Set-Prop $cfg.xml2pdf "path" "xml2pdf"
    Set-Prop $cfg.xml2pdf "cbeta_ebook" ""   # 用户自行指向 CBETA XML 目录
}
if ($null -ne $cfg.ui) {
    Set-Prop $cfg.ui "supplement_ttf" ""
    # last_collection 改存本地 config/ui_state.json（不进版本库），不写进 config
    if ($null -ne $cfg.ui.PSObject.Properties["last_collection"]) {
        $cfg.ui.PSObject.Properties.Remove("last_collection")
    }
}
if ($null -ne $cfg.cover -and $null -ne $cfg.cover.images) {
    if ($null -ne $cfg.cover.images.buddha) { Set-Prop $cfg.cover.images.buddha "file" "assets/images/B01.jpg" }
    if ($null -ne $cfg.cover.images.weituo) { Set-Prop $cfg.cover.images.weituo "file" "assets/images/B02.jpg" }
}
if ($null -ne $cfg.cover -and $null -ne $cfg.cover.edit_note) {
    Set-Prop $cfg.cover.edit_note "file" ""
}

$json = $cfg | ConvertTo-Json -Depth 100
# 写 UTF-8 无 BOM（PowerShell 5.1 的 Set-Content -Encoding UTF8 会加 BOM，json.loads 会报错）
[System.IO.File]::WriteAllText($cfgPath, $json, (New-Object System.Text.UTF8Encoding($false)))

# ---------- 7. 可选：Chromium（playwright）----------
if ($WithBrowsers) {
    $src = Join-Path $env:LOCALAPPDATA "ms-playwright"
    if (Test-Path $src) {
        Info "拷贝 Chromium（playwright）-> exe\ms-playwright …"
        robocopy $src (Join-Path $Dist "ms-playwright") /E /NFL /NDL /NJH /NJS /NP | Out-Null
    } else {
        Warn "未找到 $src；先在构建机执行：python -m playwright install chromium"
    }
} else {
    Info "未打包 Chromium（按需，目标机制书时自行安装：python -m playwright install chromium）"
}

# ---------- 8. 代码签名（可选；须在压缩前对 exe 签名）----------
$exePath = Join-Path $Dist "$appId.exe"
if ($CertThumbprint -or $PfxPath) {
    # 找 signtool（Windows SDK）
    $signtool = (Get-Command signtool.exe -ErrorAction SilentlyContinue).Source
    if (-not $signtool) {
        $signtool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $signtool) { throw "未找到 signtool.exe（需安装 Windows SDK 的签名工具）" }

    Info "签名：$exePath"
    $signArgs = @("sign", "/fd", "SHA256", "/tr", $TimestampUrl, "/td", "SHA256", "/v")
    if ($CertThumbprint) {
        $signArgs += @("/sha1", $CertThumbprint)     # USB token / 证书库
    } else {
        $signArgs += @("/f", $PfxPath)               # .pfx 文件
        if ($PfxPassword) { $signArgs += @("/p", $PfxPassword) }
    }
    $signArgs += $exePath
    & $signtool @signArgs
    if ($LASTEXITCODE -ne 0) { throw "签名失败（code $LASTEXITCODE）" }
    & $signtool verify /pa /v $exePath | Out-Null
    Info "签名并校验完成"
} elseif (-not $SkipBuild) {
    Warn "未签名（如需要：-CertThumbprint <指纹> 或 -PfxPath <文件> -PfxPassword <密码>）"
}

# ---------- 9. 打包 zip（交付件；-NoZip 跳过）----------
if (-not $NoZip) {
    $zip = Join-Path $Repo "dist\$appId.zip"
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Info "压缩交付包 -> dist\$appId.zip …"
    Compress-Archive -Path $Dist -DestinationPath $zip -CompressionLevel Optimal
    Info ("zip 大小：{0} MB" -f [math]::Round((Get-Item $zip).Length / 1MB, 1))
}

# ---------- 10. 汇总 ----------
$exe = Join-Path $Dist "$appId.exe"
$sizeMB = [math]::Round((Get-ChildItem $Dist -Recurse -File |
    Measure-Object -Property Length -Sum).Sum / 1MB, 1)
Info "完成：$exe"
Info "产物大小：$sizeMB MB"
Write-Host ""
Write-Host "交付（给用户）：" -ForegroundColor Green
Write-Host "  把 dist\$appId.zip 发给用户；解压后双击 $appId.exe"
Write-Host ""
Write-Host "本地使用：" -ForegroundColor Green
Write-Host "  1) 整个 dist\$appId 目录拷到目标机任意位置"
Write-Host "  2) 双击 $appId.exe"
Write-Host "  3) 首次用制书：设置里填 CBETA XML 目录（config 的 xml2pdf.cbeta_ebook）"
Write-Host "     并确保目标机有 Chromium（或用 -WithBrowsers 打包）"
