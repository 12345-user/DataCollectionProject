from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Step 06 (baseline): embed + cluster into domains.")
    p.add_argument("--input", required=True, help="Step05 keyword_entity JSONL")
    p.add_argument("--paper-domains-output", required=True, help="Output JSONL: per-paper domain label")
    p.add_argument("--domains-output", required=True, help="Output JSON: domain summaries")
    p.add_argument("--embedding-model", default="sentence-transformers/all-MiniLM-L6-v2", help="Embedding model name")
    p.add_argument("--min-cluster-size", type=int, default=3)
    p.add_argument("--min-samples", type=int, default=1)
    args = p.parse_args()

    rows = _read_jsonl(Path(args.input))
    texts: list[str] = []
    paper_ids: list[str] = []
    meta: list[dict[str, Any]] = []
    for r in rows:
        paper_id = str(r.get("paper_id") or "")
        title = (r.get("title") or "").strip()
        abstract = (r.get("abstract") or "").strip()
        pub_date = (r.get("pub_date") or "").strip() if isinstance(r.get("pub_date"), str) else (r.get("pub_date") or "")
        identity_score = float(r.get("identity_score", 1.0) or 1.0)
        kws = r.get("keywords") or []
        ents = r.get("entities") or []
        extra = " ".join([*(kws if isinstance(kws, list) else []), *[e.get("text", "") for e in ents if isinstance(e, dict)]])
        text = "\n\n".join([x for x in [title, abstract, extra] if x])
        paper_ids.append(paper_id)
        texts.append(text)
        meta.append(
            {
                "paper_id": paper_id,
                "pub_date": pub_date,
                "identity_score": identity_score,
                "title": title,
            }
        )

    from sentence_transformers import SentenceTransformer
    import numpy as np
    import hdbscan

    model = SentenceTransformer(args.embedding_model)
    emb = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    emb = np.asarray(emb)

    clusterer = hdbscan.HDBSCAN(min_cluster_size=int(args.min_cluster_size), min_samples=int(args.min_samples))
    labels = clusterer.fit_predict(emb)
    probs = getattr(clusterer, "probabilities_", None)

    paper_domains: list[dict[str, Any]] = []
    domains: dict[str, Any] = {}

    for idx, (paper_id, label) in enumerate(zip(paper_ids, labels)):
        prob = float(probs[idx]) if probs is not None else 1.0
        domain_label = f"domain_{label}" if label >= 0 else "domain_noise"
        m = meta[idx]
        paper_domains.append(
            {
                "paper_id": paper_id,
                "domain_label": domain_label,
                "domain_confidence": round(prob, 4),
                "pub_date": m.get("pub_date", ""),
                "identity_score": m.get("identity_score", 1.0),
                "title": m.get("title", ""),
            }
        )
        domains.setdefault(domain_label, {"domain_label": domain_label, "paper_ids": [], "count": 0})
        domains[domain_label]["paper_ids"].append(paper_id)
        domains[domain_label]["count"] += 1

    _write_jsonl(Path(args.paper_domains_output), paper_domains)
    _write_json(Path(args.domains_output), {"domains": sorted(domains.values(), key=lambda d: (-d["count"], d["domain_label"]))})
    print(args.paper_domains_output)
    print(args.domains_output)


if __name__ == "__main__":
    main()

