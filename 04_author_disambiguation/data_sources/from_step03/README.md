# Step 04 输入来源（from_step03）

来源：`03_pdf_parsing/step_results`

推荐输入：

- `03_pdf_parsing/step_results/*.json`（GROBID + scipdf_parser 的结构化元数据：标题/摘要/作者/发表日期/引用/关键词等）

可选增强（若你实现 Step 03 的缓存/补全字段）：

- Step 03 中提取到的机构/引用段落（用于身份一致性评分与解释性输出）

