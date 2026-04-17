from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


def _read_json(url: str, timeout_s: int = 30) -> dict[str, Any]:
    with urlopen(url, timeout=timeout_s) as response:
        return json.load(response)


def _fetch_xml(url: str, timeout_s: int = 30) -> ET.Element:
    with urlopen(url, timeout=timeout_s) as response:
        content = response.read()
    return ET.fromstring(content)


def _fetch_text(url: str, timeout_s: int = 30) -> str:
    with urlopen(url, timeout=timeout_s) as response:
        return response.read().decode("utf-8", errors="ignore")


def _normalize_title(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff ]+", "", s)
    return s.strip()


def _normalize_person_name(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z ]+", "", s)
    return s.strip()


def _author_matches(candidate: str, professor_name: str) -> bool:
    candidate_norm = _normalize_person_name(candidate)
    professor_norm = _normalize_person_name(professor_name)
    if not candidate_norm or not professor_norm:
        return False
    if candidate_norm == professor_norm:
        return True

    professor_parts = [p for p in professor_norm.split(" ") if p]
    candidate_parts = [p for p in candidate_norm.split(" ") if p]
    if not professor_parts or not candidate_parts:
        return False

    professor_last = professor_parts[-1]
    professor_given = professor_parts[:-1]
    professor_initials = "".join(p[0] for p in professor_given if p)

    # Pattern A: "given-name surname" <-> "given-name surname"
    candidate_last = candidate_parts[-1]
    candidate_given = candidate_parts[:-1]
    candidate_initials = "".join(p[0] for p in candidate_given if p)
    if professor_last == candidate_last:
        if professor_initials and candidate_initials and professor_initials[0] == candidate_initials[0]:
            return True
        if any(g == c for g in professor_given for c in candidate_given):
            return True

    # Pattern B: PubMed summary often uses "surname initials", e.g. "Yang W"
    candidate_first = candidate_parts[0]
    candidate_rest = candidate_parts[1:]
    candidate_rest_initials = "".join(p[0] for p in candidate_rest if p)
    if candidate_first == professor_last:
        if professor_initials and candidate_rest_initials and professor_initials[0] == candidate_rest_initials[0]:
            return True

    return False


def _fetch_summary(pmid_list: list[str]) -> dict[str, Any]:
    summary_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
        + urlencode({"db": "pubmed", "id": ",".join(pmid_list), "retmode": "json"})
    )
    return _read_json(summary_url)


def _search_pubmed_html_pmids(seed_title: str) -> list[str]:
    # Final fallback: PubMed web search sometimes returns pages that the E-utilities
    # title query does not reliably surface yet. Extract article PMIDs from HTML.
    search_url = "https://pubmed.ncbi.nlm.nih.gov/?" + urlencode({"term": f'"{seed_title}"'})
    html = _fetch_text(search_url)
    pmids = re.findall(r'href="/(\d+)/"', html)
    ordered: list[str] = []
    seen: set[str] = set()
    for pmid in pmids:
        if pmid not in seen:
            seen.add(pmid)
            ordered.append(pmid)
    return ordered[:20]


def _search_seed_pmids(author: str, seed_title: str, retmax: int = 20) -> list[str]:
    # Seed title matching often fails if the provided string is not exactly indexed in PubMed.
    # We try multiple increasingly-flexible strategies.
    candidates: list[str] = []

    def try_term(term: str) -> list[str]:
        search_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
            + urlencode({"db": "pubmed", "term": term, "retmax": str(retmax), "retmode": "json"})
        )
        data = _read_json(search_url)
        return data.get("esearchresult", {}).get("idlist", [])

    # 1) Phrase search (most strict, but correct when the title matches)
    candidates = try_term(f'{author}[au] AND "{seed_title}"[tiab]')
    if candidates:
        return candidates

    # 2) Token search (less strict; PubMed splits into keywords)
    candidates = try_term(f"{author}[au] AND {seed_title}[tiab]")
    if candidates:
        return candidates

    # 3) Search by leading words (usually robust for long titles)
    words = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff ]+", " ", seed_title)
    words = re.sub(r"\s+", " ", words).strip()
    leading = " ".join(words.split(" ")[:6]).strip()
    if leading:
        candidates = try_term(f'{author}[au] AND "{leading}"[tiab]')
        if candidates:
            return candidates

    # 4) Fallback: search title only, then filter by authors in PubMed summary
    fallback_terms: list[str] = []
    if seed_title.strip():
        fallback_terms.append(f'"{seed_title}"[tiab]')
        fallback_terms.append(f"{seed_title}[tiab]")
    if leading:
        fallback_terms.append(f'"{leading}"[tiab]')

    for term in fallback_terms:
        pmids = try_term(term)
        if not pmids:
            continue
        summary_data = _fetch_summary(pmids)
        filtered: list[str] = []
        for pmid in pmids:
            authors = summary_data.get("result", {}).get(pmid, {}).get("authors", []) or []
            author_names = [str(item.get("name", "")).strip() for item in authors if isinstance(item, dict)]
            if any(_author_matches(name, author) for name in author_names):
                filtered.append(pmid)
        if filtered:
            return filtered

    # 5) Final fallback: use PubMed webpage search results to locate PMIDs.
    html_pmids = _search_pubmed_html_pmids(seed_title)
    if html_pmids:
        summary_data = _fetch_summary(html_pmids)
        filtered: list[str] = []
        for pmid in html_pmids:
            authors = summary_data.get("result", {}).get(pmid, {}).get("authors", []) or []
            author_names = [str(item.get("name", "")).strip() for item in authors if isinstance(item, dict)]
            if any(_author_matches(name, author) for name in author_names):
                filtered.append(pmid)
        if filtered:
            return filtered

    return []


