param(
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$venvPath = Join-Path $projectRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

Write-Host "[1/4] 检查 Python $PythonVersion ..."
py "-$PythonVersion" --version | Out-Host

if (-not (Test-Path $venvPath)) {
    Write-Host "[2/4] 创建项目根虚拟环境 .venv ..."
    py "-$PythonVersion" -m venv $venvPath
} else {
    Write-Host "[2/4] 已存在 .venv，直接复用 ..."
}

Write-Host "[3/4] 安装 Step 02-06 依赖 ..."
& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install `
    paperscraper `
    gliner `
    keybert `
    sentence-transformers `
    hdbscan `
    umap-learn `
    scikit-learn `
    pandas `
    pydantic

Write-Host "[4/4] 环境检查 ..."
& $pythonExe -c "import paperscraper, keybert, sentence_transformers, hdbscan, umap, gliner, sklearn, pandas, pydantic; print('python packages ok')"

Write-Host "已取消原 Step03（PDF/GROBID），当前流程为 Step01 -> Step02 -> Step03(原Step04) -> Step04(原Step05) -> Step05(原Step06) -> Step06(原Step07)。"

Write-Host ""
Write-Host "配置模板：shared/config/professor_pipeline.env.example"
Write-Host "输入输出契约：shared/config/professor_pipeline.io.contract.yaml"
