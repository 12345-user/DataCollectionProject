from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen
import xml.etree.ElementTree as ET


def _text_or_empty(node: ET.Element | None, xpath: str) -> str:
    if node is None:
        return ""
    v = node.findtext(xpath) or ""
    return v.strip()


def _parse_pub_date(article: ET.Element) -> str:
    # Prefer Year/Month/Day when available; otherwise fall back to MedlineDate.
    year = _text_or_empty(article, ".//PubDate/Year")
    month = _text_or_empty(article, ".//PubDate/Month")
    day = _text_or_empty(article, ".//PubDate/Day")
    if year:
        mm = month if month.isdigit() else ""
        dd = day if day.isdigit() else ""
        if mm and dd:
            return f"{year}-{int(mm):02d}-{int(dd):02d}"
        if mm:
            return f"{year}-{int(mm):02d}"
        return year
    medline = _text_or_empty(article, ".//PubDate/MedlineDate")
    return medline


def _parse_doi(article: ET.Element) -> str:
    doi = (article.findtext(".//ArticleId[@IdType='doi']") or "").strip()
    if doi:
        return doi
    doi2 = (article.findtext(".//ELocationID[@EIdType='doi']") or "").strip()
    return doi2


def _parse_journal(article: ET.Element) -> str:
    # Prefer full journal title; fallback to ISO abbreviation.
    journal = (article.findtext(".//Journal/Title") or "").strip()
    if journal:
        return journal
    return (article.findtext(".//Journal/ISOAbbreviation") or "").strip()


def _parse_authors(article: ET.Element) -> list[str]:
    authors: list[str] = []
    for a in article.findall(".//AuthorList/Author"):
        # Some PubMed records use CollectiveName instead of LastName/ForeName
        collective = (a.findtext("CollectiveName") or "").strip()
        if collective:
            authors.append(collective)
            continue

        last = (a.findtext("LastName") or "").strip()
        initials = (a.findtext("ForeName/Initials") or (a.findtext("Initials") or "")).strip()
        fore = (a.findtext("ForeName") or "").strip()

        if last and initials:
            authors.append(f"{last} {initials}")
        elif last and fore:
            # Avoid full given name explosion; prefer initials when present.
            authors.append(f"{last} {fore}")
        elif last:
            authors.append(last)
    return authors


def fetch_xml(url: str, cache_dir: Path, cache_key: str, retries: int = 3) -> ET.Element:
    cache_file = cache_dir / f"{cache_key}.xml"
    if cache_file.exists():
        return ET.fromstring(cache_file.read_bytes())

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(url, timeout=30) as response:
                content = response.read()
            cache_file.write_bytes(content)
            return ET.fromstring(content)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    if last_error is not None:
        raise last_error
    return ET.Element("PubmedArticleSet")


def fetch_abstracts(pmids: list[str], cache_dir: Path) -> list[dict[str, Any]]:
    if not pmids:
        return []
    fetch_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
        + urlencode({"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"})
    )
    root = fetch_xml(fetch_url, cache_dir, "efetch_abstracts")
    results: list[dict[str, Any]] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = (article.findtext(".//PMID") or "").strip()
        title = (article.findtext(".//ArticleTitle") or "").strip()
        abstract_nodes = article.findall(".//Abstract/AbstractText")
        abstract_text = " ".join(
            [" ".join((node.itertext() or [])).strip() for node in abstract_nodes if node is not None]
        ).strip()

        record: dict[str, Any] = {
            "pmid": pmid,
            "title": title,
            "abstract": abstract_text,
            "pub_date": _parse_pub_date(article),
            "doi": _parse_doi(article),
            "journal": _parse_journal(article),
            "authors": _parse_authors(article),
        }
        if pmid:
            results.append(record)
    # Strict de-dup by PMID.
    seen_pmids: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in results:
        pmid = str(item.get("pmid", "")).strip()
        if not pmid or pmid in seen_pmids:
            continue
        seen_pmids.add(pmid)
        deduped.append(item)
    return deduped


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch PubMed abstracts by titles JSON.")
    parser.add_argument("--titles-json", required=True, help="Input titles json path")
    parser.add_argument("--output-prefix", required=True, help="Output prefix")
    parser.add_argument(
        "--cache-dir",
        default=".cache/pubmed_abstracts",
        help="Cache directory for PubMed abstract XML",
    )
    args = parser.parse_args()

    titles_data = json.loads(Path(args.titles_json).read_text(encoding="utf-8"))
    pmids = [item.get("pmid", "").strip() for item in titles_data.get("titles", []) if item.get("pmid")]
    cache_dir = Path(args.cache_dir) / args.output_prefix
    cache_dir.mkdir(parents=True, exist_ok=True)
    records = fetch_abstracts(pmids, cache_dir)
    output_dir = Path("01_data_collection/step_results/professor_paper_abstracts")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_json = output_dir / f"{args.output_prefix}_abstracts.json"
    out_md = output_dir / f"{args.output_prefix}_abstracts_list.md"
    out_jsonl = output_dir / f"{args.output_prefix}_abstracts.jsonl"
    out_json.write_text(json.dumps({"count": len(records), "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")

    # JSONL (one record per line) for downstream pipeline steps.
    out_jsonl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")

    lines = [f"# PubMed Abstract List: {args.output_prefix}", "", f"Total: {len(records)}", ""]
    for i, item in enumerate(records, 1):
        pub_date = item.get("pub_date", "") or ""
        doi = item.get("doi", "") or ""
        journal = item.get("journal", "") or ""
        lines.append(
            f"## {i}. {item.get('title', '')} (PMID: {item.get('pmid', '')}, PubDate: {pub_date}, Journal: {journal}, DOI: {doi})"
        )
        lines.append(item.get("abstract", "(no abstract)"))
        authors = item.get("authors", []) or []
        if authors:
            lines.append(f"Authors: {', '.join(authors[:20])}{'...' if len(authors) > 20 else ''}")
        lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(out_json)
    print(out_md)
    print(out_jsonl)


if __name__ == "__main__":
    main()
