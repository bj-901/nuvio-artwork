#requires -Version 5.1
<#
Creates ONLY streaming-service animation folders in the local Nuvio artwork repo.

Target:
  D:\GitHub\nuvio-artwork\Streaming Services Animations

This script:
  - Creates the Streaming Services Animations parent folder if missing.
  - Creates one folder per streaming service listed below.
  - Uses "+" in service folder names where appropriate.
  - Preserves all existing folders and files.
  - Does not create Movies or TV-Shows folders.
  - Does not download artwork, create README files, move/delete files, commit, or push.
#>

$ErrorActionPreference = 'Stop'

# Resolve the repository from this script's location when saved in the repo.
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$GitFolder = Join-Path $RepoRoot '.git'

if (-not (Test-Path -LiteralPath $GitFolder -PathType Container)) {
    # Fallback to the user's established local repository path.
    $RepoRoot = 'D:\GitHub\nuvio-artwork'
    if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.git') -PathType Container)) {
        throw "GitHub repository not found. Save this script inside D:\GitHub\nuvio-artwork and run it again."
    }
}

$AnimationRoot = Join-Path $RepoRoot 'Streaming Services Animations'

$Services = @(
    'Netflix',
    'Apple TV',
    'HBO Max',
    'Disney+',
    'Prime Video',
    'Paramount+',
    'Peacock',
    'Hulu',
    'STARZ',
    'AMC+',
    'MGM+',
    'Shudder'
)

if (-not (Test-Path -LiteralPath $AnimationRoot -PathType Container)) {
    New-Item -ItemType Directory -Path $AnimationRoot -Force | Out-Null
    Write-Host "[CREATED] Streaming Services Animations" -ForegroundColor Green
} else {
    Write-Host "[EXISTS]  Streaming Services Animations" -ForegroundColor Yellow
}

$Created = 0
$Existing = 0

foreach ($Service in $Services) {
    $Folder = Join-Path $AnimationRoot $Service

    if (Test-Path -LiteralPath $Folder -PathType Container) {
        Write-Host "[EXISTS]  $Service" -ForegroundColor DarkGray
        $Existing++
    } else {
        New-Item -ItemType Directory -Path $Folder -Force | Out-Null
        Write-Host "[CREATED] $Service" -ForegroundColor Green
        $Created++
    }
}

Write-Host ''
Write-Host 'Streaming animation folder setup complete.' -ForegroundColor Green
Write-Host "Repository: $RepoRoot"
Write-Host "Animation folders created: $Created"
Write-Host "Animation folders already present: $Existing"
Write-Host ''
Write-Host 'No Movies or TV-Shows folders were created or changed.'
Write-Host 'No artwork files were downloaded, moved, overwritten, or deleted.'
Write-Host 'Review the folder changes in GitHub Desktop, then commit and push when ready.'
