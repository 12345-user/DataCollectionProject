from __future__ import annotations

import argparse
import json
import math
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


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _score_affiliations(affs: list[str], keywords: list[str]) -> tuple[float, dict[str, Any]]:
    if not affs:
        return 0.0, {"matched_keywords": [], "matched_affiliations": []}
    aff_norm = [_norm(a) for a in affs if a and a.strip()]
    kw_norm = [_norm(k) for k in keywords if k and k.strip()]
    matched_kw: list[str] = []
    matched_affs: list[str] = []
    for kw, kw_n in zip(keywords, kw_norm):
        if not kw_n:
            continue
        for a_raw, a_n in zip(affs, aff_norm):
            if kw_n in a_n:
                matched_kw.append(kw)
                matched_affs.append(a_raw)
                break
    matched_kw = list(dict.fromkeys(matched_kw))
    matched_affs = list(dict.fromkeys(matched_affs))

    # Simple saturating score: more distinct keyword hits => higher confidence.
    k = len(matched_kw)
    score = 1.0 - math.exp(-0.7 * k)  # 0, 0.50, 0.75, 0.88...
    return score, {"matched_keywords": matched_kw, "matched_affiliations": matched_affs}


def main() -> None:
    p = argparse.ArgumentParser(description="Step 04 (baseline): author disambiguation using Step01 lab_info affiliations.")
    p.add_argument(
        "--expanded-papers",
        required=True,
        help="Step02 expanded papers JSONL (02_paper_list_extend/step_results/<prefix>_expanded_papers.jsonl)",
    )
    p.add_argument(
        "--lab-info",
        required=True,
        help="Step01 lab_info.json (01_data_collection/step_results/professor_lab_info/<prefix>_lab_info.json)",
    )
    p.add_argument("--output", required=True, help="Output JSONL path for disambiguated papers")
    p.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="identity_score threshold for identity_decision=true (baseline).",
    )
    args = p.parse_args()

    expanded_path = Path(args.expanded_papers)
    lab_path = Path(args.lab_info)
    out_path = Path(args.output)
    rows = _read_jsonl(expanded_path)
    lab = json.loads(lab_path.read_text(encoding="utf-8", errors="replace"))

    keywords: list[str] = lab.get("disambiguation_keywords", []) or []
    pmid_affs_after: dict[str, list[str]] = lab.get("pmid_affiliations_after_filter", {}) or {}
    pmid_affs_raw: dict[str, list[str]] = lab.get("pmid_affiliations", {}) or {}

    out_rows: list[dict[str, Any]] = []
    for r in rows:
        source = (r.get("source") or "").strip().lower()
        pmid = (r.get("pmid") or "").strip()

        identity_score = 0.5
        evidence: dict[str, Any] = {"strategy": "baseline", "source": source}

        if source == "pubmed" and pmid:
            affs = pmid_affs_after.get(pmid) or pmid_affs_raw.get(pmid) or []
            score, ev = _score_affiliations(affs, keywords)
            # If per-paper filter was empty but raw had content, keep a conservative floor.
            identity_score = max(score, 0.2 if affs else 0.0)
            evidence |= {"pmid": pmid, "affiliations_count": len(affs)} | ev
        else:
            # Preprints: we don't have affiliation evidence yet; keep neutral and let downstream weight it.
            identity_score = 0.5
            evidence |= {"reason": "no_pmid_affiliation_evidence"}

        decision = bool(identity_score >= float(args.threshold))
        out_rows.append(
            {
                **r,
                "identity_score": round(float(identity_score), 4),
                "identity_decision": decision,
                "identity_evidence": evidence,
            }
        )

    _write_jsonl(out_path, out_rows)
    print(out_path)


if __name__ == "__main__":
    main()

