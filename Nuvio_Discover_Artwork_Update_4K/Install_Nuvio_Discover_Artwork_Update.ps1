[CmdletBinding()]
param([switch]$Apply)

$ErrorActionPreference = "Stop"
$RepoRoot = "D:\GitHub\nuvio-artwork"
$PackageRoot = Join-Path $PSScriptRoot "Nuvio_Discover_Artwork_Update"

if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "Repository not found: $RepoRoot"
}
if (-not (Test-Path -LiteralPath $PackageRoot -PathType Container)) {
    throw "Package folder not found: $PackageRoot. Extract the ZIP into the repository root first."
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRoot = Join-Path $RepoRoot "_Nuvio_Artwork_Update_Backup_$Timestamp"

$Files = @(
    @{ Source = "scripts\generate_discover_backdrops.py"; Destination = "scripts\generate_discover_backdrops.py" },
    @{ Source = ".github\workflows\regenerate-discover-backdrops.yml"; Destination = ".github\workflows\regenerate-discover-backdrops.yml" },
    @{ Source = "Logo_Assets\Trending\Logo\logo.webp"; Destination = "Discover\Trending\Logo\logo.webp" },
    @{ Source = "Logo_Assets\Popular\Logo\logo.webp"; Destination = "Discover\Popular\Logo\logo.webp" },
    @{ Source = "Logo_Assets\Latest Releases\Logo\logo.webp"; Destination = "Discover\Latest Releases\Logo\logo.webp" },
    @{ Source = "Logo_Assets\Top Rated\Logo\logo.webp"; Destination = "Discover\Top Rated\Logo\logo.webp" },
    @{ Source = "Logo_Assets\For You\Logo\logo.webp"; Destination = "Discover\For You\Logo\logo.webp" }
)

foreach ($Entry in $Files) {
    $Source = Join-Path $PackageRoot $Entry.Source
    $Destination = Join-Path $RepoRoot $Entry.Destination
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Required package file is missing: $Source"
    }
    if (-not (Test-Path -LiteralPath (Split-Path $Destination -Parent) -PathType Container)) {
        throw "Destination folder is missing: $(Split-Path $Destination -Parent)"
    }
}

Write-Host "`nNuvio Discover artwork update" -ForegroundColor Cyan
$Files | ForEach-Object {
    $dest = Join-Path $RepoRoot $_.Destination
    [pscustomobject]@{
        File = $_.Destination
        Existing = Test-Path -LiteralPath $dest
    }
} | Format-Table -AutoSize

if (-not $Apply) {
    Write-Host "`nPREVIEW ONLY. No files changed." -ForegroundColor Yellow
    Write-Host "If the list looks right, run: .\Install_Nuvio_Discover_Artwork_Update.ps1 -Apply"
    exit 0
}

New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
foreach ($Entry in $Files) {
    $Source = Join-Path $PackageRoot $Entry.Source
    $Destination = Join-Path $RepoRoot $Entry.Destination
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        $Backup = Join-Path $BackupRoot $Entry.Destination
        New-Item -ItemType Directory -Path (Split-Path $Backup -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $Destination -Destination $Backup -Force
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
    Write-Host "Updated: $($Entry.Destination)" -ForegroundColor Green
}

Write-Host "`nBackups saved to: $BackupRoot" -ForegroundColor Yellow
Write-Host "Next: review the seven changed files in GitHub Desktop. Commit and push when ready."
