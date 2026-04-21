import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer
from huggingface_hub import snapshot_download


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

def _domain_name_cn(domain_keywords: list[str]) -> str:
    """
    Generate a short Chinese domain/theme name (<=20 chars) from keywords.
    This is a heuristic mapping for local, offline use.
    """
    text = " ".join(str(x).lower() for x in (domain_keywords or []))
    rules: list[tuple[list[str], str]] = [
        (["microrna", "mirna", "mrna", "regulatory rna", "rna"], "miRNA/RNA调控"),
        (["adverse drug", "adr", "drug target", "dti", "toxicity"], "药物反应与靶点预测"),
        (["omega", "pufa", "fatty acid", "metabolic"], "Omega-3与代谢健康"),
        (["atad2", "bromodomain", "chromatin", "e2f", "myc"], "ATAD2/表观肿瘤机制"),
        (["hydrogel", "nanocomposite", "tendon", "bone healing", "osteoarthritis", "nanoparticle"], "水凝胶/材料修复"),
        (["ferroptosis"], "铁死亡与调控机制"),
        (["antioxidant", "keap1", "xuebijing", "xbj", "baicalein"], "抗氧化/中药机制"),
        (["infection", "diagnostic", "sequencing", "pathogen"], "感染诊断与测序"),
        (["glioblastoma", "gbm", "cancer", "tumor", "oncology"], "肿瘤机制与治疗"),
    ]
    for keys, name in rules:
        if any(k in text for k in keys):
            return name[:20]
    # Fallback: generic but Chinese.
    return "研究主题"[:20]


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
        domain_kw_top[dn] = [k for k, _ in cnt.most_common(12)]

    paper_rows: list[dict[str, Any]] = []
    for row, dn in zip(rows, label_names):
        theme_cn = _domain_name_cn(domain_kw_top.get(dn, []))
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
        theme_cn = _domain_name_cn(domain_kw_top.get(dn, []))
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

