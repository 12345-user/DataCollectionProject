# 04_author_disambiguation（同名教授消歧）

目标：在扩展论文集合里，剔除与目标教授同名但不同人的论文，形成“目标教授真实论文集合”。

输入：
- Step 03 的结构化 JSON（标题、摘要、作者列表、发表日期、机构等）
- 可选：Step 01 的 lab_info（用于强化身份一致性）

工具（建议）：
- `WhoIsWho`（OAG-BERT 方向的同名消歧）
- `GLiNER`：作者-机构-合著者关系抽取（零样本）

输出（写入 step_results）：
- `*_disambiguated_papers.json`：仅保留目标教授身份一致的论文集合
- `*_disambiguation_report.json`：可解释的消歧置信度/保留规则摘要

关键策略（简化实现顺序）：
1. affiliation/合著者关系构建身份打分
2. 低一致性样本剔除
3. 与领域聚类结果进行一致性检查（可选）

