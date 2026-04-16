# 05_keyword_entity / processing

建议的数据字段（供后续 Step 06/07 直接消费）：

- `paper_id`（可用 PMID/DOI/哈希）
- `title`
- `abstract`
- `keywords[]`
- `entities[]`
- `project_candidates[]`（由 keywords/entities 生成）
- `identity_score`（来自 Step 04，如果有）

Project 候选归一化（供 Step 07 使用）：
1. 候选项目名 = 高频 n-gram（3-6 gram）+ 技术实体 + 引用语境中的项目型短语
2. 去掉非项目停用词
3. 同义合并（可用简单规则或向量相似度聚合）

