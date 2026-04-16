param(
    [Parameter(Mandatory = $true)]
    [string]$ProfessorName,

    [Parameter(Mandatory = $true)]
    [string]$AffiliationUnit,

    # 可选：自定义输出前缀（默认从教授姓名生成）
    [string]$OutputPrefix = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $projectRoot

function Get-Slug([string]$s) {
    $s = $s.Trim()
    # 保留字母数字与下划线，其他转为下划线
    $s = ($s -replace '[^a-zA-Z0-9]+', '_')
    $s = $s.Trim('_')
    if ([string]::IsNullOrWhiteSpace($s)) { return 'unknown' }
    return $s.ToLowerInvariant()
}

$escapedUnit = $AffiliationUnit.Replace('"', '""')
$query = "$ProfessorName[au] AND `"$escapedUnit`"[ad]"

if ([string]::IsNullOrWhiteSpace($OutputPrefix)) {
    $OutputPrefix = "pubmed_$(Get-Slug $ProfessorName)"
}

Write-Host "=== 教授论文采集（姓名 + 所属单位）开始 ==="
Write-Host "ProfessorName: $ProfessorName"
Write-Host "AffiliationUnit: $AffiliationUnit"
Write-Host "ProfessorQuery: $query"
Write-Host "OutputPrefix: $OutputPrefix"

powershell -ExecutionPolicy Bypass -File "scripts\\bootstrap\\run_professor_collection.ps1" `
    -ProfessorQuery $query `
    -OutputPrefix $OutputPrefix

Write-Host "=== 教授论文采集（姓名 + 所属单位）完成 ==="
