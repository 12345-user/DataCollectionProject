#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

EXPANDED_PAPERS=""
LAB_INFO=""
TARGET_NAME=""
PREFIX="professor"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --expanded-papers) EXPANDED_PAPERS="${2:-}"; shift 2 ;;
    --lab-info) LAB_INFO="${2:-}"; shift 2 ;;
    --target-name) TARGET_NAME="${2:-}"; shift 2 ;;
    --prefix) PREFIX="${2:-}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$EXPANDED_PAPERS" || -z "$LAB_INFO" || -z "$TARGET_NAME" ]]; then
  echo "Usage: run_steps04_05_06_cloud_glue.sh --expanded-papers <jsonl> --lab-info <json> --target-name <name> [--prefix <prefix>]" >&2
  exit 2
fi

PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python not found: $PYTHON_BIN" >&2
  exit 2
fi

STEP03_OUT="03_author_disambiguation/step_results/${PREFIX}_step03_disambiguated_papers.jsonl"
STEP04_OUT="04_keyword_entity/step_results/${PREFIX}_step04_keyword_entity.jsonl"
STEP05_PAPER_OUT="05_domain_analysis/step_results/${PREFIX}_step05_paper_domains.jsonl"
STEP05_DOMAINS_OUT="05_domain_analysis/step_results/${PREFIX}_step05_domains.json"
STEP05_WORDCLOUD_TERMS_OUT="05_domain_analysis/step_results/${PREFIX}_step05_wordcloud_terms.json"
STEP05_WORDCLOUD_IMAGE_OUT="05_domain_analysis/step_results/${PREFIX}_step05_wordcloud.png"

"$PYTHON_BIN" "03_author_disambiguation/processing/run_step03_author_disambiguation.py" \
  --expanded-papers "$EXPANDED_PAPERS" \
  --lab-info "$LAB_INFO" \
  --target-name "$TARGET_NAME" \
  --output "$STEP03_OUT" \
  --threshold 0.5

"$PYTHON_BIN" "04_keyword_entity/processing/run_step04_keyword_entity.py" \
  --input "$STEP03_OUT" \
  --output "$STEP04_OUT" \
  --min-identity-score 0.5 \
  --top-n 12 \
  --keybert-model "sentence-transformers/all-MiniLM-L6-v2" \
  --local-files-only

"$PYTHON_BIN" "05_domain_analysis/processing/run_step05_domain_analysis.py" \
  --input "$STEP04_OUT" \
  --paper-domains-output "$STEP05_PAPER_OUT" \
  --domains-output "$STEP05_DOMAINS_OUT" \
  --wordcloud-terms-output "$STEP05_WORDCLOUD_TERMS_OUT" \
  --wordcloud-image-output "$STEP05_WORDCLOUD_IMAGE_OUT" \
  --model "sentence-transformers/all-MiniLM-L6-v2" \
  --local-files-only

echo "DONE"
echo "$STEP03_OUT"
echo "$STEP04_OUT"
echo "$STEP05_PAPER_OUT"
echo "$STEP05_DOMAINS_OUT"
echo "$STEP05_WORDCLOUD_TERMS_OUT"
echo "$STEP05_WORDCLOUD_IMAGE_OUT"
