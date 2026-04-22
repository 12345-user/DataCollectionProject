from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CFG = Path("08_taxonomy_memory/config/tag_taxonomy_3layer.yaml")
_DEFAULT_LEARNED_L2 = Path("08_taxonomy_memory/step_results/learned_l2.jsonl")
_DEFAULT_LEARNED_L3 = Path("08_taxonomy_memory/step_results/learned_l3.jsonl")
_DEFAULT_STOPWORDS = Path("08_taxonomy_memory/config/stopwords_zh.yaml")
_DEFAULT_MESH_LEXICON = Path("08_taxonomy_memory/resources/mesh/mesh_terms.jsonl")
_DEFAULT_MESH_MAPPING = Path("08_taxonomy_memory/config/mesh_mapping.yaml")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _norm_key(s: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (s or "").lower()).strip()


def _load_stopwords(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        obj = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        sw = obj.get("stopwords", []) or []
        return {str(x).strip() for x in sw if str(x).strip()}
    except Exception:
        return set()


def _load_cfg(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {"l1_categories": [], "l2_tags": [], "l3_tags": []}
    obj = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
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
    return {"l1_categories": out.get("l1_categories", []), "l2_tags": out.get("l2_tags", []), "l3_tags": out.get("l3_tags", [])}


def _merge_learned(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Deduplicate learned tags by normalized key to avoid repeated/near-duplicate rows.
    # Prefer Chinese display name when available.
    by_key: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name_zh") or r.get("name") or "").strip()
        kws = [str(x).strip().lower() for x in (r.get("keywords") or []) if str(x).strip()]
        if not name or not kws:
            continue
        key = _norm_key(name)
        if not key:
            continue
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = {"name": name, "keywords": kws}
            continue
        # merge keywords
        merged = list(dict.fromkeys((prev.get("keywords") or []) + kws))
        by_key[key] = {"name": prev.get("name") or name, "keywords": merged}
    return list(by_key.values())


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Deduplicate weighted tag items by normalized key, then re-normalize weights to sum to 1.
    """
    score: dict[str, float] = {}
    rep: dict[str, str] = {}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        n = str(it.get("tag_name") or "").strip()
        if not n:
            continue
        k = _norm_key(n)
        if not k:
            continue
        try:
            w = float(it.get("tag_weight", 0.0) or 0.0)
        except Exception:
            w = 0.0
        if w <= 0.0:
            continue
        score[k] = score.get(k, 0.0) + w
        # keep the longer representative name (usually more specific)
        prev = rep.get(k, "")
        rep[k] = n if len(n) >= len(prev) else prev
    if not score:
        return []
    ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)
    total = sum(v for _, v in ranked) or 1.0
    return [{"tag_name": rep.get(k, k), "tag_weight": round(float(v / total), 6)} for k, v in ranked]


def _match(text: str, rows: list[dict[str, Any]], max_k: int, min_weight: float, stopwords: set[str]) -> list[dict[str, Any]]:
    text_low = (text or "").lower()
    scored: list[tuple[str, float, int]] = []
    for r in rows:
        name = str(r.get("name") or "").strip()
        if not name or name in stopwords:
            continue
        kws = r.get("keywords") or []
        hits = 0
        for kw in kws:
            if kw and kw in text_low:
                hits += 1
        if hits <= 0:
            continue
        # Weight favors multiple evidence; normalize roughly by keywords length.
        denom = max(3.0, float(len(kws)) * 0.25)
        w = min(1.0, hits / denom)
        scored.append((name, float(w), int(hits)))
    if not scored:
        return []
    scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
    kept = [(n, w) for n, w, _ in scored if w >= float(min_weight)]
    kept = kept[: max(1, int(max_k))]
    total = sum(w for _, w in kept) or 1.0
    return _dedupe_items([{"tag_name": n, "tag_weight": round(float(w / total), 6)} for n, w in kept])


def _pick_l1(text: str, l1_rows: list[dict[str, Any]], stopwords: set[str]) -> str:
    items = _match(text, l1_rows, max_k=1, min_weight=0.01, stopwords=stopwords)
    if items:
        return str(items[0].get("tag_name") or "").strip() or "方法学/工具开发"
    return "方法学/工具开发"


@dataclass
class TaggerConfig:
    cfg_path: Path = _DEFAULT_CFG
    learned_l2_path: Path = _DEFAULT_LEARNED_L2
    learned_l3_path: Path = _DEFAULT_LEARNED_L3
    stopwords_path: Path = _DEFAULT_STOPWORDS
    l2_top_k: int = 2
    l3_top_k: int = 2
    layer_min_weight: float = 0.2
    mesh_lexicon_path: Path = _DEFAULT_MESH_LEXICON
    mesh_mapping_path: Path = _DEFAULT_MESH_MAPPING


def _load_mesh_terms(path: Path) -> list[str]:
    terms: list[str] = []
    for r in _read_jsonl(path):
        t = str(r.get("mesh_term") or "").strip()
        if t:
            terms.append(t)
    return terms


def _load_mesh_mapping(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        obj = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    rows = obj.get("mappings", []) or []
    out: dict[str, dict[str, str]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        mt = str(r.get("mesh_term") or "").strip().lower()
        if not mt:
            continue
        out[mt] = {
            "l2_tag": str(r.get("l2_tag") or "").strip(),
            "l3_tag": str(r.get("l3_tag") or "").strip(),
        }
    return out


def _mesh_map(text: str, terms: list[str], mapping: dict[str, dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    low = (text or "").lower()
    l2_hits: list[str] = []
    l3_hits: list[str] = []
    for t in terms:
        tl = t.lower()
        if tl not in low:
            continue
        m = mapping.get(tl, {})
        l2 = str(m.get("l2_tag") or "").strip()
        l3 = str(m.get("l3_tag") or "").strip()
        if l2:
            l2_hits.append(l2)
        if l3:
            l3_hits.append(l3)
    def _to_weighted(names: list[str]) -> list[dict[str, Any]]:
        c = {}
        for n in names:
            c[n] = c.get(n, 0) + 1
        if not c:
            return []
        total = float(sum(c.values())) or 1.0
        return [{"tag_name": k, "tag_weight": round(v / total, 6)} for k, v in sorted(c.items(), key=lambda x: x[1], reverse=True)]
    return _to_weighted(l2_hits), _to_weighted(l3_hits)


def tag_paper(text: str, config: TaggerConfig | None = None) -> dict[str, Any]:
    cfg = config or TaggerConfig()
    stopwords = _load_stopwords(cfg.stopwords_path)
    base = _load_cfg(cfg.cfg_path)
    learned_l2 = _merge_learned(_read_jsonl(cfg.learned_l2_path))
    learned_l3 = _merge_learned(_read_jsonl(cfg.learned_l3_path))

    l1_rows = base.get("l1_categories", [])
    l2_rows = learned_l2 + base.get("l2_tags", [])
    l3_rows = learned_l3 + base.get("l3_tags", [])

    mesh_terms = _load_mesh_terms(cfg.mesh_lexicon_path)
    mesh_map = _load_mesh_mapping(cfg.mesh_mapping_path)
    mesh_l2, mesh_l3 = _mesh_map(text, mesh_terms, mesh_map) if mesh_terms else ([], [])

    l1 = _pick_l1(text, l1_rows, stopwords=stopwords)
    l2_items = _match(text, l2_rows, max_k=cfg.l2_top_k, min_weight=cfg.layer_min_weight, stopwords=stopwords)
    l3_items = _match(text, l3_rows, max_k=cfg.l3_top_k, min_weight=cfg.layer_min_weight, stopwords=stopwords)

    # A+B融合：优先合并 MeSH 命中，增强生物医学标签稳定性
    def _merge_items(base_items: list[dict[str, Any]], extra_items: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        score: dict[str, float] = {}
        for it in base_items:
            n = str(it.get("tag_name") or "").strip()
            if not n:
                continue
            score[n] = score.get(n, 0.0) + float(it.get("tag_weight", 0.0) or 0.0)
        for it in extra_items:
            n = str(it.get("tag_name") or "").strip()
            if not n:
                continue
            score[n] = score.get(n, 0.0) + 0.6 * float(it.get("tag_weight", 0.0) or 0.0)
        if not score:
            return []
        ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)[: max(1, int(top_k))]
        total = sum(v for _, v in ranked) or 1.0
        return [{"tag_name": n, "tag_weight": round(v / total, 6)} for n, v in ranked]

    l2_items = _merge_items(l2_items, mesh_l2, cfg.l2_top_k)
    l3_items = _merge_items(l3_items, mesh_l3, cfg.l3_top_k)
    l2_items = _dedupe_items(l2_items)[: max(1, int(cfg.l2_top_k))]
    l3_items = _dedupe_items(l3_items)[: max(1, int(cfg.l3_top_k))]
    return {"layer_l1_tag": l1, "layer_l2_items": l2_items, "layer_l3_items": l3_items}

