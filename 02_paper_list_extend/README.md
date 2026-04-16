# 02_paper_list_extend（扩展论文列表采集）

目标：基于 Step 01 已采集的教授论文元数据，扩展获取同领域/同方向的论文条目，并形成可供后续 PDF 解析与消歧使用的 `JSONL` 元数据文件。

输入（来自 Step 01）：
- `01_data_collection/step_results/professor_paper_titles/*_titles.json`
- `01_data_collection/step_results/professor_paper_abstracts/*_abstracts.json`

可选输入：
- 由 Step 01 抽取的 DOI/链接（如果你在 Step 01 中补齐）
- 由 Step 01 得到的关键词/领域（如果你后续接入 Step 05 反哺）

工具（建议）：
- `paperscraper`：从 `arXiv/bioRxiv/medRxiv/chemRxiv` 批量爬取论文元数据

输出（写入 step_results）：
- `*.jsonl`：扩展后的论文元数据（标题、摘要、发表日期、作者、DOI/链接等）

