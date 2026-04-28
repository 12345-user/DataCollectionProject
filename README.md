# 教授研究投入分析流水线（本地 + 开源）

## 1) 项目简介

本项目用于输入教授信息后，自动完成：
- 论文与实验室信息采集
- 扩展候选论文集
- 同名作者消歧
- 关键词与实体抽取
- 领域聚类
- 时间趋势与投入预测
- 可视化展示（DuckDB + Streamlit + Plotly）

目标产出：教授在各研究方向上的当前投入与未来 4 个季度趋势预测。

---

## 2) 开源依赖与远程来源（优先 clone / 官方包）

### Step01-03 依赖（补齐）

- **Step01 数据采集**
  - `NCBI E-utilities (PubMed)`：<https://www.ncbi.nlm.nih.gov/books/NBK25501/>
  - Python 标准库：`urllib`、`xml.etree.ElementTree`（本地脚本使用）
- **Step02 扩展论文列表**
  - `paperscraper`：<https://github.com/blackadad/paper-scraper>
  - 预印本 dump/索引来源：`arXiv / bioRxiv / medRxiv / chemRxiv`
- **Step03 同名作者消歧**
  - `WhoIsWho`：<https://github.com/THUDM/WhoIsWho>

- `WhoIsWho`：`https://github.com/THUDM/WhoIsWho`
- `KeyBERT`：`https://github.com/MaartenGr/KeyBERT`
- `sentence-transformers`：`https://github.com/UKPLab/sentence-transformers`
- 预测模型库 `statsmodels`（ETS / ARIMA）：`https://github.com/statsmodels/statsmodels`

示例（如本地缺失时）：

```powershell
git clone https://github.com/THUDM/WhoIsWho "03_author_disambiguation/processing/WhoIsWho"
git clone https://github.com/MaartenGr/KeyBERT "04_keyword_entity/processing/KeyBERT"
git clone https://github.com/UKPLab/sentence-transformers "05_domain_analysis/processing/sentence-transformers"
.\.venv\Scripts\python.exe -m pip install statsmodels
```

---

## 2.1) 一键简化命令（推荐）

只输入教授名和种子论文名即可跑完整 01->08（可选追加来源网站）：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/run_full_pipeline_oneclick.ps1" `
  -ProfessorName "【教授姓名】" `
  -SeedPaperTitle "【种子论文名称】" `
  -SeedPMID "【可选PMID】" `
  -ExtraSourceUrls "【可选来源URL1】" "【可选来源URL2】" `
  -EnableSnorkel `
  -EnableSetFit `
  -EnableBERTopic `
  -LocalFilesOnly
```

说明：
- 该命令会自动运行 Step01 到 Step08，其中 Step05 同步生成标签分级与词云，并更新 `pipeline.duckdb`。
- 默认额外运行 Step08 质量守卫（完整性与脏数据检查）。
- 中长期增强按开关启用（均为本地执行）：`-EnableSetFit` / `-EnableBERTopic` / `-EnableSnorkel`。
- `-LocalFilesOnly` 用于 SetFit/BERTopic 强制仅使用本地缓存模型（离线优先）。
- 若参数 `-StartWeb` 默认开启，会尝试启动网页（默认端口 8502）。
- 网页内也提供了同等的一键执行入口（输入作者名、种子论文、来源 URL）。

### Ubuntu 22.04（linux 分支推荐）

本项目已在 `scripts/linux` 提供 Linux 原生脚本，避免 `powershell` 和 `.venv\Scripts\*.exe` 依赖：

```bash
bash scripts/linux/setup_ubuntu22.sh

bash scripts/linux/run_full_pipeline_oneclick.sh \
  --professor-name "教授姓名" \
  --seed-paper-title "种子论文名称" \
  --seed-pmid "可选PMID" \
  --no-start-web
```

关键 Linux 脚本：
- `scripts/linux/setup_ubuntu22.sh`：安装 Ubuntu 22.04 依赖并初始化 venv
- `scripts/linux/run_professor_collection_simple.sh`：Step01 + bridge（Linux）
- `scripts/linux/run_steps04_05_06_cloud_glue.sh`：Step03-05（Linux）
- `scripts/linux/run_full_pipeline_oneclick.sh`：Step01-08 一键（Linux）

---

## 3) 全流程逻辑图（01 -> 08）

