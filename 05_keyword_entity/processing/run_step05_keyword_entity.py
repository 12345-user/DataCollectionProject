from __future__ import annotations

import argparse
import json
import re
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


def _text_for_kw(title: str, abstract: str) -> str:
    title = (title or "").strip()
    abstract = (abstract or "").strip()
    if title and abstract:
        return f"{title}\n\n{abstract}"
    return title or abstract


def _safe_slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "unknown"


def main() -> None:
    p = argparse.ArgumentParser(description="Step 05 (baseline): extract keywords/entities/project candidates.")
    p.add_argument("--input", required=True, help="Step04 disambiguated papers JSONL")
    p.add_argument("--output", required=True, help="Output JSONL path")
    p.add_argument("--min-identity-score", type=float, default=0.5, help="Filter papers below this identity_score")
    p.add_argument("--top-n", type=int, default=12, help="Top N keywords")
    p.add_argument("--use-gliner", action="store_true", help="Enable GLiNER entity extraction (may download model)")
    p.add_argument("--gliner-model", default="urchade/gliner_medium-v2.1", help="GLiNER model name")
    p.add_argument("--keybert-model", default="all-MiniLM-L6-v2", help="SentenceTransformer model for KeyBERT")
    args = p.parse_args()

    rows = _read_jsonl(Path(args.input))
    filtered = [r for r in rows if float(r.get("identity_score", 1.0) or 0.0) >= float(args.min_identity_score)]

    # Lazy imports to keep failure messages clearer.
    from keybert import KeyBERT

    kw_model = KeyBERT(model=args.keybert_model)

    gliner = None
    if args.use_gliner:
        try:
            from gliner import GLiNER  # type: ignore

            gliner = GLiNER.from_pretrained(args.gliner_model)
        except Exception as e:
            print(f"[warn] GLiNER 初始化失败，已跳过实体抽取：{e}")
            gliner = None

    out_rows: list[dict[str, Any]] = []
    for r in filtered:
        paper_id = r.get("paper_id") or r.get("pmid") or r.get("doi") or _safe_slug(r.get("title", ""))
        title = r.get("title", "") or ""
        abstract = r.get("abstract", "") or ""
        text = _text_for_kw(title, abstract)

        keywords_scored = kw_model.extract_keywords(
            text,
            keyphrase_ngram_range=(1, 3),
            stop_words="english",
            top_n=int(args.top_n),
        )
        keywords = [k for k, _ in keywords_scored]

        entities: list[dict[str, Any]] = []
        if gliner is not None and text.strip():
            # A small, generic label set; you can extend later.
            labels = ["METHOD", "MODEL", "DATASET", "TOOL", "DISEASE", "CHEMICAL", "GENE", "PROTEIN"]
            try:
                ents = gliner.predict_entities(text, labels)  # type: ignore
                # Normalize shape
                for e in ents or []:
                    entities.append(
                        {
                            "text": e.get("text"),
                            "label": e.get("label"),
                            "score": e.get("score"),
                            "start": e.get("start"),
                            "end": e.get("end"),
                        }
                    )
            except Exception as e:
                print(f"[warn] GLiNER 抽取失败 paper_id={paper_id}：{e}")

        # Baseline "project candidates": merge keywords + high-confidence entities.
        project_candidates = list(dict.fromkeys([*keywords, *[e["text"] for e in entities if (e.get("score") or 0) >= 0.6]]))

        out_rows.append(
            {
                **r,
                "paper_id": paper_id,
                "keywords": keywords,
                "entities": entities,
                "project_candidates": project_candidates,
            }
        )

    _write_jsonl(Path(args.output), out_rows)
    print(args.output)


if __name__ == "__main__":
    main()

