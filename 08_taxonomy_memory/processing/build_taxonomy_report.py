import argparse
import json
from collections import Counter
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


def main() -> None:
    p = argparse.ArgumentParser(description="Build local taxonomy memory report.")
    p.add_argument("--queue", default="08_taxonomy_memory/step_results/domain_taxonomy_learning_queue.jsonl")
    p.add_argument("--learned", default="08_taxonomy_memory/step_results/domain_taxonomy_learned.jsonl")
    p.add_argument("--output", default="08_taxonomy_memory/step_results/domain_taxonomy_report.json")
    args = p.parse_args()

    queue_rows = _read_jsonl(Path(args.queue))
    learned_rows = _read_jsonl(Path(args.learned))
    kw_counter = Counter()
    for r in queue_rows:
        for kw in r.get("keywords", []) or []:
            kw_counter[str(kw)] += 1
    report: dict[str, Any] = {
        "queue_count": len(queue_rows),
        "learned_count": len(learned_rows),
        "top_queue_keywords": [{"keyword": k, "count": c} for k, c in kw_counter.most_common(20)],
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()

