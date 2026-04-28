import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore

try:
    import pandera.pandas as pa  # type: ignore

    HAS_PANDERA = True
except Exception:  # pragma: no cover
    HAS_PANDERA = False


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_date(s: str) -> bool:
    s = (s or "").strip()
    if not s:
        return False
    if pd is not None:
        try:
            return bool(pd.notna(pd.to_datetime(s, errors="coerce")))
        except Exception:
            pass
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return True
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y"):
        try:
            datetime.strptime(s[: len(fmt)], fmt)
            return True
        except Exception:
            continue
    return False


@dataclass
class Finding:
    severity: str
    check: str
    detail: str


def _validate_required_fields(
    rows: list[dict[str, Any]], required: list[str], name: str, findings: list[Finding]
) -> None:
    if not rows:
        findings.append(Finding("error", f"{name}.rows", "no records"))
        return
    missing = 0
    for r in rows:
        if any(str(r.get(k, "")).strip() == "" for k in required):
            missing += 1
    if missing > 0:
        findings.append(Finding("error", f"{name}.required_fields", f"missing rows: {missing}/{len(rows)}"))


def _validate_schema_with_pandera(rows: list[dict[str, Any]], name: str, findings: list[Finding]) -> None:
    if not (HAS_PANDERA and pd is not None and rows):
        return
    try:
        df = pd.DataFrame(rows)
        schema = pa.DataFrameSchema(
            {
                "paper_id": pa.Column(str, nullable=False),
                "title": pa.Column(str, nullable=False),
            },
            strict=False,
        )
        schema.validate(df, lazy=True)
    except Exception as exc:
        findings.append(Finding("error", f"{name}.pandera", str(exc)[:300]))


