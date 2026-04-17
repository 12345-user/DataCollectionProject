# 05_keyword_entity / processing

目标：从已消歧的论文集合里抽取关键词、实体和项目候选，作为 Step 06/07 的共同输入。

## 当前环境

项目根 `.venv` 已安装：
- `keybert`
- `gliner`
- `sentence-transformers`

共享配置：
- `shared/config/professor_pipeline.env.example`

## 稳定输入输出

输入：
- `04_author_disambiguation/step_results/<前缀>_disambiguated_papers.jsonl`

输出：
- `05_keyword_entity/step_results/<前缀>_keyword_entity.jsonl`

必保留字段：
- `paper_id`
- `title`
- `abstract`
- `keywords`
- `entities`
- `project_candidates`
- `identity_score`

## 推荐命令形式

```powershell
.\.venv\Scripts\python.exe 05_keyword_entity/processing/run_step05_keyword_entity.py `
  --input 04_author_disambiguation/step_results/示例教授_disambiguated_papers.jsonl `
  --output 05_keyword_entity/step_results/示例教授_keyword_entity.jsonl
```

## 归一化建议

1. `project_candidates` 优先来自高频关键词 + 技术实体
2. 同义项目名统一到一个标准名
3. 保留原始证据短语，便于 Step 07 做可解释输出

