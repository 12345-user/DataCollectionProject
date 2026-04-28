# 06_temporal_analysis（时间分析与投入精力推断）

目标：基于“论文发表时间 + domain_label + project 候选 + 身份一致性权重”，推断教授：
- 当前主要投入的项目/领域
- 未来可能加大投入的方向（趋势预测）
- 以及同名教授混入风险（一致性报告）

输入（建议字段）：
- `paper_date`
- `domain_label`
- `project`（由 Step 05 推断/归一化得到）
- `identity_score`（来自新 Step 03，如果有；没有就默认 1）

输出（写入 step_results）：
- `*_project_timeline.json`：按时间分桶的领域时间线
- `*_effort_allocation.json`：当前投入比例（share_current）+ 趋势（trend_future）
- `*_trend_report.md`：可读报告（摘要）

可视化扩展（推荐）：
- `pipeline.duckdb`：单文件 DuckDB（用于网站/SQL 查询）
- Streamlit 可视化网站：
  - 领域比例饼图（share / weight）
  - 领域发布频率折线图（paper_count）
  - 领域“精力/质量”折线图（weight=identity_score*quality_score）

## 投入比例与时间趋势的“可解释”计算（建议实现优先级）

### 1）项目时间序列与加权当前投入 share_current

对每个 `project_id`（canonical project）建立时间序列 `count(project_id, t)`（例如按月/季度/年分桶）。

当前投入权重可用指数衰减：

- `w(t)=exp(-(T-now)/tau)`
- `score_current(project_id)=sum_t w(t) * count(project_id,t) * identity_score`
- `share_current = score_current / sum(score_current over all projects)`

identity_score 来自新 Step 03（没有就默认 1）。

### 4）可视化网站（DuckDB + FastAPI + Streamlit + Plotly）

为了让结果“可交互、可筛选、可对比多个教授”，推荐把 Step05/06/07 的关键字段写入 DuckDB：

- DuckDB：单文件、免配置、SQL 查询
- FastAPI：提供教授列表、时间范围、领域份额、领域时间序列等 API
- Streamlit+Plotly：快速构建可视化网站（饼图 + 折线图），支持选择教授与时间范围

质量（paper quality）字段目前在上游数据里缺失，建议：
- 先以 `quality_score=1.0` 占位（不影响结构）
- 后续再接入引用数/期刊信息/模型评分（可选，可能用到 `scikit-learn`）

### 2）未来趋势 trend_future（项目频率 + 时间前后）

对每个 project 的最近窗口与更早窗口做“增长率”：

- `recent = sum count(project_id, t) for t in [now-k, now]`
- `past   = sum count(project_id, t) for t in [now-m-k, now-k]`
- `trend = (recent+eps)/(past+eps)`（比值型）或对最近窗口做线性回归得到斜率

最终输出时同时给出证据论文数量与时间范围，保证可解释。

### 3）同名混入一致性 consistency_report

当同名混入发生时，通常会出现：

- 身份一致性分数（Step 04）明显下降
- domain_label 分布出现不连续跳变
- project_mentions 的别名/主题突变

建议报告中包含：
- identity_score 的分布与分位数
- 近期 domain_label 与过去 domain_label 的距离/占比变化
- 若检测到突变，输出“可能混入的时间段/论文列表（PMID 列表）”

