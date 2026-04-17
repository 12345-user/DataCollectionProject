from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download paperscraper server dumps for Step 02.")
    parser.add_argument(
        "--output-dir",
        default="02_paper_list_extend/data_sources/paperscraper_server_dumps/server_dumps",
        help="Directory for storing paperscraper dump files.",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["biorxiv", "medrxiv", "chemrxiv"],
        choices=["biorxiv", "medrxiv", "chemrxiv"],
        help="Sources to download.",
    )
    parser.add_argument("--start-date", default="", help="Optional start date YYYY-MM-DD.")
    parser.add_argument("--end-date", default="", help="Optional end date YYYY-MM-DD.")
    parser.add_argument(
        "--recent-days",
        type=int,
        default=0,
        help="If > 0 and start/end not provided, only download recent N days for quicker local deployment/test.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_date = args.start_date.strip()
    end_date = args.end_date.strip()
    if args.recent_days > 0 and not start_date and not end_date:
        end = date.today()
        start = end - timedelta(days=args.recent_days)
        start_date = start.isoformat()
        end_date = end.isoformat()

    from paperscraper.get_dumps import biorxiv, chemrxiv, medrxiv

    downloaders = {
        "biorxiv": biorxiv,
        "medrxiv": medrxiv,
        "chemrxiv": chemrxiv,
    }

    today = date.today().isoformat()
    for source in args.sources:
        save_path = output_dir / f"{source}_{today}.jsonl"
        print(f"[download] {source} -> {save_path}")
        kwargs = {"save_path": str(save_path)}
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        downloaders[source](**kwargs)
        print(f"[done] {source}")


if __name__ == "__main__":
    main()
