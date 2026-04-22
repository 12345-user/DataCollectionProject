import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _norm_key(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


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


def _load_stopwords_zh(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        # allow JSON as well
        if isinstance(obj, dict):
            rows = obj.get("stopwords") or []
            return {str(x).strip() for x in rows if str(x).strip()}
    except Exception:
        pass
    # minimal YAML parsing (the file is tiny and predictable)
    sw: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            sw.add(line.lstrip("-").strip())
    return {x for x in sw if x}


_EN_STOP = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "for",
    "from",
    "have",
    "has",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "new",
    "novel",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "this",
    "to",
    "via",
    "was",
    "were",
    "we",
    "with",
}


def _has_cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in (s or ""))


def _has_ascii_alpha(s: str) -> bool:
    return bool(re.search(r"[A-Za-z]", s or ""))


def _to_tag_name_zh(name: str) -> str:
    """
    Local, no-API bilingual mapping.
    - If already Chinese, keep.
    - Else map common biomedical/CS terms to Chinese; fallback to "<EN>相关".
    """
    s = (name or "").strip()
    if not s:
        return ""
    if _has_cjk(s) and not _has_ascii_alpha(s):
        return s
    low = _norm_key(s)
    token_map = {
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
        "cancer genome atlas": "癌症基因组图谱",
        "genome atlas": "基因组图谱",
        "updated database": "更新数据库",
    }
    token_map_norm = {_norm_key(k): v for k, v in token_map.items()}
    if low in token_map_norm:
        return token_map_norm[low]

    # Phrase-level replacement then remove leftover English fragments.
    out = (name or "").strip().lower()
    for k in sorted(token_map.keys(), key=len, reverse=True):
        out = out.replace(k, token_map[k])
    out = re.sub(r"[A-Za-z]+", " ", out)
    out = re.sub(r"\s+", " ", out).strip(" -_/，。;；()[]{}")
    if _has_cjk(out) and not _has_ascii_alpha(out):
        return out
    only_zh = "".join(
        [ch for ch in out if ("\u4e00" <= ch <= "\u9fff") or ch in "/-+（）()、，； "]
    ).strip()
    only_zh = re.sub(r"\s+", " ", only_zh).strip(" -_/，。;；")
    if _has_cjk(only_zh) and not _has_ascii_alpha(only_zh):
        return only_zh
    return "综合主题汇总"


def _tokenize_en(s: str) -> list[str]:
    toks = [t for t in _norm_key(s).replace("/", " ").replace("-", " ").split() if t]
    return toks


def _is_good_candidate(
    name: str,
    keywords: list[str],
    *,
    min_score: int,
    score: int,
    min_len_cjk: int,
    min_len_ascii: int,
    stopwords_zh: set[str],
) -> tuple[bool, str]:
    n = (name or "").strip()
    if not n:
        return False, "empty"
    if score < int(min_score):
        return False, f"score<{min_score}"

    # basic cleanup
    n_norm = _norm_key(n)
    if not n_norm:
        return False, "empty_norm"

    # reject if contains obvious boilerplate tokens
    if any(x in n for x in ("http://", "https://", "www.")):
        return False, "url_like"

    # Chinese stopword containment (very short Chinese phrases are often meaningless)
    if _has_cjk(n):
        if len(n) < int(min_len_cjk):
            return False, "cjk_too_short"
        if any(sw and (sw in n) and (len(n) <= len(sw) + 2) for sw in stopwords_zh):
            return False, "mostly_stopword_zh"
        return True, "ok"

    # ASCII/English-like gating
    toks = _tokenize_en(n)
    if not toks:
        return False, "no_tokens"
    if len(n_norm) < int(min_len_ascii):
        return False, "ascii_too_short"

    # reject if starts/ends with stopwords (e.g., "of mirna", "framework for")
    if toks and toks[0] in _EN_STOP:
        return False, "starts_with_stopword"
    if toks and toks[-1] in _EN_STOP:
        return False, "ends_with_stopword"

    # reject if contains verb-ish glue like "are/is/was" anywhere (e.g., "mirnas are small")
    if any(t in {"are", "is", "was", "were"} for t in toks):
        return False, "contains_copula"

    # reject phrases dominated by stopwords
    non_stop = [t for t in toks if t not in _EN_STOP]
    if not non_stop:
        return False, "all_stopwords"
    if len(non_stop) <= 1 and len(toks) >= 2:
        return False, "stopword_heavy"
    # if short phrase (<=3 tokens) contains any stopword inside, it is usually boilerplate ("database has ...", "x for y")
    if len(toks) <= 3 and any(t in _EN_STOP for t in toks):
        return False, "short_contains_stopword"

    # require some "content": at least one token length >= 3 (avoid "of mi")
    if not any(len(t) >= 3 for t in non_stop):
        return False, "no_content_token"

    # keywords sanity
    kws = [str(x).strip() for x in (keywords or []) if str(x).strip()]
    if not kws:
        return False, "no_keywords"

    # reject truncated prefixes like "xxx signific" when keyword is "xxx significantly"
    # (often caused by candidate extraction max-length cutting mid-token)
    k0 = _norm_key(kws[0])
    if k0 and k0.startswith(n_norm) and len(k0) - len(n_norm) >= 4:
        try:
            if n_norm and n_norm[-1].isalpha():
                nxt = k0[len(n_norm)] if len(k0) > len(n_norm) else ""
                if nxt.isalpha():
                    return False, "truncated_prefix"
        except Exception:
            pass

    return True, "ok"


