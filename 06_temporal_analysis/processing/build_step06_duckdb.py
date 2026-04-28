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
    p.add_argument("--paper-domains", required=True, help="Step05 paper tags JSONL")
    p.add_argument("--duckdb-path", required=True, help="DuckDB file path (e.g. 07_visualization/step_results/pipeline.duckdb)")
    args = p.parse_args()

    professor = str(args.professor).strip()
    rows = _read_jsonl(Path(args.paper_domains))

    out: list[dict[str, Any]] = []
    for r in rows:
        d = _parse_pub_date(str(r.get("pub_date") or r.get("publication_date") or ""))

        # L1/L2/L3 tags + detailed tags (L4 kept for paper tag details)
        layer_rows: list[dict[str, Any]] = []
        l1 = str(r.get("layer_l1_tag") or "").strip()
        if l1:
            layer_rows.append({"level": 1, "tag_name": l1, "tag_weight": 1.0})
        l2_items = r.get("layer_l2_items") or []
        if isinstance(l2_items, list):
            for t in l2_items:
                if isinstance(t, dict):
                    layer_rows.append(
                        {
                            "level": 2,
                            "tag_name": t.get("tag_name"),
                            "tag_weight": t.get("tag_weight", 0.0),
                        }
                    )
        l3_items = r.get("layer_l3_items") or []
        if isinstance(l3_items, list):
            for t in l3_items:
                if isinstance(t, dict):
                    layer_rows.append(
                        {
                            "level": 3,
                            "tag_name": t.get("tag_name"),
                            "tag_weight": t.get("tag_weight", 0.0),
                        }
                    )

        for t in layer_rows:
            tag_name = str(t.get("tag_name") or "").strip()
            if not tag_name:
                continue
            try:
                tag_weight = float(t.get("tag_weight", 0.0) or 0.0)
            except Exception:
                tag_weight = 0.0
            if tag_weight <= 0.0:
                continue
            out.append(
                {
                    "professor": professor,
                    "paper_id": str(r.get("paper_id") or ""),
                    "title": str(r.get("title") or ""),
                    "pub_date": d.isoformat() if d else None,
                    "level": int(t.get("level") or 0),
                    "tag_name": tag_name,
                    "tag_weight": tag_weight,
                    "identity_score": float(r.get("identity_score", 1.0) or 1.0),
                    "quality_score": float(r.get("quality_score", 1.0) or 1.0),
                }
            )

        tag_items = r.get("tag_items") or []
        if not isinstance(tag_items, list) or not tag_items:
            fallback = str(r.get("primary_tag_name") or r.get("domain_label") or "综合标签")
            tag_items = [{"tag_name": fallback, "tag_weight": 1.0}]
        for t in tag_items:
            tag_name = str(t.get("tag_name") or "").strip()
            if not tag_name:
                continue
            try:
                tag_weight = float(t.get("tag_weight", 0.0) or 0.0)
            except Exception:
                tag_weight = 0.0
            if tag_weight <= 0.0:
                continue
            out.append(
                {
                    "professor": professor,
                    "paper_id": str(r.get("paper_id") or ""),
                    "title": str(r.get("title") or ""),
                    "pub_date": d.isoformat() if d else None,
                    "level": 4,
                    "tag_name": tag_name,
                    "tag_weight": tag_weight,
                    "identity_score": float(r.get("identity_score", 1.0) or 1.0),
                    "quality_score": float(r.get("quality_score", 1.0) or 1.0),
                }
            )

    db_path = Path(args.duckdb_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    con.execute(
        """
        create table if not exists paper_tags (
          professor varchar,
          paper_id varchar,
          title varchar,
          pub_date date,
          level integer,
          tag_name varchar,
          tag_weight double,
          identity_score double,
          quality_score double
        )
        """
    )
    cols = [r[1] for r in con.execute("pragma table_info('paper_tags')").fetchall()]
    if "level" not in cols:
        con.execute("alter table paper_tags add column level integer")
    con.execute("delete from paper_tags where professor = ?", [professor])
    df = pd.DataFrame(out)
    con.register("tmp_rows", df)
    con.execute(
        """
        insert into paper_tags (
          professor,
          paper_id,
          title,
          pub_date,
          level,
          tag_name,
          tag_weight,
          identity_score,
          quality_score
        )
        select
          professor,
          paper_id,
          title,
          cast(pub_date as date),
          level,
          tag_name,
          tag_weight,
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
        create or replace view v_tag_share as
        select
          professor,
          level,
          tag_name,
          sum(identity_score * quality_score * tag_weight) as weight
        from paper_tags
        where pub_date is not null
        group by professor, level, tag_name
        """
    )

    con.execute(
        """
        create or replace view v_tag_time as
        select
          professor,
          level,
          tag_name,
          date_trunc('quarter', pub_date) as month,
          count(distinct paper_id) as paper_count,
          sum(identity_score * quality_score * tag_weight) as weight
        from paper_tags
        where pub_date is not null and pub_date >= date '2021-01-01'
        group by professor, level, tag_name, month
        """
    )

    con.close()
    print(str(db_path))


if __name__ == "__main__":
    main()

