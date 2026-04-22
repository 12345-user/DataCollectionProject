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
    p = argparse.ArgumentParser(description="Discover new topic candidates locally with BERTopic.")
    p.add_argument("--input-jsonl", required=True, help="Step04 or Step05 jsonl with title/abstract fields")
    p.add_argument("--output-json", default="08_taxonomy_memory/step_results/bertopic_candidates.json")
    p.add_argument("--embedding-model", default="sentence-transformers/all-MiniLM-L6-v2")
    p.add_argument("--local-files-only", action="store_true")
    args = p.parse_args()

    rows = _read_jsonl(Path(args.input_jsonl))
    docs = []
    for r in rows:
        title = str(r.get("title") or "").strip()
        abstract = str(r.get("abstract") or "").strip()
        text = f"{title}\n{abstract}".strip()
        if text:
            docs.append(text)
    if len(docs) < 10:
        print("[info] insufficient documents for BERTopic")
        return

    try:
        from bertopic import BERTopic  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as e:
        print(f"[warn] BERTopic dependencies unavailable, skip discovery: {e}")
        return

    emb = SentenceTransformer(args.embedding_model, local_files_only=bool(args.local_files_only))
    topic_model = BERTopic(embedding_model=emb, calculate_probabilities=False, verbose=False)
    topics, _ = topic_model.fit_transform(docs)
    info = topic_model.get_topic_info()
    out = {
        "topic_count": int(len(set([t for t in topics if int(t) >= 0]))),
        "topics": info.to_dict(orient="records"),
    }
    out_path = Path(args.output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()

