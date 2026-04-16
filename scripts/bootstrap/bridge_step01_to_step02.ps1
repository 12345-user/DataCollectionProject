param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPrefix
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $projectRoot

$srcTitles = "01_data_collection/step_results/professor_paper_titles/$OutputPrefix`_titles.json"
$srcAbstracts = "01_data_collection/step_results/professor_paper_abstracts/$OutputPrefix`_abstracts.json"
$srcLab = "01_data_collection/step_results/professor_lab_info/$OutputPrefix`_lab_info.json"

$targetDir = "02_parsing/data_sources/from_01_collection/$OutputPrefix"
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

if (Test-Path $srcTitles) { Copy-Item -Force $srcTitles "$targetDir/titles.json" }
if (Test-Path $srcAbstracts) { Copy-Item -Force $srcAbstracts "$targetDir/abstracts.json" }
if (Test-Path $srcLab) { Copy-Item -Force $srcLab "$targetDir/lab_info.json" }

Write-Host "Bridge completed: $targetDir"
