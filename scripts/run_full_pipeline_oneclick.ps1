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
    [string[]]$ExtraSourceUrls = @(),
    [switch]$EnableSetFit,
    [switch]$EnableBERTopic,
    [switch]$EnableSnorkel,
    [switch]$EnableTagLearning,
    [switch]$LocalFilesOnly
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
$step09Json = "09_quality_guard/step_results/${OutputPrefix}_step09_quality_report.json"
$step09Md = "09_quality_guard/step_results/${OutputPrefix}_step09_quality_report.md"
$step04Out = "05_keyword_entity/step_results/${OutputPrefix}_step04_keyword_entity.jsonl"
$setfitModelDir = "08_taxonomy_memory/models/setfit_local"
$bertopicOut = "08_taxonomy_memory/step_results/${OutputPrefix}_bertopic_candidates.json"
$snorkelOut = "08_taxonomy_memory/step_results/${OutputPrefix}_snorkel_weak_labels.jsonl"
$queueOut = "08_taxonomy_memory/step_results/domain_taxonomy_learning_queue.jsonl"
$taxReportOut = "08_taxonomy_memory/step_results/domain_taxonomy_report.json"
$queueL2Out = "08_taxonomy_memory/step_results/learning_queue_l2.jsonl"
$queueL3Out = "08_taxonomy_memory/step_results/learning_queue_l3.jsonl"
$learnedL2Out = "08_taxonomy_memory/step_results/learned_l2.jsonl"
$learnedL3Out = "08_taxonomy_memory/step_results/learned_l3.jsonl"
$tagReportOut = "08_taxonomy_memory/step_results/tag_report.json"

Write-Host "=== 一键全流程开始 ==="
Write-Host "ProfessorName: $ProfessorName"
Write-Host "SeedPaperTitle: $SeedPaperTitle"
Write-Host "SeedPMID: $SeedPMID"
Write-Host "OutputPrefix: $OutputPrefix"
Write-Host "EnableSetFit: $EnableSetFit"
Write-Host "EnableBERTopic: $EnableBERTopic"
Write-Host "EnableSnorkel: $EnableSnorkel"
Write-Host "EnableTagLearning: $EnableTagLearning"
Write-Host "LocalFilesOnly: $LocalFilesOnly"
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

# Step09: quality guard (integrity/linkage/dirty-data/readability)
& $python "09_quality_guard/processing/run_step09_quality_guard.py" `
  --prefix $OutputPrefix `
  --output-json $step09Json `
  --output-md $step09Md
Assert-LastExit "Step09-QualityGuard"

# Step08: optional local mid/long-term taxonomy enhancement
if ($EnableSetFit) {
    $setfitArgs = @(
        "08_taxonomy_memory/processing/train_setfit_local.py",
        "--train-jsonl", "08_taxonomy_memory/step_results/domain_taxonomy_learned.jsonl",
        "--output-dir", $setfitModelDir
    )
    if ($LocalFilesOnly) {
        $setfitArgs += "--local-files-only"
    }
    & $python @setfitArgs
    Assert-LastExit "Step08-SetFit"
}

if ($EnableBERTopic) {
    $bertopicArgs = @(
        "08_taxonomy_memory/processing/discover_bertopic_local.py",
        "--input-jsonl", $step04Out,
        "--output-json", $bertopicOut
    )
    if ($LocalFilesOnly) {
        $bertopicArgs += "--local-files-only"
    }
    & $python @bertopicArgs
    Assert-LastExit "Step08-BERTopic"
}

if ($EnableSnorkel) {
    & $python "08_taxonomy_memory/processing/snorkel_labeling_local.py" `
      --input-jsonl $step04Out `
      --output-jsonl $snorkelOut
    Assert-LastExit "Step08-Snorkel"

    & $python "08_taxonomy_memory/processing/merge_weak_labels_to_queue.py" `
      --weak-labels-jsonl $snorkelOut `
      --step04-jsonl $step04Out `
      --queue-jsonl $queueOut
    Assert-LastExit "Step08-SnorkelMergeQueue"

    & $python "08_taxonomy_memory/processing/build_taxonomy_report.py" `
      --queue $queueOut `
      --learned "08_taxonomy_memory/step_results/domain_taxonomy_learned.jsonl" `
      --output $taxReportOut
    Assert-LastExit "Step08-TaxonomyReport"
}

if ($EnableTagLearning) {
    & $python "08_taxonomy_memory/processing/extract_tag_candidates.py" `
      --input-jsonl $step04Out `
      --output-l2 $queueL2Out `
      --output-l3 $queueL3Out
    Assert-LastExit "Step08-ExtractTagCandidates"

    & $python "08_taxonomy_memory/processing/build_tag_report.py" `
      --queue-l2 $queueL2Out `
      --queue-l3 $queueL3Out `
      --learned-l2 $learnedL2Out `
      --learned-l3 $learnedL3Out `
      --output $tagReportOut
    Assert-LastExit "Step08-BuildTagReport"
}

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
Write-Host "Step09 Quality JSON: $step09Json"
Write-Host "Step09 Quality MD: $step09Md"
if ($EnableSetFit) { Write-Host "Step08 SetFit ModelDir: $setfitModelDir" }
if ($EnableBERTopic) { Write-Host "Step08 BERTopic Candidates: $bertopicOut" }
if ($EnableSnorkel) { Write-Host "Step08 Snorkel Weak Labels: $snorkelOut" }
if ($EnableSnorkel) { Write-Host "Step08 Learning Queue: $queueOut" }
if ($EnableSnorkel) { Write-Host "Step08 Taxonomy Report: $taxReportOut" }
if ($EnableTagLearning) { Write-Host "Step08 Queue L2: $queueL2Out" }
if ($EnableTagLearning) { Write-Host "Step08 Queue L3: $queueL3Out" }
if ($EnableTagLearning) { Write-Host "Step08 Tag Report: $tagReportOut" }
