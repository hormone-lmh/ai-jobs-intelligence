<#
setup.ps1 — 初始化本项目环境（可重复执行，不覆盖已有数据）

用法：
  pwsh -ExecutionPolicy Bypass -File scripts\setup.ps1

做什么：
  1. 定位 Python 3.12（不与 Doubao 沙箱运行时混用）
  2. 在 backend\.venv 建独立虚拟环境
  3. 安装 backend\requirements.txt 并生成 requirements.lock.txt
  4. 从 .env.example 生成 .env（已存在则不动）
  5. 建 data 子目录
  6. 自检：依赖可导入、配置文件可解析

不做什么：
  - 不下载 Playwright 浏览器（直接驱动本机 Chrome）
  - 不建表；服务首次启动时自动创建所需表
#>

$ErrorActionPreference = 'Stop'
$Root     = Split-Path -Parent $PSScriptRoot
$VenvDir  = Join-Path $Root 'backend\.venv'
$ReqFile  = Join-Path $Root 'backend\requirements.txt'
$LockFile = Join-Path $Root 'backend\requirements.lock.txt'
$EnvFile  = Join-Path $Root '.env'
$EnvSample= Join-Path $Root '.env.example'

function Write-Step($msg) { Write-Host "[setup] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[ ok ] $msg" -ForegroundColor Green }
function Fail($msg)       { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

Set-Location -LiteralPath $Root

# ---------- 1. 定位 Python 3.12 ----------
Write-Step '1/6 定位 Python 3.12'
$candidates = @()
if ($env:JOBS_PYTHON) { $candidates += $env:JOBS_PYTHON }
$userPy = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (Test-Path -LiteralPath $userPy) { $candidates += $userPy }

$python = $null
foreach ($c in $candidates) {
    if (-not (Test-Path -LiteralPath $c)) { continue }
    try {
        $ver = (& $c -c "import sys;print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))").Trim()
    } catch { continue }
    if ($ver -eq '3.12') { $python = $c; break }
}
if (-not $python) {
    Fail '未找到 Python 3.12。请安装 python-3.12.10-amd64.exe（python.org），或设置环境变量 JOBS_PYTHON 指向 python.exe。'
}
Write-Ok "Python 3.12 => $python"

# 守门：确认不是沙箱运行时
try {
    $where = (& $python -c "import sys;print(sys.executable)").Trim()
} catch { Fail 'Python 无法执行。' }
if ($where -like '*sandbox_runtime*') {
    Fail "检测到沙箱运行时（$where），不可作为长期运行环境。请改用系统安装的 Python 3.12。"
}
Write-Ok "运行时隔离检查通过 => $where"

# ---------- 2. 建虚拟环境 ----------
Write-Step '2/6 创建虚拟环境 backend\.venv'
$venvPy = Join-Path $VenvDir 'Scripts\python.exe'
if (Test-Path -LiteralPath $venvPy) {
    Write-Ok '虚拟环境已存在，跳过创建'
} else {
    & $python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Fail '创建虚拟环境失败' }
    Write-Ok '虚拟环境已创建'
}
if (-not (Test-Path -LiteralPath $venvPy)) { Fail "虚拟环境不完整：$venvPy 不存在" }

# ---------- 3. 安装依赖 ----------
Write-Step '3/6 安装依赖（首次约 2-4 分钟）'
& $venvPy -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { Fail 'pip 升级失败' }
& $venvPy -m pip install -r $ReqFile
if ($LASTEXITCODE -ne 0) { Fail '依赖安装失败，见上方 pip 输出' }
& $venvPy -m pip freeze | Set-Content -LiteralPath $LockFile -Encoding utf8
Write-Ok "依赖已安装，已生成 requirements.lock.txt"

# ---------- 4. 生成 .env ----------
Write-Step '4/6 生成配置文件 .env'
if (Test-Path -LiteralPath $EnvFile) {
    Write-Ok '.env 已存在，不覆盖'
} else {
    Copy-Item -LiteralPath $EnvSample -Destination $EnvFile
    Write-Ok '.env 已从 .env.example 生成'
}

# ---------- 5. 建数据目录 ----------
Write-Step '5/6 建数据目录'
foreach ($d in 'data\raw', 'data\logs', 'data\exports', 'data\browser_profile') {
    $p = Join-Path $Root $d
    if (-not (Test-Path -LiteralPath $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
}
Write-Ok 'data 子目录就绪'

# ---------- 6. 自检 ----------
Write-Step '6/6 自检'
& $venvPy -c "import fastapi, sqlalchemy, pandas, yaml, loguru, apscheduler, openpyxl; print('deps-ok')"
if ($LASTEXITCODE -ne 0) { Fail '依赖导入自检失败' }

& $venvPy -c "import yaml; d=yaml.safe_load(open('config/taxonomy.yaml', encoding='utf-8')); print('taxonomy-ok skills='+str(len(d['skills']))+' dirs='+str(len(d['directions']))); s=yaml.safe_load(open('config/sources.yaml', encoding='utf-8')); print('sources-ok sources='+str(len(s['sources']))+' compliance='+str(len(s['compliance']))); i=yaml.safe_load(open('config/taxonomy.yaml', encoding='utf-8'))['skills']; dup=[k for k in set(x['canonical'] for x in i) if sum(1 for y in i if y['canonical']==k)>1]; print('dup-canonical='+(','.join(dup) if dup else 'none'))"
if ($LASTEXITCODE -ne 0) { Fail '配置文件解析失败' }

Write-Host ''
Write-Host '环境就绪。' -ForegroundColor Green
Write-Host "  虚拟环境 : $venvPy"
Write-Host "  配置文件 : $EnvFile"
Write-Host "  数据库   : 服务首次启动时自动初始化"
Write-Host "  下一步   : 运行 scripts/start.ps1，然后打开 http://127.0.0.1:8000/"
