# 输入/输出文件契约（Step 01 -> Step 08）

为避免不同步骤在字段/文件命名上产生偏差，建议你按下面“最小契约”实现：

## Step 01（保持现有 datacollection）

- 输入：教授名 + SeedPaperTitle/SeedPMID（可选 ExtraUrls）
- 输出（按 `OutputPrefix`）：
  - `01_data_collection/step_results/professor_paper_titles/*_titles.json`
  - `01_data_collection/step_results/professor_paper_abstracts/*_abstracts.json`（包含：title/abstract/pub_date/doi/authors）
  - `01_data_collection/step_results/professor_paper_abstracts/*_abstracts.jsonl`（同上，JSONL 便于下游流水线）
  - `01_data_collection/step_results/professor_lab_info/*_lab_info.json`（包含：top affiliations + `pmid_affiliations` 映射）

## Step 02：02_paper_list_extend

- 输入：
  - 来自 Step 01 的 `professor_paper_titles/*_titles.json`
  - 来自 Step 01 的 `professor_paper_abstracts/*_abstracts.json`
- 输出（建议）：
  - `02_paper_list_extend/step_results/*_expanded_papers.jsonl`

## Step 03：03_author_disambiguation

- 输入：
  - `02_paper_list_extend/step_results/*_expanded_papers.jsonl`
  - （可选）`01_data_collection/step_results/professor_lab_info/*_lab_info.json`
- 输出（建议）：
  - `03_author_disambiguation/step_results/*_step03_disambiguated_papers.jsonl`

## Step 04：04_keyword_entity

- 输入：
  - `03_author_disambiguation/step_results/*_step03_disambiguated_papers.jsonl`
- 输出（建议）：
  - `04_keyword_entity/step_results/*_step04_keyword_entity.jsonl`

## Step 05：05_domain_analysis

- 输入：
  - `04_keyword_entity/step_results/*_step04_keyword_entity.jsonl`
- 输出（建议）：
  - `05_domain_analysis/step_results/*_step05_paper_domains.jsonl`
  - `05_domain_analysis/step_results/*_step05_domains.json`
  - `05_domain_analysis/step_results/*_step05_wordcloud_terms.json`
  - `05_domain_analysis/step_results/*_step05_wordcloud.png`

说明：
- 该步内部并列运行 `domain_clustering + tag_taxonomy + wordcloud`

## Step 06：06_temporal_analysis

- 输入：
  - `05_domain_analysis/step_results/*_step05_paper_domains.jsonl`
- 输出（建议）：
  - `06_temporal_analysis/step_results/*_step06_project_timeline.json`
  - `06_temporal_analysis/step_results/*_step06_effort_allocation.json`
  - `06_temporal_analysis/step_results/*_step06_trend_report.md`

## Step 07：07_visualization

- 输入：
  - `05_domain_analysis/step_results/*_step05_paper_domains.jsonl`
  - `06_temporal_analysis/step_results/*_step06_project_timeline.json`
- 输出（建议）：
  - `07_visualization/step_results/pipeline.duckdb`
  - `07_visualization/step_results/*_source_sites.json`

## Step 08：08_quality_guard

- 输入：
  - Step02 ~ Step06 产物
  - Step05 词云产物
- 输出（建议）：
  - `08_quality_guard/step_results/*_step08_quality_report.json`
  - `08_quality_guard/step_results/*_step08_quality_report.md`

