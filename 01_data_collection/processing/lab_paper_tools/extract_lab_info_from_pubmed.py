from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import xml.etree.ElementTree as ET


def fetch_xml(url: str) -> ET.Element:
    with urlopen(url, timeout=30) as response:
        content = response.read()
    return ET.fromstring(content)


def collect_affiliations(pmids: list[str]) -> list[str]:
    if not pmids:
        return []
    fetch_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
        + urlencode({"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"})
    )
    root = fetch_xml(fetch_url)
    values: list[str] = []
    for node in root.findall(".//AffiliationInfo/Affiliation"):
        text = " ".join((node.itertext() or [])).strip()
        if text:
            values.append(text)
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract lab affiliation clues from PubMed PMIDs.")
    parser.add_argument("--titles-json", required=True, help="Input titles json path")
    parser.add_argument("--output-prefix", required=True, help="Output prefix")
    args = parser.parse_args()

    titles_data = json.loads(Path(args.titles_json).read_text(encoding="utf-8"))
    pmids = [item.get("pmid", "").strip() for item in titles_data.get("titles", []) if item.get("pmid")]
    affiliations = collect_affiliations(pmids)
    top_counts = Counter(affiliations).most_common(200)

    output_dir = Path("01_data_collection/step_results/professor_lab_info")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_json = output_dir / f"{args.output_prefix}_lab_info.json"
    out_md = output_dir / f"{args.output_prefix}_lab_info_list.md"

    out_json.write_text(
        json.dumps(
            {
                "count_affiliations": len(affiliations),
                "unique_affiliations": len(set(affiliations)),
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
        "",
    ]
    for i, (affiliation, count) in enumerate(top_counts, 1):
        lines.append(f"{i}. [{count}] {affiliation}")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(out_json)
    print(out_md)


if __name__ == "__main__":
    main()
