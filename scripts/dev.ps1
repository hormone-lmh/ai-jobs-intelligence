<#
dev.ps1 — 启动本地服务（开发用，带自动重载）

用法：
  pwsh -ExecutionPolicy Bypass -File scripts\dev.ps1
#>

$ErrorActionPreference = 'Stop'
$Root    = Split-Path -Parent $PSScriptRoot
$VenvPy  = Join-Path $Root 'backend\.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Host '未找到虚拟环境，请先运行 scripts\setup.ps1' -ForegroundColor Red
    exit 1
}

Set-Location -LiteralPath (Join-Path $Root 'backend')
Write-Host '本地服务： http://127.0.0.1:8000' -ForegroundColor Cyan
Write-Host '接口文档： http://127.0.0.1:8000/docs' -ForegroundColor Cyan
& $VenvPy -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
