# 05_keyword_entity（关键词与实体抽取）

目标：对“目标教授论文集合”做关键词/实体抽取，构建可用于后续“项目名统计与时间投入推断”的特征。

输入：
- 新 Step 03（原 Step 04）的消歧后论文列表（title + abstract + authors/affiliations 可选）

工具（建议）：
- `KeyBERT`：语义关键词提取（零训练）
- `GLiNER`：零样本方法/技术实体抽取

输出（写入 step_results）：
- `*_paper_features.jsonl`：
  - `pmid`：论文唯一标识（若有）
  - `pub_date`：发表日期（来自 Step 01/02）
  - `keywords[]`：语义关键词（KeyBERT）
  - `entities[]`：技术/方法实体（GLiNER）
  - `project_candidates[]`：项目名候选（由 `keywords + entities` 组合 + 归一化同义合并）
  - `project_mentions[]`：每个候选项目在该论文中的“出现证据”（短语片段/计数），用于后续频率统计与可解释性

归一化与项目名构造（建议规则，便于后续“项目频率 + 时间前后”建模）：

- 候选 project 概念优先选择：
  - 高频 n-gram（3-6 gram）且包含技术实体类型（来自 `entities`）
  - 关键词中与研究方向一致的“项目型短语”（例如方法体系/框架名/技术路线名）
- 同义合并：
  - 只保留一个 canonical project 名称（其余做 aliases）
  - 使用简单字符串规范化（空格/大小写/中英标点）+ 同义表（可从高频别名自动收敛）

