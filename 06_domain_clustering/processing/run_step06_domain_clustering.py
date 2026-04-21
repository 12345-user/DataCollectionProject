import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer
from huggingface_hub import snapshot_download
import yaml

_BAD_THEME_TOKENS = {
    "研究关键词",
    "相关",
    "影响",
    "包含",
    "指标",
    "研究",
    "主题",
    "汇总",
}

_DOMAIN_THEME_RULES: list[tuple[list[str], str]] = [
    (["database", "sql", "mysql", "postgres", "duckdb", "etl", "data warehouse", "数据库", "数据仓库"], "数据库开发与应用"),
    (
        [
            "machine learning",
            "deep learning",
            "neural network",
            "transformer",
            "xgboost",
            "random forest",
            "training",
            "机器学习",
            "深度学习",
            "神经网络",
            "模型训练",
        ],
        "机器学习模型训练",
    ),
    (["微小rna", "mirna", "mrna", "调控rna", "rna"], "miRNA/RNA调控"),
    (["不良药物反应", "药物靶点", "毒性"], "药物反应与靶点预测"),
    (["omega-3", "脂肪酸", "代谢"], "Omega-3与代谢健康"),
    (["atad2", "溴结构域", "染色质"], "ATAD2/表观肿瘤机制"),
    (["水凝胶", "纳米复合材料", "纳米颗粒", "骨修复"], "水凝胶/材料修复"),
    (["铁死亡"], "铁死亡与调控机制"),
    (["抗氧化"], "抗氧化/中药机制"),
    (["感染", "诊断", "测序"], "感染诊断与测序"),
    (["胶质母细胞瘤", "肿瘤", "癌"], "肿瘤机制与治疗"),
]

_TAXONOMY_PATH = Path("shared/config/domain_taxonomy.yaml")
_LEARNED_TAXONOMY_PATH = Path("08_taxonomy_memory/step_results/domain_taxonomy_learned.jsonl")
_LEARNING_QUEUE_PATH = Path("08_taxonomy_memory/step_results/domain_taxonomy_learning_queue.jsonl")


def _load_taxonomy_rules() -> list[tuple[list[str], str]]:
    rules: list[tuple[list[str], str]] = list(_DOMAIN_THEME_RULES)
    if _TAXONOMY_PATH.exists():
        try:
            data = yaml.safe_load(_TAXONOMY_PATH.read_text(encoding="utf-8")) or {}
            for item in data.get("fixed_categories", []) or []:
                name = str(item.get("name", "")).strip()
                kws = [str(x).strip().lower() for x in (item.get("keywords", []) or []) if str(x).strip()]
                if name and kws:
                    rules.insert(0, (kws, name))
        except Exception:
            pass
    if _LEARNED_TAXONOMY_PATH.exists():
        for line in _LEARNED_TAXONOMY_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            name = str(item.get("name", "")).strip()
            kws = [str(x).strip().lower() for x in (item.get("keywords", []) or []) if str(x).strip()]
            if name and kws:
                rules.insert(0, (kws, name))
    return rules


def _append_learning_queue(domain_label: str, tokens: list[str], evidence_titles: list[str]) -> None:
    cleaned = [_clean_theme_token(str(t)) for t in tokens]
    cleaned = [x for x in cleaned if x and x not in _BAD_THEME_TOKENS]
    if not cleaned:
        return
    _LEARNING_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "domain_label": domain_label,
        "candidate_name": f"{'/'.join(cleaned[:2])}主题汇总"[:30],
        "keywords": cleaned[:8],
        "evidence_titles": evidence_titles[:3],
    }
    with _LEARNING_QUEUE_PATH.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_text(row: dict[str, Any]) -> str:
    title = str(row.get("title", "") or "")
    abstract = str(row.get("abstract", "") or "")
    kws = row.get("keywords") or []
    pcs = row.get("project_candidates") or []
    if not isinstance(kws, list):
        kws = [str(kws)]
    if not isinstance(pcs, list):
        pcs = [str(pcs)]
    return "\n".join([title, abstract, " ".join(map(str, kws[:20])), " ".join(map(str, pcs[:20]))]).strip()


def _abstract_snippet(row: dict[str, Any], max_len: int = 180) -> str:
    abstract = str(row.get("abstract", "") or "").strip()
    if not abstract:
        return ""
    if len(abstract) <= max_len:
        return abstract
    return abstract[:max_len].rstrip() + "..."


