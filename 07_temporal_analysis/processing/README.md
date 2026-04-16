# 07_temporal_analysis / processing

投入推断（建议轻量实现，避免过度复杂）：

1. 时间加权频率
   - 对每个 domain/project 计算时间序列 `count(t)`
   - 用指数衰减：`w(t)=exp(-(T-now)/tau)` 得到当前 share_current
2. 未来趋势
   - 最近窗口内的 `count(t)` 做趋势拟合/平滑
   - 或用“最近 N 篇出现频率上升”作为简单上升指标
3. 同名混入抑制
   - 引入身份一致性 `identity_score`（Step 04 得到）
   - 将权重乘到时间序列上：`effective_count = identity_score * count`
4. 可解释 baseline 模型（可选）
   - 用 `sklearn` 训练一个 baseline：预测下一时间窗是否继续出现于同一 project/domain

