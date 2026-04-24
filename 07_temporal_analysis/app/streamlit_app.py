from __future__ import annotations

import json
import os
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
import yaml

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


def _is_first_author(authors: list[str], target_author: str) -> tuple[str, str]:
    if not authors:
        return "未知", "无作者列表"
    if not target_author.strip():
        return "未设置目标作者", "未填写目标作者名"
    first_raw = str(authors[0] or "").strip()
    target_raw = str(target_author or "").strip()
    if not first_raw or not target_raw:
        return "未知", "首位作者或目标作者为空"

    def _looks_like_initials(tok: str) -> bool:
        t = re.sub(r"[^a-z]", "", tok.lower())
        if not t:
            return False
        # e.g., "hd", "h", "hdy"
        return len(t) <= 4

    def _name_parts(s: str) -> tuple[str, str]:
        s = s.strip()
        if "," in s:
            # Last, Given/Initials
            parts = [x.strip() for x in s.split(",", 1)]
            last = re.sub(r"[^a-z]", "", parts[0].lower())
            given = re.sub(r"[^a-z]", "", parts[1].lower() if len(parts) > 1 else "")
            return last, given
        toks = [re.sub(r"[^a-z]", "", t.lower()) for t in re.split(r"[\s\-\.]+", s) if t.strip()]
        toks = [t for t in toks if t]
        if not toks:
            return "", ""
        if len(toks) == 1:
            return toks[0], ""
        # Heuristic: "Huang HD" / "Huang H" => Last + initials.
        if _looks_like_initials(toks[-1]) and len(toks[0]) > 1:
            return toks[0], toks[-1]
        # Default: Given ... Last
        return toks[-1], "".join(toks[:-1])

    f_last, f_given = _name_parts(first_raw)
    t_last, t_given = _name_parts(target_raw)
    if not f_last or not t_last or f_last != t_last:
        return "否", f"姓不匹配：first={f_last or '∅'} target={t_last or '∅'}"
    # Given-name tolerance: initials or partial matching.
    if not t_given:
        return "是", "姓匹配；目标名缺失名/缩写，按姓匹配判定"
    if not f_given:
        return "否", "姓匹配但首位作者缺失名/缩写"
    ok = (
        f_given.startswith(t_given[:1])
        or t_given.startswith(f_given[:1])
        or (t_given in f_given)
        or (f_given in t_given)
    )
    if ok:
        return "是", f"姓匹配；名/缩写匹配：first={f_given} target={t_given}"
    return "否", f"姓匹配但名/缩写不匹配：first={f_given} target={t_given}"


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


def _norm_lex_key(s: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (s or "").lower()).strip()


@st.cache_data(show_spinner=False)
def _load_prof_lexicon() -> tuple[dict[str, str], dict[str, str]]:
    p = Path("08_taxonomy_memory/config/professional_tag_lexicon.yaml")
    if not p.exists():
        return {}, {}
    try:
        obj = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}, {}
    aliases_raw = obj.get("canonical_aliases", {}) or {}
    zh_raw = obj.get("canonical_zh", {}) or {}
    alias_map: dict[str, str] = {}
    zh_map: dict[str, str] = {}
    if isinstance(aliases_raw, dict):
        for k, v in aliases_raw.items():
            nk = _norm_lex_key(str(k))
            nv = _norm_lex_key(str(v))
            if nk and nv:
                alias_map[nk] = nv
    if isinstance(zh_raw, dict):
        for k, v in zh_raw.items():
            nk = _norm_lex_key(str(k))
            zv = str(v or "").strip()
            if nk and zv:
                zh_map[nk] = zv
    return alias_map, zh_map


def _has_cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in (s or ""))


def _has_ascii_alpha(s: str) -> bool:
    return bool(re.search(r"[A-Za-z]", s or ""))


