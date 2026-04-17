from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import requests
from lxml import etree


NS = {"tei": "http://www.tei-c.org/ns/1.0"}


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


def _safe_slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "unknown"


def _first_text(node: Any) -> str:
    if node is None:
        return ""
    if isinstance(node, list):
        node = node[0] if node else None
    if node is None:
        return ""
    txt = " ".join(node.itertext()).strip()
    txt = re.sub(r"\s+", " ", txt)
    return txt


def _texts(nodes: list[Any]) -> list[str]:
    out: list[str] = []
    for n in nodes or []:
        t = _first_text(n)
        if t:
            out.append(t)
    return out


def _parse_tei(tei_xml: bytes) -> dict[str, Any]:
    root = etree.fromstring(tei_xml)

    title = _first_text(root.xpath(".//tei:teiHeader//tei:titleStmt/tei:title", namespaces=NS))
    abstract = _first_text(
        root.xpath(".//tei:teiHeader//tei:profileDesc//tei:abstract", namespaces=NS)
    ) or _first_text(root.xpath(".//tei:text//tei:abstract", namespaces=NS))

    authors: list[str] = []
    for a in root.xpath(".//tei:teiHeader//tei:fileDesc//tei:sourceDesc//tei:author", namespaces=NS):
        name = _first_text(a.xpath(".//tei:persName", namespaces=NS)) or _first_text(a)
        if name:
            authors.append(name)
    authors = list(dict.fromkeys(authors))

    affiliations: list[str] = []
    affiliations += _texts(
        root.xpath(".//tei:teiHeader//tei:fileDesc//tei:sourceDesc//tei:affiliation", namespaces=NS)
    )
    affiliations += _texts(
        root.xpath(".//tei:teiHeader//tei:fileDesc//tei:sourceDesc//tei:orgName", namespaces=NS)
    )
    affiliations = [a for a in affiliations if a]
    affiliations = list(dict.fromkeys(affiliations))

    keywords: list[str] = []
    for term in root.xpath(".//tei:teiHeader//tei:profileDesc//tei:textClass//tei:keywords//tei:term", namespaces=NS):
        t = _first_text(term)
        if t:
            keywords.append(t)
    keywords = list(dict.fromkeys(keywords))

    references: list[dict[str, Any]] = []
    for bibl in root.xpath(".//tei:listBibl//tei:biblStruct", namespaces=NS):
        ref_title = _first_text(bibl.xpath(".//tei:title", namespaces=NS))
        ref_doi = ""
        for idno in bibl.xpath(".//tei:idno", namespaces=NS):
            if (idno.get("type") or "").lower() == "doi":
                ref_doi = _first_text(idno)
                break
        references.append({"title": ref_title, "doi": ref_doi})

    # Sections: keep lightweight. (Full text can be huge; downstream can re-fetch TEI if needed.)
    sections: list[dict[str, Any]] = []
    for div in root.xpath(".//tei:text//tei:body//tei:div", namespaces=NS)[:50]:
        head = _first_text(div.xpath("./tei:head", namespaces=NS))
        p = _first_text(div.xpath("./tei:p", namespaces=NS))
        if head or p:
            sections.append({"heading": head, "text": p})

    return {
        "title_extracted": title,
        "abstract_extracted": abstract,
        "authors_extracted": authors,
        "affiliations_extracted": affiliations,
        "keywords_extracted": keywords,
        "references_extracted": references,
        "sections_extracted": sections,
    }


def _call_grobid(pdf_path: Path, grobid_url: str, timeout_s: int = 120) -> bytes:
    with pdf_path.open("rb") as f:
        files = {"input": (pdf_path.name, f, "application/pdf")}
        r = requests.post(grobid_url, files=files, timeout=timeout_s)
        r.raise_for_status()
        return r.content


def main() -> None:
    p = argparse.ArgumentParser(description="Step03: parse PDFs via local GROBID (Docker) and output structured JSONL.")
    p.add_argument("--input-step02-jsonl", default="", help="Step02 expanded papers JSONL (optional for metadata join).")
    p.add_argument("--pdf-dir", required=True, help="Directory containing PDF files to parse.")
    p.add_argument("--output-jsonl", required=True, help="Output JSONL path.")
    p.add_argument("--grobid-host", default="http://localhost:8070", help="GROBID host.")
    p.add_argument("--grobid-endpoint", default="/api/processFulltextDocument", help="GROBID endpoint path.")
    p.add_argument("--timeout-s", type=int, default=120, help="HTTP timeout seconds.")
    args = p.parse_args()

    grobid_url = args.grobid_host.rstrip("/") + "/" + args.grobid_endpoint.lstrip("/")

    step02_rows: dict[str, dict[str, Any]] = {}
    if args.input_step02_jsonl.strip():
        for r in _read_jsonl(Path(args.input_step02_jsonl)):
            pid = str(r.get("paper_id") or r.get("source_id") or r.get("pmid") or _safe_slug(r.get("title", "")))
            step02_rows[pid] = r

    pdf_dir = Path(args.pdf_dir)
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in: {pdf_dir}")

    out: list[dict[str, Any]] = []
    for pdf_path in pdfs:
        paper_id = pdf_path.stem
        base = {
            "paper_id": paper_id,
            "pdf_path": str(pdf_path),
        }
        if paper_id in step02_rows:
            base |= {
                "source": step02_rows[paper_id].get("source", ""),
                "title": step02_rows[paper_id].get("title", ""),
                "abstract": step02_rows[paper_id].get("abstract", ""),
                "pub_date": step02_rows[paper_id].get("pub_date", ""),
                "authors": step02_rows[paper_id].get("authors", []),
                "doi": step02_rows[paper_id].get("doi", ""),
                "url": step02_rows[paper_id].get("url", ""),
            }

        tei = _call_grobid(pdf_path, grobid_url=grobid_url, timeout_s=int(args.timeout_s))
        parsed = _parse_tei(tei)
        out.append(base | parsed)

    _write_jsonl(Path(args.output_jsonl), out)
    print(args.output_jsonl)


if __name__ == "__main__":
    main()

