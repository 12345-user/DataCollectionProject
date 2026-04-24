#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

PROFESSOR_NAME=""
SEED_PAPER_TITLE=""
SEED_PMID=""
OUTPUT_PREFIX=""
EXTRA_URLS=()

slug() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g; s/^_+|_+$//g'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --professor-name) PROFESSOR_NAME="${2:-}"; shift 2 ;;
    --seed-paper-title) SEED_PAPER_TITLE="${2:-}"; shift 2 ;;
    --seed-pmid) SEED_PMID="${2:-}"; shift 2 ;;
    --output-prefix) OUTPUT_PREFIX="${2:-}"; shift 2 ;;
    --extra-url) EXTRA_URLS+=("${2:-}"); shift 2 ;;
    *) EXTRA_URLS+=("$1"); shift ;;
  esac
done

if [[ -z "$PROFESSOR_NAME" || -z "$SEED_PAPER_TITLE" ]]; then
  echo "Usage: run_professor_collection_simple.sh --professor-name <name> --seed-paper-title <title> [--seed-pmid <pmid>] [--output-prefix <prefix>] [--extra-url <url> ...]" >&2
  exit 2
fi

if [[ -z "$OUTPUT_PREFIX" ]]; then
  OUTPUT_PREFIX="pubmed_$(slug "$PROFESSOR_NAME")"
fi

PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python not found: $PYTHON_BIN" >&2
  exit 2
fi

SEED_JSON_FILE="$(mktemp)"
trap 'rm -f "$SEED_JSON_FILE"' EXIT

RESOLVER_ARGS=(
  "01_data_collection/processing/lab_paper_tools/resolve_seed_to_affiliation_keywords.py"
  "--professor-name" "$PROFESSOR_NAME"
  "--seed-title" "$SEED_PAPER_TITLE"
)
if [[ -n "$SEED_PMID" ]]; then
  RESOLVER_ARGS+=("--seed-pmid" "$SEED_PMID")
fi
"$PYTHON_BIN" "${RESOLVER_ARGS[@]}" > "$SEED_JSON_FILE"

mapfile -t RESOLVED < <(
  "$PYTHON_BIN" - "$SEED_JSON_FILE" "$PROFESSOR_NAME" <<'PY'
import json, re, sys
from pathlib import Path
seed = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
prof = sys.argv[2]
unit = str(seed.get("affiliation_unit_for_ad") or "")
kws = [str(x).strip() for x in (seed.get("affiliation_keywords") or []) if str(x).strip()]
aff_kw = ",".join(kws)
tokens = [t.strip() for t in re.split(r"\s+", unit) if len(t.strip()) > 2]
tokens = [re.sub(r"[^\w\-]+", "", t) for t in tokens]
stop = {"and","or","of","the","a","an","in","on","for","to","with","without","under","by"}
tokens = [t for t in tokens if t and t.lower() not in stop]
if tokens:
    ad_expr = " AND ".join(f"{t}[ad]" for t in tokens)
    query = f"{prof}[au] AND ({ad_expr})"
else:
    query = f"{prof}[au]"
print(query)
print(aff_kw)
print(unit)
PY
)

PROFESSOR_QUERY="${RESOLVED[0]:-}"
AFFILIATION_KEYWORDS="${RESOLVED[1]:-}"
AFFILIATION_UNIT_FOR_AD="${RESOLVED[2]:-}"

echo "=== 教授论文采集（Linux版）==="
echo "ProfessorName: $PROFESSOR_NAME"
echo "SeedPaperTitle: $SEED_PAPER_TITLE"
echo "SeedPMID: $SEED_PMID"
echo "AffiliationUnitForAd: $AFFILIATION_UNIT_FOR_AD"
echo "OutputPrefix: $OUTPUT_PREFIX"
echo "ProfessorQuery: $PROFESSOR_QUERY"

"$PYTHON_BIN" "01_data_collection/processing/lab_paper_tools/fetch_pubmed_titles.py" \
  --query "$PROFESSOR_QUERY" \
  --output-prefix "$OUTPUT_PREFIX"

TITLES_JSON="01_data_collection/step_results/professor_paper_titles/${OUTPUT_PREFIX}_titles.json"
"$PYTHON_BIN" "01_data_collection/processing/lab_paper_tools/fetch_pubmed_abstracts.py" \
  --titles-json "$TITLES_JSON" \
  --output-prefix "$OUTPUT_PREFIX"

"$PYTHON_BIN" "01_data_collection/processing/lab_paper_tools/extract_lab_info_from_pubmed.py" \
  --titles-json "$TITLES_JSON" \
  --output-prefix "$OUTPUT_PREFIX"

if [[ -n "$AFFILIATION_KEYWORDS" ]]; then
  "$PYTHON_BIN" "01_data_collection/processing/lab_paper_tools/extract_lab_info_from_pubmed.py" \
    --titles-json "$TITLES_JSON" \
    --output-prefix "$OUTPUT_PREFIX" \
    --affiliation-keywords "$AFFILIATION_KEYWORDS"
fi

TARGET_DIR="02_paper_list_extend/data_sources/from_step01/$OUTPUT_PREFIX"
mkdir -p "$TARGET_DIR"
[[ -f "01_data_collection/step_results/professor_paper_titles/${OUTPUT_PREFIX}_titles.json" ]] && cp -f "01_data_collection/step_results/professor_paper_titles/${OUTPUT_PREFIX}_titles.json" "$TARGET_DIR/titles.json"
[[ -f "01_data_collection/step_results/professor_paper_abstracts/${OUTPUT_PREFIX}_abstracts.json" ]] && cp -f "01_data_collection/step_results/professor_paper_abstracts/${OUTPUT_PREFIX}_abstracts.json" "$TARGET_DIR/abstracts.json"
[[ -f "01_data_collection/step_results/professor_paper_abstracts/${OUTPUT_PREFIX}_abstracts.jsonl" ]] && cp -f "01_data_collection/step_results/professor_paper_abstracts/${OUTPUT_PREFIX}_abstracts.jsonl" "$TARGET_DIR/abstracts.jsonl"
[[ -f "01_data_collection/step_results/professor_lab_info/${OUTPUT_PREFIX}_lab_info.json" ]] && cp -f "01_data_collection/step_results/professor_lab_info/${OUTPUT_PREFIX}_lab_info.json" "$TARGET_DIR/lab_info.json"

if [[ ${#EXTRA_URLS[@]} -gt 0 ]]; then
  CRAWL_FILE="01_data_collection/processing/web_crawler_local/crawl_urls.txt"
  : > "$CRAWL_FILE"
  for u in "${EXTRA_URLS[@]}"; do
    [[ -n "${u// }" ]] && printf '%s\n' "$u" >> "$CRAWL_FILE"
  done
  "$PYTHON_BIN" "01_data_collection/processing/web_crawler_local/run_local_crawl.py"
fi

echo "Bridge completed: $TARGET_DIR"
echo "=== 教授论文采集完成 ==="
