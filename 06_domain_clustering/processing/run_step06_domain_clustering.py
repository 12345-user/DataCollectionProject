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
import importlib.util


def _load_step08_tagger():
    tagger_path = Path("08_taxonomy_memory/processing/tagger.py")
    if not tagger_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("step08_tagger", str(tagger_path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules["step08_tagger"] = mod
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod

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
_SETFIT_MODEL_DIR = Path("08_taxonomy_memory/models/setfit_local")
_TAG_TAXONOMY_3L_PATH = Path("08_taxonomy_memory/config/tag_taxonomy_3layer.yaml")
_TAG_TAXONOMY_3L_FALLBACK = Path("shared/config/tag_taxonomy_3layer.yaml")


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
    # Remove meaningless numeric-only labels and collapse repeated segments.
    if re.fullmatch(r"[0-9\.\-]+", s):
        return ""
    parts = [x for x in re.split(r"[ /]+", s) if x]
    uniq_parts: list[str] = []
    for p in parts:
        if not uniq_parts or uniq_parts[-1] != p:
            uniq_parts.append(p)
    s = " ".join(uniq_parts).strip()
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


def _load_setfit_model(model_dir: Path):
    if not model_dir.exists():
        return None
    try:
        from setfit import SetFitModel  # type: ignore

        return SetFitModel.from_pretrained(str(model_dir), local_files_only=True)
    except Exception:
        return None


def _predict_theme_with_setfit(setfit_model: Any, domain_keywords: list[str]) -> str:
    if setfit_model is None:
        return ""
    text = " ".join([str(x).strip() for x in (domain_keywords or []) if str(x).strip()])
    if not text:
        return ""
    try:
        pred = setfit_model.predict([text])
        if not pred:
            return ""
        label = str(pred[0]).strip()
        if not label:
            return ""
        return label[:20]
    except Exception:
        return ""


def _norm_tag_key(s: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", (s or "").lower())


def _dedupe_weighted_items(items: object, top_k: int | None = None) -> list[dict[str, Any]]:
    """
    Dedupe items like [{"tag_name":..., "tag_weight":...}] by normalized key,
    merge weights, then re-normalize to sum to 1.
    """
    if not isinstance(items, list) or not items:
        return []
    score: dict[str, float] = {}
    rep: dict[str, str] = {}
    extra: dict[str, dict[str, Any]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        n = str(it.get("tag_name") or "").strip()
        if not n:
            continue
        k = _norm_tag_key(n)
        if not k:
            continue
        try:
            w = float(it.get("tag_weight", 0.0) or 0.0)
        except Exception:
            w = 0.0
        if w <= 0.0:
            continue
        score[k] = score.get(k, 0.0) + w
        prev = rep.get(k, "")
        rep[k] = n if len(n) >= len(prev) else prev
        extra[k] = it
    if not score:
        return []
    ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)
    if top_k is not None:
        ranked = ranked[: max(1, int(top_k))]
    total = sum(v for _, v in ranked) or 1.0
    out: list[dict[str, Any]] = []
    for k, v in ranked:
        row = dict(extra.get(k, {}))
        row["tag_name"] = rep.get(k, k)
        row["tag_weight"] = round(float(v / total), 6)
        out.append(row)
    return out


def _build_tag_scores_for_paper(
    row: dict[str, Any],
    cluster_tags: list[str],
    min_weight: float,
    top_k: int,
) -> list[dict[str, Any]]:
    candidates: list[str] = []
    for src in (row.get("keywords") or [])[:20]:
        candidates.append(_clean_theme_token(_kw_to_cn(str(src))))
    for src in (row.get("project_candidates") or [])[:20]:
        candidates.append(_clean_theme_token(_kw_to_cn(str(src))))
    candidates.extend(cluster_tags[:8])

    text = f"{row.get('title','')} {row.get('abstract','')}".lower()
    cnt = Counter([c for c in candidates if c and c not in _BAD_THEME_TOKENS])
    if not cnt:
        return []

    raw_scores: dict[str, float] = {}
    max_freq = max(cnt.values()) or 1
    for tag, freq in cnt.items():
        key = _norm_tag_key(tag)
        if not key:
            continue
        freq_score = float(freq) / float(max_freq)
        hit_score = 1.0 if str(tag).lower() in text else 0.0
        cluster_boost = 1.0 if tag in cluster_tags else 0.0
        score = 0.55 * freq_score + 0.25 * hit_score + 0.20 * cluster_boost
        raw_scores[tag] = max(raw_scores.get(tag, 0.0), score)

    if not raw_scores:
        return []
    kept = [(k, v) for k, v in raw_scores.items() if v >= float(min_weight)]
    if not kept:
        kept = sorted(raw_scores.items(), key=lambda x: x[1], reverse=True)[:1]
    kept = sorted(kept, key=lambda x: x[1], reverse=True)[: max(1, int(top_k))]
    total = sum(v for _, v in kept) or 1.0
    items = [
        {"tag_name": k[:30], "tag_weight": round(float(v / total), 6), "raw_score": round(float(v), 6)}
        for k, v in kept
    ]
    return _dedupe_weighted_items(items, top_k=int(top_k))


def _load_tag_taxonomy_3layer() -> dict[str, list[dict[str, Any]]]:
    cfg_path = _TAG_TAXONOMY_3L_PATH if _TAG_TAXONOMY_3L_PATH.exists() else _TAG_TAXONOMY_3L_FALLBACK
    if not cfg_path.exists():
        return {"l1_categories": [], "l2_tags": [], "l3_tags": []}
    try:
        obj = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"l1_categories": [], "l2_tags": [], "l3_tags": []}
    out: dict[str, list[dict[str, Any]]] = {}
    for k in ("l1_categories", "l2_tags", "l3_tags"):
        rows = obj.get(k, []) or []
        if not isinstance(rows, list):
            rows = []
        cleaned: list[dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            name = str(r.get("name") or "").strip()
            kws = [str(x).strip().lower() for x in (r.get("keywords") or []) if str(x).strip()]
            if name and kws:
                cleaned.append({"name": name, "keywords": kws})
        out[k] = cleaned
    return {
        "l1_categories": out.get("l1_categories", []),
        "l2_tags": out.get("l2_tags", []),
        "l3_tags": out.get("l3_tags", []),
    }


def _match_layer_tags(text: str, layer_rows: list[dict[str, Any]], max_k: int, min_weight: float) -> list[dict[str, Any]]:
    text_low = (text or "").lower()
    scored: list[tuple[str, float]] = []
    for r in layer_rows:
        name = str(r.get("name") or "").strip()
        kws = r.get("keywords") or []
        if not name or not kws:
            continue
        hits = 0
        for kw in kws:
            if kw and kw in text_low:
                hits += 1
        if hits <= 0:
            continue
        # Weight: hit ratio with soft cap, favors multiple evidence.
        weight = min(1.0, hits / max(3.0, float(len(kws)) * 0.25))
        scored.append((name, float(weight)))
    if not scored:
        return []
    scored.sort(key=lambda x: x[1], reverse=True)
    kept = [(n, w) for n, w in scored if w >= float(min_weight)]
    kept = kept[: max(1, int(max_k))]
    total = sum(w for _, w in kept) or 1.0
    return [{"tag_name": n, "tag_weight": round(float(w / total), 6)} for n, w in kept]


def _pick_l1(text: str, l1_rows: list[dict[str, Any]]) -> str:
    # Single best L1. If no match, default to 方法学/工具开发 (neutral for many comp bio papers).
    items = _match_layer_tags(text, l1_rows, max_k=1, min_weight=0.01)
    if items:
        return str(items[0].get("tag_name") or "").strip() or "方法学/工具开发"
    return "方法学/工具开发"


def _resolve_st_model_path(model_name_or_path: str, local_files_only: bool) -> str:
    p = Path(model_name_or_path)
    if p.exists():
        return str(p)
    try:
        return snapshot_download(repo_id=model_name_or_path, local_files_only=bool(local_files_only))
    except Exception:
        return ""


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
    p.add_argument(
        "--setfit-model-dir",
        default=str(_SETFIT_MODEL_DIR),
        help="Optional SetFit model path for domain theme prediction (fallback to rules if missing).",
    )
    p.add_argument("--tag-top-k", type=int, default=5, help="Max representative tags per paper.")
    p.add_argument("--tag-min-weight", type=float, default=0.20, help="Drop low-weight tags below this score.")
    p.add_argument("--l2-top-k", type=int, default=2, help="Max L2 tags per paper.")
    p.add_argument("--l3-top-k", type=int, default=2, help="Max L3 tags per paper.")
    p.add_argument("--layer-min-weight", type=float, default=0.20, help="Drop low-weight L2/L3 tags below this score.")
    args = p.parse_args()

    rows = _read_jsonl(Path(args.input))
    texts = [_build_text(r) for r in rows]

    st_path = _resolve_st_model_path(str(args.model), bool(args.local_files_only))
    if st_path:
        model = SentenceTransformer(st_path)
        emb = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        labels = _cluster_labels(emb, int(args.min_cluster_size), int(args.min_domains), int(args.max_domains))
    else:
        # Offline fallback: skip embeddings and treat as one bucket for tag extraction.
        labels = np.zeros(len(texts), dtype=int)

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
    setfit_model = _load_setfit_model(Path(args.setfit_model_dir))
    theme_by_dn: dict[str, str] = {}
    for dn in sorted(set(label_names)):
        model_theme = _predict_theme_with_setfit(setfit_model, domain_kw_top.get(dn, []))
        if model_theme:
            theme_by_dn[dn] = model_theme
        else:
            theme_by_dn[dn] = _domain_name_cn(domain_kw_top.get(dn, []), rules=taxonomy_rules)

    tax3 = _load_tag_taxonomy_3layer()
    l1_rows = tax3.get("l1_categories", [])
    l2_rows = tax3.get("l2_tags", [])
    l3_rows = tax3.get("l3_tags", [])
    step08 = _load_step08_tagger()

    paper_rows: list[dict[str, Any]] = []
    for row, dn in zip(rows, label_names):
        cluster_tags = domain_kw_top.get(dn, [])
        tag_items = _build_tag_scores_for_paper(
            row=row,
            cluster_tags=cluster_tags,
            min_weight=float(args.tag_min_weight),
            top_k=int(args.tag_top_k),
        )
        if not tag_items and cluster_tags:
            tag_items = [{"tag_name": cluster_tags[0], "tag_weight": 1.0, "raw_score": 1.0}]
        tag_names = [str(x.get("tag_name") or "") for x in tag_items if str(x.get("tag_name") or "").strip()]
        primary_tag = tag_names[0] if tag_names else "综合标签"
        full_text = _build_text(row)
        if step08 is not None and hasattr(step08, "tag_paper"):
            tagged = step08.tag_paper(full_text)
            l1 = str(tagged.get("layer_l1_tag") or "").strip() or "方法学/工具开发"
            l2_items = _dedupe_weighted_items(tagged.get("layer_l2_items") or [], top_k=int(args.l2_top_k))
            l3_items = _dedupe_weighted_items(tagged.get("layer_l3_items") or [], top_k=int(args.l3_top_k))
        else:
            l1 = _pick_l1(full_text, l1_rows)
            l2_items = _match_layer_tags(
                full_text,
                l2_rows,
                max_k=int(args.l2_top_k),
                min_weight=float(args.layer_min_weight),
            )
            l3_items = _match_layer_tags(
                full_text,
                l3_rows,
                max_k=int(args.l3_top_k),
                min_weight=float(args.layer_min_weight),
            )
            l2_items = _dedupe_weighted_items(l2_items, top_k=int(args.l2_top_k))
            l3_items = _dedupe_weighted_items(l3_items, top_k=int(args.l3_top_k))
        paper_rows.append(
            {
                "paper_id": row.get("paper_id"),
                "title": row.get("title"),
                "abstract_snippet": _abstract_snippet(row),
                "pub_date": row.get("pub_date"),
                "identity_score": row.get("identity_score", 1.0),
                "quality_score": row.get("quality_score", 0.0),
                "tag_items": _dedupe_weighted_items(tag_items, top_k=int(args.tag_top_k)),
                "tag_names": tag_names,
                "primary_tag_name": primary_tag,
                "tag_filter_pass": True,
                "layer_l1_tag": l1,
                "layer_l2_items": l2_items,
                "layer_l3_items": l3_items,
                # backward compatibility
                "domain_label": primary_tag,
                "domain_theme": primary_tag,
                "domain_theme_cn": primary_tag,
                "domain_keywords": tag_names,
            }
        )

    tags_counter: Counter[str] = Counter()
    tags_weight_sum: defaultdict[str, float] = defaultdict(float)
    tags_papers: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for prow in paper_rows:
        titems = prow.get("tag_items") or []
        for t in titems:
            tn = str(t.get("tag_name") or "").strip()
            try:
                tw = float(t.get("tag_weight", 0.0) or 0.0)
            except Exception:
                continue
            if not tn:
                continue
            tags_counter[tn] += 1
            tags_weight_sum[tn] += tw
            tags_papers[tn].append(
                {
                    "paper_id": prow.get("paper_id"),
                    "title": prow.get("title"),
                    "abstract_snippet": prow.get("abstract_snippet"),
                }
            )

    tags = []
    for tn, c in tags_counter.most_common():
        tags.append(
            {
                "tag_name": tn,
                "paper_count": int(c),
                "avg_tag_weight": round(float(tags_weight_sum[tn] / max(1, c)), 6),
                "total_tag_weight": round(float(tags_weight_sum[tn]), 6),
                "evidence_papers": tags_papers[tn][:3],
            }
        )

    _write_jsonl(Path(args.paper_domains_output), paper_rows)
    _write_json(Path(args.domains_output), {"tags": tags})
    print(args.paper_domains_output)
    print(args.domains_output)


if __name__ == "__main__":
    main()