```text
Step01 数据采集
  ---> Step02 扩展论文列表
  ---> Step03 同名作者消歧（目录：03_author_disambiguation）
  ---> Step04 关键词/实体抽取（目录：04_keyword_entity）
  ---> Step05 领域分析 + 标签分级 + 词云（目录：05_domain_analysis）
  ---> Step06 时间分析与投入推断（目录：06_temporal_analysis/processing）
  ---> Step07 可视化网站（目录：07_visualization/app）
  ---> Step08 质量守卫（目录：08_quality_guard）
```

---

## 4) 分步骤说明（作用 + 用法 + 指令 + 输入输出示例）

### Step01 数据采集（`01_data_collection`）

- **步骤作用**：采集教授论文基础元数据与实验室信息，生成后续步骤的基础输入。
- **使用方法简介**：输入教授姓名和种子论文，得到 `title/abstract/pub_date/doi/journal/authors`。
- **步骤指令（待填入用中文）**：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts\bootstrap\run_professor_collection_simple.ps1" `
  -ProfessorName "【教授姓名】" `
  -SeedPaperTitle "【种子论文标题】" `
  -SeedPMID "【可选PMID】"
```

- **输入示例**：教授姓名 + 种子论文标题  
- **输出示例**：
  - `01_data_collection/step_results/professor_paper_abstracts/pubmed_xxx_abstracts.jsonl`
  - `01_data_collection/step_results/professor_lab_info/pubmed_xxx_lab_info.json`

---

### Step02 扩展论文列表（`02_paper_list_extend`）

- **步骤作用**：从 Step01 基础论文集合扩展为更完整候选池，并统一 schema。
- **使用方法简介**：读取 Step01 输出，补充预印本来源，合并去重后输出标准 JSONL。
- **步骤指令（待填入用中文）**：

```powershell
.\.venv\Scripts\python.exe "02_paper_list_extend\processing\run_step02_paper_list_extend_paperscraper.py" `
  --professor-name "【教授姓名】" `
  --step01-output-prefix "【Step01输出前缀】" `
  --output-prefix "【Step02输出前缀】" `
  --server-dump-dir "02_paper_list_extend/data_sources/paperscraper_server_dumps/server_dumps"
```

- **输入示例**：Step01 的 `abstracts.json/jsonl`  
- **输出示例**：
  - `02_paper_list_extend/step_results/pubmed_xxx_expanded_papers.jsonl`
  - 关键字段：`title,abstract,pub_date,venue,doi,citation_count,source`

---

### Step03 同名作者消歧（`03_author_disambiguation`）

- **步骤作用**：识别并过滤同名不同人，给出 `identity_score`。
- **使用方法简介**：结合 Step02 论文与 Step01 实验室信息进行身份判别。
- **步骤指令（待填入用中文）**：由胶水脚本统一执行（见 Step03-05 一键脚本）。
- **输入示例**：`expanded_papers.jsonl` + `lab_info.json`  
- **输出示例**：`03_author_disambiguation/step_results/xxx_step03_disambiguated_papers.jsonl`

---

### Step04 关键词与实体抽取（`04_keyword_entity`）

- **步骤作用**：抽取关键词、实体、项目候选，并计算 `quality_score`。
- **使用方法简介**：对消歧后的论文文本执行 KeyBERT/实体抽取，输出结构化特征。
- **步骤指令（待填入用中文）**：由胶水脚本统一执行（见 Step03-05 一键脚本）。
- **输入示例**：Step03 输出 JSONL  
- **输出示例**：`04_keyword_entity/step_results/xxx_step04_keyword_entity.jsonl`

---

### Step05 领域分析（`05_domain_analysis`）

- **步骤作用**：将论文映射到研究领域，并并列生成标签分级与词云结果。
- **使用方法简介**：对摘要向量化后聚类，生成每篇论文领域标签、L1/L2/L3 标签和词云权重结果。
- **步骤指令（待填入用中文）**：由胶水脚本统一执行（见 Step03-05 一键脚本）。
- **输入示例**：Step04 输出 JSONL  
- **输出示例**：
  - `05_domain_analysis/step_results/xxx_step05_paper_domains.jsonl`
  - `05_domain_analysis/step_results/xxx_step05_domains.json`
  - `05_domain_analysis/step_results/xxx_step05_wordcloud_terms.json`
  - `05_domain_analysis/step_results/xxx_step05_wordcloud.png`

---

### Step03-05 一键运行（推荐）

- **步骤作用**：串联执行消歧、特征抽取、领域聚类。
- **步骤指令（待填入用中文）**：

```powershell
.\scripts\run_steps04_05_06_cloud_glue.ps1 `
  -ExpandedPapers "02_paper_list_extend/step_results/【Step02输出文件】.jsonl" `
  -LabInfo "01_data_collection/step_results/professor_lab_info/【Step01实验室文件】.json" `
  -TargetName "【目标教授标准名】" `
  -Prefix "【统一输出前缀】"
