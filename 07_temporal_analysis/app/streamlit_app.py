from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


def _connect(db_path: str) -> duckdb.DuckDBPyConnection:
    p = Path(db_path)
    if not p.exists():
        raise FileNotFoundError(f"DuckDB not found: {p}")
    return duckdb.connect(str(p), read_only=True)


def _load_professors(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute("select professor from professors order by professor").fetchall()
    return [r[0] for r in rows]


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
        where.append("month >= date_trunc('month', ?)")
        params.append(start)
    if end is not None:
        where.append("month <= date_trunc('month', ?)")
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
        for i, pred in enumerate(future_y, start=1):
            out_rows.append(
                {
                    "month": last_ts + pd.DateOffset(months=3 * i),
                    "domain_name": domain,
                    value_col: float(pred),
                    "series_type": "预测",
                }
            )
    return pd.DataFrame(out_rows)


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
            lines.append(f"最近季度最活跃方向：{r['domain_name']}（季度权重{r['weight']:.2f}）。")
    return lines


st.set_page_config(page_title="教授研究投入可视化（Step07）", layout="wide")

st.title("教授研究投入可视化（Step07）")
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

start = st.sidebar.date_input("开始日期（可选）", value=None)
end = st.sidebar.date_input("结束日期（可选）", value=None)

if start is not None and isinstance(start, datetime):
    start = start.date()
if end is not None and isinstance(end, datetime):
    end = end.date()

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1) 主要领域占比（饼图）")
    df_share = _domain_share_df(con, professor, start, end)
    if df_share.empty:
        st.info("该筛选范围内无数据。")
    else:
        fig = px.pie(df_share, names="domain_name", values="weight", hole=0.35)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df_share, use_container_width=True)

with col2:
    st.subheader("2) 领域时间折线（季度论文发布频率，2021起）")
    df_time = _domain_time_df(con, professor, start, end)
    if df_time.empty:
        st.info("该筛选范围内无数据。")
    else:
        hist = df_time.copy()
        hist["series_type"] = "历史"
        pred_cnt = _predict_next_quarters(df_time, "paper_count", steps=4)
        plot_cnt = pd.concat([hist[["month", "domain_name", "paper_count", "series_type"]], pred_cnt], ignore_index=True)
        fig = px.line(
            plot_cnt,
            x="month",
            y="paper_count",
            color="domain_name",
            line_dash="series_type",
            markers=True,
        )
        st.plotly_chart(fig, use_container_width=True)

st.subheader("3) 领域时间折线（季度精力/质量加权，2021起）")
if df_time.empty:
    st.info("该筛选范围内无数据。")
else:
    hist_w = df_time.copy()
    hist_w["series_type"] = "历史"
    pred_w = _predict_next_quarters(df_time, "weight", steps=4)
    plot_w = pd.concat([hist_w[["month", "domain_name", "weight", "series_type"]], pred_w], ignore_index=True)
    fig = px.line(
        plot_w,
        x="month",
        y="weight",
        color="domain_name",
        line_dash="series_type",
        markers=True,
    )
    st.plotly_chart(fig, use_container_width=True)

st.subheader("4) 自动语言总结")
for line in _summary_text(df_share if 'df_share' in locals() else pd.DataFrame(), df_time if 'df_time' in locals() else pd.DataFrame(), pred_w if 'pred_w' in locals() else pd.DataFrame()):
    st.markdown(f"- {line}")

st.caption(
    "说明：时间轴按季度节点（每3个月）统计，起始于2021-01-01；预测使用各方向历史序列线性外推（未来4个季度）。"
)

con.close()

