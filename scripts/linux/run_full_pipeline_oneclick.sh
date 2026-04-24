#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

PROFESSOR_NAME=""
SEED_PAPER_TITLE=""
SEED_PMID=""
OUTPUT_PREFIX=""
SKIP_ARXIV=true
NO_START_WEB=false
WEB_PORT=8502
EXTRA_SOURCE_URLS=()
ENABLE_SETFIT=false
ENABLE_BERTOPIC=false
ENABLE_SNORKEL=false
ENABLE_TAG_LEARNING=false
LOCAL_FILES_ONLY=false

slug() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g; s/^_+|_+$//g'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --professor-name) PROFESSOR_NAME="${2:-}"; shift 2 ;;
    --seed-paper-title) SEED_PAPER_TITLE="${2:-}"; shift 2 ;;
    --seed-pmid) SEED_PMID="${2:-}"; shift 2 ;;
    --output-prefix) OUTPUT_PREFIX="${2:-}"; shift 2 ;;
    --skip-arxiv) SKIP_ARXIV=true; shift ;;
    --no-skip-arxiv) SKIP_ARXIV=false; shift ;;
    --no-start-web) NO_START_WEB=true; shift ;;
    --web-port) WEB_PORT="${2:-8502}"; shift 2 ;;
    --extra-source-url) EXTRA_SOURCE_URLS+=("${2:-}"); shift 2 ;;
    --enable-setfit) ENABLE_SETFIT=true; shift ;;
    --enable-bertopic) ENABLE_BERTOPIC=true; shift ;;
    --enable-snorkel) ENABLE_SNORKEL=true; shift ;;
    --enable-tag-learning) ENABLE_TAG_LEARNING=true; shift ;;
    --local-files-only) LOCAL_FILES_ONLY=true; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$PROFESSOR_NAME" || -z "$SEED_PAPER_TITLE" ]]; then
  echo "Usage: run_full_pipeline_oneclick.sh --professor-name <name> --seed-paper-title <title> [options]" >&2
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

STEP02_OUT="02_paper_list_extend/step_results/${OUTPUT_PREFIX}_expanded_papers.jsonl"
LAB_INFO="01_data_collection/step_results/professor_lab_info/${OUTPUT_PREFIX}_lab_info.json"
STEP05_PAPER_OUT="06_domain_clustering/step_results/${OUTPUT_PREFIX}_step05_paper_domains.jsonl"
TIMELINE_OUT="07_temporal_analysis/step_results/${OUTPUT_PREFIX}_step06_project_timeline.json"
ALLOCATION_OUT="07_temporal_analysis/step_results/${OUTPUT_PREFIX}_step06_effort_allocation.json"
REPORT_OUT="07_temporal_analysis/step_results/${OUTPUT_PREFIX}_step06_trend_report.md"
DUCKDB_PATH="07_temporal_analysis/step_results/pipeline.duckdb"
STEP09_JSON="09_quality_guard/step_results/${OUTPUT_PREFIX}_step09_quality_report.json"
STEP09_MD="09_quality_guard/step_results/${OUTPUT_PREFIX}_step09_quality_report.md"
STEP04_OUT="05_keyword_entity/step_results/${OUTPUT_PREFIX}_step04_keyword_entity.jsonl"
SETFIT_MODEL_DIR="08_taxonomy_memory/models/setfit_local"
BERTOPIC_OUT="08_taxonomy_memory/step_results/${OUTPUT_PREFIX}_bertopic_candidates.json"
SNORKEL_OUT="08_taxonomy_memory/step_results/${OUTPUT_PREFIX}_snorkel_weak_labels.jsonl"
QUEUE_OUT="08_taxonomy_memory/step_results/domain_taxonomy_learning_queue.jsonl"
TAX_REPORT_OUT="08_taxonomy_memory/step_results/domain_taxonomy_report.json"
QUEUE_L2_OUT="08_taxonomy_memory/step_results/learning_queue_l2.jsonl"
QUEUE_L3_OUT="08_taxonomy_memory/step_results/learning_queue_l3.jsonl"
LEARNED_L2_OUT="08_taxonomy_memory/step_results/learned_l2.jsonl"
LEARNED_L3_OUT="08_taxonomy_memory/step_results/learned_l3.jsonl"
TAG_REPORT_OUT="08_taxonomy_memory/step_results/tag_report.json"

echo "=== 一键全流程开始（Linux/Ubuntu22.04）==="
echo "ProfessorName: $PROFESSOR_NAME"
echo "SeedPaperTitle: $SEED_PAPER_TITLE"
echo "SeedPMID: $SEED_PMID"
echo "OutputPrefix: $OUTPUT_PREFIX"

STEP01_ARGS=(
  "scripts/linux/run_professor_collection_simple.sh"
  "--professor-name" "$PROFESSOR_NAME"
  "--seed-paper-title" "$SEED_PAPER_TITLE"
  "--output-prefix" "$OUTPUT_PREFIX"
)
if [[ -n "$SEED_PMID" ]]; then
  STEP01_ARGS+=("--seed-pmid" "$SEED_PMID")
fi
for u in "${EXTRA_SOURCE_URLS[@]}"; do
  STEP01_ARGS+=("--extra-url" "$u")
done
bash "${STEP01_ARGS[@]}"

STEP02_ARGS=(
  "02_paper_list_extend/processing/run_step02_paper_list_extend_paperscraper.py"
  "--professor-name" "$PROFESSOR_NAME"
  "--step01-output-prefix" "$OUTPUT_PREFIX"
  "--output-prefix" "$OUTPUT_PREFIX"
  "--server-dump-dir" "02_paper_list_extend/data_sources/paperscraper_server_dumps/server_dumps"
)
if [[ "$SKIP_ARXIV" == "true" ]]; then
  STEP02_ARGS+=("--skip-arxiv")
