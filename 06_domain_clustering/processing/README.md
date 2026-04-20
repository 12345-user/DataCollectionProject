# 06_domain_clustering / processing

目标：把新 Step 04（原 Step 05）的关键词/实体/项目候选转成“研究方向域”。

## 当前环境

项目根 `.venv` 已安装：
- `sentence-transformers`
- `umap-learn`
- `hdbscan`
- `scikit-learn`

共享配置：
- `shared/config/professor_pipeline.env.example`

## 稳定输入输出

输入：
- `05_keyword_entity/step_results/<前缀>_keyword_entity.jsonl`

输出：
- `06_domain_clustering/step_results/<前缀>_paper_domains.jsonl`
- `06_domain_clustering/step_results/<前缀>_domains.json`

建议字段：
- `paper_id`
- `text_for_embedding`
- `domain_label`
- `domain_confidence`
- `domain_keywords`

## 推荐命令形式

```powershell
.\.venv\Scripts\python.exe 06_domain_clustering/processing/run_step06_domain_clustering.py `
  --input 05_keyword_entity/step_results/示例教授_keyword_entity.jsonl `
  --paper-domains-output 06_domain_clustering/step_results/示例教授_paper_domains.jsonl `
  --domains-output 06_domain_clustering/step_results/示例教授_domains.json
```