def _append_learned(learned_path: Path, level: str, name: str, keywords: list[str]) -> None:
    learned_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    name_en = name if not _has_cjk(name) else ""
    name_zh = _to_tag_name_zh(name)
    with learned_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(
            json.dumps(
                {
                    "name": name,
                    "name_en": name_en,
                    "name_zh": name_zh,
                    "keywords": keywords[:10],
                    "level": level,
                    "learned_at": ts,
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def _purge_and_rewrite_learned(
    learned_path: Path,
    *,
    min_score: int,
    min_len_cjk: int,
    min_len_ascii: int,
    stopwords_zh: set[str],
) -> dict[str, int]:
    rows = _read_jsonl(learned_path)
    kept: dict[str, dict[str, Any]] = {}
    dropped = 0
    for r in rows:
        name = str(r.get("name") or "").strip()
        kws = [str(x).strip() for x in (r.get("keywords") or []) if str(x).strip()]
        # (re)compute bilingual fields so Chinese display stays clean
        if name:
            r["name_zh"] = _to_tag_name_zh(str(r.get("name_en") or name))
            r["name_en"] = str(r.get("name_en") or "").strip() or (name if (name and not _has_cjk(name)) else "")
        # learned rows may not have score; treat as high enough to be judged by content
        ok, _reason = _is_good_candidate(
            name,
            kws,
            min_score=min_score,
            score=max(int(min_score), 999),
            min_len_cjk=min_len_cjk,
            min_len_ascii=min_len_ascii,
            stopwords_zh=stopwords_zh,
        )
        if not ok:
            dropped += 1
            continue
        key = _norm_key(name)
        prev = kept.get(key)
        if prev is None:
            kept[key] = r
            continue
        # keep newest learned_at
        if str(r.get("learned_at") or "") > str(prev.get("learned_at") or ""):
            kept[key] = r
    out_rows = sorted(kept.values(), key=lambda x: str(x.get("learned_at") or ""), reverse=False)
    learned_path.parent.mkdir(parents=True, exist_ok=True)
    learned_path.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in out_rows) + ("\n" if out_rows else ""),
        encoding="utf-8",
    )
    return {"before": len(rows), "after": len(out_rows), "dropped": dropped}


def main() -> None:
    p = argparse.ArgumentParser(description="Review and promote L2/L3 queue records into learned taxonomy.")
    p.add_argument("--queue-l2", default="08_taxonomy_memory/step_results/learning_queue_l2.jsonl")
    p.add_argument("--queue-l3", default="08_taxonomy_memory/step_results/learning_queue_l3.jsonl")
    p.add_argument("--learned-l2", default="08_taxonomy_memory/step_results/learned_l2.jsonl")
    p.add_argument("--learned-l3", default="08_taxonomy_memory/step_results/learned_l3.jsonl")
    p.add_argument("--approve-contains", default="", help="approve only candidates containing this substring")
    p.add_argument("--min-score", type=int, default=8, help="min queue score to approve (default: 8)")
    p.add_argument("--min-len-cjk", type=int, default=2, help="min length for Chinese tags (default: 2)")
    p.add_argument("--min-len-ascii", type=int, default=6, help="min length for ASCII tags (default: 6)")
    p.add_argument(
        "--stopwords-zh",
        default="08_taxonomy_memory/config/stopwords_zh.yaml",
        help="Chinese stopwords yaml (default: 08_taxonomy_memory/config/stopwords_zh.yaml)",
    )
    p.add_argument("--purge-learned", action="store_true", help="purge and rewrite learned files before approving")
    args = p.parse_args()

    stopwords_zh = _load_stopwords_zh(Path(args.stopwords_zh))

    if args.purge_learned:
        s2 = _purge_and_rewrite_learned(
            Path(args.learned_l2),
            min_score=int(args.min_score),
            min_len_cjk=int(args.min_len_cjk),
            min_len_ascii=int(args.min_len_ascii),
            stopwords_zh=stopwords_zh,
        )
        s3 = _purge_and_rewrite_learned(
            Path(args.learned_l3),
            min_score=int(args.min_score),
            min_len_cjk=int(args.min_len_cjk),
            min_len_ascii=int(args.min_len_ascii),
            stopwords_zh=stopwords_zh,
        )
        print(f"[ok] purged learned_l2: {s2}")
        print(f"[ok] purged learned_l3: {s3}")

    approved = 0
    rejected = 0
    for q_path, l_path, level in [
        (Path(args.queue_l2), Path(args.learned_l2), "L2"),
        (Path(args.queue_l3), Path(args.learned_l3), "L3"),
    ]:
        existing = {str(r.get("name") or "").strip().lower() for r in _read_jsonl(l_path) if str(r.get("name") or "").strip()}
        rows = _read_jsonl(q_path)
        for r in rows:
            name = str(r.get("candidate_name") or "").strip()
            kws = [str(x).strip() for x in (r.get("keywords") or []) if str(x).strip()]
            score = 0
            try:
                score = int(r.get("score") or 0)
            except Exception:
                score = 0
            if not name or not kws:
                rejected += 1
                continue
            if args.approve_contains and args.approve_contains not in name:
                continue
            if name.strip().lower() in existing:
                continue
            ok, _reason = _is_good_candidate(
                name,
                kws,
                min_score=int(args.min_score),
                score=int(score),
                min_len_cjk=int(args.min_len_cjk),
                min_len_ascii=int(args.min_len_ascii),
                stopwords_zh=stopwords_zh,
            )
            if not ok:
                rejected += 1
                continue
            _append_learned(l_path, level=level, name=name, keywords=kws)
            approved += 1
    print(f"[ok] approved into learned: {approved} (rejected: {rejected})")


if __name__ == "__main__":
    main()

