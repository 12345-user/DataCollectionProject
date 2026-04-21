from __future__ import annotations

import json
import re
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import duckdb
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from statsmodels.tsa.arima.model import ARIMA
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    HAS_STATSMODELS = True
except Exception:
    HAS_STATSMODELS = False


def _connect(db_path: str) -> duckdb.DuckDBPyConnection:
    p = Path(db_path)
    if not p.exists():
        raise FileNotFoundError(f"DuckDB not found: {p}")
    return duckdb.connect(str(p), read_only=True)


def _load_professors(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute("select professor from professors order by professor").fetchall()
    return [r[0] for r in rows]


def _source_to_site(source: str) -> str:
    s = (source or "").strip().lower()
    mapping = {
        "pubmed": "https://pubmed.ncbi.nlm.nih.gov/",
        "arxiv": "https://arxiv.org/",
        "biorxiv": "https://www.biorxiv.org/",
        "medrxiv": "https://www.medrxiv.org/",
        "chemrxiv": "https://chemrxiv.org/",
        "openaire": "https://explore.openaire.eu/",
    }
    return mapping.get(s, "")


def _load_source_sites(professor: str) -> list[str]:
    sites: list[str] = []
    seen: set[str] = set()

    # 1) Inferred from Step02 sources
    step02 = Path(f"02_paper_list_extend/step_results/{professor}_expanded_papers.jsonl")
    for r in _read_jsonl(step02):
        site = _source_to_site(str(r.get("source") or ""))
        if site and site not in seen:
            seen.add(site)
            sites.append(site)

    # 2) User-provided extra source URLs from one-click metadata
    meta = Path(f"07_temporal_analysis/step_results/{professor}_source_sites.json")
    if meta.exists():
        try:
            obj = json.loads(meta.read_text(encoding="utf-8"))
            for u in obj.get("input_extra_urls", []) or []:
                us = str(u).strip()
                if us and us not in seen:
                    seen.add(us)
                    sites.append(us)
        except Exception:
            pass

    return sites


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _is_first_author(authors: list[str], target_author: str) -> str:
    if not authors:
        return "未知"
    if not target_author.strip():
        return "未设置目标作者"
    first_raw = str(authors[0] or "").strip()
    target_raw = str(target_author or "").strip()
    if not first_raw or not target_raw:
        return "未知"

    def _name_parts(s: str) -> tuple[str, str]:
        s = s.strip()
        if "," in s:
            parts = [x.strip() for x in s.split(",", 1)]
            last = re.sub(r"[^a-z]", "", parts[0].lower())
            given = re.sub(r"[^a-z]", "", parts[1].lower() if len(parts) > 1 else "")
            return last, given
        toks = [re.sub(r"[^a-z]", "", t.lower()) for t in re.split(r"[\s\-\.]+", s) if t.strip()]
        toks = [t for t in toks if t]
        if not toks:
            return "", ""
        return toks[-1], "".join(toks[:-1])

    f_last, f_given = _name_parts(first_raw)
    t_last, t_given = _name_parts(target_raw)
    if not f_last or not t_last or f_last != t_last:
        return "否"
    # Given-name tolerance: initials or partial matching.
    if not t_given:
        return "是"
    if not f_given:
        return "否"
    ok = f_given.startswith(t_given[:1]) or t_given.startswith(f_given[:1]) or (t_given in f_given) or (f_given in t_given)
    return "是" if ok else "否"


def _to_keyword_text(raw_keywords: object, topn: int = 6) -> str:
    if not raw_keywords:
        return ""
    out: list[str] = []
    if isinstance(raw_keywords, list):
        for item in raw_keywords:
            if isinstance(item, str):
                out.append(item.strip())
            elif isinstance(item, (list, tuple)) and item:
                out.append(str(item[0]).strip())
            elif isinstance(item, dict):
                out.append(str(item.get("keyword", "")).strip())
            if len(out) >= topn:
                break
    return "；".join([x for x in out if x])


def _kw_to_cn(kw: str) -> str:
    s = (kw or "").strip()
    if not s:
        return ""
    low = s.lower()
    token_map = {
        "atad2": "ATAD2",
        "bromodomain": "溴结构域",
        "oncogenic": "致癌",
        "chromatin": "染色质",
        "anti cancer": "抗肿瘤",
        "proliferative": "增殖",
        "cell cycle": "细胞周期",
        "targeted therapies": "靶向治疗",
        "omega-3": "Omega-3",
        "omega 3": "Omega-3",
        "metabolic": "代谢",
        "ferroptosis": "铁死亡",
        "oxidative": "氧化应激",
        "hydrogel": "水凝胶",
        "nanoparticle": "纳米颗粒",
        "drug target": "药物靶点",
        "diagnostic": "诊断",
        "sequencing": "测序",
        "glioblastoma": "胶质母细胞瘤",
        "tumor": "肿瘤",
    }
    for k, v in token_map.items():
        low = low.replace(k, v)
    low = re.sub(r"\s+", " ", low).strip()
    # If still mostly English, convert to "X相关" short Chinese style.
    if re.fullmatch(r"[A-Za-z0-9\-/\s]+", low):
        core = low.strip()
        return f"{core}相关"
    return low


def _build_related_keywords_cn(
    domain_theme_cn: str,
    domain_keywords: list[str] | None,
    paper_keywords: list[str] | None,
    max_total: int = 5,
) -> str:
    domain_keywords = domain_keywords or []
    paper_keywords = paper_keywords or []
    picked: list[str] = []
    seen: set[str] = set()

    # Domain keywords first: keep high relevance.
    for kw in domain_keywords[:3]:
        cn = _kw_to_cn(str(kw))
        key = _norm_name(cn)
        if cn and key and key not in seen:
            seen.add(key)
            picked.append(cn)
        if len(picked) >= max_total:
            break

    # Paper keywords: enrich slightly, not too much.
    if len(picked) < max_total:
        for kw in paper_keywords:
            cn = _kw_to_cn(str(kw))
            key = _norm_name(cn)
            if cn and key and key not in seen:
                seen.add(key)
                picked.append(cn)
            if len(picked) >= max_total:
                break

    # Ensure Chinese context via domain theme prefix.
    prefix = f"{(domain_theme_cn or '').strip()}："
    return prefix + "；".join(picked[:max_total]) if picked else (domain_theme_cn or "")


def _load_paper_catalog(
    professor: str,
    start: date | None,
    end: date | None,
    target_author: str,
    strict_only: bool = True,
) -> pd.DataFrame:
    step03 = Path(f"04_author_disambiguation/step_results/{professor}_step03_disambiguated_papers.jsonl")
    step05 = Path(f"06_domain_clustering/step_results/{professor}_step05_paper_domains.jsonl")
    step04 = Path(f"05_keyword_entity/step_results/{professor}_step04_keyword_entity.jsonl")
    step02 = Path(f"02_paper_list_extend/step_results/{professor}_expanded_papers.jsonl")

    step03_rows = _read_jsonl(step03)
    step05_rows = _read_jsonl(step05)
    step04_rows = _read_jsonl(step04)
    step02_rows = _read_jsonl(step02)

    by_id_step05 = {str(r.get("paper_id") or ""): r for r in step05_rows if str(r.get("paper_id") or "")}
    by_id_step04 = {str(r.get("paper_id") or ""): r for r in step04_rows if str(r.get("paper_id") or "")}

    # Default strict mode: only keep identity_decision=True rows.
    rows: list[dict] = step03_rows
    if rows and strict_only:
        rows = [r for r in rows if str(r.get("identity_decision") or "").strip().lower() == "true"]

    # Fallback only when Step03 is unavailable.
    if not rows:
        rows = step04_rows if step04_rows else step02_rows

    out_rows: list[dict[str, object]] = []
    for r in rows:
        pid = str(r.get("paper_id") or "")
        r05 = by_id_step05.get(pid, {})
        r04 = by_id_step04.get(pid, r)
        title = str(r.get("title") or "").strip()
        if not title:
            continue

        pub_date_raw = str(r.get("pub_date") or r.get("publication_date") or "").strip()
        pub_ts = pd.to_datetime(pub_date_raw, errors="coerce")
        if pd.isna(pub_ts):
            pub_date_show = ""
        else:
            pub_date_show = pub_ts.date().isoformat()
            if start is not None and pub_ts.date() < start:
                continue
            if end is not None and pub_ts.date() > end:
                continue

        authors = r.get("authors") or []
        if not isinstance(authors, list):
            authors = [str(authors)] if authors else []

        out_rows.append(
            {
                "论文名称": title,
                "发表期刊": str(r.get("venue") or r.get("journal") or "").strip(),
                "发表时间": pub_date_show,
                "论文来源": str(r.get("source") or "").strip(),
                "消歧判定": str(r.get("identity_decision") or ""),
                "消歧分数": (
                    float(r.get("identity_score", 0.0) or 0.0)
                    if str(r.get("identity_score", "")).strip() != ""
                    else None
                ),
                "一作是否目标作者": _is_first_author(authors, target_author),
                "主要概要关键词": _build_related_keywords_cn(
                    str(r05.get("domain_theme_cn") or r05.get("domain_theme") or ""),
                    list(r05.get("domain_keywords") or []),
                    list(r04.get("keywords") or []),
                    max_total=5,
                ),
                "首位作者": (str(authors[0]).strip() if authors else ""),
            }
        )
    df = pd.DataFrame(out_rows)
    if not df.empty:
        df = df.sort_values("发表时间", ascending=False).reset_index(drop=True)
    return df


def _run_oneclick_pipeline(
    professor_name: str,
    seed_paper_title: str,
    seed_pmid: str,
    extra_source_urls: list[str],
    output_prefix: str,
) -> tuple[bool, str]:
    cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "scripts/run_full_pipeline_oneclick.ps1",
        "-ProfessorName",
        professor_name,
        "-SeedPaperTitle",
        seed_paper_title,
        "-OutputPrefix",
        output_prefix,
        "-NoStartWeb",
    ]
    if seed_pmid.strip():
        cmd.extend(["-SeedPMID", seed_pmid.strip()])
    if extra_source_urls:
        cmd.extend(["-ExtraSourceUrls", *extra_source_urls])

    try:
        cp = subprocess.run(
            cmd,
            cwd=str(Path(__file__).resolve().parents[2]),
            text=True,
            capture_output=True,
            timeout=1800,
            check=False,
        )
    except Exception as e:
        return False, f"执行异常：{e}"

    out = (cp.stdout or "") + ("\n" + cp.stderr if cp.stderr else "")
    ok = cp.returncode == 0
    return ok, out.strip()


