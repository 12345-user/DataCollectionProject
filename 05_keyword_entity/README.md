# 05_keyword_entity（关键词与实体抽取）

目标：对“目标教授论文集合”做关键词/实体抽取，构建可用于后续“项目名统计与时间投入推断”的特征。

输入：
- Step 04 的消歧后论文列表（title + abstract + authors/affiliations 可选）

工具（建议）：
- `KeyBERT`：语义关键词提取（零训练）
- `GLiNER`：零样本方法/技术实体抽取

输出（写入 step_results）：
- `*_paper_features.jsonl`：
  - `keywords[]`：关键词/技术方向（候选 project 概念）
  - `entities[]`：方法/模型/技术术语
  - `project_candidates[]`：由 keywords+entities 归一化后的项目名候选

