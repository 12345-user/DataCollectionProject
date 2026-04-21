from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").split("\n"):
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _parse_pub_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


def main() -> None:
    p = argparse.ArgumentParser(description="Build DuckDB for Step07 visualization (single-file DB).")
    p.add_argument("--professor", required=True, help="Professor identifier (e.g. wanling_yang)")
    p.add_argument("--paper-domains", required=True, help="Step05 paper_domains JSONL")
    p.add_argument("--duckdb-path", required=True, help="DuckDB file path (e.g. 07_temporal_analysis/step_results/pipeline.duckdb)")
    args = p.parse_args()

    professor = str(args.professor).strip()
    rows = _read_jsonl(Path(args.paper_domains))

    out: list[dict[str, Any]] = []
    for r in rows:
        d = _parse_pub_date(str(r.get("pub_date") or r.get("publication_date") or ""))
        out.append(
            {
                "professor": professor,
                "paper_id": str(r.get("paper_id") or ""),
                "title": str(r.get("title") or ""),
                "pub_date": d.isoformat() if d else None,
                "domain_label": str(r.get("domain_label") or "domain_unknown"),
                "domain_theme": str(r.get("domain_theme") or "").strip(),
                "domain_confidence": float(r.get("domain_confidence", 1.0) or 1.0),
                "identity_score": float(r.get("identity_score", 1.0) or 1.0),
                # placeholder: quality_score can be replaced later by citations / venue score / model-based score
                "quality_score": float(r.get("quality_score", 1.0) or 1.0),
            }
        )

    db_path = Path(args.duckdb_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    con.execute(
        """
        create table if not exists paper_domains (
          professor varchar,
          paper_id varchar,
          title varchar,
          pub_date date,
          domain_label varchar,
          domain_theme varchar,
          domain_confidence double,
          identity_score double,
          quality_score double
        )
        """
    )
    # Compatible migration for existing databases created before domain_theme field.
    cols = [r[1] for r in con.execute("pragma table_info('paper_domains')").fetchall()]
    if "domain_theme" not in cols:
        con.execute("alter table paper_domains add column domain_theme varchar")
    con.execute("delete from paper_domains where professor = ?", [professor])
    df = pd.DataFrame(out)
    con.register("tmp_rows", df)
    con.execute(
        """
        insert into paper_domains (
          professor,
          paper_id,
          title,
          pub_date,
          domain_label,
          domain_theme,
          domain_confidence,
          identity_score,
          quality_score
        )
        select
          professor,
          paper_id,
          title,
          cast(pub_date as date),
          domain_label,
          domain_theme,
          domain_confidence,
          identity_score,
          quality_score
        from tmp_rows
        """
    )

    con.execute(
        """
        create table if not exists professors (
          professor varchar primary key
        )
        """
    )
    con.execute("insert or ignore into professors values (?)", [professor])

    # Convenience views for visualization
    con.execute(
        """
        create or replace view v_domain_share as
        select
          professor,
          coalesce(nullif(domain_theme, ''), domain_label) as domain_name,
          sum(identity_score * quality_score) as weight
        from paper_domains
        where pub_date is not null
        group by professor, domain_name
        """
    )

    con.execute(
        """
        create or replace view v_domain_time as
        select
          professor,
          coalesce(nullif(domain_theme, ''), domain_label) as domain_name,
          date_trunc('quarter', pub_date) as month,
          count(*) as paper_count,
          sum(identity_score * quality_score) as weight
        from paper_domains
        where pub_date is not null and pub_date >= date '2021-01-01'
        group by professor, domain_name, month
        """
    )

    con.close()
    print(str(db_path))


if __name__ == "__main__":
    main()