def _pick_seed_pmid(seed_pmids: list[str], author: str, seed_title: str) -> str:
    # If multiple candidates exist, pick the one whose esummary title best matches the provided title.
    data = _fetch_summary(seed_pmids)
    seed_norm = _normalize_title(seed_title)

    best_pmid = seed_pmids[0]
    best_score = -1.0

    for pmid in seed_pmids:
        title = (data.get("result", {}).get(pmid, {}).get("title") or "").strip()
        title_norm = _normalize_title(title)
        if not title_norm:
            continue
        if title_norm == seed_norm:
            return pmid
        # Simple token overlap score (fast, enough for exact seed selection)
        seed_tokens = set(seed_norm.split(" "))
        title_tokens = set(title_norm.split(" "))
        overlap = len(seed_tokens.intersection(title_tokens))
        score = overlap / max(1, len(seed_tokens))
        if score > best_score:
            best_score = score
            best_pmid = pmid

    return best_pmid


def _collect_affiliations(pmid: str) -> list[str]:
    fetch_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
        + urlencode({"db": "pubmed", "id": pmid, "retmode": "xml"})
    )
    root = _fetch_xml(fetch_url)
    values: list[str] = []
    for node in root.findall(".//AffiliationInfo/Affiliation"):
        text = " ".join((node.itertext() or [])).strip()
        if text:
            values.append(text)
    return values


def _segment_affiliation(aff: str) -> list[str]:
    # Split by common separators and keep longer segments as candidates.
    parts = [p.strip() for p in re.split(r"[;,]", aff) if p.strip()]
    # Keep segments that are likely to be organization parts.
    segs: list[str] = []
    for p in parts:
        p2 = re.sub(r"\s+", " ", p).strip()
        if len(p2) >= 8:
            segs.append(p2)
    return segs


def _extract_keywords_and_unit(affiliations: list[str], top_n: int = 12) -> tuple[str, list[str]]:
    # Aggregate segments and choose:
    # - affiliation_unit_for_ad: most frequent "segment"
    # - affiliation_keywords: top segments with institution-like hints (fallback to top_n)
    seg_counter: Counter[str] = Counter()
    seg_keywords_counter: Counter[str] = Counter()

    inst_hint = re.compile(
        r"(university|institute|laboratory|college|department|hospital|school|academy|ministry|center|academy|cas)",
        re.IGNORECASE,
    )

    for aff in affiliations:
        for seg in _segment_affiliation(aff):
            seg_counter[seg] += 1
            if inst_hint.search(seg):
                seg_keywords_counter[seg] += 1

    if seg_keywords_counter:
        candidates = seg_keywords_counter.most_common(top_n)
    else:
        candidates = seg_counter.most_common(top_n)

    keywords = []
    for seg, _ in candidates:
        # remove commas because downstream filtering splits by comma
        seg_clean = seg.replace(",", " ").strip()
        if seg_clean and seg_clean not in keywords:
            keywords.append(seg_clean)

    affiliation_unit_for_ad = keywords[0] if keywords else (seg_counter.most_common(1)[0][0] if seg_counter else "")
    return affiliation_unit_for_ad, keywords


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve seed paper to affiliation keywords for disambiguation.")
    parser.add_argument("--professor-name", required=True, help="Professor name, used in PubMed author field.")
    parser.add_argument("--seed-title", required=True, help="A paper title that the professor authored.")
    parser.add_argument("--seed-pmid", default="", help="Optional known PMID to bypass seed title search.")
    parser.add_argument("--retmax", type=int, default=20, help="Max seed candidates in PubMed search.")
    args = parser.parse_args()

    if args.seed_pmid.strip():
        seed_pmid = args.seed_pmid.strip()
    else:
        seed_pmids = _search_seed_pmids(args.professor_name, args.seed_title, retmax=args.retmax)
        if not seed_pmids:
            raise SystemExit(
                "Seed paper not found in PubMed by the provided author+title. "
                "Please use one paper title that is actually indexed in PubMed and authored by this professor, "
                "or provide --seed-pmid directly."
            )
        seed_pmid = _pick_seed_pmid(seed_pmids, args.professor_name, args.seed_title)

    affiliations = _collect_affiliations(seed_pmid)
    if not affiliations:
        raise SystemExit("Seed PMID found, but affiliation info is empty in PubMed XML.")

    affiliation_unit_for_ad, affiliation_keywords = _extract_keywords_and_unit(affiliations)
    if not affiliation_unit_for_ad:
        raise SystemExit("Could not resolve a usable affiliation unit for PubMed [ad] filter.")

    out = {
        "seed_title": args.seed_title,
        "seed_pmid": seed_pmid,
        "seed_affiliations_count": len(affiliations),
        "affiliation_unit_for_ad": affiliation_unit_for_ad,
        "affiliation_keywords": affiliation_keywords,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

