import argparse
import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _weak_label(text: str) -> str:
    low = text.lower()
    if any(k in low for k in ["database", "duckdb", "sql", "etl", "数据仓库", "数据库"]):
        return "数据库开发与应用"
    if any(k in low for k in ["machine learning", "deep learning", "xgboost", "神经网络", "机器学习", "模型训练"]):
        return "机器学习模型训练"
    return ""


def main() -> None:
    p = argparse.ArgumentParser(description="Local weak labeling scaffold inspired by Snorkel rules.")
    p.add_argument("--input-jsonl", required=True)
    p.add_argument("--output-jsonl", default="05_domain_analysis/step_results/snorkel_weak_labels.jsonl")
    args = p.parse_args()

    rows = _read_jsonl(Path(args.input_jsonl))
    out_rows: list[dict[str, Any]] = []
    for r in rows:
        text = f"{r.get('title','')} {r.get('abstract','')} {r.get('project_candidates','')}"
        label = _weak_label(str(text))
        if not label:
            continue
        out_rows.append(
            {
                "paper_id": r.get("paper_id"),
                "weak_label": label,
                "source": "snorkel_style_rule_local",
            }
        )
    out_path = Path(args.output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for row in out_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(str(out_path))


if __name__ == "__main__":
    main()

