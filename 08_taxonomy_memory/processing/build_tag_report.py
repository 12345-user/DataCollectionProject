import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Build layered tag memory report.")
    p.add_argument("--queue-l2", default="08_taxonomy_memory/step_results/learning_queue_l2.jsonl")
    p.add_argument("--queue-l3", default="08_taxonomy_memory/step_results/learning_queue_l3.jsonl")
    p.add_argument("--learned-l2", default="08_taxonomy_memory/step_results/learned_l2.jsonl")
    p.add_argument("--learned-l3", default="08_taxonomy_memory/step_results/learned_l3.jsonl")
    p.add_argument("--output", default="08_taxonomy_memory/step_results/tag_report.json")
    args = p.parse_args()

    q2 = _read_jsonl(Path(args.queue_l2))
    q3 = _read_jsonl(Path(args.queue_l3))
    l2 = _read_jsonl(Path(args.learned_l2))
    l3 = _read_jsonl(Path(args.learned_l3))

    c2 = Counter([str(x.get("candidate_name") or x.get("name") or "").strip() for x in q2 if str(x.get("candidate_name") or x.get("name") or "").strip()])
    c3 = Counter([str(x.get("candidate_name") or x.get("name") or "").strip() for x in q3 if str(x.get("candidate_name") or x.get("name") or "").strip()])

    out = {
        "queue_l2_count": len(q2),
        "queue_l3_count": len(q3),
        "learned_l2_count": len(l2),
        "learned_l3_count": len(l3),
        "top_queue_l2": [{"tag": k, "count": v} for k, v in c2.most_common(20)],
        "top_queue_l3": [{"tag": k, "count": v} for k, v in c3.most_common(20)],
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()

