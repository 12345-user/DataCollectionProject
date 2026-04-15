from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


def read_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=30) as response:
        return json.load(response)


def fetch_titles(author_query: str) -> dict[str, Any]:
    search_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
        + urlencode(
            {
                "db": "pubmed",
                "term": author_query,
                "retmax": "100000",
                "retmode": "json",
            }
        )
    )
    search_data = read_json(search_url)
    ids = search_data.get("esearchresult", {}).get("idlist", [])
    titles: list[dict[str, str]] = []
    batch = 200
    for idx in range(0, len(ids), batch):
        chunk = ids[idx : idx + batch]
        summary_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
            + urlencode({"db": "pubmed", "id": ",".join(chunk), "retmode": "json"})
        )
        summary_data = read_json(summary_url)
        for pmid in chunk:
            title = (summary_data.get("result", {}).get(pmid, {}).get("title") or "").strip()
            if title:
                titles.append({"pmid": pmid, "title": title})
    return {"query": author_query, "count": len(titles), "titles": titles}


def write_markdown(data: dict[str, Any], path: Path) -> None:
    lines = [
        f"# PubMed Title List: {data.get('query', '')}",
        "",
        f"Total: {data.get('count', 0)}",
        "",
    ]
    for i, item in enumerate(data.get("titles", []), 1):
        lines.append(f"{i}. {item.get('title', '')} (PMID: {item.get('pmid', '')})")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch PubMed titles for one professor.")
    parser.add_argument("--query", required=True, help="PubMed author query, e.g. 'Yong-Fei Wang[au]'")
    parser.add_argument(
        "--output-prefix",
        required=True,
        help="Output prefix, e.g. pubmed_yong_fei_wang",
    )
    args = parser.parse_args()

    output_dir = Path("01_data_collection/step_results/professor_paper_titles")
    output_dir.mkdir(parents=True, exist_ok=True)

    data = fetch_titles(args.query)
    json_path = output_dir / f"{args.output_prefix}_titles.json"
    md_path = output_dir / f"{args.output_prefix}_titles_list.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(data, md_path)
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
