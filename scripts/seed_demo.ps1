$ErrorActionPreference = 'Stop'
$cmRepo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Convert-CampusMindSecureString {
    param([System.Security.SecureString]$Value)
    $cmPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($cmPointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($cmPointer)
    }
}

$cmDemo = Read-Host 'Demo user password (12+ characters)' -AsSecureString
$cmAdmin = Read-Host 'Admin password (12+ characters, different)' -AsSecureString

Push-Location $cmRepo
try {
    $env:PYTHONPATH = Join-Path $cmRepo 'src'
    $env:CAMPUSMIND_DEMO_PASSWORD = Convert-CampusMindSecureString $cmDemo
    $env:CAMPUSMIND_ADMIN_PASSWORD = Convert-CampusMindSecureString $cmAdmin
    & python -m scripts.seed_core
    if ($LASTEXITCODE -ne 0) {
        throw "CampusMind seed failed with exit code $LASTEXITCODE"
    }
} finally {
    Remove-Item Env:CAMPUSMIND_DEMO_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:CAMPUSMIND_ADMIN_PASSWORD -ErrorAction SilentlyContinue
    Pop-Location
}
