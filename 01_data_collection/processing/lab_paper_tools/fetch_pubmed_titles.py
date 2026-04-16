from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


def read_json(url: str, cache_dir: Path, cache_key: str, retries: int = 3) -> dict[str, Any]:
    cache_file = cache_dir / f"{cache_key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(url, timeout=30) as response:
                data = json.load(response)
            cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    if last_error is not None:
        raise last_error
    return {}


def fetch_titles(author_query: str, cache_dir: Path) -> dict[str, Any]:
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
    search_data = read_json(search_url, cache_dir, "esearch")
    ids = search_data.get("esearchresult", {}).get("idlist", [])
    titles: list[dict[str, str]] = []
    batch = 200
    for idx in range(0, len(ids), batch):
        chunk = ids[idx : idx + batch]
        summary_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
            + urlencode({"db": "pubmed", "id": ",".join(chunk), "retmode": "json"})
        )
        summary_data = read_json(summary_url, cache_dir, f"esummary_{idx}")
        for pmid in chunk:
            title = (summary_data.get("result", {}).get(pmid, {}).get("title") or "").strip()
            if title:
                titles.append({"pmid": pmid, "title": title})
    # Strict de-dup: PubMed query results should be unique by PMID.
    seen_pmids: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in titles:
        pmid = str(item.get("pmid", "")).strip()
        if not pmid or pmid in seen_pmids:
            continue
        seen_pmids.add(pmid)
        deduped.append({"pmid": pmid, "title": item.get("title", "")})

    return {"query": author_query, "count": len(deduped), "titles": deduped}


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
    parser.add_argument(
        "--cache-dir",
        default=".cache/pubmed_titles",
        help="Cache directory for PubMed API responses",
    )
    args = parser.parse_args()

    output_dir = Path("01_data_collection/step_results/professor_paper_titles")
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir) / args.output_prefix
    cache_dir.mkdir(parents=True, exist_ok=True)

    data = fetch_titles(args.query, cache_dir)
    json_path = output_dir / f"{args.output_prefix}_titles.json"
    md_path = output_dir / f"{args.output_prefix}_titles_list.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(data, md_path)
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
