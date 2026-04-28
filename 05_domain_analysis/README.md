# 05_domain_analysis（领域聚类）

目标：把“目标教授论文集合”的文本表示成领域标签（domain），并给出领域列表/代表关键词，便于做时间维度的投入推断与未来趋势预测。

输入：
- 新 Step 04（原 Step 05）的摘要文本拼接（或 keywords/entities 拼接文本）

工具（建议）：
- `sentence-transformers`：向量化（例如 `all-MiniLM-L6-v2`）
- `HDBSCAN`：自适应密度聚类
- `UMAP`：可选可视化

输出（写入 step_results）：
- 每篇论文 `domain_label`
- `domains[]`：领域列表与代表关键词（可从 top words/centroid 反推）

