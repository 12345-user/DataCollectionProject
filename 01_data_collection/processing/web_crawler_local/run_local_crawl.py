from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


USER_AGENT = "ECE4010-DataCollectionBot/0.1"
MAX_LINKS = 20


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


@dataclass
class CrawlRecord:
    url: str
    fetched_at_utc: str
    status: str
    title: str
    links: list[str]
    snippet: str
    error: str | None = None


def extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def extract_snippet(html: str, max_length: int = 280) -> str:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_length]


def crawl_url(url: str) -> CrawlRecord:
    now = datetime.now(timezone.utc).isoformat()
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
            parser = LinkParser()
            parser.feed(html)
            normalized_links = []
            for link in parser.links:
                abs_link = urljoin(url, link)
                normalized_links.append(abs_link)
                if len(normalized_links) >= MAX_LINKS:
                    break
            return CrawlRecord(
                url=url,
                fetched_at_utc=now,
                status="ok",
                title=extract_title(html),
                links=normalized_links,
                snippet=extract_snippet(html),
            )
    except (URLError, TimeoutError, ValueError) as exc:
        return CrawlRecord(
            url=url,
            fetched_at_utc=now,
            status="error",
            title="",
            links=[],
            snippet="",
            error=str(exc),
        )


def read_urls(url_file: Path) -> list[str]:
    urls: list[str] = []
    for line in url_file.read_text(encoding="utf-8").splitlines():
        # Remove UTF-8 BOM if present (Windows PowerShell Set-Content -Encoding utf8 adds BOM).
        stripped = line.strip().lstrip("\ufeff")
        if stripped and not stripped.startswith("#"):
            urls.append(stripped)
    return urls


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    url_file = base_dir / "crawl_urls.txt"
    # Step-01: 本地网页抓取结果作为“实验室/机构线索”的辅助证据
    output_dir = base_dir.parent.parent / "step_results" / "professor_lab_info"
    output_dir.mkdir(parents=True, exist_ok=True)

    urls = read_urls(url_file)
    records = [crawl_url(url) for url in urls]

    json_path = output_dir / "local_crawl_results.json"
    md_path = output_dir / "local_crawl_results.md"

    json_path.write_text(
        json.dumps([asdict(record) for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = ["# Local Crawl Results", ""]
    for record in records:
        lines.append(f"## {record.url}")
        lines.append(f"- status: {record.status}")
        lines.append(f"- title: {record.title or '(none)'}")
        if record.error:
            lines.append(f"- error: {record.error}")
        lines.append(f"- links_collected: {len(record.links)}")
        lines.append(f"- snippet: {record.snippet or '(none)'}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote: {json_path}")
    print(f"Wrote: {md_path}")


if __name__ == "__main__":
    main()
