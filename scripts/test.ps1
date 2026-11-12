$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
$TestParent = Join-Path $Root 'data\test-runs'
New-Item -ItemType Directory -Force -Path $TestParent | Out-Null
$TestTemp = Join-Path $TestParent ([guid]::NewGuid().ToString('N'))
& "$Root\backend\.venv\Scripts\python.exe" -B -m pytest tests -q -p no:cacheprovider --basetemp $TestTemp --tb=short
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
node --test tests\extension.test.cjs tests\extractor.test.cjs
exit $LASTEXITCODE
