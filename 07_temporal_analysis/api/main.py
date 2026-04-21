from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import duckdb
from fastapi import FastAPI, Query


def _connect(db_path: str) -> duckdb.DuckDBPyConnection:
    p = Path(db_path)
    if not p.exists():
        raise FileNotFoundError(f"DuckDB not found: {p}")
    return duckdb.connect(str(p), read_only=True)


app = FastAPI(title="Step07 Visualization API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/professors")
def list_professors(db: str = Query(..., description="DuckDB file path")) -> list[str]:
    con = _connect(db)
    rows = con.execute("select professor from professors order by professor").fetchall()
    con.close()
    return [r[0] for r in rows]


@app.get("/domain_share")
def domain_share(
    db: str = Query(..., description="DuckDB file path"),
    professor: str = Query(...),
    start: date | None = Query(None),
    end: date | None = Query(None),
) -> list[dict[str, Any]]:
    con = _connect(db)
    where = ["professor = ?"]
    params: list[Any] = [professor]
    if start is not None:
        where.append("pub_date >= ?")
        params.append(start)
    if end is not None:
        where.append("pub_date <= ?")
        params.append(end)
    sql = f"""
      select domain_name, sum(weight) as weight
      from v_domain_share
      where {' and '.join(where)}
      group by domain_name
      order by weight desc
    """
    rows = con.execute(sql, params).fetchall()
    con.close()
    return [{"domain_name": r[0], "weight": float(r[1])} for r in rows]


@app.get("/domain_time")
def domain_time(
    db: str = Query(..., description="DuckDB file path"),
    professor: str = Query(...),
    start: date | None = Query(None),
    end: date | None = Query(None),
) -> list[dict[str, Any]]:
    con = _connect(db)
    where = ["professor = ?"]
    params: list[Any] = [professor]
    if start is not None:
        where.append("month >= date_trunc('quarter', ?)")
        params.append(start)
    if end is not None:
        where.append("month <= date_trunc('quarter', ?)")
        params.append(end)
    sql = f"""
      select domain_name, month, paper_count, weight
      from v_domain_time
      where {' and '.join(where)}
      order by month asc, domain_name asc
    """
    rows = con.execute(sql, params).fetchall()
    con.close()
    return [
        {
            "domain_name": r[0],
            "month": r[1].isoformat() if r[1] is not None else None,
            "paper_count": int(r[2]),
            "weight": float(r[3]),
        }
        for r in rows
    ]

