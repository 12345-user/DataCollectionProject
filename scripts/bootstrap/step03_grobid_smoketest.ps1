param(
  [string]$SamplePdfUrl = "https://arxiv.org/pdf/1706.03762.pdf",
  [string]$SamplePdfName = "sample_arxiv_1706_03762.pdf",
  [string]$Distro = "Debian"
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $projectRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  # Docker is no longer used for Step03; keep script fully local/WSL.
}

Write-Host "[1/4] Ensure GROBID server is running (WSL local)..."
$starter = Join-Path $projectRoot "scripts\\bootstrap\\step03_grobid_wsl_start.ps1"
if (Test-Path $starter) {
  powershell -NoProfile -ExecutionPolicy Bypass -File $starter -Distro $Distro | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to start GROBID in WSL. See output above."
  }
} else {
  throw "Missing starter script: $starter"
}

Write-Host "[2/4] Check service liveness..."
$alive = Invoke-WebRequest "http://localhost:8070/api/isalive" -UseBasicParsing
Write-Host $alive.StatusCode

Write-Host "[3/4] Download sample PDF..."
$pdfDir = "03_pdf_parsing/data_sources/pdf_cache"
New-Item -ItemType Directory -Force -Path $pdfDir | Out-Null
$pdfPath = Join-Path $pdfDir $SamplePdfName
Invoke-WebRequest $SamplePdfUrl -OutFile $pdfPath -UseBasicParsing

Write-Host "[4/4] Run Step03 parsing script..."
$out = "03_pdf_parsing/step_results/step03_smoketest_parsed.jsonl"
& ".\\.venv\\Scripts\\python.exe" "03_pdf_parsing/processing/run_step03_pdf_parsing_grobid.py" `
  --pdf-dir "$pdfDir" `
  --output-jsonl "$out"

Write-Host ("OK: " + $out)

