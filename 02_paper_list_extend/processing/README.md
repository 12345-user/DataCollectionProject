# 02_paper_list_extend / processing

这里放 Step 02 的本地执行代码/封装脚本，用于：

1. 读取 Step 01 的论文元数据（titles/abstracts 中的标题与可能的 DOI）
2. 生成扩展搜索任务（例如基于标题相似、关键词、作者线索、或 PubMed MeSH/实体回填）
3. 通过 `paperscraper` 获取 arXiv/bioRxiv/medRxiv/chemRxiv 的元数据
4. 统一字段格式并导出到 `step_results/*.jsonl`

占位约定（建议后续按此接代码）：
- 输入：来自 `../data_sources/` 的本地 json/jsonl
- 输出：写入 `../step_results/expanded_papers_*.jsonl`

