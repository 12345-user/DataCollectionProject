from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
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
        if pmid:
            results.append({"pmid": pmid, "title": title, "abstract": abstract_text})
    return results


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
    out_json.write_text(json.dumps({"count": len(records), "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# PubMed Abstract List: {args.output_prefix}", "", f"Total: {len(records)}", ""]
    for i, item in enumerate(records, 1):
        lines.append(f"## {i}. {item.get('title', '')} (PMID: {item.get('pmid', '')})")
        lines.append(item.get("abstract", "(no abstract)"))
        lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(out_json)
    print(out_md)


if __name__ == "__main__":
    main()
