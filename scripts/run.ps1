$ErrorActionPreference = "Stop"
$env:PYTHONPATH = (Join-Path $PSScriptRoot "..\src")
Write-Host "CampusMind UI:      http://127.0.0.1:8000/ui/"
Write-Host "CampusMind Swagger: http://127.0.0.1:8000/docs"
python -m uvicorn campusmind.main:app --host 0.0.0.0 --port 8000 --reload
