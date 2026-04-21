param(
    [Parameter(Mandatory = $true)]
    [string]$ProfessorName,

    [Parameter(Mandatory = $true)]
    [string]$SeedPaperTitle,

    [string]$SeedPMID = "",
    [string]$OutputPrefix = "",
    [bool]$SkipArxiv = $true,
    [switch]$NoStartWeb,
    [int]$WebPort = 8502,
    [string[]]$ExtraSourceUrls = @()
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $projectRoot

function Assert-LastExit([string]$stepName) {
    if ($LASTEXITCODE -ne 0) {
        throw "$stepName 执行失败，退出码：$LASTEXITCODE"
    }
}

function Slug([string]$s) {
    $s = $s.ToLowerInvariant()
    $s = $s -replace '[^a-z0-9]+', '_'
    return $s.Trim('_')
}

if ([string]::IsNullOrWhiteSpace($OutputPrefix)) {
    $OutputPrefix = "pubmed_$(Slug $ProfessorName)"
}

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "未找到虚拟环境 Python：$python"
}

$step02Out = "02_paper_list_extend/step_results/${OutputPrefix}_expanded_papers.jsonl"
$labInfo = "01_data_collection/step_results/professor_lab_info/${OutputPrefix}_lab_info.json"
$step05PaperOut = "06_domain_clustering/step_results/${OutputPrefix}_step05_paper_domains.jsonl"
$timelineOut = "07_temporal_analysis/step_results/${OutputPrefix}_step06_project_timeline.json"
$allocationOut = "07_temporal_analysis/step_results/${OutputPrefix}_step06_effort_allocation.json"
$reportOut = "07_temporal_analysis/step_results/${OutputPrefix}_step06_trend_report.md"
$duckdbPath = "07_temporal_analysis/step_results/pipeline.duckdb"

Write-Host "=== 一键全流程开始 ==="
Write-Host "ProfessorName: $ProfessorName"
Write-Host "SeedPaperTitle: $SeedPaperTitle"
Write-Host "SeedPMID: $SeedPMID"
Write-Host "OutputPrefix: $OutputPrefix"
if ($ExtraSourceUrls.Count -gt 0) {
    Write-Host "ExtraSourceUrls: $($ExtraSourceUrls -join ', ')"
}

# Step01: data collection + bridge
$step01Args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", "scripts/bootstrap/run_professor_collection_simple.ps1",
    "-ProfessorName", $ProfessorName,
    "-SeedPaperTitle", $SeedPaperTitle,
    "-OutputPrefix", $OutputPrefix
)
if (-not [string]::IsNullOrWhiteSpace($SeedPMID)) {
    $step01Args += @("-SeedPMID", $SeedPMID)
}
if ($ExtraSourceUrls.Count -gt 0) {
    $step01Args += $ExtraSourceUrls
}
& powershell @step01Args
Assert-LastExit "Step01"

# Step02: paper list extend
$step02Args = @(
    "02_paper_list_extend/processing/run_step02_paper_list_extend_paperscraper.py",
    "--professor-name", $ProfessorName,
    "--step01-output-prefix", $OutputPrefix,
    "--output-prefix", $OutputPrefix,
    "--server-dump-dir", "02_paper_list_extend/data_sources/paperscraper_server_dumps/server_dumps"
)
if ($SkipArxiv) {
    $step02Args += "--skip-arxiv"
}
& $python @step02Args
Assert-LastExit "Step02"

# Step03-05: cloud glue chain
& powershell -ExecutionPolicy Bypass -File "scripts/run_steps04_05_06_cloud_glue.ps1" `
  -ExpandedPapers $step02Out `
  -LabInfo $labInfo `
  -TargetName $ProfessorName `
  -Prefix $OutputPrefix
Assert-LastExit "Step03-05"

# Step06: temporal analysis
& $python "07_temporal_analysis/processing/run_step07_temporal_analysis.py" `
  --input $step05PaperOut `
  --timeline-output $timelineOut `
  --allocation-output $allocationOut `
  --report-output $reportOut
Assert-LastExit "Step06"

# Step07: build DuckDB for web
& $python "07_temporal_analysis/processing/build_step07_duckdb.py" `
  --professor $OutputPrefix `
  --paper-domains $step05PaperOut `
  --duckdb-path $duckdbPath
Assert-LastExit "Step07-DB"

# Save source-site metadata for web display.
$sourceMetaPath = "07_temporal_analysis/step_results/${OutputPrefix}_source_sites.json"
$sourceMeta = @{
    professor = $OutputPrefix
    input_extra_urls = @($ExtraSourceUrls)
    generated_at = (Get-Date).ToString("s")
}
$sourceMeta | ConvertTo-Json -Depth 5 | Out-File -Encoding utf8 $sourceMetaPath

if (-not $NoStartWeb) {
    $streamlit = Join-Path $projectRoot ".venv\Scripts\streamlit.exe"
    if (-not (Test-Path $streamlit)) {
        Write-Warning "未找到 streamlit 可执行文件：$streamlit"
    } else {
        Write-Host "启动网页： http://localhost:$WebPort"
        & $streamlit run "07_temporal_analysis/app/streamlit_app.py" --server.port $WebPort --server.headless true
    }
}

Write-Host "=== 一键全流程完成 ==="
Write-Host "Step02 Output: $step02Out"
Write-Host "Step05 PaperDomains: $step05PaperOut"
Write-Host "Step06 Timeline: $timelineOut"
Write-Host "Step06 Allocation: $allocationOut"
Write-Host "Step06 Report: $reportOut"
Write-Host "DuckDB: $duckdbPath"
Write-Host "SourceSitesMeta: $sourceMetaPath"
