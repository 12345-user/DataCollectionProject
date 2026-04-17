param(
    [switch]$RunCrewAI,
    [switch]$StartMCP
)

$ErrorActionPreference = "Stop"

Write-Host "=== Step 01 一键执行开始 ==="

$projectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $projectRoot

$localCrawler = Join-Path $projectRoot "01_data_collection\processing\web_crawler_local\run_local_crawl.py"
if (-not (Test-Path $localCrawler)) {
    throw "未找到本地爬虫脚本: $localCrawler"
}

Write-Host "[1/3] 执行本地爬虫..."
python $localCrawler

if ($RunCrewAI) {
    Write-Host "[2/3] 执行 CrewAI..."
    $crewDir = Join-Path $projectRoot "01_data_collection\processing\crewai_scheduler\data_collection_orchestrator"
    $crewPython = Join-Path $projectRoot "01_data_collection\processing\crewai_scheduler\runtime\.venv\Scripts\python.exe"

    if (-not (Test-Path $crewDir)) {
        throw "未找到 CrewAI 目录: $crewDir"
    }
    if (-not (Test-Path $crewPython)) {
        throw "未找到 CrewAI Python 运行时: $crewPython"
    }

    Push-Location $crewDir
    try {
        & $crewPython -m src.data_collection_orchestrator.main
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "[2/3] 跳过 CrewAI（未传入 -RunCrewAI）"
}

if ($StartMCP) {
    Write-Host "[3/3] 启动 Bright Data MCP..."
    $mcpDir = Join-Path $projectRoot "01_data_collection\processing\brightdata_mcp_connector\service"
    if (-not (Test-Path $mcpDir)) {
        throw "未找到 Bright Data MCP 目录: $mcpDir"
    }

    Push-Location $mcpDir
    try {
        npm run mcp:start:research
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "[3/3] 跳过 MCP 启动（未传入 -StartMCP）"
}

Write-Host "=== Step 01 一键执行完成 ==="
