$ErrorActionPreference = "Stop"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = (Join-Path $PSScriptRoot "..\src")
python -m scripts.diagnose_runtime
