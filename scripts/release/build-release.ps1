#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][string]$PostgresImage,
    [Parameter(Mandatory)][string]$NginxImage,
    [ValidateSet('linux/amd64', 'linux/arm64')][string]$Platform = 'linux/amd64',
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
& $Python (Join-Path $PSScriptRoot 'build_release.py') --version $Version --output $OutputDirectory --platform $Platform --postgres-image $PostgresImage --nginx-image $NginxImage
if ($LASTEXITCODE -ne 0) { throw "Сборка выпуска остановлена (код $LASTEXITCODE)." }
