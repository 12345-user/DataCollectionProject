# 08_taxonomy_memory（本地学习记忆层）

目标：在不依赖任何付费 API/token 的前提下，让固定类目随样本增长逐步完善。

## 本地文件

- `shared/config/domain_taxonomy.yaml`：基础固定类目（人工维护，版本化）
- `08_taxonomy_memory/step_results/domain_taxonomy_learning_queue.jsonl`：自动发现待审核候选
- `08_taxonomy_memory/step_results/domain_taxonomy_learned.jsonl`：审核通过后的增量类目
- `08_taxonomy_memory/step_results/domain_taxonomy_report.json`：统计报告

## 执行流程

1. 运行 Step05（聚类）后，未命中的主题会自动写入 learning queue。
2. 人工审核后执行：

```powershell
.\.venv\Scripts\python.exe "08_taxonomy_memory/processing/review_learning_queue.py"
```

3. 生成报告：

```powershell
.\.venv\Scripts\python.exe "08_taxonomy_memory/processing/build_taxonomy_report.py"
```

4. 下次 Step05 会自动读取 learned taxonomy 并优先命中。

## 纯本地说明

- 默认不调用任何付费 API/token。
- SetFit/BERTopic 只建议后续在本地模型缓存完备后启用（可选增强层）。

