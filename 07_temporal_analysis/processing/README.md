# 07_temporal_analysis / processing

目标：根据论文时间分布、项目候选频率和新 Step 03 的身份一致性，推测教授当前与未来的研究投入方向。

## 当前环境

项目根 `.venv` 已安装：
- `pandas`
- `scikit-learn`

共享配置：
- `shared/config/professor_pipeline.env.example`

## 稳定输入输出

输入：
- `06_domain_clustering/step_results/<前缀>_paper_domains.jsonl`

输出：
- `07_temporal_analysis/step_results/<前缀>_project_timeline.json`
- `07_temporal_analysis/step_results/<前缀>_effort_allocation.json`
- `07_temporal_analysis/step_results/<前缀>_trend_report.md`

关键输出字段：
- `project_or_domain`
- `share_current`
- `trend_future`
- `evidence`

## 推荐命令形式

```powershell
.\.venv\Scripts\python.exe 07_temporal_analysis/processing/run_step07_temporal_analysis.py `
  --input 06_domain_clustering/step_results/示例教授_paper_domains.jsonl `
  --timeline-output 07_temporal_analysis/step_results/示例教授_project_timeline.json `
  --allocation-output 07_temporal_analysis/step_results/示例教授_effort_allocation.json `
  --report-output 07_temporal_analysis/step_results/示例教授_trend_report.md
```

## 建议方法

1. 用指数衰减频次估算 `share_current`
2. 用最近窗口与历史窗口对比估算 `trend_future`
3. 把 `identity_score` 乘进每条论文权重，降低同名误混风险