def _tag_name_zh(tag_name: str) -> str:
    """
    Map internal tag key -> Chinese display name (local, no API).
    If already Chinese, keep. Else use a small glossary; fallback to "<EN>相关".
    """
    s = (tag_name or "").strip()
    if not s:
        return ""
    alias_map, zh_map = _load_prof_lexicon()
    ck = alias_map.get(_norm_lex_key(s), _norm_lex_key(s))
    if ck and ck in zh_map:
        return zh_map[ck]
    sl = s.lower()
    if ("mirna" in sl or "microrna" in sl) and "target" in sl:
        return "微小RNA靶点调控"
    if ("mirna" in sl or "microrna" in sl) and "mrna" in sl:
        return "微小RNA与mRNA互作"
    # If it contains English letters, try to translate + strip leftovers.
    if _has_cjk(s) and not _has_ascii_alpha(s):
        return s
    low = re.sub(r"\s+", " ", s.lower()).strip()
    glossary = {
        "database": "数据库/平台",
        "databases": "数据库/平台",
        "atlas": "图谱/数据库",
        "platform": "平台",
        "framework": "框架",
        "pipeline": "流程/管线",
        "tool": "工具开发",
        "benchmark": "基准评测",
        "dataset": "数据集",
        "datasets": "数据集",
        "deep learning": "深度学习",
        "neural network": "神经网络",
        "deep neural network": "深度神经网络",
        "transformer": "Transformer模型",
        "multimodal": "多模态学习",
        "bioinformatics": "生物信息学",
        "cancer genome atlas": "癌症基因组图谱",
        "cancer": "肿瘤生物学",
        "tumor": "肿瘤生物学",
        "breast cancer": "乳腺癌",
        "glioblastoma": "胶质母细胞瘤",
        "microrna": "微小RNA（miRNA）",
        "mirna": "微小RNA（miRNA）",
        "mirnas": "微小RNA（miRNA）",
        "omics": "组学",
        "drug": "药物研究",
        "drugs": "药物研究",
        "drug discovery": "药物发现",
        "drug target": "药物靶点",
    }
    if low in glossary:
        return glossary[low]

    # Phrase-level replacement then remove leftover English fragments.
    out = low
    # longer keys first
    for k in sorted(glossary.keys(), key=len, reverse=True):
        out = out.replace(k, glossary[k])
    out = re.sub(r"[A-Za-z]+", " ", out)
    out = out.replace("（）", " ").replace("()", " ")
    out = re.sub(r"\s+", " ", out).strip(" -_/，。;；()[]{}")
    if _has_cjk(out) and not _has_ascii_alpha(out):
        return out
    # Last resort: keep only Chinese chars if any
    only_zh = "".join([ch for ch in out if "\u4e00" <= ch <= "\u9fff" or ch in "/-+（）()、，； "]).strip()
    only_zh = re.sub(r"\s+", " ", only_zh).strip(" -_/，。;；")
    only_zh = re.sub(r"(微小\s*){2,}RNA", "微小RNA", only_zh)
    only_zh = re.sub(r"(微小RNA)(\s+\1)+", r"\1", only_zh)
    only_zh = re.sub(r"\s*相关\s*$", "", only_zh).strip()
    if _has_cjk(only_zh) and not _has_ascii_alpha(only_zh):
        return only_zh
    return "综合主题汇总"


def _tag_label(tag_name: str) -> str:
    zh = _tag_name_zh(tag_name)
    if not zh:
        return ""
    if zh == tag_name:
        return zh
    return f"{zh}（{tag_name}）"


