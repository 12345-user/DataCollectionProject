# 04_author_disambiguation / processing

这里放消歧实现与必要的 ML/规则封装。

建议数据流字段（输入结构化后沿用）：
- `title`
- `abstract`
- `authors[]`（姓名、机构、可选作者顺序）
- `affiliations[]`
- `publication_date`

输出结构建议：
- `papers[]`：保留后的目标教授论文
- `paper_scores[]`：每篇的身份一致性分数与解释

