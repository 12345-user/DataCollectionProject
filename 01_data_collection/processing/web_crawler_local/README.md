# Local Web Crawler (No API Key)

This crawler provides a first-pass crawl test in `01_data_collection` without external API keys.

## Run

```powershell
python run_local_crawl.py
```

## Inputs

- `crawl_urls.txt`: one URL per line.

## Outputs

- `../../step_results/raw_multisource_dataset/local_crawl_results.json`
- `../../step_results/raw_multisource_dataset/local_crawl_results.md`
