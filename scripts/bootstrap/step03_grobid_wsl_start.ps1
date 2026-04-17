param(
  [string]$Distro = "Ubuntu-24.04",
  [string]$GrobidDir = "~/grobid",
  [int]$Port = 8070
)

$ErrorActionPreference = "Stop"

function Invoke-Wsl([string]$cmd) {
  wsl -d $Distro -u root -e sh -lc $cmd
  if ($LASTEXITCODE -ne 0) { throw "WSL command failed: $cmd" }
}

Write-Host "[step03] Ensure WSL distro exists..."
$list = (wsl -l -q | ForEach-Object { $_.Trim() }) | Where-Object { $_ -ne "" }
if ($list -notcontains $Distro) {
  throw "WSL distro not found: $Distro. Please install it first (e.g. from Microsoft Store), then re-run."
}

Write-Host "[step03] Installing prerequisites in WSL (git, JRE 17)..."
Invoke-Wsl "apt-get update -y"
Invoke-Wsl "apt-get install -y git"
Invoke-Wsl "if command -v java >/dev/null 2>&1; then java -version >/dev/null 2>&1; elif apt-cache show openjdk-21-jre-headless >/dev/null 2>&1; then apt-get install -y openjdk-21-jre-headless; elif apt-cache show openjdk-17-jre-headless >/dev/null 2>&1; then apt-get install -y openjdk-17-jre-headless; else apt-get install -y default-jre-headless; fi"

Write-Host "[step03] Preparing GROBID repo in WSL..."
Invoke-Wsl "if [ ! -d $GrobidDir/.git ]; then rm -rf $GrobidDir; git clone https://github.com/kermitt2/grobid.git $GrobidDir; else cd $GrobidDir && git fetch --all -p; fi"

Write-Host "[step03] Starting GROBID server in background (WSL)..."
Invoke-Wsl "cd $GrobidDir && nohup ./gradlew run > grobid_run.log 2>&1 &"

Write-Host "[step03] Waiting for http://localhost:$Port/api/isalive ..."
for ($i = 0; $i -lt 60; $i++) {
  try {
    $r = Invoke-WebRequest "http://localhost:$Port/api/isalive" -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) {
      Write-Host "[step03] OK: GROBID is alive."
      exit 0
    }
  } catch {
    Start-Sleep -Seconds 2
  }
}

throw "GROBID did not become ready on port $Port. Check WSL log: $GrobidDir/grobid_run.log"
