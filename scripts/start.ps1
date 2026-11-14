$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot 'backend\.venv\Scripts\python.exe'
$ServiceUrl = 'http://127.0.0.1:8000'
if (-not (Test-Path -LiteralPath $Python)) {
    throw '未找到虚拟环境，请先运行 scripts\setup.ps1。'
}
function Test-JobService {
    try {
        # Windows PowerShell 5.1 may decode JSON without a charset as ANSI.
        $Response = Invoke-WebRequest "$ServiceUrl/api/health" -UseBasicParsing -TimeoutSec 2
        $Health = [System.Text.Encoding]::UTF8.GetString($Response.RawContentStream.ToArray()) | ConvertFrom-Json
        return ($Health.ok -and $Health.service -eq 'jobs-intel' -and $Health.root -eq $ProjectRoot)
    } catch { return $false }
}
if (Test-JobService) {
    Write-Host "服务已运行：$ServiceUrl"
    exit 0
}
$Listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($Listener) { throw '8000 端口被其他服务占用；未终止任何现有进程。' }
$LogDirectory = Join-Path $ProjectRoot 'data\logs'
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$OutputLog = Join-Path $LogDirectory "server-$Stamp.out.log"
$ErrorLog = Join-Path $LogDirectory "server-$Stamp.err.log"
$ServiceProcess = Start-Process -FilePath $Python -ArgumentList '-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory (Join-Path $ProjectRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput $OutputLog -RedirectStandardError $ErrorLog -PassThru
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    Start-Sleep -Milliseconds 500
    if (Test-JobService) {
        $Page = Invoke-WebRequest "$ServiceUrl/" -UseBasicParsing -TimeoutSec 5
        if ($Page.StatusCode -eq 200) {
            Write-Host "已启动：$ServiceUrl（进程 $($ServiceProcess.Id)）"
            Write-Host "日志：$ErrorLog"
            exit 0
        }
    }
    if ($ServiceProcess.HasExited) { break }
}
if (Test-Path -LiteralPath $ErrorLog) { Get-Content -LiteralPath $ErrorLog -Tail 25 }
throw "启动后未通过健康检查，请检查日志：$ErrorLog"
