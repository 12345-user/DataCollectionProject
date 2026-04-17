# Step 02 输入来源（from_step01）

来源：`01_data_collection/step_results`

推荐拷贝/对齐的输入文件（匹配同一个 `OutputPrefix`）：

- `01_data_collection/step_results/professor_paper_titles/*_titles.json`
- `01_data_collection/step_results/professor_paper_abstracts/*_abstracts.json`
- `01_data_collection/step_results/professor_paper_abstracts/*_abstracts.jsonl`（Step 02 优先读取）

可选（如果 Step 01 已生成 DOI/链接等字段，或你后续接入）：
- `01_data_collection/step_results/professor_lab_info/*_lab_info.json`（用于辅助同名消歧/身份一致性）

## 自动同步（已集成到 Step01 一键命令）

当你运行：
- `scripts/bootstrap/run_professor_collection_simple.ps1`
- 或 `scripts/bootstrap/run_professor_collection_simple_by_url.ps1`

Step01 执行结束后会自动调用：
- `scripts/bootstrap/bridge_step01_to_step02.ps1`

把结果同步到：
- `02_paper_list_extend/data_sources/from_step01/<OutputPrefix>/`

其中会生成：
- `abstracts.jsonl`
- `abstracts.json`
- `titles.json`
- `lab_info.json`

