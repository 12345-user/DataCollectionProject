param(
    [Parameter(Mandatory = $true)]
    [string]$ProfessorName,

    [Parameter(Mandatory = $true)]
    [string]$AffiliationUnit,

    # 末尾追加的参数都会被当作额外网页 URL
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraUrls,

    [string]$OutputPrefix = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $projectRoot

function Get-Slug([string]$s) {
    $s = $s.Trim()
    $s = ($s -replace '[^a-zA-Z0-9]+', '_')
    $s = $s.Trim('_')
    if ([string]::IsNullOrWhiteSpace($s)) { return 'unknown' }
    return $s.ToLowerInvariant()
}

if ([string]::IsNullOrWhiteSpace($OutputPrefix)) {
    $OutputPrefix = "pubmed_$(Get-Slug $ProfessorName)"
}

$crawlFile = "01_data_collection\processing\web_crawler_local\crawl_urls.txt"
$backupFile = "$crawlFile.bak"

Write-Host "=== 教授采集 + 额外网页证据开始 ==="
Write-Host "ProfessorName: $ProfessorName"
Write-Host "AffiliationUnit: $AffiliationUnit"
Write-Host "OutputPrefix: $OutputPrefix"

if (Test-Path $crawlFile) {
    Copy-Item -Force $crawlFile $backupFile
}

try {
    $extras = @()
    if ($null -ne $ExtraUrls) {
        $extras = $ExtraUrls | Where-Object { $_ -and $_.Trim() -ne "" }
    }

    if ($extras.Count -gt 0) {
        $existing = @()
        $existing = Get-Content $crawlFile -ErrorAction SilentlyContinue
        foreach ($u in $extras) {
            if (-not ($existing -contains $u)) {
                $existing += $u
            }
        }
        $existing | Set-Content -Encoding utf8 $crawlFile
        Write-Host "追加的网页 URL 数量: $($extras.Count)"
    }

    # 1) 先跑网页抓取（写入 professor_lab_info/local_crawl_results.*）
    python "01_data_collection\processing\web_crawler_local/run_local_crawl.py"

    # 2) 再跑 PubMed titles/abstracts/lab_info
    powershell -ExecutionPolicy Bypass -File "scripts\\bootstrap\\run_professor_collection_by_name_unit.ps1" `
        -ProfessorName $ProfessorName `
        -AffiliationUnit $AffiliationUnit `
        -OutputPrefix $OutputPrefix
}
finally {
    if (Test-Path $backupFile) {
        Move-Item -Force $backupFile $crawlFile
    }
}

Write-Host "=== 教授采集 + 额外网页证据完成 ==="
