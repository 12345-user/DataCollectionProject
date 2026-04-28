import argparse
import json
from collections import defaultdict
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


def _existing_keys(rows: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for r in rows:
        name = str(r.get("candidate_name") or "").strip()
        kws = [str(x).strip() for x in (r.get("keywords") or []) if str(x).strip()]
        if not name or not kws:
            continue
        keys.add(f"{name}||{'|'.join(sorted(set(kws)))}")
    return keys


def main() -> None:
    p = argparse.ArgumentParser(description="Merge Snorkel weak labels into taxonomy learning queue.")
    p.add_argument("--weak-labels-jsonl", required=True)
    p.add_argument("--step04-jsonl", required=True)
    p.add_argument("--queue-jsonl", default="05_domain_analysis/step_results/domain_taxonomy_learning_queue.jsonl")
    args = p.parse_args()

    weak_rows = _read_jsonl(Path(args.weak_labels_jsonl))
    s4_rows = _read_jsonl(Path(args.step04_jsonl))
    queue_path = Path(args.queue_jsonl)
    queue_rows = _read_jsonl(queue_path)
    exists = _existing_keys(queue_rows)

    by_pid: dict[str, dict[str, Any]] = {}
    for r in s4_rows:
        pid = str(r.get("paper_id") or "").strip()
        if pid:
            by_pid[pid] = r

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in weak_rows:
        label = str(r.get("weak_label") or "").strip()
        pid = str(r.get("paper_id") or "").strip()
        if label and pid in by_pid:
            grouped[label].append(by_pid[pid])

    new_records: list[dict[str, Any]] = []
    for label, papers in grouped.items():
        kw_counter: dict[str, int] = defaultdict(int)
        titles: list[str] = []
        for p_row in papers:
            for kw in (p_row.get("keywords") or [])[:8]:
                k = str(kw).strip()
                if k:
                    kw_counter[k] += 1
            t = str(p_row.get("title") or "").strip()
            if t:
                titles.append(t)
        top_kws = [k for k, _ in sorted(kw_counter.items(), key=lambda x: x[1], reverse=True)[:10]]
        if not top_kws:
            continue
        rec = {
            "domain_label": "snorkel_bootstrap",
            "candidate_name": label,
            "keywords": top_kws,
            "evidence_titles": titles[:5],
            "source": "snorkel_weak_merge",
        }
        key = f"{label}||{'|'.join(sorted(set(top_kws)))}"
        if key in exists:
            continue
        exists.add(key)
        new_records.append(rec)

    if not new_records:
        print("[info] no new queue records from weak labels")
        return

    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8", newline="\n") as f:
        for rec in new_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[ok] appended queue records: {len(new_records)}")


if __name__ == "__main__":
    main()

