from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _parse_pub_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    # Try YYYY-MM-DD, YYYY-MM, YYYY
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.date()
        except Exception:
            continue
    return None


@dataclass
class Item:
    paper_id: str
    domain: str
    d: date
    w: float
    q: float


def main() -> None:
    p = argparse.ArgumentParser(description="Step 07 (baseline): temporal effort allocation + trends.")
    p.add_argument("--input", required=True, help="Step06 paper_domains JSONL (may be joined with Step05 fields upstream)")
    p.add_argument("--timeline-output", required=True, help="Output JSON: per-domain timeline buckets")
    p.add_argument("--allocation-output", required=True, help="Output JSON: share_current per domain")
    p.add_argument("--report-output", required=True, help="Output MD: readable summary")
    p.add_argument("--tau-days", type=int, default=365, help="Exponential decay tau in days")
    args = p.parse_args()

    rows = _read_jsonl(Path(args.input))
    today = date.today()
    tau = max(1, int(args.tau_days))

    items: list[Item] = []
    for r in rows:
        paper_id = str(r.get("paper_id") or "")
        domain = str(r.get("domain_label") or "domain_unknown")
        pub_date = _parse_pub_date(str(r.get("pub_date") or r.get("publication_date") or ""))
        if pub_date is None:
            continue
        identity_score = float(r.get("identity_score", 1.0) or 1.0)
        quality_score = float(r.get("quality_score", 0.0) or 0.0)
        quality_score = max(0.0, min(1.0, quality_score))
        age_days = max(0, (today - pub_date).days)
        decay = math.exp(-age_days / float(tau))
        # Combined effort weight: identity confidence * (frequency + quality impact) * time decay
        effort_factor = 0.6 + 0.4 * quality_score
        w = decay * max(0.0, min(1.0, identity_score)) * effort_factor
        items.append(Item(paper_id=paper_id, domain=domain, d=pub_date, w=w, q=quality_score))

    # Timeline: year buckets (effort and quality)
    timeline: dict[str, dict[str, float]] = {}
    timeline_quality: dict[str, dict[str, float]] = {}
    timeline_count: dict[str, dict[str, int]] = {}
    for it in items:
        y = str(it.d.year)
        timeline.setdefault(it.domain, {})
        timeline[it.domain][y] = timeline[it.domain].get(y, 0.0) + it.w
        timeline_quality.setdefault(it.domain, {})
        timeline_quality[it.domain][y] = timeline_quality[it.domain].get(y, 0.0) + it.q
        timeline_count.setdefault(it.domain, {})
        timeline_count[it.domain][y] = timeline_count[it.domain].get(y, 0) + 1

    # Allocation
    scores: dict[str, float] = {}
    for it in items:
        scores[it.domain] = scores.get(it.domain, 0.0) + it.w
    total = sum(scores.values()) or 1.0
    shares = {k: v / total for k, v in scores.items()}

    allocation = {
        "tau_days": tau,
        "total_weight": total,
        "share_current": [{"project_or_domain": k, "share_current": round(shares[k], 6), "weight": round(scores[k], 4)} for k in sorted(scores, key=scores.get, reverse=True)],
    }
    timeline_out = {
        "timeline": [
            {
                "project_or_domain": k,
                "year_weights": timeline.get(k, {}),
                "year_avg_quality": {
                    y: round(timeline_quality.get(k, {}).get(y, 0.0) / max(1, timeline_count.get(k, {}).get(y, 0)), 6)
                    for y in sorted(timeline_count.get(k, {}).keys())
                },
            }
            for k in sorted(timeline.keys())
        ]
    }

    # Trend heuristic: compare last 1 year vs previous 1 year (by pub_date count weights)
    one_year = 365
    trend_rows: list[dict[str, Any]] = []
    for domain in scores.keys():
        recent = 0.0
        past = 0.0
        recent_q = 0.0
        past_q = 0.0
        recent_n = 0
        past_n = 0
        for it in items:
            if it.domain != domain:
                continue
            delta = (today - it.d).days
            if delta <= one_year:
                recent += it.w
                recent_q += it.q
                recent_n += 1
            elif delta <= 2 * one_year:
                past += it.w
                past_q += it.q
                past_n += 1
        ratio = (recent + 1e-6) / (past + 1e-6)
        trend_rows.append(
            {
                "project_or_domain": domain,
                "trend_future": round(ratio, 4),
                "recent_weight": round(recent, 4),
                "past_weight": round(past, 4),
                "recent_avg_quality": round(recent_q / max(1, recent_n), 6),
                "past_avg_quality": round(past_q / max(1, past_n), 6),
            }
        )
    trend_rows.sort(key=lambda r: r["trend_future"], reverse=True)

    md_lines = [
        "# Step07 Temporal Analysis Report (baseline)",
        "",
        f"- tau_days: {tau}",
        f"- total_papers_used: {len(items)}",
        "",
        "## share_current（当前投入比例；按时间衰减加权）",
        "",
    ]
    for row in allocation["share_current"][:20]:
        md_lines.append(f"- **{row['project_or_domain']}**: share_current={row['share_current']}, weight={row['weight']}")
    md_lines += ["", "## trend_future（趋势比值：近1年/前1年）", ""]
    for row in trend_rows[:20]:
        md_lines.append(
            f"- **{row['project_or_domain']}**: trend_future={row['trend_future']} (recent={row['recent_weight']}, past={row['past_weight']})"
        )

    _write_json(Path(args.timeline_output), timeline_out)
    _write_json(Path(args.allocation_output), {"allocation": allocation, "trend": trend_rows})
    _write_md(Path(args.report_output), "\n".join(md_lines) + "\n")
    print(args.timeline_output)
    print(args.allocation_output)
    print(args.report_output)


if __name__ == "__main__":
    main()