def _paper_tags_text_from_step05(r05: dict) -> str:
    """
    Display all tags for a paper: L1/L2/L3 layer tags + L4 detailed tags with weights.
    """
    parts: list[str] = []

    l1 = str(r05.get("layer_l1_tag") or "").strip()
    if l1:
        parts.append(f"L1:{l1}")

    def _layer_items_to_str(items: object, level: str) -> None:
        if not isinstance(items, list) or not items:
            return
        segs: list[str] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("tag_name") or "").strip()
            if not name:
                continue
            name = _tag_name_zh(name)
            w = it.get("tag_weight", None)
            try:
                wf = float(w) if w is not None else None
            except Exception:
                wf = None
            segs.append(f"{name}({wf:.2f})" if wf is not None else name)
        if segs:
            parts.append(f"{level}:" + "，".join(segs))

    _layer_items_to_str(r05.get("layer_l2_items"), "L2")
    _layer_items_to_str(r05.get("layer_l3_items"), "L3")

    tag_items = r05.get("tag_items") or []
    if isinstance(tag_items, list) and tag_items:
        segs: list[str] = []
        for it in tag_items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("tag_name") or "").strip()
            if not name:
                continue
            name = _tag_name_zh(name)
            w = it.get("tag_weight", None)
            try:
                wf = float(w) if w is not None else None
            except Exception:
                wf = None
            segs.append(f"{name}({wf:.2f})" if wf is not None else name)
        if segs:
            parts.append("L4:" + "，".join(segs))

    return "；".join(parts)


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

        fa, fa_reason = _is_first_author(authors, target_author)
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
                "一作是否目标作者": fa,
                "一作判定依据": fa_reason,
                "论文标签": _paper_tags_text_from_step05(r05),
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
    project_root = Path(__file__).resolve().parents[2]
    if os.name == "nt":
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
    else:
        cmd = [
            "bash",
            "scripts/linux/run_full_pipeline_oneclick.sh",
            "--professor-name",
            professor_name,
            "--seed-paper-title",
            seed_paper_title,
            "--output-prefix",
            output_prefix,
            "--no-start-web",
        ]
        if seed_pmid.strip():
            cmd.extend(["--seed-pmid", seed_pmid.strip()])
        if extra_source_urls:
            cmd.extend(["--extra-source-url", *extra_source_urls])

    try:
        cp = subprocess.run(
            cmd,
            cwd=str(project_root),
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


def _run_tag_learning_and_refresh(prefix: str) -> tuple[bool, str]:
    """
    One-click: purge+dedupe learned tags, rebuild report, rerun Step06 tagging, rerun Step07 outputs + DuckDB.
    This updates charts + paper list without re-collecting papers.
    """
    project_root = Path(__file__).resolve().parents[2]
    python = project_root / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = project_root / ".venv" / "bin" / "python"
    if not python.exists():
        return False, f"未找到虚拟环境 Python：{python}"

    step04 = project_root / f"05_keyword_entity/step_results/{prefix}_step04_keyword_entity.jsonl"
    step06_paper = project_root / f"06_domain_clustering/step_results/{prefix}_step05_paper_domains.jsonl"
    step06_domains = project_root / f"06_domain_clustering/step_results/{prefix}_step05_domains.json"
    timeline_out = project_root / f"07_temporal_analysis/step_results/{prefix}_step06_project_timeline.json"
    allocation_out = project_root / f"07_temporal_analysis/step_results/{prefix}_step06_effort_allocation.json"
    report_out = project_root / f"07_temporal_analysis/step_results/{prefix}_step06_trend_report.md"
    duckdb_path = project_root / "07_temporal_analysis/step_results/pipeline.duckdb"

    cmds: list[list[str]] = [
        [
            str(python),
            "08_taxonomy_memory/processing/review_queue_3layer.py",
            "--purge-learned",
            "--min-score",
            "8",
            "--min-len-ascii",
            "6",
        ],
        [
            str(python),
            "08_taxonomy_memory/processing/build_tag_report.py",
            "--queue-l2",
            "08_taxonomy_memory/step_results/learning_queue_l2.jsonl",
            "--queue-l3",
            "08_taxonomy_memory/step_results/learning_queue_l3.jsonl",
            "--learned-l2",
            "08_taxonomy_memory/step_results/learned_l2.jsonl",
            "--learned-l3",
            "08_taxonomy_memory/step_results/learned_l3.jsonl",
            "--output",
            "08_taxonomy_memory/step_results/tag_report.json",
        ],
        [
            str(python),
            "06_domain_clustering/processing/run_step06_domain_clustering.py",
            "--input",
            str(step04),
            "--paper-domains-output",
            str(step06_paper),
            "--domains-output",
            str(step06_domains),
            "--model",
            "sentence-transformers/all-MiniLM-L6-v2",
            "--local-files-only",
        ],
        [
            str(python),
            "07_temporal_analysis/processing/run_step07_temporal_analysis.py",
            "--input",
            str(step06_paper),
            "--timeline-output",
            str(timeline_out),
            "--allocation-output",
            str(allocation_out),
            "--report-output",
            str(report_out),
        ],
        [
            str(python),
            "07_temporal_analysis/processing/build_step07_duckdb.py",
            "--professor",
            prefix,
            "--paper-domains",
            str(step06_paper),
            "--duckdb-path",
            str(duckdb_path),
        ],
    ]

    logs: list[str] = []
    for cmd in cmds:
        try:
            cp = subprocess.run(cmd, cwd=str(project_root), text=True, capture_output=True, timeout=1800, check=False)
        except Exception as e:
            return False, "\n".join(logs + [f"[异常] {e}"])
        out = (cp.stdout or "") + ("\n" + cp.stderr if cp.stderr else "")
        logs.append(f"$ {' '.join(cmd)}\n{out}".rstrip())
        if cp.returncode != 0:
            return False, "\n\n".join(logs)
    return True, "\n\n".join(logs)


def _tag_share_df(
    con: duckdb.DuckDBPyConnection,
    professor: str,
    level: int,
    start: date | None,
    end: date | None,
) -> pd.DataFrame:
    where = ["professor = ?"]
    params: list[object] = [professor]
    where.append("level = ?")
    params.append(int(level))
    if start is not None:
        where.append("pub_date >= ?")
        params.append(start)
    if end is not None:
        where.append("pub_date <= ?")
        params.append(end)
    sql = f"""
      select tag_name, sum(weight) as weight
      from v_tag_share
      where {' and '.join(where)}
      group by tag_name
      order by weight desc
    """
    return con.execute(sql, params).df()


def _tag_time_df(
    con: duckdb.DuckDBPyConnection,
    professor: str,
    level: int,
    start: date | None,
    end: date | None,
) -> pd.DataFrame:
    where = ["professor = ?"]
    params: list[object] = [professor]
    where.append("level = ?")
    params.append(int(level))
    if start is not None:
        where.append("month >= date_trunc('quarter', ?)")
        params.append(start)
    if end is not None:
        where.append("month <= date_trunc('quarter', ?)")
        params.append(end)
    sql = f"""
      select tag_name, month, paper_count, weight
      from v_tag_time
      where {' and '.join(where)}
      order by month asc, tag_name asc
    """
    df = con.execute(sql, params).df()
    if not df.empty:
        df["month"] = pd.to_datetime(df["month"])
    return df


def _predict_next_quarters(df_time: pd.DataFrame, value_col: str, steps: int = 4) -> pd.DataFrame:
    if df_time.empty:
        return pd.DataFrame(columns=["month", "tag_name", value_col, "series_type"])
    now_q_start = pd.Timestamp.now().to_period("Q").start_time
    out_rows: list[dict[str, object]] = []
    for domain, grp in df_time.groupby("tag_name"):
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
                    "tag_name": domain,
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
    g = df_time[df_time["tag_name"] == domain].copy().sort_values("month")
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
        out.groupby(["tag_name", "month"], as_index=False)[["paper_count", "weight"]]
        .sum()
        .sort_values(["month", "tag_name"])
    )


