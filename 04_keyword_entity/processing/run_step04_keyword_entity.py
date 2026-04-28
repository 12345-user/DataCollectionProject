import argparse
import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from keybert import KeyBERT
from sentence_transformers import SentenceTransformer
from huggingface_hub import snapshot_download


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _safe_slug(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[^a-z0-9]+", "_", t)
    t = re.sub(r"_+", "_", t).strip("_")
    return t or "unknown"


def _text_for_kw(title: str, abstract: str) -> str:
    return f"{title}\n{abstract}".strip()


def _parse_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


def _calc_quality_score(row: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    title = str(row.get("title") or "")
    abstract = str(row.get("abstract") or "")
    pub_date = _parse_date(str(row.get("pub_date") or ""))
    venue = str(row.get("venue") or "").strip()
    source = str(row.get("source") or "").strip().lower()
    doi = str(row.get("doi") or "").strip()
    citation_raw = row.get("citation_count")

    citation_count = 0.0
    try:
        if citation_raw not in ("", None):
            citation_count = max(0.0, float(citation_raw))
    except Exception:
        citation_count = 0.0

    # Scoring in [0,1]: local and deterministic.
    abstract_score = min(1.0, len(abstract) / 2000.0)
    doi_score = 1.0 if doi else 0.0
    citation_score = min(1.0, math.log1p(citation_count) / math.log1p(200.0))

    source_weight = {
        "pubmed": 1.0,
        "arxiv": 0.75,
        "biorxiv": 0.65,
        "medrxiv": 0.65,
        "chemrxiv": 0.65,
    }.get(source, 0.6)

    recency_score = 0.5
    if pub_date is not None:
        age_days = max(0, (date.today() - pub_date).days)
        # Newer papers should not dominate; keep gentle decay.
        recency_score = math.exp(-age_days / 3650.0)

    venue_bonus = 1.0 if venue else 0.0
    title_score = 1.0 if len(title) >= 20 else min(1.0, len(title) / 20.0)

    quality = (
        0.30 * citation_score
        + 0.20 * doi_score
        + 0.20 * source_weight
        + 0.15 * recency_score
        + 0.10 * abstract_score
        + 0.03 * venue_bonus
        + 0.02 * title_score
    )
    quality = max(0.0, min(1.0, quality))
    evidence = {
        "citation_count": citation_count,
        "citation_score": round(citation_score, 6),
        "doi_score": doi_score,
        "source_weight": source_weight,
        "recency_score": round(recency_score, 6),
        "abstract_score": round(abstract_score, 6),
        "venue_bonus": venue_bonus,
        "title_score": round(title_score, 6),
    }
    return round(quality, 6), evidence


def _resolve_st_model_path(model_name_or_path: str, local_files_only: bool) -> str:
    # If user passed a local path, use it directly.
    p = Path(model_name_or_path)
    if p.exists():
        return str(p)
    # Otherwise, resolve to the local HF cache snapshot path.
    # This avoids extra network HEAD calls during model init.
    return snapshot_download(repo_id=model_name_or_path, local_files_only=bool(local_files_only))


def main() -> None:
    p = argparse.ArgumentParser(description="Step05 glue: KeyBERT keyword extraction + optional GLiNER entities.")
    p.add_argument("--input", required=True, help="Step04 disambiguated papers JSONL")
    p.add_argument("--output", required=True, help="Output JSONL path")
    p.add_argument("--min-identity-score", type=float, default=0.5)
    p.add_argument("--top-n", type=int, default=12)
    p.add_argument("--keybert-model", default="all-MiniLM-L6-v2")
    p.add_argument(
        "--local-files-only",
        action="store_true",
        help="Only use locally cached HuggingFace files (avoid network).",
    )
    p.add_argument("--use-gliner", action="store_true")
    p.add_argument("--gliner-model", default="urchade/gliner_medium-v2.1")
    args = p.parse_args()

    rows = _read_jsonl(Path(args.input))
    filtered = [r for r in rows if float(r.get("identity_score", 1.0) or 0.0) >= float(args.min_identity_score)]

    st_path = _resolve_st_model_path(str(args.keybert_model), bool(args.local_files_only))
    st_model = SentenceTransformer(st_path)
    kw_model = KeyBERT(model=st_model)

    gliner = None
    if args.use_gliner:
        try:
            from gliner import GLiNER

            gliner = GLiNER.from_pretrained(args.gliner_model)
        except Exception as e:
            print(f"[warn] GLiNER disabled: {e}")

    out_rows: list[dict[str, Any]] = []
    for r in filtered:
        paper_id = r.get("paper_id") or r.get("pmid") or r.get("doi") or _safe_slug(str(r.get("title", "")))
        title = str(r.get("title", "") or "")
        abstract = str(r.get("abstract", "") or "")
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
            labels = ["METHOD", "MODEL", "DATASET", "TOOL", "DISEASE", "CHEMICAL", "GENE", "PROTEIN"]
            try:
                ents = gliner.predict_entities(text, labels) or []
                for e in ents:
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
                print(f"[warn] GLiNER extraction failed paper_id={paper_id}: {e}")

        project_candidates = list(
            dict.fromkeys(
                [
                    *keywords,
                    *[e.get("text") for e in entities if (e.get("score") or 0.0) >= 0.6 and e.get("text")],
                ]
            )
        )

        quality_score, quality_evidence = _calc_quality_score(r)
        out_rows.append(
            {
                **r,
                "paper_id": paper_id,
                "keywords": keywords,
                "entities": entities,
                "project_candidates": project_candidates,
                "quality_score": quality_score,
                "quality_evidence": quality_evidence,
            }
        )

    _write_jsonl(Path(args.output), out_rows)
    print(args.output)


if __name__ == "__main__":
    main()

