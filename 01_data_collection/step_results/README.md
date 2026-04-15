# Step Results 分类与执行摘要

`01_data_collection/step_results` 按教授采集场景拆分为三类：

- `professor_paper_titles`：教授论文标题与 PMID
- `professor_lab_info`：从论文作者单位抽取的实验室/机构线索
- `professor_paper_abstracts`：教授论文摘要

## 一、配置模板位置

- 论文标题模板：`01_data_collection/data_sources/request_profiles/professor_paper_titles.request.template.yaml`
- 实验室信息模板：`01_data_collection/data_sources/request_profiles/professor_lab_info.request.template.yaml`
- 论文摘要模板：`01_data_collection/data_sources/request_profiles/professor_paper_abstracts.request.template.yaml`

## 二、执行命令（完整版）

### 1) 采集论文标题

```powershell
python "01_data_collection/processing/lab_paper_tools/fetch_pubmed_titles.py" --query "Yong-Fei Wang[au]" --output-prefix "pubmed_yong_fei_wang"
```

### 2) 采集论文摘要（依赖上一步 titles.json）

```powershell
python "01_data_collection/processing/lab_paper_tools/fetch_pubmed_abstracts.py" --titles-json "01_data_collection/step_results/professor_paper_titles/pubmed_yong_fei_wang_titles.json" --output-prefix "pubmed_yong_fei_wang"
```

### 3) 提取实验室信息（依赖 titles.json）

```powershell
python "01_data_collection/processing/lab_paper_tools/extract_lab_info_from_pubmed.py" --titles-json "01_data_collection/step_results/professor_paper_titles/pubmed_yong_fei_wang_titles.json" --output-prefix "pubmed_yong_fei_wang"
```

## 三、执行命令（简化版）

在项目根目录执行：

```powershell
$P="pubmed_yong_fei_wang"; $Q="Yong-Fei Wang[au]"
python "01_data_collection/processing/lab_paper_tools/fetch_pubmed_titles.py" --query $Q --output-prefix $P
python "01_data_collection/processing/lab_paper_tools/fetch_pubmed_abstracts.py" --titles-json "01_data_collection/step_results/professor_paper_titles/$P`_titles.json" --output-prefix $P
python "01_data_collection/processing/lab_paper_tools/extract_lab_info_from_pubmed.py" --titles-json "01_data_collection/step_results/professor_paper_titles/$P`_titles.json" --output-prefix $P
```

## 四、一键执行（最简）

脚本位置：

- `scripts/bootstrap/run_professor_collection.ps1`

执行命令：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/bootstrap/run_professor_collection.ps1" -ProfessorQuery "Yong-Fei Wang[au]" -OutputPrefix "pubmed_yong_fei_wang"
```