def _to_year(df_time: pd.DataFrame) -> pd.DataFrame:
    if df_time.empty:
        return df_time
    out = df_time.copy()
    out["month"] = out["month"].apply(lambda x: _period_start(pd.Timestamp(x), 12))
    return (
        out.groupby(["tag_name", "month"], as_index=False)[["paper_count", "weight"]]
        .sum()
        .sort_values(["month", "tag_name"])
    )


def _fill_history_quarters(
    df_time: pd.DataFrame,
    value_col: str,
    min_start: str = "2021-01-01",
    months_step: int = 3,
) -> pd.DataFrame:
    if df_time.empty:
        return pd.DataFrame(columns=["month", "tag_name", value_col, "series_type"])
    start = max(pd.Timestamp(min_start), _period_start(pd.Timestamp(df_time["month"].min()), months_step))
    end = _period_start(pd.Timestamp(df_time["month"].max()), months_step)
    q_idx = _period_index(start, end, months_step)
    rows: list[dict[str, object]] = []
    for domain in sorted(df_time["tag_name"].dropna().unique()):
        g = df_time[df_time["tag_name"] == domain].copy()
        s = g.set_index("month")[value_col].astype(float).reindex(q_idx, fill_value=0.0)
        for ts, val in s.items():
            rows.append(
                {
                    "month": pd.Timestamp(ts),
                    "tag_name": domain,
                    value_col: float(max(0.0, val)),
                    "series_type": "历史",
                }
            )
    return pd.DataFrame(rows)


