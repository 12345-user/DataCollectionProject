# 教授项目投入精力推断（本地部署版）

## 一、项目目标

输入一位教授（姓名 + 种子论文信息），构建完整流程：
1. 采集论文与实验室信息
2. 扩展候选论文池
3. 同名作者消歧
4. 关键词与技术实体抽取
5. 领域聚类
6. 时间趋势与投入比例推断

最终给出“教授当前/未来更可能投入的研究方向”。

---

## 二、流程逻辑图（01 ---> 06）

```text
Step01 数据采集
  ---> Step02 扩展论文列表
  ---> Step03 同名作者消歧（目录名 04_author_disambiguation）
  ---> Step04 关键词/实体抽取（目录名 05_keyword_entity）
  ---> Step05 领域聚类（目录名 06_domain_clustering）
  ---> Step06 时间分析与投入推断（目录名 07_temporal_analysis）
```

---

## 三、每一步详细说明（Input / Output / 作用）

### Step01：数据采集（`01_data_collection`）
- **Input**
  - 教授姓名
  - 种子论文标题（可带 PMID）
  - 可选补充 URL
- **Output**
  - `01_data_collection/step_results/professor_paper_abstracts/<前缀>_abstracts.jsonl`
  - `01_data_collection/step_results/professor_paper_abstracts/<前缀>_abstracts.md`
  - `01_data_collection/step_results/professor_lab_info/<前缀>_lab_info.json`
- **作用**
  - 产出后续流程的基础论文元数据和实验室线索
  - 为同名消歧提供身份证据

### Step02：扩展论文列表（`02_paper_list_extend`）
- **Input**
  - Step01 的论文集合（标题/摘要/作者/时间）
  - 教授姓名
- **Output**
  - `02_paper_list_extend/step_results/<前缀>_expanded_papers.jsonl`
  - 典型字段：`paper_id,title,abstract,pub_date,authors,doi,source,url,venue,citation_count`
- **作用**
  - 从初始论文扩展到更完整候选池
  - 统一格式，为消歧与特征抽取提供稳定输入

### Step03：同名作者消歧（`04_author_disambiguation`）
- **Input**
  - Step02 扩展论文：`*_expanded_papers.jsonl`
  - Step01 实验室信息：`*_lab_info.json`
  - WhoIsWho 本地仓库（已放置）：`04_author_disambiguation/processing/WhoIsWho`
- **Output**
  - `04_author_disambiguation/step_results/<前缀>_step03_disambiguated_papers.jsonl`
  - 关键字段：`identity_score,identity_decision,identity_evidence`
- **作用**
  - 降低同名不同人混入风险
  - 给每篇论文增加“身份可信度”权重

### Step04：关键词与实体抽取（`05_keyword_entity`）
- **Input**
  - Step03 消歧输出（标题 + 摘要 + identity_score）
  - KeyBERT 本地仓库（已放置）：`05_keyword_entity/processing/KeyBERT`
- **Output**
  - `05_keyword_entity/step_results/<前缀>_step04_keyword_entity.jsonl`
  - 关键字段：`keywords,entities,project_candidates,quality_score,quality_evidence`
- **作用**
  - 从论文文本提炼可解释特征
  - 将“文本信息”转为“项目/技术候选集合”
  - 产出质量评分字段，供 Step05/Step06 直接使用

### Step05：领域聚类（`06_domain_clustering`）
- **Input**
  - Step04 特征输出（标题/摘要/关键词/项目候选）
  - sentence-transformers 本地仓库（已放置）：`06_domain_clustering/processing/sentence-transformers`
  - 模型：`all-MiniLM-L6-v2`
- **Output**
  - `06_domain_clustering/step_results/<前缀>_step05_paper_domains.jsonl`
  - `06_domain_clustering/step_results/<前缀>_step05_domains.json`
  - 关键字段：`domain_label,domain_confidence,domain_keywords,quality_score,avg_quality_score`
- **作用**
  - 将论文映射到“研究领域域标签”
  - 形成领域清单与代表关键词

### Step06：时间分析与投入推断（`07_temporal_analysis`）
- **Input**
  - Step05 的 `paper_domains.jsonl`
  - 论文时间字段 `pub_date`
  - Step03 的 `identity_score`（用于加权）
  - Step04/05 的 `quality_score`（用于质量加权）
- **Output**
  - `07_temporal_analysis/step_results/<前缀>_project_timeline.json`
  - `07_temporal_analysis/step_results/<前缀>_effort_allocation.json`
  - `07_temporal_analysis/step_results/<前缀>_trend_report.md`
- **作用**
  - 估计当前研究投入比例（`share_current`）
  - 估计未来趋势（`trend_future`）
  - 同时输出按年份的 `year_avg_quality` 与趋势质量对比（`recent_avg_quality/past_avg_quality`）
  - 输出可读报告供决策参考

---

## 四、第六步做完后的成果是什么

Step06 完成后，你会得到三类核心成果：
- **时间线成果**：每个领域/项目在时间上的活跃变化（timeline）
- **投入成果**：当前投入比例分布（allocation，`share_current` 总和应接近 1）
- **趋势成果**：未来增减趋势提示（trend + markdown 报告）

这代表流程从“原始论文文本”走到了“可解释的教授研究投入画像”。