def _kw_to_cn(kw: str) -> str:
    s = (kw or "").strip()
    if not s:
        return ""
    low = s.lower()
    token_map = {
        "hypertension": "高血压",
        "air pollution": "空气污染",
        "pollution": "污染",
        "blood pressure": "血压",
        "blood": "血液",
        "elderly": "老年人",
        "prevalence": "患病率",
        "including": "包含",
        "effect": "影响",
        "indices": "指标",
        "pm2.5": "PM2.5",
        "pm10": "PM10",
        "china": "中国",
        "microrna": "微小RNA",
        "mirna": "微小RNA",
        "mrna": "信使RNA",
        "regulatory rna": "调控RNA",
        "rna": "RNA",
        "adverse drug": "不良药物反应",
        "drug target": "药物靶点",
        "toxicity": "毒性",
        "omega-3": "Omega-3",
        "omega 3": "Omega-3",
        "fatty acid": "脂肪酸",
        "metabolic": "代谢",
        "atad2": "ATAD2",
        "bromodomain": "溴结构域",
        "chromatin": "染色质",
        "hydrogel": "水凝胶",
        "nanoparticle": "纳米颗粒",
        "nanocomposite": "纳米复合材料",
        "ferroptosis": "铁死亡",
        "antioxidant": "抗氧化",
        "infection": "感染",
        "diagnostic": "诊断",
        "sequencing": "测序",
        "glioblastoma": "胶质母细胞瘤",
        "cancer": "肿瘤",
        "tumor": "肿瘤",
    }
    for k, v in token_map.items():
        low = low.replace(k, v)
    low = re.sub(r"\s+", " ", low).strip()
    # Remove leftover English fragments to keep Chinese-friendly labels.
    low = re.sub(r"[a-z]+", " ", low)
    low = re.sub(r"\s+", " ", low).strip(" -_/")
    if not low:
        return "研究关键词"
    if re.fullmatch(r"[A-Za-z0-9\-/\s]+", low):
        return "研究关键词"
    return low