def _fill_history_with_pred_for_gaps(
    df_time: pd.DataFrame,
    value_col: str,
    min_start: str = "2021-01-01",
    months_step: int = 12,
) -> pd.DataFrame:
    """
    Build historical series with gap filling by model estimate (instead of zero).
    If a year has no observed data, use a fitted trend value as "预测补全".
    """
    if df_time.empty:
        return pd.DataFrame(columns=["month", "tag_name", value_col, "series_type"])
    start = max(pd.Timestamp(min_start), _period_start(pd.Timestamp(df_time["month"].min()), months_step))
    end = _period_start(pd.Timestamp(df_time["month"].max()), months_step)
    idx = _period_index(start, end, months_step)
    rows: list[dict[str, object]] = []
    for domain in sorted(df_time["tag_name"].dropna().unique()):
        g = df_time[df_time["tag_name"] == domain].copy()
        if g.empty:
            continue
        observed = g.groupby("month", as_index=True)[value_col].sum().astype(float)
        observed = observed.reindex(idx)
        is_missing = observed.isna()
        s = observed.copy()
        if is_missing.any():
            known = observed.dropna()
            if len(known) >= 2:
                x_all = np.arange(len(observed), dtype=float)
                x_known = np.array([idx.index(ts) for ts in known.index], dtype=float)
                y_known = known.to_numpy(dtype=float)
                coef = np.polyfit(x_known, y_known, deg=1)
                pred_all = np.maximum(0.0, coef[0] * x_all + coef[1])
                for i, miss in enumerate(is_missing.to_numpy()):
                    if bool(miss):
                        s.iloc[i] = float(pred_all[i])
            elif len(known) == 1:
                s = s.fillna(float(max(0.0, known.iloc[0])))
            else:
                s = s.fillna(0.0)
        for i, ts in enumerate(idx):
            val = float(max(0.0, s.iloc[i] if pd.notna(s.iloc[i]) else 0.0))
            stype = "预测补全" if bool(is_missing.iloc[i]) else "历史"
            rows.append({"month": pd.Timestamp(ts), "tag_name": domain, value_col: val, "series_type": stype})
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
        empty_pred = pd.DataFrame(columns=["month", "tag_name", value_col, "series_type", "model"])
        empty_meta = pd.DataFrame(columns=["tag_name", "value_col", "model", "mae", "mape"])
        return empty_pred, empty_meta

    now_q_start = _period_start_now(months_step)
    # User requirement: only forecast after 2026.
    min_after_2026 = _period_start(pd.Timestamp("2027-01-01"), months_step)
    pred_rows: list[dict[str, object]] = []
    meta_rows: list[dict[str, object]] = []
    for domain in sorted(df_time["tag_name"].dropna().unique()):
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
        if first_ts < min_after_2026:
            first_ts = min_after_2026
        start_idx = max(0, q_gap - 1)
        end_idx = start_idx + steps
        fut_slice = fut[start_idx:end_idx]
        for i, pred in enumerate(fut_slice):
            pred_rows.append(
                {
                    "month": first_ts + pd.DateOffset(months=months_step * i),
                    "tag_name": domain,
                    value_col: float(pred),
                    "series_type": "预测",
                    "model": selected,
                }
            )
        meta_rows.append(
            {
                "tag_name": domain,
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
        "当前主要标签："
        + "；".join([f"{_tag_label(r.tag_name)}（权重{r.weight:.2f}）" for r in top_now.itertuples(index=False)])
    )
    if not df_pred_weight.empty:
        pred_sum = (
            df_pred_weight.groupby("tag_name", as_index=False)["weight"]
            .sum()
            .sort_values("weight", ascending=False)
            .head(3)
        )
        lines.append(
            "未来4个季度预测："
            + "；".join([f"{_tag_label(r.tag_name)}（预测累计{r.weight:.2f}）" for r in pred_sum.itertuples(index=False)])
        )
    if not df_time.empty:
        latest = df_time.sort_values("month").groupby("tag_name", as_index=False).tail(1)
        strongest = latest.sort_values("weight", ascending=False).head(1)
        if not strongest.empty:
            r = strongest.iloc[0]
            lines.append(f"最近年度最活跃标签：{_tag_label(str(r['tag_name']))}（年度权重{r['weight']:.2f}）。")
    return lines


def _zh_model_meta(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    renamed = df.rename(
        columns={
            "tag_name": "标签名称",
            "value_col": "预测指标",
            "model": "模型",
            "mae": "MAE误差",
            "mape": "MAPE误差(%)",
        }
    ).copy()
    if "标签名称" in renamed.columns:
        renamed["标签名称"] = renamed["标签名称"].astype(str).apply(_tag_label)
    if "预测指标" in renamed.columns:
        renamed["预测指标"] = renamed["预测指标"].replace(
            {"paper_count": "论文数量", "weight": "精力/质量加权值"}
        )
    if "模型" in renamed.columns:
        renamed["模型"] = renamed["模型"].astype(str).str.upper()
    return renamed


def _render_level_charts(level_title: str, df_time: pd.DataFrame, forecast_mode: str) -> pd.DataFrame:
    st.markdown(f"**{level_title} 权重折线**")
    if df_time.empty:
        st.info("该筛选范围内无数据。")
        return pd.DataFrame()
    q_start = pd.Timestamp("2021-01-01")
    hist_w = _fill_history_with_pred_for_gaps(df_time, "weight", min_start="2021-01-01", months_step=12)
    pred_w, model_meta_w = _predict_with_model(df_time, "weight", steps=2, mode=forecast_mode, months_step=12)
    if not pred_w.empty:
        pred_w["series_type"] = pred_w["model"].apply(lambda m: f"预测({str(m).upper()})")
        bridge_rows_w: list[dict[str, object]] = []
        hist_last_w = hist_w.sort_values("month").groupby("tag_name", as_index=False).tail(1)
        model_by_tag_w = pred_w.groupby("tag_name", as_index=False).head(1)[["tag_name", "model"]]
        for r in hist_last_w.itertuples(index=False):
            mrow = model_by_tag_w[model_by_tag_w["tag_name"] == r.tag_name]
            if mrow.empty:
                continue
            model_name = str(mrow.iloc[0]["model"]).upper()
            bridge_rows_w.append(
                {
                    "month": r.month,
                    "tag_name": r.tag_name,
                    "weight": float(r.weight),
                    "series_type": f"预测({model_name})",
                    "model": str(mrow.iloc[0]["model"]),
                }
            )
        if bridge_rows_w:
            pred_w = pd.concat([pd.DataFrame(bridge_rows_w), pred_w], ignore_index=True)
    plot_w = pd.concat([hist_w[["month", "tag_name", "weight", "series_type"]], pred_w], ignore_index=True)
    plot_w["tag_label"] = plot_w["tag_name"].astype(str).apply(_tag_name_zh)
    fig = px.line(
        plot_w,
        x="month",
        y="weight",
        color="tag_label",
        line_dash="series_type",
        markers=True,
        labels={"month": "年份", "weight": "精力/质量加权值", "tag_label": "标签名称", "series_type": "序列类型"},
    )
    max_w = float(plot_w["weight"].max()) if not plot_w.empty else 1.0
    q_end = pd.Timestamp(plot_w["month"].max()) if not plot_w.empty else pd.Timestamp.now().to_period("Q").start_time
    tick_vals, tick_texts = _year_tick_labels(q_start, q_end)
    fig.update_xaxes(tickmode="array", tickvals=tick_vals, ticktext=tick_texts, range=[q_start, q_end + pd.DateOffset(months=12)])
    fig.update_yaxes(rangemode="tozero", range=[0.0, max(1.0, max_w * 1.15)])
    st.plotly_chart(fig, use_container_width=True)
    if not model_meta_w.empty:
        st.caption(f"{level_title} 权重预测模型与误差（回测）")
        st.dataframe(_zh_model_meta(model_meta_w), use_container_width=True)
    return pred_w


def _load_latest_learned_tags() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path, lvl in [
        (Path("08_taxonomy_memory/step_results/learned_l2.jsonl"), "L2"),
        (Path("08_taxonomy_memory/step_results/learned_l3.jsonl"), "L3"),
    ]:
        for r in _read_jsonl(path):
            name = str(r.get("name") or "").strip()
            name_zh = str(r.get("name_zh") or "").strip() or _tag_name_zh(name)
            name_en = str(r.get("name_en") or "").strip() or (name if (name and not _has_cjk(name)) else "")
            if not (name_zh or name_en):
                continue
            learned_at = str(r.get("learned_at") or "").strip()
            rows.append(
                {
                    "标签中文": name_zh,
                    "标签英文": name_en,
                    "标签层级": str(r.get("level") or lvl),
                    "习得时间": learned_at,
                }
            )
    if not rows:
        return pd.DataFrame(columns=["标签中文", "标签英文", "标签层级", "习得时间"])
    df = pd.DataFrame(rows)
    dt = pd.to_datetime(df["习得时间"], errors="coerce")
    df["_ts"] = dt
    df = df.sort_values("_ts", ascending=False, na_position="last").drop(columns=["_ts"]).reset_index(drop=True)
    return df


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
    help="auto 会按每个标签回测误差自动选择；ets/arima 来自 statsmodels 开源库。",
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

st.sidebar.markdown("### 标签筛选体系")
min_tag_weight = st.sidebar.slider("标签最小权重（适用于L1/L2/L3）", min_value=0.0, max_value=1.0, value=0.03, step=0.01)

df_share_l1 = _tag_share_df(con, professor, level=1, start=start, end=end)
df_share_l2 = _tag_share_df(con, professor, level=2, start=start, end=end)
df_share_l3 = _tag_share_df(con, professor, level=3, start=start, end=end)
if not df_share_l1.empty:
    df_share_l1 = df_share_l1[df_share_l1["weight"] >= float(min_tag_weight)].copy()
if not df_share_l2.empty:
    df_share_l2 = df_share_l2[df_share_l2["weight"] >= float(min_tag_weight)].copy()
if not df_share_l3.empty:
    df_share_l3 = df_share_l3[df_share_l3["weight"] >= float(min_tag_weight)].copy()

tag_options_l1 = sorted(df_share_l1["tag_name"].tolist()) if not df_share_l1.empty else []
tag_options_l2 = sorted(df_share_l2["tag_name"].tolist()) if not df_share_l2.empty else []
tag_options_l3 = sorted(df_share_l3["tag_name"].tolist()) if not df_share_l3.empty else []
label_to_key_l1 = { _tag_label(k): k for k in tag_options_l1 }
label_to_key_l2 = { _tag_label(k): k for k in tag_options_l2 }
label_to_key_l3 = { _tag_label(k): k for k in tag_options_l3 }
label_opts_l1 = sorted(label_to_key_l1.keys())
label_opts_l2 = sorted(label_to_key_l2.keys())
label_opts_l3 = sorted(label_to_key_l3.keys())
sel_label_l1 = st.sidebar.multiselect("L1 标签筛选（中文展示）", options=label_opts_l1, default=label_opts_l1)
sel_label_l2 = st.sidebar.multiselect("L2 标签筛选（中文展示）", options=label_opts_l2, default=label_opts_l2[:6])
sel_label_l3 = st.sidebar.multiselect("L3 标签筛选（中文展示）", options=label_opts_l3, default=label_opts_l3[:6])
selected_l1 = [label_to_key_l1[x] for x in sel_label_l1 if x in label_to_key_l1]
selected_l2 = [label_to_key_l2[x] for x in sel_label_l2 if x in label_to_key_l2]
selected_l3 = [label_to_key_l3[x] for x in sel_label_l3 if x in label_to_key_l3]

df_time_l1 = _to_year(_tag_time_df(con, professor, level=1, start=start, end=end))
df_time_l2 = _to_year(_tag_time_df(con, professor, level=2, start=start, end=end))
df_time_l3 = _to_year(_tag_time_df(con, professor, level=3, start=start, end=end))
if selected_l1:
    df_share_l1 = df_share_l1[df_share_l1["tag_name"].isin(selected_l1)].copy()
    df_time_l1 = df_time_l1[df_time_l1["tag_name"].isin(selected_l1)].copy()
if selected_l2:
    df_share_l2 = df_share_l2[df_share_l2["tag_name"].isin(selected_l2)].copy()
    df_time_l2 = df_time_l2[df_time_l2["tag_name"].isin(selected_l2)].copy()
if selected_l3:
    df_share_l3 = df_share_l3[df_share_l3["tag_name"].isin(selected_l3)].copy()
    df_time_l3 = df_time_l3[df_time_l3["tag_name"].isin(selected_l3)].copy()
pred_w_l3 = pd.DataFrame()

st.subheader("1) L1 顶层大类轮盘（3类）")
if df_share_l1.empty:
    st.info("该筛选范围内无数据。")
else:
    df_share_l1 = df_share_l1.copy()
    df_share_l1["tag_label"] = df_share_l1["tag_name"].astype(str).apply(_tag_name_zh)
    fig = px.pie(
        df_share_l1,
        names="tag_label",
        values="weight",
        hole=0.35,
        labels={"tag_label": "标签名称", "weight": "权重"},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        df_share_l1.rename(columns={"tag_label": "标签名称", "weight": "权重"})[["标签名称", "权重"]],
        use_container_width=True,
    )
pred_w_l1 = _render_level_charts("L1", df_time_l1, forecast_mode)

st.subheader("2) L2 高频标签轮盘")
if df_share_l2.empty:
    st.info("该筛选范围内无数据。")
else:
    df_share_l2 = df_share_l2.copy()
    df_share_l2["tag_label"] = df_share_l2["tag_name"].astype(str).apply(_tag_name_zh)
    fig = px.pie(
        df_share_l2,
        names="tag_label",
        values="weight",
        hole=0.35,
        labels={"tag_label": "标签名称", "weight": "权重"},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df_share_l2.rename(columns={"tag_label": "标签名称", "weight": "权重"})[["标签名称", "权重"]], use_container_width=True)
pred_w_l2 = _render_level_charts("L2", df_time_l2, forecast_mode)

st.subheader("3) L3 高频标签轮盘")
if df_share_l3.empty:
    st.info("该筛选范围内无数据。")
else:
    df_share_l3 = df_share_l3.copy()
    df_share_l3["tag_label"] = df_share_l3["tag_name"].astype(str).apply(_tag_name_zh)
    fig = px.pie(
        df_share_l3,
        names="tag_label",
        values="weight",
        hole=0.35,
        labels={"tag_label": "标签名称", "weight": "权重"},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df_share_l3.rename(columns={"tag_label": "标签名称", "weight": "权重"})[["标签名称", "权重"]], use_container_width=True)
pred_w_l3 = _render_level_charts("L3", df_time_l3, forecast_mode)

st.subheader("4) 权重与精力预测公式")
with st.expander("展开查看权重计算与预测模型原理", expanded=False):
    st.markdown("**论文权重（用于标签占比与时间加权）**")
    st.latex(r"w_{\text{paper}} = \text{identity\_score} \times \text{quality\_score}")
    st.markdown("其中：`identity_score` 来自同名消歧置信度，`quality_score` 来自论文质量评分。")

    st.markdown("**年度聚合权重（图中 weight）**")
    st.latex(r"W_{t,y} = \sum_{i \in (t,y)} \left(\text{identity\_score}_i \times \text{quality\_score}_i \times \text{tag\_weight}_i\right)")
    st.markdown("其中：`t` 为标签，`y` 为年份。")

    st.markdown("**精力预测（未来4个季度线性外推）**")
    st.latex(r"\hat{y}_{t} = f_{\theta}(y_{1:t-1}),\quad t=\text{当前季度},\dots,\text{当前季度}+3")
    st.markdown(
        "`f_θ` 支持三种开源方法：`Linear`（线性回归外推）、`ETS`（指数平滑，statsmodels）、"
        "`ARIMA(1,1,1)`（statsmodels）。`Auto` 模式按每个标签回测误差（MAE/MAPE）自动选最优。"
    )
    st.markdown(
        "- `Linear`：用历史点拟合一条直线，按斜率向未来外推，优点是稳定、可解释。\n"
        "- `ETS`：指数平滑模型，对近期数据赋予更高权重，可建模水平/趋势，适合平滑时序。\n"
        "- `ARIMA(1,1,1)`：先差分去趋势，再用自回归+移动平均建模时序相关性，适合有惯性波动的数据。\n"
        "- `Auto`：对每个标签做回测，比较 MAE/MAPE 后自动选当前最优模型。"
    )

st.subheader("5) 自动语言总结")
df_share_summary = df_share_l3 if "df_share_l3" in globals() else pd.DataFrame(columns=["tag_name", "weight"])
for line in _summary_text(df_share_summary, df_time_l3, pred_w_l3):
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
full_paper_df = _load_paper_catalog(
    professor,
    start=None,
    end=None,
    target_author=target_author,
    strict_only=False,
)
with st.expander("展开查看全量论文", expanded=False):
    if full_paper_df.empty:
        st.info("暂无全量论文数据。")
    else:
        st.caption("全量口径：不受时间范围与严格模式影响，展示可读取到的全部候选论文。")
        st.caption(f"全量论文条数：{len(full_paper_df)}")
        st.dataframe(full_paper_df, use_container_width=True)

with st.expander("展开查看当前符合要求的论文", expanded=False):
    if paper_df.empty:
        st.info("当前筛选条件下暂无论文。")
    else:
        if show_all_candidates:
            st.caption("当前口径：受时间筛选影响，且显示 Step03 全部候选（含 identity_decision=False）。")
        else:
            st.caption("当前口径：受时间筛选影响，且仅显示 identity_decision=True（严格模式）。")
        st.caption(f"当前符合要求条数：{len(paper_df)}")
        st.dataframe(paper_df, use_container_width=True)

st.subheader("8) 最新学习标签（按习得时间倒序）")
learned_df = _load_latest_learned_tags()
if learned_df.empty:
    st.info("当前暂无已习得标签。请先执行 Step08 审核写入 learned_l2/learned_l3。")
else:
    st.dataframe(learned_df, use_container_width=True)

st.subheader("9) 一键学习与更新（标签去重 + 重新归类 + 同步论文清单）")
with st.expander("展开执行：learned 去重清洗 → 重新计算 L1/L2/L3 → 刷新 DuckDB/图表/论文清单", expanded=False):
    st.markdown(
        "- 会对 `learned_l2/learned_l3` 做去重与质量门控清洗；\n"
        "- 然后重跑 `Step06` 生成新的 L1/L2/L3 分类结果；\n"
        "- 再重跑 `Step07` 与 DuckDB 写入，使图表与论文清单同步更新。\n"
    )
    if st.button("一键学习并更新当前教授标签", type="primary"):
        with st.spinner("正在学习与更新标签（可能需要 1-3 分钟）..."):
            ok, logs = _run_tag_learning_and_refresh(professor)
        if ok:
            st.success("已完成：标签去重/归类/刷新。页面会自动使用最新数据。")
            st.rerun()
        else:
            st.error("执行失败，请查看日志。")
            st.text_area("执行日志", value=logs[-12000:], height=260)

st.caption(
    "说明：时间轴按年度节点统计，起始于2021-01-01；预测默认展示未来2个年度节点。"
)

con.close()

