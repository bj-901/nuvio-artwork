# Setup_Nuvio_Discover_Artwork_Folders.ps1
# Creates the Discover artwork folder structure in the existing Nuvio artwork repository.
# Safe to run repeatedly: it creates missing folders only and does not modify existing files.

[CmdletBinding()]
param(
    [string]$RepositoryPath = "D:\GitHub\nuvio-artwork"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $RepositoryPath -PathType Container)) {
    throw "Repository folder not found: $RepositoryPath`nCheck the path or run this script with -RepositoryPath <your repo path>."
}

$discoverPath = Join-Path $RepositoryPath "Discover"

$categories = @(
    "Trending",
    "Popular",
    "Latest Releases",
    "Top Rated",
    "For You"
)

$assetFolders = @(
    "Cover",
    "Backdrop",
    "Logo"
)

Write-Host "Nuvio Discover artwork folder setup" -ForegroundColor Cyan
Write-Host "Repository: $RepositoryPath"
Write-Host ""

New-Item -ItemType Directory -Path $discoverPath -Force | Out-Null

foreach ($category in $categories) {
    $categoryPath = Join-Path $discoverPath $category
    New-Item -ItemType Directory -Path $categoryPath -Force | Out-Null

    foreach ($assetFolder in $assetFolders) {
        $assetPath = Join-Path $categoryPath $assetFolder
        New-Item -ItemType Directory -Path $assetPath -Force | Out-Null

        # Git does not track empty directories, so add a small placeholder.
        $readmePath = Join-Path $assetPath "README.md"
        if (-not (Test-Path -LiteralPath $readmePath)) {
            $description = switch ($assetFolder) {
                "Cover"    { "Place the category's landscape cover artwork in this folder." }
                "Backdrop" { "Place the category's hero backdrop artwork in this folder." }
                "Logo"     { "Place the category's transparent title logo artwork in this folder." }
            }
            Set-Content -LiteralPath $readmePath -Value $description -Encoding UTF8
        }
    }
}

Write-Host "Created or verified these folders:" -ForegroundColor Green
foreach ($category in $categories) {
    Write-Host "  Discover\$category\Cover"
    Write-Host "  Discover\$category\Backdrop"
    Write-Host "  Discover\$category\Logo"
}

Write-Host ""
Write-Host "Done. Existing repository files were not overwritten or deleted." -ForegroundColor Green
Write-Host "Next: add the artwork files, commit, and push the Discover folder to GitHub."
