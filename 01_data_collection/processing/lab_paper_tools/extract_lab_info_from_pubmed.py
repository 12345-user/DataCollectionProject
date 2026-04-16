from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from urllib.request import urlopen
import xml.etree.ElementTree as ET


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


def collect_affiliations(pmids: list[str], cache_dir: Path) -> list[str]:
    if not pmids:
        return []
    fetch_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
        + urlencode({"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"})
    )
    root = fetch_xml(fetch_url, cache_dir, "efetch_affiliations")
    values: list[str] = []
    for node in root.findall(".//AffiliationInfo/Affiliation"):
        text = " ".join((node.itertext() or [])).strip()
        if text:
            values.append(text)
    return values


def filter_affiliations(affiliations: list[str], keywords: list[str]) -> list[str]:
    if not keywords:
        return affiliations
    patterns = [re.compile(re.escape(k), flags=re.IGNORECASE) for k in keywords if k.strip()]
    if not patterns:
        return affiliations
    return [a for a in affiliations if any(p.search(a) for p in patterns)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract lab affiliation clues from PubMed PMIDs.")
    parser.add_argument("--titles-json", required=True, help="Input titles json path")
    parser.add_argument("--output-prefix", required=True, help="Output prefix")
    parser.add_argument(
        "--affiliation-keywords",
        default="",
        help="Comma-separated affiliation keywords for disambiguation, e.g. Shanghai,Fudan",
    )
    parser.add_argument(
        "--cache-dir",
        default=".cache/pubmed_lab_info",
        help="Cache directory for PubMed affiliation XML",
    )
    args = parser.parse_args()

    titles_data = json.loads(Path(args.titles_json).read_text(encoding="utf-8"))
    pmids = [item.get("pmid", "").strip() for item in titles_data.get("titles", []) if item.get("pmid")]
    cache_dir = Path(args.cache_dir) / args.output_prefix
    cache_dir.mkdir(parents=True, exist_ok=True)
    affiliations = collect_affiliations(pmids, cache_dir)
    keywords = [x.strip() for x in args.affiliation_keywords.split(",") if x.strip()]
    filtered_affiliations = filter_affiliations(affiliations, keywords)
    effective = filtered_affiliations if filtered_affiliations else affiliations
    top_counts = Counter(effective).most_common(200)

    output_dir = Path("01_data_collection/step_results/professor_lab_info")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_json = output_dir / f"{args.output_prefix}_lab_info.json"
    out_md = output_dir / f"{args.output_prefix}_lab_info_list.md"

    out_json.write_text(
        json.dumps(
            {
                "count_affiliations": len(affiliations),
                "unique_affiliations": len(set(affiliations)),
                "disambiguation_keywords": keywords,
                "count_affiliations_after_filter": len(effective),
                "unique_affiliations_after_filter": len(set(effective)),
                "top_affiliations": [{"affiliation": k, "count": v} for k, v in top_counts],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        f"# Lab Info (Affiliation Clues): {args.output_prefix}",
        "",
        f"Total affiliations: {len(affiliations)}",
        f"Unique affiliations: {len(set(affiliations))}",
        f"Filter keywords: {', '.join(keywords) if keywords else '(none)'}",
        f"After filter count: {len(effective)}",
        f"After filter unique: {len(set(effective))}",
        "",
    ]
    for i, (affiliation, count) in enumerate(top_counts, 1):
        lines.append(f"{i}. [{count}] {affiliation}")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(out_json)
    print(out_md)


if __name__ == "__main__":
    main()