def _domain_share_df(con: duckdb.DuckDBPyConnection, professor: str, start: date | None, end: date | None) -> pd.DataFrame:
    where = ["professor = ?"]
    params: list[object] = [professor]
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
    return con.execute(sql, params).df()


def _domain_time_df(con: duckdb.DuckDBPyConnection, professor: str, start: date | None, end: date | None) -> pd.DataFrame:
    where = ["professor = ?"]
    params: list[object] = [professor]
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
    df = con.execute(sql, params).df()
    if not df.empty:
        df["month"] = pd.to_datetime(df["month"])
    return df


def _predict_next_quarters(df_time: pd.DataFrame, value_col: str, steps: int = 4) -> pd.DataFrame:
    if df_time.empty:
        return pd.DataFrame(columns=["month", "domain_name", value_col, "series_type"])
    now_q_start = pd.Timestamp.now().to_period("Q").start_time
    out_rows: list[dict[str, object]] = []
    for domain, grp in df_time.groupby("domain_name"):
        g = grp.sort_values("month")
        y = g[value_col].astype(float).to_numpy()
        if len(y) < 2:
            continue
        x = np.arange(len(y), dtype=float)
        coef = np.polyfit(x, y, deg=1)
        future_x = np.arange(len(y), len(y) + steps, dtype=float)
        future_y = np.maximum(0.0, coef[0] * future_x + coef[1])
        last_ts = pd.Timestamp(g["month"].max())
        # Predict from current quarter (e.g. 2026-04), unless history already reached it.
        first_pred_ts = now_q_start if now_q_start > last_ts else (last_ts + pd.DateOffset(months=3))
        for i, pred in enumerate(future_y, start=0):
            out_rows.append(
                {
                    "month": first_pred_ts + pd.DateOffset(months=3 * i),
                    "domain_name": domain,
                    value_col: float(pred),
                    "series_type": "预测",
                }
            )
    return pd.DataFrame(out_rows)


