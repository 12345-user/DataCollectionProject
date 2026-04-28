import argparse
import json
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description="Build local MeSH lexicon jsonl from plain term list.")
    p.add_argument("--mesh-terms", required=True, help="Path to text file, one MeSH term per line")
    p.add_argument("--output-jsonl", default="05_domain_analysis/resources/mesh/mesh_terms.jsonl")
    args = p.parse_args()

    src = Path(args.mesh_terms)
    if not src.exists():
        raise FileNotFoundError(f"mesh terms file not found: {src}")

    out = Path(args.output_jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for line in src.read_text(encoding="utf-8", errors="replace").splitlines():
            term = line.strip()
            if not term or term.startswith("#"):
                continue
            row = {"mesh_term": term}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    print(f"[ok] mesh lexicon built: {out} ({count} terms)")


if __name__ == "__main__":
    main()

