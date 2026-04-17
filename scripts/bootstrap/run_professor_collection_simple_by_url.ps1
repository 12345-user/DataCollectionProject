param(
    [Parameter(Mandatory = $true)]
    [string]$ProfessorName,

    [Parameter(Mandatory = $true)]
    [string]$SeedPaperUrl,

    [string]$OutputPrefix = "",

    # 允许你在命令末尾继续追加 URL，作为额外信息源
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraUrls
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $projectRoot

function Extract-PmidFromUrl([string]$url) {
    $m = [regex]::Match($url, '/(\d+)/')
    if ($m.Success) { return $m.Groups[1].Value }

    $m = [regex]::Match($url, 'pmid=(\d+)')
    if ($m.Success) { return $m.Groups[1].Value }

    return ""
}

$pmid = Extract-PmidFromUrl $SeedPaperUrl
if ([string]::IsNullOrWhiteSpace($pmid)) {
    throw "无法从 SeedPaperUrl 解析 PMID，请确保传入的是类似 PubMed: https://pubmed.ncbi.nlm.nih.gov/<pmid>/ 的链接。SeedPaperUrl=$SeedPaperUrl"
}

$simple = Join-Path $projectRoot "scripts\bootstrap\run_professor_collection_simple.ps1"
if (-not (Test-Path $simple)) {
    throw "未找到脚本: $simple"
}

# run_professor_collection_simple.ps1 里 SeedPaperTitle 参数是必填的，这里为了沿用同一条逻辑链，
# 给一个占位字符串即可（因为解析 affiliations 时优先使用 SeedPMID）。
$placeholderTitle = "seed_title_unused"

$args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $simple,
    "-ProfessorName", $ProfessorName,
    "-SeedPaperTitle", $placeholderTitle,
    "-SeedPMID", $pmid
)

if (-not [string]::IsNullOrWhiteSpace($OutputPrefix)) {
    $args += @("-OutputPrefix", $OutputPrefix)
}

if ($ExtraUrls -and $ExtraUrls.Count -gt 0) {
    $args += $ExtraUrls
}

& powershell @args