fi
"$PYTHON_BIN" "${STEP02_ARGS[@]}"

bash "scripts/linux/run_steps04_05_06_cloud_glue.sh" \
  --expanded-papers "$STEP02_OUT" \
  --lab-info "$LAB_INFO" \
  --target-name "$PROFESSOR_NAME" \
  --prefix "$OUTPUT_PREFIX"

"$PYTHON_BIN" "07_temporal_analysis/processing/run_step07_temporal_analysis.py" \
  --input "$STEP05_PAPER_OUT" \
  --timeline-output "$TIMELINE_OUT" \
  --allocation-output "$ALLOCATION_OUT" \
  --report-output "$REPORT_OUT"

"$PYTHON_BIN" "07_temporal_analysis/processing/build_step07_duckdb.py" \
  --professor "$OUTPUT_PREFIX" \
  --paper-domains "$STEP05_PAPER_OUT" \
  --duckdb-path "$DUCKDB_PATH"

"$PYTHON_BIN" "09_quality_guard/processing/run_step09_quality_guard.py" \
  --prefix "$OUTPUT_PREFIX" \
  --output-json "$STEP09_JSON" \
  --output-md "$STEP09_MD"

if [[ "$ENABLE_SETFIT" == "true" ]]; then
  SETFIT_ARGS=(
    "08_taxonomy_memory/processing/train_setfit_local.py"
    "--train-jsonl" "08_taxonomy_memory/step_results/domain_taxonomy_learned.jsonl"
    "--output-dir" "$SETFIT_MODEL_DIR"
  )
  [[ "$LOCAL_FILES_ONLY" == "true" ]] && SETFIT_ARGS+=("--local-files-only")
  "$PYTHON_BIN" "${SETFIT_ARGS[@]}"
fi

if [[ "$ENABLE_BERTOPIC" == "true" ]]; then
  BERTOPIC_ARGS=(
    "08_taxonomy_memory/processing/discover_bertopic_local.py"
    "--input-jsonl" "$STEP04_OUT"
    "--output-json" "$BERTOPIC_OUT"
  )
  [[ "$LOCAL_FILES_ONLY" == "true" ]] && BERTOPIC_ARGS+=("--local-files-only")
  "$PYTHON_BIN" "${BERTOPIC_ARGS[@]}"
fi

if [[ "$ENABLE_SNORKEL" == "true" ]]; then
  "$PYTHON_BIN" "08_taxonomy_memory/processing/snorkel_labeling_local.py" \
    --input-jsonl "$STEP04_OUT" \
    --output-jsonl "$SNORKEL_OUT"
  "$PYTHON_BIN" "08_taxonomy_memory/processing/merge_weak_labels_to_queue.py" \
    --weak-labels-jsonl "$SNORKEL_OUT" \
    --step04-jsonl "$STEP04_OUT" \
    --queue-jsonl "$QUEUE_OUT"
  "$PYTHON_BIN" "08_taxonomy_memory/processing/build_taxonomy_report.py" \
    --queue "$QUEUE_OUT" \
    --learned "08_taxonomy_memory/step_results/domain_taxonomy_learned.jsonl" \
    --output "$TAX_REPORT_OUT"
fi

if [[ "$ENABLE_TAG_LEARNING" == "true" ]]; then
  "$PYTHON_BIN" "08_taxonomy_memory/processing/extract_tag_candidates.py" \
    --input-jsonl "$STEP04_OUT" \
    --output-l2 "$QUEUE_L2_OUT" \
    --output-l3 "$QUEUE_L3_OUT"
  "$PYTHON_BIN" "08_taxonomy_memory/processing/build_tag_report.py" \
    --queue-l2 "$QUEUE_L2_OUT" \
    --queue-l3 "$QUEUE_L3_OUT" \
    --learned-l2 "$LEARNED_L2_OUT" \
    --learned-l3 "$LEARNED_L3_OUT" \
    --output "$TAG_REPORT_OUT"
fi

SOURCE_META_PATH="07_temporal_analysis/step_results/${OUTPUT_PREFIX}_source_sites.json"
"$PYTHON_BIN" - "$SOURCE_META_PATH" "$OUTPUT_PREFIX" "${EXTRA_SOURCE_URLS[@]}" <<'PY'
import json, sys
from datetime import datetime
out_path = sys.argv[1]
prefix = sys.argv[2]
urls = sys.argv[3:]
obj = {
    "professor": prefix,
    "input_extra_urls": urls,
    "generated_at": datetime.now().isoformat(timespec="seconds"),
}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(obj, f, ensure_ascii=False, indent=2)
PY

if [[ "$NO_START_WEB" == "false" ]]; then
  echo "启动网页：http://localhost:${WEB_PORT}"
  "$PYTHON_BIN" -m streamlit run "07_temporal_analysis/app/streamlit_app.py" --server.port "$WEB_PORT" --server.headless true
fi

echo "=== 一键全流程完成 ==="
echo "Step02 Output: $STEP02_OUT"
echo "Step05 PaperDomains: $STEP05_PAPER_OUT"
echo "Step06 Timeline: $TIMELINE_OUT"
echo "Step06 Allocation: $ALLOCATION_OUT"
echo "Step06 Report: $REPORT_OUT"
echo "DuckDB: $DUCKDB_PATH"
echo "SourceSitesMeta: $SOURCE_META_PATH"
echo "Step09 Quality JSON: $STEP09_JSON"
echo "Step09 Quality MD: $STEP09_MD"
