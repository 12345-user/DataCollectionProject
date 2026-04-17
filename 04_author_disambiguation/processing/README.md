# 04_author_disambiguation / processing

目标：把 Step 03 的结构化论文结果与 Step 01 的实验室/单位线索合并，过滤同名作者混入。

## 当前环境

项目根 `.venv` 已安装：
- `gliner`
- `sentence-transformers`
- `scikit-learn`

配置模板：
- `shared/config/professor_pipeline.env.example`
- `shared/config/professor_pipeline.io.contract.yaml`

## 稳定输入

- `03_pdf_parsing/step_results/<前缀>_parsed_papers.jsonl`
- `01_data_collection/step_results/<前缀>_lab_info.json`

## 稳定输出

- `04_author_disambiguation/step_results/<前缀>_disambiguated_papers.jsonl`

至少输出字段：
- `paper_id`
- `identity_score`
- `identity_decision`
- `identity_evidence`
- `authors`
- `affiliations`

## 推荐命令形式

后续实现脚本时统一按下面接口：

```powershell
.\.venv\Scripts\python.exe 04_author_disambiguation/processing/run_step04_author_disambiguation.py `
  --parsed-papers 03_pdf_parsing/step_results/示例教授_parsed_papers.jsonl `
  --lab-info 01_data_collection/step_results/示例教授_lab_info.json `
  --output 04_author_disambiguation/step_results/示例教授_disambiguated_papers.jsonl
```

