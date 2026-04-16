# 07_temporal_analysis（时间分析与投入精力推断）

目标：基于“论文发表时间 + domain_label + project 候选 + 身份一致性权重”，推断教授：
- 当前主要投入的项目/领域
- 未来可能加大投入的方向（趋势预测）
- 以及同名教授混入风险（一致性报告）

输入（建议字段）：
- `paper_date`
- `domain_label`
- `project`（由 Step 05 推断/归一化得到）
- `identity_score`（来自 Step 04，如果有；没有就默认 1）

输出（写入 step_results）：
- `*_share_current.json`：当前投入比例（按项目/领域分布）
- `*_trend_future.json`：未来趋势（哪些项目/领域更可能增长）
- `*_consistency_report.md/json`：一致性与混入风险提示

