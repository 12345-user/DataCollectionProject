param(
    [Parameter(Mandatory = $true)]
    [string]$ProfessorQuery,

    [Parameter(Mandatory = $true)]
    [string]$OutputPrefix
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $projectRoot

Write-Host "=== 教授论文采集一键执行开始 ==="
Write-Host "Query: $ProfessorQuery"
Write-Host "Prefix: $OutputPrefix"

python "01_data_collection/processing/lab_paper_tools/fetch_pubmed_titles.py" `
  --query $ProfessorQuery `
  --output-prefix $OutputPrefix

$titlesJson = "01_data_collection/step_results/professor_paper_titles/$OutputPrefix`_titles.json"

python "01_data_collection/processing/lab_paper_tools/fetch_pubmed_abstracts.py" `
  --titles-json $titlesJson `
  --output-prefix $OutputPrefix

python "01_data_collection/processing/lab_paper_tools/extract_lab_info_from_pubmed.py" `
  --titles-json $titlesJson `
  --output-prefix $OutputPrefix

Write-Host "=== 教授论文采集一键执行完成 ==="
