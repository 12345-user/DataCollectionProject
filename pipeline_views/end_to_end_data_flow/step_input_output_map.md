# 输入/输出文件契约（Step 01 -> Step 06）

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

## Step 03（新）：04_author_disambiguation

- 输入：
  - `02_paper_list_extend/step_results/*_expanded_papers.jsonl`
  - （可选）`01_data_collection/step_results/professor_lab_info/*_lab_info.json`
- 输出（建议）：
  - `04_author_disambiguation/step_results/*_disambiguated_papers.jsonl`

## Step 04（新）：05_keyword_entity

- 输入：
  - `04_author_disambiguation/step_results/*_disambiguated_papers.jsonl`
- 输出（建议）：
  - `05_keyword_entity/step_results/*_keyword_entity.jsonl`

## Step 05（新）：06_domain_clustering

- 输入：
  - `05_keyword_entity/step_results/*_paper_features.jsonl`
- 输出（建议）：
  - `06_domain_clustering/step_results/*_domain_labels.json`

## Step 06（新）：07_temporal_analysis

- 输入：
  - `06_domain_clustering/step_results/*_domain_labels.json`
  - `05_keyword_entity/step_results/*_paper_features.jsonl`（project 统计）
  - 身份一致性权重（若有；否则默认 1）
- 输出（建议）：
  - `07_temporal_analysis/step_results/*_share_current.json`
  - `07_temporal_analysis/step_results/*_trend_future.json`
  - `07_temporal_analysis/step_results/*_consistency_report.md`

