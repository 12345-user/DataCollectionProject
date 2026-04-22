# 08_taxonomy_memory（A+B 标签中枢与学习记忆层）

目标：在不依赖任何付费 API/token 的前提下，统一管理三层标签体系并持续学习更新。  
A 路线：MeSH/UMLS 本地词典映射；B 路线：Snorkel + SetFit + BERTopic 本地学习。

## 架构分层

### 1) 配置层（唯一真源）

- `08_taxonomy_memory/config/tag_taxonomy_3layer.yaml`：L1/L2/L3 初始标签体系
- `08_taxonomy_memory/config/stopwords_zh.yaml`：标签清洗停用词
- `08_taxonomy_memory/config/mesh_mapping.yaml`：MeSH 术语映射到 L2/L3（A 路线）

### 2) 资源层（可选）

- `08_taxonomy_memory/resources/mesh/mesh_terms.jsonl`：本地 MeSH 词典（由脚本构建）

### 3) 记忆层（学习闭环）

- `08_taxonomy_memory/step_results/learning_queue_l2.jsonl`
- `08_taxonomy_memory/step_results/learning_queue_l3.jsonl`
- `08_taxonomy_memory/step_results/learned_l2.jsonl`
- `08_taxonomy_memory/step_results/learned_l3.jsonl`
- `08_taxonomy_memory/step_results/tag_report.json`

## 核心执行脚本

- `08_taxonomy_memory/processing/tagger.py`：统一标签判定入口（Step05 直接调用）
- `08_taxonomy_memory/processing/extract_tag_candidates.py`：从摘要提取 L2/L3 候选
- `08_taxonomy_memory/processing/review_queue_3layer.py`：审核候选并晋升 learned
- `08_taxonomy_memory/processing/build_tag_report.py`：构建分层标签报告
- `08_taxonomy_memory/processing/build_mesh_lexicon.py`：构建本地 MeSH 词典（可选）

- `shared/config/domain_taxonomy.yaml`：基础固定类目（人工维护，版本化）
- `08_taxonomy_memory/step_results/domain_taxonomy_learning_queue.jsonl`：自动发现待审核候选
- `08_taxonomy_memory/step_results/domain_taxonomy_learned.jsonl`：审核通过后的增量类目
- `08_taxonomy_memory/step_results/domain_taxonomy_report.json`：统计报告

## 执行流程（推荐）

1. 运行 Step04 后，抽取候选标签：

```powershell
.\.venv\Scripts\python.exe "08_taxonomy_memory/processing/extract_tag_candidates.py" `
  --input-jsonl "05_keyword_entity/step_results/<prefix>_step04_keyword_entity.jsonl"
```

2. 审核并晋升到 learned：

```powershell
.\.venv\Scripts\python.exe "08_taxonomy_memory/processing/review_queue_3layer.py"
```

3. 生成标签报告：

```powershell
.\.venv\Scripts\python.exe "08_taxonomy_memory/processing/build_tag_report.py"
```

4. 下次 Step05 会自动读取 learned 与 MeSH 映射并优先命中。

## A 路线（MeSH）可选初始化

```powershell
.\.venv\Scripts\python.exe "08_taxonomy_memory/processing/build_mesh_lexicon.py" `
  --mesh-terms "08_taxonomy_memory/resources/mesh/mesh_terms.txt" `
  --output-jsonl "08_taxonomy_memory/resources/mesh/mesh_terms.jsonl"
```

## 中长期增强（本地版）

### 中期：SetFit 固定类目分类器（本地训练）

```powershell
.\.venv\Scripts\python.exe "08_taxonomy_memory/processing/train_setfit_local.py" `
  --train-jsonl "08_taxonomy_memory/step_results/domain_taxonomy_learned.jsonl" `
  --output-dir "08_taxonomy_memory/models/setfit_local" `
  --local-files-only
```

### 长期：BERTopic 新主题发现（本地）

```powershell
.\.venv\Scripts\python.exe "08_taxonomy_memory/processing/discover_bertopic_local.py" `
  --input-jsonl "05_keyword_entity/step_results/<prefix>_step04_keyword_entity.jsonl" `
  --output-json "08_taxonomy_memory/step_results/bertopic_candidates.json" `
  --local-files-only
```

### 长期：Snorkel 风格弱监督规则（本地）

```powershell
.\.venv\Scripts\python.exe "08_taxonomy_memory/processing/snorkel_labeling_local.py" `
  --input-jsonl "05_keyword_entity/step_results/<prefix>_step04_keyword_entity.jsonl" `
  --output-jsonl "08_taxonomy_memory/step_results/snorkel_weak_labels.jsonl"
```

### 弱监督闭环：弱标签自动入队 + 报告

```powershell
.\.venv\Scripts\python.exe "08_taxonomy_memory/processing/merge_weak_labels_to_queue.py" `
  --weak-labels-jsonl "08_taxonomy_memory/step_results/snorkel_weak_labels.jsonl" `
  --step04-jsonl "05_keyword_entity/step_results/<prefix>_step04_keyword_entity.jsonl" `
  --queue-jsonl "08_taxonomy_memory/step_results/domain_taxonomy_learning_queue.jsonl"

.\.venv\Scripts\python.exe "08_taxonomy_memory/processing/build_taxonomy_report.py"
```

## 纯本地说明

- 默认不调用任何付费 API/token。
- SetFit/BERTopic 只建议后续在本地模型缓存完备后启用（可选增强层）。

