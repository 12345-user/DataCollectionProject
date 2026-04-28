import argparse
import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="Train local SetFit classifier from reviewed taxonomy memory samples.")
    p.add_argument("--train-jsonl", default="05_domain_analysis/step_results/domain_taxonomy_learned.jsonl")
    p.add_argument("--output-dir", default="05_domain_analysis/models/setfit_local")
    p.add_argument("--base-model", default="sentence-transformers/all-MiniLM-L6-v2")
    p.add_argument("--local-files-only", action="store_true")
    args = p.parse_args()

    rows = _read_jsonl(Path(args.train_jsonl))
    if not rows:
        print("[info] no learned samples, skip SetFit training")
        return

    try:
        from datasets import Dataset  # type: ignore
        from setfit import SetFitModel, Trainer, TrainingArguments  # type: ignore
    except Exception as e:
        print(f"[warn] SetFit dependencies unavailable, skip training: {e}")
        return

    texts: list[str] = []
    labels: list[str] = []
    for r in rows:
        name = str(r.get("name") or "").strip()
        kws = [str(x).strip() for x in (r.get("keywords") or []) if str(x).strip()]
        if not name or not kws:
            continue
        texts.append(" ".join(kws[:8]))
        labels.append(name)
    if len(set(labels)) < 2 or len(texts) < 8:
        print("[info] insufficient class diversity for SetFit training")
        return

    ds = Dataset.from_dict({"text": texts, "label": labels})
    model = SetFitModel.from_pretrained(args.base_model, local_files_only=bool(args.local_files_only))
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            num_epochs=1,
            batch_size=8,
        ),
        train_dataset=ds,
    )
    trainer.train()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out_dir))
    print(str(out_dir))


if __name__ == "__main__":
    main()

