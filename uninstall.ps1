# Remove the maj-scripts copy installed by install.ps1, without removing dependencies
# or maj-scripts's configuration and downloaded data.
#
#   irm https://raw.githubusercontent.com/majal/maj-scripts/main/uninstall.ps1 | iex

$ErrorActionPreference = "Stop"
$MajScriptsHome = if ($env:MAJ_SCRIPTS_HOME) { $env:MAJ_SCRIPTS_HOME } else { Join-Path $HOME ".maj-scripts" }
$DefaultHome = Join-Path $HOME ".maj-scripts"
$Tools = @("ffcut", "gmail-cleanup", "thumb", "wh", "whisper")

function Stop-Uninstall($msg) { Write-Host "maj-scripts uninstall: $msg" -ForegroundColor Red; exit 1 }
function Write-Ok($msg) { Write-Host $msg -ForegroundColor Green }

if ([string]::IsNullOrWhiteSpace($MajScriptsHome) -or $MajScriptsHome -eq (Split-Path $HOME -Qualifier) -or $MajScriptsHome -eq $HOME) {
    Stop-Uninstall "refusing unsafe MAJ_SCRIPTS_HOME: $MajScriptsHome"
}

if ((Test-Path $MajScriptsHome) -and $MajScriptsHome -ne $DefaultHome) {
    $hasFootprint = (Test-Path (Join-Path $MajScriptsHome "maj-scripts-update.cmd"))
    foreach ($tool in $Tools) { $hasFootprint = $hasFootprint -and (Test-Path (Join-Path $MajScriptsHome $tool)) }
    if (-not $hasFootprint) { Stop-Uninstall "refusing to remove custom MAJ_SCRIPTS_HOME without an installer footprint: $MajScriptsHome" }
}

$statePath = Join-Path $MajScriptsHome ".maj-scripts-install-state.json"
$installedPackageIds = @()
if (Test-Path $statePath) {
    try { $installedPackageIds = @((Get-Content $statePath -Raw | ConvertFrom-Json).dependencies) } catch { }
}

$currentUserPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
if ($currentUserPath) {
    $target = $MajScriptsHome.TrimEnd("\\", "/")
    $remaining = @($currentUserPath -split ';' | Where-Object { $_ -and $_.TrimEnd("\\", "/") -ine $target })
    $newPath = $remaining -join ';'
    if ($newPath -ne $currentUserPath) {
        [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Ok "Removed $MajScriptsHome from your user PATH"
    }
}

if (Test-Path $MajScriptsHome) {
    Remove-Item -Recurse -Force $MajScriptsHome
    Write-Ok "Removed installed maj-scripts copy at $MajScriptsHome"
} else {
    Write-Host "No installed maj-scripts copy found at $MajScriptsHome"
}

foreach ($packageId in $installedPackageIds) {
    if ($packageId) {
        Write-Host "Removing installer-added dependency: $packageId"
        try { winget uninstall --id $packageId -e --accept-source-agreements } catch { Write-Host "Could not remove $packageId; leaving it installed." -ForegroundColor Yellow }
    }
}

Write-Host "Kept your scripts' own settings and data. Existing dependencies not recorded as installer-added were kept."
