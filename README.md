# Data Collection Pipeline Project

This repository implements a local-first, step-by-step pipeline:

1. `01_data_collection`
2. `02_parsing`
3. `03_feature_extraction`
4. `04_report_generation`
5. `05_delivery`

The current implementation focus is on making step `01_data_collection` runnable end-to-end and providing the full project skeleton for later steps.

## 0) Prerequisites

- Windows 10/11 (PowerShell)
- Python 3.12
- Node.js + npm
- (Optional) API keys for external services

Quick checks:

```powershell
py -3.12 --version
node --version
npm --version
```

## 1) Required Information You Must Fill

### 1.1 Enterprise request input

Fill file:

- `01_data_collection/data_sources/request_profiles/enterprise_search.request.template.yaml`

Minimum required fields before running enterprise collection:

- `target_company.company_name_zh` or `target_company.company_name_en`
- `target_company.official_domains` (at least one domain)
- `search_scope.time_range.start_date`
- `search_scope.time_range.end_date`
- `collection_objectives.required_questions`

### 1.2 Environment variables

#### CrewAI

Copy and edit:

- `01_data_collection/processing/crewai_scheduler/data_collection_orchestrator/.env.example`

Required:

- `OPENAI_API_KEY` (or replace model/provider in config if using another provider)

#### Bright Data MCP

Create `.env` in:

- `01_data_collection/processing/brightdata_mcp_connector/service`

Required:

- `API_TOKEN`

Optional:

- `GROUPS` (for example: `research,advanced_scraping`)

## 2) Step-by-Step Execution

## Step 01 - Data Collection

### 01-A. Run local crawler (no API key required)

Inputs:

- `01_data_collection/processing/web_crawler_local/crawl_urls.txt`

Command:

```powershell
python "01_data_collection/processing/web_crawler_local/run_local_crawl.py"
```

Outputs:

- `01_data_collection/step_results/raw_multisource_dataset/local_crawl_results.json`
- `01_data_collection/step_results/raw_multisource_dataset/local_crawl_results.md`

### 01-B. Run PubMed title collection example

Use this pattern to fetch author publications into project outputs:

```powershell
python -c "import json, urllib.parse, urllib.request, pathlib; term='huang hsien-da[au]'; q=urllib.parse.urlencode({'db':'pubmed','term':term,'retmax':'100000','retmode':'json'}); u='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?'+q; d=json.load(urllib.request.urlopen(u)); ids=d['esearchresult'].get('idlist',[]); titles=[]; from urllib.parse import urlencode; batch=200; [titles.extend([{'pmid':pid,'title':(s.get('result',{}).get(pid,{}).get('title') or '').strip()} for pid in chunk if (s:=json.load(urllib.request.urlopen('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?'+urlencode({'db':'pubmed','id':','.join(chunk),'retmode':'json'}))))]) for chunk in [ids[i:i+batch] for i in range(0,len(ids),batch)]]; out=pathlib.Path(r'01_data_collection/step_results/raw_multisource_dataset/pubmed_titles.json'); out.write_text(json.dumps({'query':term,'count':len(titles),'titles':titles},ensure_ascii=False,indent=2),encoding='utf-8'); print(out)"
```

### 01-C. Run CrewAI orchestrator

Activate runtime and execute:

```powershell
& "01_data_collection/processing/crewai_scheduler/runtime/.venv/Scripts/python.exe" -m src.data_collection_orchestrator.main
```

Working directory for the command above:

- `01_data_collection/processing/crewai_scheduler/data_collection_orchestrator`

Main files:

- `01_data_collection/processing/crewai_scheduler/data_collection_orchestrator/src/data_collection_orchestrator/config/agents.yaml`
- `01_data_collection/processing/crewai_scheduler/data_collection_orchestrator/src/data_collection_orchestrator/config/tasks.yaml`
- `01_data_collection/processing/crewai_scheduler/data_collection_orchestrator/src/data_collection_orchestrator/crew.py`

### 01-D. Start Bright Data MCP service

Working directory:

- `01_data_collection/processing/brightdata_mcp_connector/service`

Commands:

```powershell
npm install
npm run mcp:start
```

or (research tool groups):

```powershell
npm run mcp:start:research
```

## Step 02 - Parsing (structure ready)

Directories:

- `02_parsing/data_sources`
- `02_parsing/processing`
- `02_parsing/step_results`

Fill before execution:

- Parsing engine configs (Unstructured/Marker/PaddleOCR)
- Pydantic schema definitions in `02_parsing/processing/pydantic_modeling`

Expected output location:

- `02_parsing/step_results/structured_json`
- `02_parsing/step_results/structured_markdown`

## Step 03 - Feature Extraction (structure ready)

Directories:

- `03_feature_extraction/data_sources`
- `03_feature_extraction/processing`
- `03_feature_extraction/step_results`

Fill before execution:

- GLiNER model/runtime settings
- Ollama endpoint/model (for example Qwen2.5 local)
- Summary/trend prompt templates

Expected output location:

- `03_feature_extraction/step_results/entities_relations`
- `03_feature_extraction/step_results/summaries`
- `03_feature_extraction/step_results/trend_insights`
- `03_feature_extraction/step_results/report_draft`

## Step 04 - Report Generation (structure ready)

Directories:

- `04_report_generation/data_sources`
- `04_report_generation/processing/python_pptx_template_fill`
- `04_report_generation/processing/deeppresenter_visual_loop`
- `04_report_generation/step_results`

Fill before execution:

- PPT template files in `04_report_generation/processing/python_pptx_template_fill/templates`
- DeepPresenter runtime settings/assets

Expected output location:

- `04_report_generation/step_results/standardized_reports/pptx`
- `04_report_generation/step_results/standardized_reports/pdf`
- `04_report_generation/step_results/presentation_slides_optimized`

## Step 05 - Delivery (structure ready)

Directories:

- `05_delivery/data_sources`
- `05_delivery/processing/openclaw_task_listener`
- `05_delivery/processing/distribution_channels/email`
- `05_delivery/step_results`

Fill before execution:

- Email SMTP settings
- Recipient list
- OpenClaw listener trigger rules

Expected output location:

- `05_delivery/step_results/distribution_logs`
- `05_delivery/step_results/delivery_receipts`

## 3) Pipeline Default Config

Default config file:

- `shared/config/enterprise_search.pipeline.defaults.yaml`

This file enforces local-only mode and defines all key paths for step-01 tooling.

## 4) Recommended Run Order

1. Fill enterprise request template
2. Fill `.env` files (CrewAI, Bright Data MCP)
3. Run local crawler test
4. Run CrewAI orchestration
5. Validate outputs in `01_data_collection/step_results/raw_multisource_dataset`
6. Continue into step-02 parsing