def _mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = np.maximum(np.abs(y_true), 1e-6)
    return float(np.mean(np.abs((y_true - y_pred) / denom)) * 100.0)


def _quarter_start_now() -> pd.Timestamp:
    return pd.Timestamp.now().to_period("Q").start_time


def _period_start(ts: pd.Timestamp, months_step: int) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    if months_step == 12:
        return pd.Timestamp(year=ts.year, month=1, day=1)
    if months_step == 6:
        return pd.Timestamp(year=ts.year, month=1 if ts.month <= 6 else 7, day=1)
    # default: quarter
    q_month = ((ts.month - 1) // 3) * 3 + 1
    return pd.Timestamp(year=ts.year, month=q_month, day=1)


def _period_start_now(months_step: int) -> pd.Timestamp:
    return _period_start(pd.Timestamp.now(), months_step)


def _period_index(start: pd.Timestamp, end: pd.Timestamp, months_step: int) -> list[pd.Timestamp]:
    out: list[pd.Timestamp] = []
    cur = _period_start(start, months_step)
    end = _period_start(end, months_step)
    while cur <= end:
        out.append(cur)
        cur = cur + pd.DateOffset(months=months_step)
    return out


def _prepare_series(df_time: pd.DataFrame, domain: str, value_col: str, months_step: int = 3) -> pd.Series:
    g = df_time[df_time["domain_name"] == domain].copy().sort_values("month")
    if g.empty:
        return pd.Series(dtype=float)
    idx = _period_index(pd.Timestamp(g["month"].min()), pd.Timestamp(g["month"].max()), months_step)
    s = g.set_index("month")[value_col].astype(float).reindex(idx, fill_value=0.0)
    s.index.name = "month"
    return s


def _to_halfyear(df_time: pd.DataFrame) -> pd.DataFrame:
    if df_time.empty:
        return df_time
    out = df_time.copy()
    out["month"] = out["month"].apply(lambda x: _period_start(pd.Timestamp(x), 6))
    return (
        out.groupby(["domain_name", "month"], as_index=False)[["paper_count", "weight"]]
        .sum()
        .sort_values(["month", "domain_name"])
    )


def _to_year(df_time: pd.DataFrame) -> pd.DataFrame:
    if df_time.empty:
        return df_time
    out = df_time.copy()
    out["month"] = out["month"].apply(lambda x: _period_start(pd.Timestamp(x), 12))
    return (
        out.groupby(["domain_name", "month"], as_index=False)[["paper_count", "weight"]]
        .sum()
        .sort_values(["month", "domain_name"])
    )


def _fill_history_quarters(
    df_time: pd.DataFrame,
    value_col: str,
    min_start: str = "2021-01-01",
    months_step: int = 3,
) -> pd.DataFrame:
    if df_time.empty:
        return pd.DataFrame(columns=["month", "domain_name", value_col, "series_type"])
    start = max(pd.Timestamp(min_start), _period_start(pd.Timestamp(df_time["month"].min()), months_step))
    end = _period_start(pd.Timestamp(df_time["month"].max()), months_step)
    q_idx = _period_index(start, end, months_step)
    rows: list[dict[str, object]] = []
    for domain in sorted(df_time["domain_name"].dropna().unique()):
        g = df_time[df_time["domain_name"] == domain].copy()
        s = g.set_index("month")[value_col].astype(float).reindex(q_idx, fill_value=0.0)
        for ts, val in s.items():
            rows.append(
                {
                    "month": pd.Timestamp(ts),
                    "domain_name": domain,
                    value_col: float(max(0.0, val)),
                    "series_type": "历史",
                }
            )
    return pd.DataFrame(rows)


def _quarter_tick_labels(start: pd.Timestamp, end: pd.Timestamp) -> tuple[list[pd.Timestamp], list[str]]:
    idx = pd.date_range(start=start.to_period("Q").start_time, end=end.to_period("Q").start_time, freq="QS")
    vals = [pd.Timestamp(x) for x in idx]
    texts = [f"{x.year}-Q{x.quarter}" for x in idx]
    return vals, texts


def _halfyear_tick_labels(start: pd.Timestamp, end: pd.Timestamp) -> tuple[list[pd.Timestamp], list[str]]:
    idx = _period_index(start, end, 6)
    vals = [pd.Timestamp(x) for x in idx]
    texts = [f"{x.year}-H{'1' if x.month == 1 else '2'}" for x in idx]
    return vals, texts


def _year_tick_labels(start: pd.Timestamp, end: pd.Timestamp) -> tuple[list[pd.Timestamp], list[str]]:
    idx = _period_index(start, end, 12)
    vals = [pd.Timestamp(x) for x in idx]
    texts = [f"{x.year}" for x in idx]
    return vals, texts


def _forecast_linear_from_series(s: pd.Series, horizon: int) -> np.ndarray:
    y = s.to_numpy(dtype=float)
    if len(y) < 2:
        return np.repeat(y[-1] if len(y) else 0.0, horizon)
    x = np.arange(len(y), dtype=float)
    coef = np.polyfit(x, y, deg=1)
    fut_x = np.arange(len(y), len(y) + horizon, dtype=float)
    return np.maximum(0.0, coef[0] * fut_x + coef[1])


def _forecast_ets_from_series(s: pd.Series, horizon: int) -> np.ndarray:
    y = s.to_numpy(dtype=float)
    if len(y) < 4:
        return _forecast_linear_from_series(s, horizon)
    model = ExponentialSmoothing(y, trend="add", seasonal=None, damped_trend=True)
    fit = model.fit(optimized=True)
    pred = fit.forecast(horizon)
    return np.maximum(0.0, np.asarray(pred, dtype=float))


def _forecast_arima_from_series(s: pd.Series, horizon: int) -> np.ndarray:
    y = s.to_numpy(dtype=float)
    if len(y) < 6:
        return _forecast_linear_from_series(s, horizon)
    model = ARIMA(y, order=(1, 1, 1))
    fit = model.fit()
    pred = fit.forecast(steps=horizon)
    return np.maximum(0.0, np.asarray(pred, dtype=float))


def _score_model(s: pd.Series, model_name: str) -> tuple[float, float]:
    y = s.to_numpy(dtype=float)
    if len(y) < 8:
        return float("inf"), float("inf")
    holdout = min(4, max(2, len(y) // 4))
    train = pd.Series(y[:-holdout])
    test = y[-holdout:]
    if model_name == "linear":
        pred = _forecast_linear_from_series(train, holdout)
    elif model_name == "ets":
        pred = _forecast_ets_from_series(train, holdout)
    elif model_name == "arima":
        pred = _forecast_arima_from_series(train, holdout)
    else:
        pred = np.repeat(float(train.iloc[-1]), holdout)
    return _mae(test, pred), _mape(test, pred)


def _predict_with_model(
    df_time: pd.DataFrame,
    value_col: str,
    steps: int = 4,
    mode: Literal["auto", "linear", "ets", "arima"] = "auto",
    months_step: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df_time.empty:
        empty_pred = pd.DataFrame(columns=["month", "domain_name", value_col, "series_type", "model"])
        empty_meta = pd.DataFrame(columns=["domain_name", "value_col", "model", "mae", "mape"])
        return empty_pred, empty_meta

    now_q_start = _period_start_now(months_step)
    pred_rows: list[dict[str, object]] = []
    meta_rows: list[dict[str, object]] = []
    for domain in sorted(df_time["domain_name"].dropna().unique()):
        s = _prepare_series(df_time, domain, value_col, months_step=months_step)
        if s.empty:
            continue
        last_ts = pd.Timestamp(s.index.max())

        q_gap = max(
            1,
            int((now_q_start.year * 12 + now_q_start.month - (last_ts.year * 12 + last_ts.month)) / months_step),
        )
        horizon = q_gap + steps - 1

        selected = mode
        if mode in ("ets", "arima") and not HAS_STATSMODELS:
            selected = "linear"
        if mode == "auto":
            candidates = ["linear"]
            if HAS_STATSMODELS:
                candidates.extend(["ets", "arima"])
            scored = []
            for c in candidates:
                mae, mape = _score_model(s, c)
                scored.append((c, mae, mape))
            scored.sort(key=lambda x: (x[1], x[2]))
            selected = scored[0][0]
            best_mae, best_mape = scored[0][1], scored[0][2]
        else:
            best_mae, best_mape = _score_model(s, selected)

        if selected == "linear":
            fut = _forecast_linear_from_series(s, horizon)
        elif selected == "ets":
            fut = _forecast_ets_from_series(s, horizon)
        elif selected == "arima":
            fut = _forecast_arima_from_series(s, horizon)
        else:
            fut = _forecast_linear_from_series(s, horizon)

        first_ts = now_q_start if now_q_start > last_ts else (last_ts + pd.DateOffset(months=months_step))
        start_idx = max(0, q_gap - 1)
        end_idx = start_idx + steps
        fut_slice = fut[start_idx:end_idx]
        for i, pred in enumerate(fut_slice):
            pred_rows.append(
                {
                    "month": first_ts + pd.DateOffset(months=months_step * i),
                    "domain_name": domain,
                    value_col: float(pred),
                    "series_type": "预测",
                    "model": selected,
                }
            )
        meta_rows.append(
            {
                "domain_name": domain,
                "value_col": value_col,
                "model": selected,
                "mae": None if np.isinf(best_mae) else round(float(best_mae), 4),
                "mape": None if np.isinf(best_mape) else round(float(best_mape), 2),
            }
        )

    return pd.DataFrame(pred_rows), pd.DataFrame(meta_rows)


def _summary_text(df_share: pd.DataFrame, df_time: pd.DataFrame, df_pred_weight: pd.DataFrame) -> list[str]:
    lines: list[str] = []
    if df_share.empty:
        return ["当前时间范围内没有可用于总结的数据。"]
    top_now = df_share.sort_values("weight", ascending=False).head(3)
    lines.append(
        "当前主要方向：" + "；".join([f"{r.domain_name}（权重{r.weight:.2f}）" for r in top_now.itertuples(index=False)])
    )
    if not df_pred_weight.empty:
        pred_sum = (
            df_pred_weight.groupby("domain_name", as_index=False)["weight"]
            .sum()
            .sort_values("weight", ascending=False)
            .head(3)
        )
        lines.append(
            "未来4个季度预测：" + "；".join([f"{r.domain_name}（预测累计{r.weight:.2f}）" for r in pred_sum.itertuples(index=False)])
        )
    if not df_time.empty:
        latest = df_time.sort_values("month").groupby("domain_name", as_index=False).tail(1)
        strongest = latest.sort_values("weight", ascending=False).head(1)
        if not strongest.empty:
            r = strongest.iloc[0]
            lines.append(f"最近年度最活跃方向：{r['domain_name']}（年度权重{r['weight']:.2f}）。")
    return lines


def _zh_model_meta(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    renamed = df.rename(
        columns={
            "domain_name": "领域名称",
            "value_col": "预测指标",
            "model": "模型",
            "mae": "MAE误差",
            "mape": "MAPE误差(%)",
        }
    ).copy()
    if "预测指标" in renamed.columns:
        renamed["预测指标"] = renamed["预测指标"].replace(
            {"paper_count": "论文数量", "weight": "精力/质量加权值"}
        )
    if "模型" in renamed.columns:
        renamed["模型"] = renamed["模型"].astype(str).str.upper()
    return renamed


st.set_page_config(page_title="教授研究投入可视化", layout="wide")

st.title("教授研究投入可视化")
st.caption("本地 DuckDB 单文件 + Streamlit + Plotly。可按教授与时间范围筛选。")

db_path = st.sidebar.text_input("DuckDB 文件路径", value="07_temporal_analysis/step_results/pipeline.duckdb")

try:
    con = _connect(db_path)
except Exception as e:
    st.error(str(e))
    st.stop()

profs = _load_professors(con)
if not profs:
    st.warning("数据库中还没有教授数据。请先运行 build_step07_duckdb.py 写入 DuckDB。")
    st.stop()

professor = st.sidebar.selectbox("选择教授", options=profs, index=0)
source_sites = _load_source_sites(professor)
forecast_mode = st.sidebar.selectbox(
    "预测模型",
    options=["auto", "linear", "ets", "arima"],
    index=0,
    help="auto 会按每个领域回测误差自动选择；ets/arima 来自 statsmodels 开源库。",
)
default_author = professor.replace("pubmed_", "").replace("_", " ")
target_author = st.sidebar.text_input("目标作者名（用于一作判断）", value=default_author)
show_all_candidates = st.sidebar.checkbox("显示全部候选论文（含 identity_decision=False）", value=False)

st.subheader("0) 一键搜索")
with st.expander("输入作者与种子论文，执行全流程（01->07）", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        run_prof_name = st.text_input("作者姓名", value=default_author)
    with c2:
        run_seed_pmid = st.text_input("种子论文 PMID（可选）", value="")
    run_seed_title = st.text_input("种子论文名称", value="")
    run_output_prefix = st.text_input("输出前缀（可选）", value=professor)
    if st.button("执行一键搜索并刷新结果", type="primary"):
        if not run_prof_name.strip() or not run_seed_title.strip():
            st.error("请至少填写作者姓名与种子论文名称。")
        else:
            with st.spinner("正在执行全流程，请稍候（可能需要几分钟）..."):
                ok, logs = _run_oneclick_pipeline(
                    professor_name=run_prof_name.strip(),
                    seed_paper_title=run_seed_title.strip(),
                    seed_pmid=run_seed_pmid.strip(),
                    extra_source_urls=[],
                    output_prefix=run_output_prefix.strip() or professor,
                )
            if ok:
                st.success("一键流程执行完成。请在侧边栏选择对应教授并查看最新结果。")
            else:
                st.error("一键流程执行失败，请查看日志。")
            st.text_area("执行日志", value=logs[-12000:], height=240)

start = st.sidebar.date_input("开始日期（可选）", value=None)
end = st.sidebar.date_input("结束日期（可选）", value=None)

if start is not None and isinstance(start, datetime):
    start = start.date()
if end is not None and isinstance(end, datetime):
    end = end.date()

df_share = _domain_share_df(con, professor, start, end)
df_time = _domain_time_df(con, professor, start, end)
df_time = _to_year(df_time)
pred_w = pd.DataFrame()

st.subheader("1) 主要领域占比（饼图）")
if df_share.empty:
    st.info("该筛选范围内无数据。")
else:
    fig = px.pie(
        df_share,
        names="domain_name",
        values="weight",
        hole=0.35,
        labels={"domain_name": "领域名称", "weight": "权重"},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        df_share.rename(columns={"domain_name": "领域名称", "weight": "权重"}),
        use_container_width=True,
    )

st.subheader("2. 时间频率折线")
if df_time.empty:
    st.info("该筛选范围内无数据。")
else:
    hist = _fill_history_quarters(df_time, "paper_count", min_start="2021-01-01", months_step=12)
    pred_cnt, model_meta_cnt = _predict_with_model(
        df_time,
        "paper_count",
        steps=2,
        mode=forecast_mode,
        months_step=12,
    )
    if not pred_cnt.empty:
        pred_cnt["series_type"] = pred_cnt["model"].apply(lambda m: f"预测({str(m).upper()})")
    plot_cnt = pd.concat([hist[["month", "domain_name", "paper_count", "series_type"]], pred_cnt], ignore_index=True)
    fig = px.line(
        plot_cnt,
        x="month",
        y="paper_count",
        color="domain_name",
        line_dash="series_type",
        markers=True,
        labels={
            "month": "年份",
            "paper_count": "论文数量",
            "domain_name": "领域名称",
            "series_type": "序列类型",
        },
    )
    max_cnt = float(plot_cnt["paper_count"].max()) if not plot_cnt.empty else 1.0
    q_start = pd.Timestamp("2021-01-01")
    q_end = pd.Timestamp(plot_cnt["month"].max()) if not plot_cnt.empty else pd.Timestamp.now().to_period("Q").start_time
    tick_vals, tick_texts = _year_tick_labels(q_start, q_end)
    fig.update_xaxes(
        tickmode="array",
        tickvals=tick_vals,
        ticktext=tick_texts,
        range=[q_start, q_end + pd.DateOffset(months=12)],
    )
    fig.update_yaxes(rangemode="tozero", range=[0.0, max(1.0, max_cnt * 1.15)])
    st.plotly_chart(fig, use_container_width=True)
    if not model_meta_cnt.empty:
        st.caption("论文频率预测模型与误差（回测）")
        st.dataframe(_zh_model_meta(model_meta_cnt), use_container_width=True)

st.subheader("3. 权重折线")
if df_time.empty:
    st.info("该筛选范围内无数据。")
else:
    hist_w = _fill_history_quarters(df_time, "weight", min_start="2021-01-01", months_step=12)
    pred_w, model_meta_w = _predict_with_model(
        df_time,
        "weight",
        steps=2,
        mode=forecast_mode,
        months_step=12,
    )
    if not pred_w.empty:
        pred_w["series_type"] = pred_w["model"].apply(lambda m: f"预测({str(m).upper()})")
    plot_w = pd.concat([hist_w[["month", "domain_name", "weight", "series_type"]], pred_w], ignore_index=True)
    fig = px.line(
        plot_w,
        x="month",
        y="weight",
        color="domain_name",
        line_dash="series_type",
        markers=True,
        labels={
            "month": "年份",
            "weight": "精力/质量加权值",
            "domain_name": "领域名称",
            "series_type": "序列类型",
        },
    )
    max_w = float(plot_w["weight"].max()) if not plot_w.empty else 1.0
    q_start = pd.Timestamp("2021-01-01")
    q_end = pd.Timestamp(plot_w["month"].max()) if not plot_w.empty else pd.Timestamp.now().to_period("Q").start_time
    tick_vals, tick_texts = _year_tick_labels(q_start, q_end)
    fig.update_xaxes(
        tickmode="array",
        tickvals=tick_vals,
        ticktext=tick_texts,
        range=[q_start, q_end + pd.DateOffset(months=12)],
    )
    fig.update_yaxes(rangemode="tozero", range=[0.0, max(1.0, max_w * 1.15)])
    st.plotly_chart(fig, use_container_width=True)
    if not model_meta_w.empty:
        st.caption("精力/质量加权预测模型与误差（回测）")
        st.dataframe(_zh_model_meta(model_meta_w), use_container_width=True)

st.subheader("4) 权重与精力预测公式")
with st.expander("展开查看权重计算与预测模型原理", expanded=False):
    st.markdown("**论文权重（用于领域占比与时间加权）**")
    st.latex(r"w_{\text{paper}} = \text{identity\_score} \times \text{quality\_score}")
    st.markdown("其中：`identity_score` 来自同名消歧置信度，`quality_score` 来自论文质量评分。")

    st.markdown("**季度聚合权重（图中 weight）**")
    st.latex(r"W_{d,q} = \sum_{i \in (d,q)} \left(\text{identity\_score}_i \times \text{quality\_score}_i\right)")
    st.markdown("其中：`d` 为领域，`q` 为季度。")

    st.markdown("**精力预测（未来4个季度线性外推）**")
    st.latex(r"\hat{y}_{t} = f_{\theta}(y_{1:t-1}),\quad t=\text{当前季度},\dots,\text{当前季度}+3")
    st.markdown(
        "`f_θ` 支持三种开源方法：`Linear`（线性回归外推）、`ETS`（指数平滑，statsmodels）、"
        "`ARIMA(1,1,1)`（statsmodels）。`Auto` 模式按每个领域回测误差（MAE/MAPE）自动选最优。"
    )
    st.markdown(
        "- `Linear`：用历史点拟合一条直线，按斜率向未来外推，优点是稳定、可解释。\n"
        "- `ETS`：指数平滑模型，对近期数据赋予更高权重，可建模水平/趋势，适合平滑时序。\n"
        "- `ARIMA(1,1,1)`：先差分去趋势，再用自回归+移动平均建模时序相关性，适合有惯性波动的数据。\n"
        "- `Auto`：对每个领域做回测，比较 MAE/MAPE 后自动选当前最优模型。"
    )

st.subheader("5) 自动语言总结")
for line in _summary_text(df_share, df_time, pred_w):
    st.markdown(f"- {line}")

st.subheader("6) 发表时间核验（上半年/下半年）")
paper_df = _load_paper_catalog(
    professor,
    start,
    end,
    target_author,
    strict_only=(not show_all_candidates),
)
if paper_df.empty:
    st.info("当前筛选范围无论文清单数据。")
else:
    pub_ts = pd.to_datetime(paper_df["发表时间"], errors="coerce")
    valid_month = pub_ts.dropna().dt.month
    h1 = int((valid_month <= 6).sum())
    h2 = int((valid_month > 6).sum())
    total = int(len(valid_month))
    if h2 == 0 and total > 0:
        st.success(f"核验结果：已发表论文时间全部在上半年（H1={h1}, H2={h2}, 有效时间={total}）。")
    else:
        st.warning(f"核验结果：并非全部在上半年（H1={h1}, H2={h2}, 有效时间={total}）。")
    with st.expander("展开查看详细检验过程", expanded=False):
        st.markdown(
            "- 统计口径：仅统计 `发表时间` 可解析为日期的论文。\n"
            "- 分组规则：月份 `1-6` 记为 `H1`，月份 `7-12` 记为 `H2`。\n"
            "- 当前筛选条件：受侧边栏教授与时间范围过滤影响。"
        )
        detail = paper_df.copy()
        detail["发表时间_dt"] = pd.to_datetime(detail["发表时间"], errors="coerce")
        detail = detail[detail["发表时间_dt"].notna()].copy()
        if detail.empty:
            st.info("无可解析日期，无法展示详细检验过程。")
        else:
            detail["year"] = detail["发表时间_dt"].dt.year
            detail["half"] = detail["发表时间_dt"].dt.month.apply(lambda m: "H1" if int(m) <= 6 else "H2")
            by_year_half = (
                detail.groupby(["year", "half"], as_index=False)
                .size()
                .rename(columns={"size": "paper_count"})
                .sort_values(["year", "half"])
            )
            st.markdown("**按年份/半年分布**")
            st.dataframe(by_year_half, use_container_width=True)
            h2_examples = detail[detail["half"] == "H2"][["论文名称", "发表时间", "论文来源"]].head(20)
            st.markdown("**H2 样本预览（最多20条）**")
            if h2_examples.empty:
                st.success("当前筛选下没有 H2 样本。")
            else:
                st.dataframe(h2_examples, use_container_width=True)

st.subheader("论文信息来源网站")
with st.expander("展开查看来源网站清单", expanded=False):
    if source_sites:
        for u in source_sites:
            st.markdown(f"- [{u}]({u})")
    else:
        st.info("当前教授未识别到来源网站清单。")

st.subheader("7) 论文清单（可折叠）")
with st.expander("展开查看全部论文（标题/期刊/时间/来源/一作判断/关键词）", expanded=False):
    if paper_df.empty:
        st.info("暂无可展示论文。")
    else:
        if show_all_candidates:
            st.caption("当前显示 Step03 全部候选（含 identity_decision=False）。")
        else:
            st.caption("当前为严格模式：仅显示 identity_decision=True。")
        st.caption(f"当前清单条数：{len(paper_df)}")
        st.dataframe(paper_df, use_container_width=True)

st.caption(
    "说明：时间轴按年度节点统计，起始于2021-01-01；预测默认展示未来2个年度节点。"
)

con.close()

