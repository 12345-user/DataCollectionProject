from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


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


def _tokenize(text: str) -> list[str]:
    # Keep both chinese and english tokens.
    text = (text or "").lower()
    # normalize punctuation
    text = re.sub(r"[\u2028\u2029]", " ", text)
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    toks = [t.strip() for t in text.split() if t.strip()]
    return toks


def _ngram_phrases(tokens: list[str], n: int) -> list[str]:
    if len(tokens) < n:
        return []
    return [" ".join(tokens[i : i + n]) for i in range(0, len(tokens) - n + 1)]


def main() -> None:
    p = argparse.ArgumentParser(description="Extract L2/L3 tag candidates from abstracts locally (no API).")
    p.add_argument("--input-jsonl", required=True, help="Step04 keyword_entity jsonl")
    p.add_argument("--output-l2", default="05_domain_analysis/step_results/learning_queue_l2.jsonl")
    p.add_argument("--output-l3", default="05_domain_analysis/step_results/learning_queue_l3.jsonl")
    p.add_argument("--min-count", type=int, default=2)
    p.add_argument("--max-candidates", type=int, default=80)
    args = p.parse_args()

    rows = _read_jsonl(Path(args.input_jsonl))
    if not rows:
        print("[info] empty input, skip")
        return

    # Heuristic split:
    # - L2: domain-ish terms (bio/medicine keywords)
    # - L3: methods/tech terms
    l3_seed = {
        "deep learning",
        "neural network",
        "transformer",
        "database",
        "atlas",
        "platform",
        "framework",
        "pipeline",
        "dataset",
        "benchmark",
        "graph",
        "知识图谱",
        "数据库",
        "平台",
        "深度学习",
        "神经网络",
        "模型",
        "框架",
        "流程",
        "数据集",
        "评测",
    }
    l2_seed = {
        "cancer",
        "tumor",
        "glioblastoma",
        "mirna",
        "microrna",
        "drug",
        "toxicity",
        "adverse",
        "immun",
        "omics",
        "肿瘤",
        "癌",
        "微小rna",
        "药物",
        "毒性",
        "不良反应",
        "免疫",
        "组学",
        "转录组",
        "蛋白组",
    }

    c2: Counter[str] = Counter()
    c3: Counter[str] = Counter()
    examples2: dict[str, list[str]] = {}
    examples3: dict[str, list[str]] = {}

    for r in rows:
        title = str(r.get("title") or "").strip()
        abstract = str(r.get("abstract") or "").strip()
        text = f"{title}\n{abstract}"
        toks = _tokenize(text)
        phrases = []
        for n in (1, 2, 3):
            phrases.extend(_ngram_phrases(toks, n))
        phrases = [p for p in phrases if len(p) >= 2]

        for ph in phrases:
            key = ph.strip()
            if not key:
                continue
            if any(seed in key for seed in l3_seed):
                c3[key] += 1
                examples3.setdefault(key, [])
                if title and len(examples3[key]) < 2:
                    examples3[key].append(title)
            if any(seed in key for seed in l2_seed):
                c2[key] += 1
                examples2.setdefault(key, [])
                if title and len(examples2[key]) < 2:
                    examples2[key].append(title)

        # also include Step04 keywords directly
        for kw in (r.get("keywords") or [])[:10]:
            k = str(kw).strip()
            if not k:
                continue
            kl = k.lower()
            if any(seed in kl for seed in l3_seed):
                c3[kl] += 2
                examples3.setdefault(kl, [])
                if title and len(examples3[kl]) < 2:
                    examples3[kl].append(title)
            if any(seed in kl for seed in l2_seed):
                c2[kl] += 2
                examples2.setdefault(kl, [])
                if title and len(examples2[kl]) < 2:
                    examples2[kl].append(title)

    def _write_queue(counter: Counter[str], examples: dict[str, list[str]], out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        kept = [(k, v) for k, v in counter.most_common(args.max_candidates) if int(v) >= int(args.min_count)]
        with out_path.open("w", encoding="utf-8", newline="\n") as f:
            for k, v in kept:
                rec = {
                    "candidate_name": k[:30],
                    "keywords": [k[:80]],
                    "score": int(v),
                    "evidence_titles": examples.get(k, [])[:2],
                    "source": "local_ngram_seed",
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    _write_queue(c2, examples2, Path(args.output_l2))
    _write_queue(c3, examples3, Path(args.output_l3))
    print(str(Path(args.output_l2)))
    print(str(Path(args.output_l3)))


if __name__ == "__main__":
    main()

