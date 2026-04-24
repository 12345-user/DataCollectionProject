#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  build-essential \
  git \
  curl

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip

if [[ -f "requirements.txt" ]]; then
  python -m pip install -r requirements.txt
else
  python -m pip install streamlit duckdb pandas plotly numpy scikit-learn statsmodels pyyaml requests lxml
fi

chmod +x scripts/linux/*.sh
echo "Ubuntu 22.04 setup done."
echo "Run pipeline: bash scripts/linux/run_full_pipeline_oneclick.sh --professor-name \"<name>\" --seed-paper-title \"<title>\" --no-start-web"