def _clean_theme_token(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return ""
    # Remove meaningless fillers but keep informative parts.
    s = re.sub(r"(影响|包含|相关|研究关键词|研究)", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -_/")
    if not s or s in _BAD_THEME_TOKENS:
        return ""
    return s


def _keywords_to_cn_list(tokens: list[str], max_n: int = 12) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    banned = set(_BAD_THEME_TOKENS)
    for t in tokens:
        cn = _clean_theme_token(_kw_to_cn(str(t)))
        if (not cn) or (cn in banned):
            continue
        key = re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", cn.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(cn)
        if len(out) >= max_n:
            break
    return out

def _domain_name_cn(domain_keywords: list[str], rules: list[tuple[list[str], str]] | None = None) -> str:
    """
    Generate a short Chinese domain/theme name (<=20 chars) from keywords.
    This is a heuristic mapping for local, offline use.
    """
    text = " ".join(str(x).lower() for x in (domain_keywords or []))
    for keys, name in (rules or _DOMAIN_THEME_RULES):
        if any(k in text for k in keys):
            return name[:20]
    # Fallback: derive a readable "XX主题汇总" from top keywords.
    cleaned = []
    for kw in (domain_keywords or []):
        k = _clean_theme_token(str(kw or "").strip())
        if (not k) or (k in _BAD_THEME_TOKENS):
            continue
        k = re.sub(r"\s+", " ", k)
        if k in _BAD_THEME_TOKENS:
            continue
        cleaned.append(k)
        if len(cleaned) >= 2:
            break
    if cleaned:
        base = "/".join(cleaned)
        base = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff/\-\+ ]+", "", base).strip()
        if (not base) or (base in _BAD_THEME_TOKENS):
            return "综合主题汇总"[:20]
        name = f"{base}主题汇总"
        return name[:20]
    return "综合主题汇总"[:20]


def _resolve_st_model_path(model_name_or_path: str, local_files_only: bool) -> str:
    p = Path(model_name_or_path)
    if p.exists():
        return str(p)
    return snapshot_download(repo_id=model_name_or_path, local_files_only=bool(local_files_only))


def _kmeans_labels(embeddings: np.ndarray, k: int) -> np.ndarray:
    from sklearn.cluster import KMeans

    km = KMeans(n_clusters=k, random_state=42, n_init="auto")
    return km.fit_predict(embeddings)


def _desired_cluster_count(n_rows: int, min_domains: int, max_domains: int) -> int:
    if n_rows <= 1:
        return 1
    lo = max(2, int(min_domains))
    hi = max(lo, int(max_domains))
    return max(lo, min(hi, n_rows))


def _cluster_labels(embeddings: np.ndarray, min_cluster_size: int, min_domains: int, max_domains: int) -> np.ndarray:
    n_rows = len(embeddings)
    if n_rows <= 1:
        return np.array([0], dtype=int)

    try:
        import hdbscan

        clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, min_samples=max(2, min_cluster_size // 2))
        labels = clusterer.fit_predict(embeddings)
        non_noise = sorted({int(x) for x in labels if int(x) >= 0})
        # If HDBSCAN yields too few domains, enforce minimum domain coverage via KMeans.
        if len(non_noise) < int(min_domains):
            k = _desired_cluster_count(n_rows, min_domains, max_domains)
            return _kmeans_labels(embeddings, k)
        return labels
    except Exception:
        k = _desired_cluster_count(n_rows, min_domains, max_domains)
        return _kmeans_labels(embeddings, k)


def main() -> None:
    p = argparse.ArgumentParser(description="Step06 glue: sentence-transformers embeddings + clustering.")
    p.add_argument("--input", required=True, help="Step05 keyword/entity JSONL")
    p.add_argument("--paper-domains-output", required=True, help="Output JSONL for per-paper domain labels")
    p.add_argument("--domains-output", required=True, help="Output JSON for domain summaries")
    p.add_argument("--model", default="all-MiniLM-L6-v2")
    p.add_argument(
        "--local-files-only",
        action="store_true",
        help="Only use locally cached HuggingFace files (avoid network).",
    )
    p.add_argument("--min-cluster-size", type=int, default=8)
    p.add_argument("--min-domains", type=int, default=5, help="Minimum domain count per professor when enough papers exist.")
    p.add_argument("--max-domains", type=int, default=8, help="Maximum domain count cap.")
    args = p.parse_args()

    rows = _read_jsonl(Path(args.input))
    texts = [_build_text(r) for r in rows]

    st_path = _resolve_st_model_path(str(args.model), bool(args.local_files_only))
    model = SentenceTransformer(st_path)
    emb = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    labels = _cluster_labels(emb, int(args.min_cluster_size), int(args.min_domains), int(args.max_domains))

    label_names = []
    for lb in labels:
        if int(lb) < 0:
            label_names.append("domain_noise")
        else:
            label_names.append(f"domain_{int(lb)}")

    bucket_keywords: dict[str, list[str]] = defaultdict(list)
    for row, dn in zip(rows, label_names):
        kws = row.get("keywords") or []
        pcs = row.get("project_candidates") or []
        if isinstance(kws, list):
            bucket_keywords[dn].extend([str(x) for x in kws])
        if isinstance(pcs, list):
            bucket_keywords[dn].extend([str(x) for x in pcs])

    domain_kw_top: dict[str, list[str]] = {}
    for dn, tokens in bucket_keywords.items():
        cnt = Counter(t.strip() for t in tokens if str(t).strip())
        domain_kw_top[dn] = _keywords_to_cn_list([k for k, _ in cnt.most_common(20)], max_n=12)
    taxonomy_rules = _load_taxonomy_rules()
    theme_by_dn: dict[str, str] = {}
    for dn in sorted(set(label_names)):
        theme_by_dn[dn] = _domain_name_cn(domain_kw_top.get(dn, []), rules=taxonomy_rules)

    paper_rows: list[dict[str, Any]] = []
    for row, dn in zip(rows, label_names):
        theme_cn = theme_by_dn.get(dn, "综合主题汇总")
        theme_en = ", ".join(domain_kw_top.get(dn, [])[:3])
        paper_rows.append(
            {
                "paper_id": row.get("paper_id"),
                "title": row.get("title"),
                "abstract_snippet": _abstract_snippet(row),
                "pub_date": row.get("pub_date"),
                "identity_score": row.get("identity_score", 1.0),
                "quality_score": row.get("quality_score", 0.0),
                "domain_label": dn,
                "domain_confidence": 1.0,
                "domain_keywords": domain_kw_top.get(dn, []),
                "domain_theme_en": theme_en,
                "domain_theme_cn": theme_cn,
                # Backward-compatible field used by DB/views (prefer CN short name).
                "domain_theme": theme_cn,
            }
        )

    domains = []
    for dn in sorted(set(label_names)):
        dn_rows = [r for r, x in zip(rows, label_names) if x == dn]
        quality_vals: list[float] = []
        for r in dn_rows:
            try:
                quality_vals.append(float(r.get("quality_score", 0.0) or 0.0))
            except Exception:
                continue
        avg_quality = (sum(quality_vals) / len(quality_vals)) if quality_vals else 0.0
        domain_rows = [row for row, x in zip(rows, label_names) if x == dn]
        theme_cn = theme_by_dn.get(dn, "综合主题汇总")
        theme_en = ", ".join(domain_kw_top.get(dn, [])[:3])
        evidence_papers = []
        for er in domain_rows:
            title = str(er.get("title") or "").strip()
            if not title:
                continue
            evidence_papers.append(
                {
                    "paper_id": er.get("paper_id"),
                    "title": title,
                    "abstract_snippet": _abstract_snippet(er),
                }
            )
            if len(evidence_papers) >= 3:
                break
        if theme_cn == "综合主题汇总":
            _append_learning_queue(
                domain_label=dn,
                tokens=domain_kw_top.get(dn, []),
                evidence_titles=[str(x.get("title") or "") for x in evidence_papers],
            )
        domains.append(
            {
                "domain_label": dn,
                "paper_count": sum(1 for x in label_names if x == dn),
                "domain_keywords": domain_kw_top.get(dn, []),
                "domain_theme_en": theme_en,
                "domain_theme_cn": theme_cn,
                "domain_theme": theme_cn,
                "avg_quality_score": round(avg_quality, 6),
                "evidence_papers": evidence_papers,
            }
        )

    _write_jsonl(Path(args.paper_domains_output), paper_rows)
    _write_json(Path(args.domains_output), {"domains": domains})
    print(args.paper_domains_output)
    print(args.domains_output)


if __name__ == "__main__":
    main()

