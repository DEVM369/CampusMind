param([switch]$BuildFrontend, [string]$DockerImage)

$ErrorActionPreference = 'Stop'
$cmArguments = @((Join-Path $PSScriptRoot 'check_project.py'))
if ($BuildFrontend) { $cmArguments += '--build-frontend' }
if ($DockerImage) { $cmArguments += @('--docker-image', $DockerImage) }
& python @cmArguments
if ($LASTEXITCODE -ne 0) {
    throw "CampusMind validation failed with exit code $LASTEXITCODE"
}

