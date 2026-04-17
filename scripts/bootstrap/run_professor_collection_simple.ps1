param(
    [Parameter(Mandatory = $true)]
    [string]$ProfessorName,

    [Parameter(Mandatory = $true)]
    [string]$SeedPaperTitle,

    [string]$SeedPMID = "",

    [string]$OutputPrefix = "",

    # 允许你在命令末尾继续追加 URL，作为额外信息源
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraUrls
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $projectRoot

function Slug([string]$s) {
    $s = $s.ToLowerInvariant()
    $s = $s -replace '[^a-z0-9]+', '_'
    return $s.Trim('_')
}

if ([string]::IsNullOrWhiteSpace($OutputPrefix)) {
    $OutputPrefix = ("pubmed_" + (Slug $ProfessorName))
}

# Resolve seed paper -> affiliation keywords for disambiguation.
$helper = "01_data_collection\processing\lab_paper_tools\resolve_seed_to_affiliation_keywords.py"
$resolverArgs = @(
    $helper,
    "--professor-name", $ProfessorName,
    "--seed-title", $SeedPaperTitle
)
if (-not [string]::IsNullOrWhiteSpace($SeedPMID)) {
    $resolverArgs += @("--seed-pmid", $SeedPMID)
}
$seedRaw = & py -3.12 @resolverArgs 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Seed resolver failed. Output:`n$seedRaw"
}
try {
    $seed = $seedRaw | ConvertFrom-Json
} catch {
    throw "Seed resolver did not return valid JSON. Output:`n$seedRaw"
}

$AffiliationUnitForAd = $seed.affiliation_unit_for_ad
$AffiliationKeywords = ($seed.affiliation_keywords | ForEach-Object { $_ }) -join ","

# PubMed author query: Name[au] AND <affiliation tokens>[ad]
# 说明：避免在 --query 里嵌套双引号导致 PowerShell 参数传递被拆分。
$unitTokens = ($AffiliationUnitForAd -split '\s+' | ForEach-Object { $_.Trim() } | Where-Object { $_.Length -gt 2 })
$unitTokens = $unitTokens | ForEach-Object { ($_ -replace '[^\p{L}\p{Nd}\-]+', '') } | Where-Object { $_.Length -gt 0 }
$stopWords = @('and', 'or', 'of', 'the', 'a', 'an', 'in', 'on', 'for', 'to', 'with', 'without', 'under', 'by')
$unitTokens = $unitTokens | Where-Object { $stopWords -notcontains $_.ToLowerInvariant() }
if ($unitTokens.Count -gt 0) {
    $adExpr = ($unitTokens | ForEach-Object { "$($_)[ad]" }) -join " AND "
    $ProfessorQuery = "$ProfessorName[au] AND ($adExpr)"
} else {
    $ProfessorQuery = "$ProfessorName[au]"
}

Write-Host "=== 教授论文采集（简化版）==="
Write-Host "ProfessorName: $ProfessorName"
Write-Host "SeedPaperTitle: $SeedPaperTitle"
Write-Host "SeedPMID: $SeedPMID"
Write-Host "AffiliationUnitForAd: $AffiliationUnitForAd"
Write-Host "AffiliationKeywordsCount: $(@($seed.affiliation_keywords).Count)"
Write-Host "OutputPrefix: $OutputPrefix"
Write-Host "ProfessorQuery: $ProfessorQuery"

# 1) 只用教授名+种子论文标题：抓标题->摘要->机构线索
& (Join-Path $projectRoot "scripts\bootstrap\run_professor_collection.ps1") `
  -ProfessorQuery $ProfessorQuery `
  -OutputPrefix $OutputPrefix `
  -AffiliationKeywords $AffiliationKeywords

# 3) 同步 Step01 结果到 Step02 的 data_sources（让 Step02 直接消费）
$bridge = Join-Path $projectRoot "scripts\bootstrap\bridge_step01_to_step02.ps1"
if (Test-Path $bridge) {
    & powershell -ExecutionPolicy Bypass -File $bridge -OutputPrefix $OutputPrefix
} else {
    Write-Warning "未找到 bridge 脚本，已跳过同步：$bridge"
}

# 2) 若提供了额外 URL：只作为“辅助网页采集证据”，同样落到 professor_lab_info 目录
if ($ExtraUrls -and $ExtraUrls.Count -gt 0) {
    Write-Host "附加 ExtraUrls 数量: $($ExtraUrls.Count)"

    $crawlFile = Join-Path $projectRoot "01_data_collection\processing\web_crawler_local\crawl_urls.txt"
    Set-Content -Encoding utf8 $crawlFile ($ExtraUrls | Where-Object { $_ -and $_.Trim().Length -gt 0 })

    $localCrawler = Join-Path $projectRoot "01_data_collection\processing\web_crawler_local\run_local_crawl.py"
    & py -3.12 $localCrawler
}

Write-Host "=== 教授论文采集完成 ==="