def main() -> None:
    p = argparse.ArgumentParser(description="Step08 quality guard: integrity, linkage, dirty-data, readability checks.")
    p.add_argument("--prefix", required=True)
    p.add_argument("--output-json", required=True)
    p.add_argument("--output-md", required=True)
    args = p.parse_args()

    prefix = args.prefix
    files = {
        "step02": Path(f"02_paper_list_extend/step_results/{prefix}_expanded_papers.jsonl"),
        "step03": Path(f"03_author_disambiguation/step_results/{prefix}_step03_disambiguated_papers.jsonl"),
        "step04": Path(f"04_keyword_entity/step_results/{prefix}_step04_keyword_entity.jsonl"),
        "step05_paper": Path(f"05_domain_analysis/step_results/{prefix}_step05_paper_domains.jsonl"),
        "step05_domain": Path(f"05_domain_analysis/step_results/{prefix}_step05_domains.json"),
        "step05_wordcloud_terms": Path(f"05_domain_analysis/step_results/{prefix}_step05_wordcloud_terms.json"),
        "step05_wordcloud_image": Path(f"05_domain_analysis/step_results/{prefix}_step05_wordcloud.png"),
        "step06_timeline": Path(f"06_temporal_analysis/step_results/{prefix}_step06_project_timeline.json"),
        "step06_alloc": Path(f"06_temporal_analysis/step_results/{prefix}_step06_effort_allocation.json"),
        "step06_report": Path(f"06_temporal_analysis/step_results/{prefix}_step06_trend_report.md"),
    }

    findings: list[Finding] = []
    for k, path in files.items():
        if not path.exists():
            findings.append(Finding("error", f"{k}.exists", f"missing file: {path}"))

    s2 = _read_jsonl(files["step02"])
    s3 = _read_jsonl(files["step03"])
    s4 = _read_jsonl(files["step04"])
    s5p = _read_jsonl(files["step05_paper"])
    s5_obj = _read_json(files["step05_domain"])
    s5d = s5_obj.get("tags", []) or s5_obj.get("domains", [])
    s5_wc = _read_json(files["step05_wordcloud_terms"])

    _validate_required_fields(s2, ["paper_id", "title", "source"], "step02", findings)
    _validate_required_fields(s3, ["paper_id", "identity_score", "identity_decision"], "step03", findings)
    _validate_required_fields(s4, ["paper_id", "keywords", "quality_score"], "step04", findings)
    _validate_required_fields(s5p, ["paper_id", "primary_tag_name", "tag_items"], "step05_paper", findings)
    _validate_schema_with_pandera(s2, "step02", findings)
    _validate_schema_with_pandera(s3, "step03", findings)

    s2_ids = {str(x.get("paper_id", "")).strip() for x in s2 if str(x.get("paper_id", "")).strip()}
    s3_ids = {str(x.get("paper_id", "")).strip() for x in s3 if str(x.get("paper_id", "")).strip()}
    s4_ids = {str(x.get("paper_id", "")).strip() for x in s4 if str(x.get("paper_id", "")).strip()}
    s5_ids = {str(x.get("paper_id", "")).strip() for x in s5p if str(x.get("paper_id", "")).strip()}

    if not s3_ids.issubset(s2_ids):
        findings.append(Finding("error", "link.step02_step03", "step03 contains paper_id not in step02"))
    if not s4_ids.issubset(s3_ids):
        findings.append(Finding("error", "link.step03_step04", "step04 contains paper_id not in step03"))
    if not s5_ids.issubset(s4_ids):
        findings.append(Finding("error", "link.step04_step05", "step05 contains paper_id not in step04"))

    # Dirty-data checks
    bad_date = sum(1 for r in s2 if not _safe_date(str(r.get("pub_date", ""))))
    if bad_date > 0:
        findings.append(Finding("warn", "step02.pub_date", f"invalid/empty pub_date rows: {bad_date}"))
    empty_title = sum(1 for r in s2 if str(r.get("title", "")).strip() == "")
    if empty_title > 0:
        findings.append(Finding("error", "step02.title", f"empty title rows: {empty_title}"))

    # Readability checks for tag names
    bad_theme_tokens = ("影响s", "影响or", "包含主题", "相关主题", "研究主题")
    unreadable = 0
    tag_rows = s5d if isinstance(s5d, list) else []
    for d in tag_rows:
        theme = str(d.get("tag_name", "")).strip()
        if (not theme) or any(t in theme for t in bad_theme_tokens):
            unreadable += 1
    if unreadable > 0:
        findings.append(Finding("error", "step05.readability", f"unreadable tag names: {unreadable}"))

    wc_terms = s5_wc.get("terms", []) if isinstance(s5_wc, dict) else []
    if not isinstance(wc_terms, list) or not wc_terms:
        findings.append(Finding("warn", "step05.wordcloud_terms", "wordcloud terms are empty"))
    else:
        bad_wc = sum(1 for t in wc_terms if str((t or {}).get("term", "")).strip() == "")
        if bad_wc > 0:
            findings.append(Finding("error", "step05.wordcloud_terms", f"empty wordcloud terms: {bad_wc}"))

    # Pipeline completeness sanity
    counts = {"step02": len(s2), "step03": len(s3), "step04": len(s4), "step05": len(s5p)}
    if counts["step02"] > 0 and counts["step03"] == 0:
        findings.append(Finding("error", "pipeline.empty_step03", "step03 has zero rows"))
    if counts["step03"] > 0 and counts["step04"] == 0:
        findings.append(Finding("error", "pipeline.empty_step04", "step04 has zero rows"))
    if counts["step04"] > 0 and counts["step05"] == 0:
        findings.append(Finding("error", "pipeline.empty_step05", "step05 has zero rows"))

    errors = [f for f in findings if f.severity == "error"]
    warns = [f for f in findings if f.severity == "warn"]
    status = "pass" if not errors else "fail"
    out = {
        "prefix": prefix,
        "status": status,
        "counts": counts,
        "summary": {"errors": len(errors), "warnings": len(warns)},
        "findings": [f.__dict__ for f in findings],
        "uses_pandera": HAS_PANDERA,
    }

    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Step08 Quality Guard ({prefix})",
        "",
        f"- status: **{status}**",
        f"- errors: {len(errors)}",
        f"- warnings: {len(warns)}",
        f"- uses_pandera: {HAS_PANDERA}",
        "",
        "## Counts",
        "",
    ]
    for k, v in counts.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if findings:
        for f in findings:
            lines.append(f"- [{f.severity}] `{f.check}`: {f.detail}")
    else:
        lines.append("- none")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(str(out_json))
    print(str(out_md))
    if status != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

