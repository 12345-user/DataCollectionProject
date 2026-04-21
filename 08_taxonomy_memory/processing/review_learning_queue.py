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


def main() -> None:
    p = argparse.ArgumentParser(description="Promote reviewed queue records into learned taxonomy (local-only).")
    p.add_argument("--queue", default="08_taxonomy_memory/step_results/domain_taxonomy_learning_queue.jsonl")
    p.add_argument("--learned", default="08_taxonomy_memory/step_results/domain_taxonomy_learned.jsonl")
    p.add_argument("--approve-keyword", default="", help="Only approve records containing this keyword")
    args = p.parse_args()

    queue_path = Path(args.queue)
    learned_path = Path(args.learned)
    rows = _read_jsonl(queue_path)
    if not rows:
        print("[info] no queue records")
        return

    learned_path.parent.mkdir(parents=True, exist_ok=True)
    approved = 0
    with learned_path.open("a", encoding="utf-8", newline="\n") as f:
        for r in rows:
            kws = [str(x).strip() for x in (r.get("keywords") or []) if str(x).strip()]
            if not kws:
                continue
            if args.approve_keyword and not any(args.approve_keyword in k for k in kws):
                continue
            name = str(r.get("candidate_name") or "").strip() or "综合主题汇总"
            f.write(json.dumps({"name": name, "keywords": kws[:10]}, ensure_ascii=False) + "\n")
            approved += 1
    print(f"[ok] approved into learned taxonomy: {approved}")


if __name__ == "__main__":
    main()