```

Linux:

```bash
bash scripts/linux/run_steps04_05_06_cloud_glue.sh \
  --expanded-papers "02_paper_list_extend/step_results/前缀_expanded_papers.jsonl" \
  --lab-info "01_data_collection/step_results/professor_lab_info/前缀_lab_info.json" \
  --target-name "目标教授标准名" \
  --prefix "统一输出前缀"
```

---

### Step06 时间分析与投入推断（`06_temporal_analysis/processing`）

- **步骤作用**：计算领域投入比例、时间趋势、质量变化。
- **使用方法简介**：基于 `pub_date + identity_score + quality_score` 聚合并生成报告。
- **步骤指令（待填入用中文）**：

```powershell
.\.venv\Scripts\python.exe "06_temporal_analysis/processing/run_step06_temporal_analysis.py" `
  --input "05_domain_analysis/step_results/【前缀】_step05_paper_domains.jsonl" `
  --timeline-output "06_temporal_analysis/step_results/【前缀】_step06_project_timeline.json" `
  --allocation-output "06_temporal_analysis/step_results/【前缀】_step06_effort_allocation.json" `
  --report-output "06_temporal_analysis/step_results/【前缀】_step06_trend_report.md"
```

Linux:

```bash
.venv/bin/python "06_temporal_analysis/processing/run_step06_temporal_analysis.py" \
  --input "05_domain_analysis/step_results/前缀_step05_paper_domains.jsonl" \
  --timeline-output "06_temporal_analysis/step_results/前缀_step06_project_timeline.json" \
  --allocation-output "06_temporal_analysis/step_results/前缀_step06_effort_allocation.json" \
  --report-output "06_temporal_analysis/step_results/前缀_step06_trend_report.md"
```

- **输入示例**：Step05 的 `paper_domains.jsonl`  
- **输出示例**：timeline/allocation/trend_report 三类文件

---

### Step07 可视化网站（`07_visualization/app`）

- **步骤作用**：把全流程结果展示为饼图、两条季度折线、自动总结、公式公示。
- **使用方法简介**：先写入 DuckDB，再启动 Streamlit（可选 FastAPI）。
- **步骤指令（待填入用中文）**：

```powershell
.\\.venv\\Scripts\\python.exe "06_temporal_analysis/processing/build_step06_duckdb.py" `
  --professor "【教授标识】" `
  --paper-domains "05_domain_analysis/step_results/【前缀】_step05_paper_domains.jsonl" `
  --duckdb-path "07_visualization/step_results/pipeline.duckdb"

.\.venv\Scripts\streamlit.exe run "07_visualization/app/streamlit_app.py"
```

Linux:

```bash
.venv/bin/python "06_temporal_analysis/processing/build_step06_duckdb.py" \
  --professor "教授标识" \
  --paper-domains "05_domain_analysis/step_results/前缀_step05_paper_domains.jsonl" \
  --duckdb-path "07_visualization/step_results/pipeline.duckdb"

.venv/bin/python -m streamlit run "07_visualization/app/streamlit_app.py"
```

- **输入示例**：Step05/Step06 结果文件  
- **输出示例**：
  - DuckDB：`07_visualization/step_results/pipeline.duckdb`
  - 网页：`http://localhost:8501`

---

## 5) 预测与加权口径（网页已同步展示）

- **权重公式**：`w_paper = identity_score × quality_score`
- **季度聚合**：`W_(domain,quarter) = Σ w_paper`
- **预测目标**：`paper_count` 与 `weight`
- **预测方法**：
  - `Linear`：线性外推
  - `ETS`：指数平滑（`statsmodels`）
  - `ARIMA(1,1,1)`（`statsmodels`）
  - `Auto`：按每个领域回测误差（MAE/MAPE）自动选模
- **预测起点**：从当前半年节点开始，向后 2 个半年节点。
