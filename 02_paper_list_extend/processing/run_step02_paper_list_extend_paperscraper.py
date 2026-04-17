from __future__ import annotations

import argparse
import glob
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "unknown"


def _norm_title(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _dedup_strs(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _as_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    return str(x).strip()


def _sanitize_jsonl_text(s: str) -> str:
    """
    Ensure JSONL stays one-record-per-line.

    Python's splitlines() treats U+2028/U+2029 as line breaks; some upstream data may contain them.
    We normalize them to regular newlines so json.dumps will escape them as \\n.
    """
    if not s:
        return ""
    return s.replace("\u2028", "\n").replace("\u2029", "\n")


def _pick(d: dict[str, Any], keys: list[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return ""


def _parse_authors(authors: Any) -> list[str]:
    # paperscraper preprint records may store authors as list[str] or list[dict].
    if not authors:
        return []
    if isinstance(authors, list):
        out: list[str] = []
        for a in authors:
            if isinstance(a, str):
                if a.strip():
                    out.append(a.strip())
            elif isinstance(a, dict):
                name = _as_str(a.get("name") or a.get("author_name") or a.get("full_name"))
                if name:
                    out.append(name)
        return out
    # fallback string
    s = _as_str(authors)
    return [s] if s else []


def _parse_pub_date(d: dict[str, Any]) -> str:
    # Try several likely keys; return YYYY or YYYY-MM if possible.
    raw = _pick(
        d,
        [
            "pub_date",
            "publication_date",
            "published_date",
            "date",
            "published",
            "year",
        ],
    )
    raw_s = _as_str(raw)
    if not raw_s:
        return ""

    # Common formats: 2024-01-20, 2024-01, 2024
    m = re.search(r"(19|20)\d{2}(-\d{2})?(-\d{2})?", raw_s)
    if m:
        # extract matched string without trailing punctuation
        return m.group(0)
    return raw_s


def _parse_doi(d: dict[str, Any]) -> str:
    doi = _pick(d, ["doi", "DOI"])
    doi_s = _as_str(doi)
    if not doi_s:
        return ""
    return doi_s


def _server_dump_candidates(dump_dir: Path, source: str) -> list[Path]:
    # Expect files like: server_dumps/biorxiv_2020-11-10.jsonl
    pattern = str(dump_dir / f"{source}_*.jsonl")
    return sorted([Path(p) for p in glob.glob(pattern)])


def _latest_dump(dump_dir: Path, source: str) -> Path:
    candidates = _server_dump_candidates(dump_dir, source)
    if not candidates:
        raise FileNotFoundError(
            f"未找到 {source} 的 server dump 文件：{dump_dir}（期望类似 {source}_YYYY-MM-DD.jsonl）"
        )
    # Sort lexicographically usually works for YYYY-MM-DD in filename.
    return candidates[-1]


def _try_latest_dump(dump_dir: Path, source: str) -> Path | None:
    try:
        return _latest_dump(dump_dir, source)
    except FileNotFoundError:
        return None


def _infer_query_from_professor(professor_name: str) -> list[list[str]]:
    # paperscraper “query” is a list of keyword groups; each inner list provides OR synonyms for that group.
    tokens = re.split(r"[\s,]+", professor_name.strip())
    tokens = [t for t in tokens if t]
    if not tokens:
        return [["unknown"]]
    surname = tokens[-1]
    given_tokens = tokens[:-1]

    query_groups: list[list[str]] = []
    if surname:
        query_groups.append([surname])

    given_synonyms: list[str] = []
    if given_tokens:
        given_name = " ".join(given_tokens)
        given_synonyms.append(given_name)
        initials = "".join(t[0] for t in given_tokens if t)
        if initials:
            given_synonyms.append(initials)
            given_synonyms.extend([t[0] for t in given_tokens if t])

    given_synonyms = _dedup_strs([s for s in given_synonyms if s])
    if given_synonyms:
        query_groups.append(given_synonyms)

    return query_groups or [["unknown"]]


def _dump_arxiv_with_retry(query: list[list[str]], output_path: Path, max_attempts: int = 3) -> bool:
    from paperscraper.arxiv import get_and_dump_arxiv_papers

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            get_and_dump_arxiv_papers(query, output_filepath=str(output_path))
            return True
        except Exception as exc:
            last_error = exc
            print(f"[warn] arXiv 抓取失败，第 {attempt}/{max_attempts} 次：{exc}")
            if output_path.exists():
                output_path.unlink()
            if attempt < max_attempts:
                time.sleep(min(10 * attempt, 30))
    print(f"[warn] arXiv 连续失败，已跳过该源：{last_error}")
    return False


@dataclass
class PaperRecord:
    title: str
    abstract: str
    pub_date: str
    authors: list[str]
    doi: str
    url: str
    source: str
    pmid: str = ""

    def to_json(self) -> dict[str, Any]:
        source_id = self.pmid or self.doi or _norm_title(self.title)
        paper_id = self.pmid or self.doi or f"{self.source}:{_slug(self.title)}"
        return {
            "paper_id": paper_id,
            "source_id": source_id,
            "title": _sanitize_jsonl_text(self.title),
            "abstract": _sanitize_jsonl_text(self.abstract),
            "pub_date": self.pub_date,
            "authors": [_sanitize_jsonl_text(a) for a in self.authors],
            "doi": _sanitize_jsonl_text(self.doi),
            "url": _sanitize_jsonl_text(self.url),
            "source": self.source,
            "pmid": self.pmid,
        }


def _read_pubmed_from_step01(abstracts_path: Path) -> list[PaperRecord]:
    if abstracts_path.suffix.lower() == ".jsonl":
        records = list(_read_jsonl_records(abstracts_path))
    else:
        data = json.loads(abstracts_path.read_text(encoding="utf-8"))
        records = data.get("records", []) or []
    out: list[PaperRecord] = []
    for r in records:
        out.append(
            PaperRecord(
                title=_as_str(r.get("title", "")),
                abstract=_as_str(r.get("abstract", "")),
                pub_date=_as_str(r.get("pub_date", "")),
                authors=_parse_authors(r.get("authors", [])),
                doi=_as_str(r.get("doi", "")),
                url="",
                source="pubmed",
                pmid=_as_str(r.get("pmid", "")),
            )
        )
    return out


def _read_jsonl_records(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _map_preprint_record(r: dict[str, Any], source: str) -> PaperRecord:
    title = _as_str(_pick(r, ["title", "paper_title", "name"]))
    abstract = _as_str(_pick(r, ["abstract", "summary", "description"]))
    pub_date = _parse_pub_date(r)
    authors = _parse_authors(r.get("authors") or r.get("author") or [])
    doi = _parse_doi(r)
    url = _as_str(_pick(r, ["url", "link", "doi_url", "publication_url"]))

    return PaperRecord(
        title=title,
        abstract=abstract,
        pub_date=pub_date,
        authors=authors,
        doi=doi,
        url=url,
        source=source,
        pmid="",
    )


def _dedup_records(records: list[PaperRecord]) -> list[PaperRecord]:
    seen_doi: set[str] = set()
    seen_title: set[str] = set()
    out: list[PaperRecord] = []
    for r in records:
        key_doi = (r.doi or "").lower()
        key_title = _norm_title(r.title)
        if key_doi:
            if key_doi in seen_doi:
                continue
            seen_doi.add(key_doi)
        elif key_title:
            if key_title in seen_title:
                continue
            seen_title.add(key_title)
        out.append(r)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 02: Extend paper list using paperscraper (metadata only, no ML).")
    parser.add_argument("--professor-name", required=True, help="教授姓名（用于构造 paperscraper 查询关键词）")
    parser.add_argument(
        "--step01-abstracts-json",
        default="",
        help="Step01 abstracts 路径（支持 .json 或 .jsonl）。不提供则通过 --step01-output-prefix 推断。",
    )
    parser.add_argument("--step01-output-prefix", default="", help="Step01 输出前缀，用于推断 abstracts json 路径。")
    parser.add_argument("--output-prefix", default="", help="Step02 输出前缀（默认从教授名生成）")
    parser.add_argument(
        "--server-dump-dir",
        default="02_paper_list_extend/data_sources/paperscraper_server_dumps/server_dumps",
        help="paperscraper server dumps 所在目录",
    )
    parser.add_argument("--skip-arxiv", action="store_true", help="跳过 arXiv API，只使用本地 xRxiv dumps 进行测试/执行")
    args = parser.parse_args()

    output_prefix = args.output_prefix or _slug(args.professor_name)
    step01_abstracts_json = args.step01_abstracts_json.strip()
    if not step01_abstracts_json:
        if not args.step01_output_prefix.strip():
            raise SystemExit("请提供 --step01-abstracts-json 或 --step01-output-prefix")
        base_dir = Path("01_data_collection/step_results/professor_paper_abstracts")
        jsonl_candidate = base_dir / f"{args.step01_output_prefix}_abstracts.jsonl"
        json_candidate = base_dir / f"{args.step01_output_prefix}_abstracts.json"
        if jsonl_candidate.exists():
            step01_abstracts_json = str(jsonl_candidate)
        else:
            step01_abstracts_json = str(json_candidate)

    abstracts_path = Path(step01_abstracts_json)
    if not abstracts_path.exists():
        raise FileNotFoundError(f"未找到 Step01 abstracts json：{abstracts_path}")

    query = _infer_query_from_professor(args.professor_name)

    # Import paperscraper only after argument validation to give a clearer error.
    try:
        from paperscraper.xrxiv.xrxiv_query import XRXivQuery
    except Exception as e:
        raise SystemExit(
            "paperscraper 未安装或导入失败。请先执行：pip install paperscraper\n"
            f"原始错误：{e}"
        )

    dump_dir = Path(args.server_dump_dir)

    step_results_dir = Path("02_paper_list_extend/step_results")
    raw_search_dir = step_results_dir / "raw_search"
    merged_dir = step_results_dir / "merged"
    final_dir = step_results_dir / "final"
    for p in [step_results_dir, raw_search_dir, merged_dir, final_dir]:
        p.mkdir(parents=True, exist_ok=True)

    pubmed_records = _read_pubmed_from_step01(abstracts_path)
    all_records: list[PaperRecord] = list(pubmed_records)

    # arXiv (no server dump required in basic mode; uses arXiv API)
    arxiv_out = raw_search_dir / f"{output_prefix}_arxiv.jsonl"
    if args.skip_arxiv:
        print("[info] 已跳过 arXiv，当前仅使用本地 dumps")
    elif _dump_arxiv_with_retry(query, arxiv_out):
        for r in _read_jsonl_records(arxiv_out):
            all_records.append(_map_preprint_record(r, "arxiv"))

    # bioRxiv / medRxiv / chemRxiv (requires server dump)
    for source in ["biorxiv", "medrxiv", "chemrxiv"]:
        dump_path = _try_latest_dump(dump_dir, source)
        if dump_path is None:
            print(f"[warn] 跳过 {source}：未找到本地 dump 文件（{dump_dir}）")
            continue
        out_path = raw_search_dir / f"{output_prefix}_{source}.jsonl"
        querier = XRXivQuery(str(dump_path))
        # query is list[list[str]] => keyword group matching
        querier.search_keywords(query, output_filepath=str(out_path))
        for r in _read_jsonl_records(out_path):
            all_records.append(_map_preprint_record(r, source))

    merged_out = merged_dir / f"{output_prefix}_all_records_before_dedup.jsonl"
    with merged_out.open("w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r.to_json(), ensure_ascii=False) + "\n")

    all_records = _dedup_records(all_records)

    out_jsonl = step_results_dir / f"{output_prefix}_expanded_papers.jsonl"
    final_jsonl = final_dir / f"{output_prefix}_expanded_papers.jsonl"

    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r.to_json(), ensure_ascii=False) + "\n")
    final_jsonl.write_text(out_jsonl.read_text(encoding="utf-8"), encoding="utf-8")

    print(out_jsonl)


if __name__ == "__main__":
    main()