并且（已扩展 Step07）：你可以进一步把结果写入 **DuckDB 单文件数据库**，用 **Streamlit+Plotly** 生成本地可视化网站（可选择教授与时间范围），并可选启用 **FastAPI** 提供查询 API。

### `quality_score v1`（已接入主流程）

- **接入位置**
  - 原始质量信号：Step02（`venue,citation_count`）
  - 质量评分计算：Step04（输出 `quality_score,quality_evidence`）
  - 聚类与时间分析消费：Step05/Step06
- **评分范围**
  - `quality_score ∈ [0,1]`，纯本地可复现，不依赖付费 API
- **v1 评分组成（加权）**
  - `citation_score`（log 归一化）
  - `doi_score`（是否有 DOI）
  - `source_weight`（PubMed/arXiv/xRxiv 来源权重）
  - `recency_score`（按发布时间衰减）
  - `abstract_score`（摘要完整度）
  - `venue_bonus`（是否有 venue）
  - `title_score`（标题完整度）
- **Step06 实际使用方式**
  - `effort_weight = decay * identity_score * (0.6 + 0.4 * quality_score)`
  - 不再使用默认 `quality_score=1.0` 占位逻辑

---

## 五、执行命令（含 04-06 云仓库胶水层）

### 1）Step01 采集
```powershell
powershell -ExecutionPolicy Bypass -File "scripts\bootstrap\run_professor_collection_simple.ps1" `
  -ProfessorName "教授名" `
  -SeedPaperTitle "种子论文标题" `
  -SeedPMID "种子 PMID"
```

### 2）Step02 扩展
```powershell
.\.venv\Scripts\python.exe "02_paper_list_extend\processing\run_step02_paper_list_extend_paperscraper.py" `
  --professor-name "教授姓名" `
  --step01-output-prefix "Step01OutputPrefix" `
  --output-prefix "Step02OutputPrefix" `
  --server-dump-dir "02_paper_list_extend/data_sources/paperscraper_server_dumps/server_dumps" `
  --skip-arxiv
```

### 3）Step03-05 一键（云仓库胶水层）
```powershell
.\scripts\run_steps04_05_06_cloud_glue.ps1 `
  -ExpandedPapers "02_paper_list_extend/step_results/pubmed_wanling_yang_expanded_papers.jsonl" `
  -LabInfo "01_data_collection/step_results/professor_lab_info/pubmed_wanling_yang_lab_info.json" `
  -TargetName "Wanling Yang" `
  -Prefix "pubmed_wanling_yang"
```

### 4）Step06 时间分析（单独执行）
```powershell
.\.venv\Scripts\python.exe "07_temporal_analysis/processing/run_step07_temporal_analysis.py" `
  --input "06_domain_clustering/step_results/pubmed_wanling_yang_step05_paper_domains.jsonl" `
  --timeline-output "07_temporal_analysis/step_results/pubmed_wanling_yang_step06_project_timeline.json" `
  --allocation-output "07_temporal_analysis/step_results/pubmed_wanling_yang_step06_effort_allocation.json" `
  --report-output "07_temporal_analysis/step_results/pubmed_wanling_yang_step06_trend_report.md"
```

### 5）Step07 可视化网站（DuckDB + FastAPI + Streamlit + Plotly）

1）把 Step05 的 per-paper 领域结果写入 DuckDB（单文件数据库）：

```powershell
.\.venv\Scripts\python.exe "07_temporal_analysis/processing/build_step07_duckdb.py" `
  --professor "pubmed_wanling_yang" `
  --paper-domains "06_domain_clustering/step_results/pubmed_wanling_yang_step05_paper_domains.jsonl" `
  --duckdb-path "07_temporal_analysis/step_results/pipeline.duckdb"
```

2）启动 Streamlit 可视化网站（饼图 + 两个折线图；可选教授与时间范围）：

```powershell
.\.venv\Scripts\streamlit.exe run "07_temporal_analysis/app/streamlit_app.py"
```

3）（可选）启动 FastAPI（提供 /professors、/domain_share、/domain_time 等接口）：

```powershell
.\.venv\Scripts\uvicorn.exe 07_temporal_analysis.api.main:app --reload --port 8000
```

---

## 六、当前本地核心仓库映射（云端来源）

- `04_author_disambiguation/processing/WhoIsWho` <--- `https://github.com/THUDM/WhoIsWho`
- `05_keyword_entity/processing/KeyBERT` <--- `https://github.com/MaartenGr/KeyBERT`
- `06_domain_clustering/processing/sentence-transformers` <--- `https://github.com/UKPLab/sentence-transformers`

说明：项目只在本仓库新增胶水层脚本，未改动上述云仓库核心实现。

---

## 七、实现建议（满足你提出的“高级好用模板”）

- **数据库（DuckDB）**：适合本项目的“单文件、零配置、SQL 直接分析”，还能直接给 Streamlit/FastAPI 提供查询层。
- **API（FastAPI）**：当你未来要接入前端框架（React/Vue）或多人共享时，FastAPI 比直接在 Streamlit 里写 SQL 更规范。
- **前端（Streamlit + Plotly）**：最省成本的开源模板，纯 Python，交互能力（筛选/缩放/悬停）足够强。
- **质量权重（paper quality）**：
  - 已接入 `quality_score v1`（本地可复现）到 Step04/05/06 全链路，07 可视化可直接使用。
  - 可继续升级到 `quality_score v2`：接入 OpenAlex/SemanticScholar 引用与期刊等级，再复标定权重。
