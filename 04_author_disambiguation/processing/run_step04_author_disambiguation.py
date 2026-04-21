import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _collect_strings(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        s = obj.strip()
        if s:
            out.append(s)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_collect_strings(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_collect_strings(v))
    return out


def _load_whoiswho_matcher(repo_root: Path):
    sys.path.insert(0, str(repo_root))
    from whoiswho.character.match_name import match_name  # type: ignore

    return match_name


def _normalize_target_name(target_name: str) -> str:
    # WhoIsWho matcher expects: first_last
    n = re.sub(r"[^a-zA-Z\s\-]", " ", target_name).strip().lower()
    parts = [p for p in re.split(r"[\s\-]+", n) if p]
    if len(parts) >= 2:
        first = "".join(parts[:-1])
        last = parts[-1]
        return f"{first}_{last}"
    if len(parts) == 1:
        return f"{parts[0]}_{parts[0]}"
    return "unknown_unknown"


def _extract_affiliations(paper: dict[str, Any]) -> list[str]:
    aff = paper.get("affiliations")
    if isinstance(aff, list):
        return [str(x).strip() for x in aff if str(x).strip()]
    if isinstance(aff, str) and aff.strip():
        return [aff.strip()]
    return []


def _score_identity(
    authors: list[str],
    target_name_norm: str,
    match_name_fn,
    affiliations: list[str],
    lab_keywords: list[str],
) -> tuple[float, dict[str, Any]]:
    author_hits = []
    for a in authors:
        ok = False
        try:
            ok = bool(match_name_fn(a, target_name_norm))
        except Exception:
            ok = False
        author_hits.append((a, ok))

    matched_authors = [a for a, ok in author_hits if ok]
    author_score = 1.0 if matched_authors else 0.0

    matched_aff = []
    if lab_keywords and affiliations:
        for a in affiliations:
            al = a.lower()
            if any(k in al for k in lab_keywords):
                matched_aff.append(a)
    aff_score = min(len(matched_aff) / 2.0, 1.0)

    score = round(0.8 * author_score + 0.2 * aff_score, 6)
    evidence = {
        "matched_authors": matched_authors,
        "matched_affiliations": matched_aff,
        "lab_keyword_count": len(lab_keywords),
    }
    return score, evidence


def main() -> None:
    p = argparse.ArgumentParser(description="Step04 glue: use WhoIsWho name matcher for author disambiguation.")
    p.add_argument("--expanded-papers", required=True, help="Step02 expanded papers JSONL")
    p.add_argument("--lab-info", required=True, help="Step01 lab_info JSON")
    p.add_argument("--output", required=True, help="Output JSONL path")
    p.add_argument("--threshold", type=float, default=0.5, help="identity_score threshold")
    p.add_argument(
        "--whoiswho-repo",
        default="04_author_disambiguation/processing/WhoIsWho",
        help="Local path to cloned WhoIsWho repository",
    )
    p.add_argument("--target-name", default="wanling yang", help="Professor target name")
    args = p.parse_args()

    matcher = _load_whoiswho_matcher(Path(args.whoiswho_repo))
    target_name_norm = _normalize_target_name(args.target_name)

    papers = _read_jsonl(Path(args.expanded_papers))
    lab_info = _read_json(Path(args.lab_info))

    lab_strings = [s.lower() for s in _collect_strings(lab_info)]
    # Keep medium-length tokens to avoid noisy matching.
    lab_keywords = sorted({re.sub(r"\s+", " ", s).strip() for s in lab_strings if len(s) >= 6})[:200]

    out_rows: list[dict[str, Any]] = []
    for r in papers:
        authors = r.get("authors") or []
        if not isinstance(authors, list):
            authors = [str(authors)]
        affiliations = _extract_affiliations(r)

        score, evidence = _score_identity(
            [str(x) for x in authors],
            target_name_norm,
            matcher,
            affiliations,
            lab_keywords,
        )
        decision = bool(score >= float(args.threshold))
        paper_id = r.get("paper_id") or r.get("pmid") or r.get("doi") or _safe_slug(str(r.get("title", "")))

        out_rows.append(
            {
                **r,
                "paper_id": paper_id,
                "identity_score": score,
                "identity_decision": decision,
                "identity_evidence": {
                    "strategy": "whoiswho_name_match_glue",
                    "target_name_norm": target_name_norm,
                    **evidence,
                },
                "affiliations": affiliations,
            }
        )

    _write_jsonl(Path(args.output), out_rows)
    print(args.output)


if __name__ == "__main__":
    main()

