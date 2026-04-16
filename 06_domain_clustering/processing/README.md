# 06_domain_clustering / processing

建议的数据字段：
- `paper_id`
- `text_for_embedding`（abstract 或 keywords/entities 拼接）

输出结构建议：
- `paper_domains[]`：`{paper_id, domain_label, domain_confidence(optional)}`
- `domains[]`：每个 domain 的代表关键词、中心向量/摘要片段

