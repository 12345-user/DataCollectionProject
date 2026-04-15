# Step Results 分类与执行摘要

`01_data_collection/step_results` 按教授采集场景拆分为三类：

- `professor_paper_titles`：教授论文标题与 PMID
- `professor_lab_info`：从论文作者单位抽取的实验室/机构线索
- `professor_paper_abstracts`：教授论文摘要

## 结果含义说明（重点）

### 1) `professor_paper_titles`

- `*_titles.json`：结构化标题数据，主要字段：
  - `query`：本次 PubMed 检索词
  - `count`：命中论文数量
  - `titles[]`：每条论文的 `pmid` 与 `title`
- `*_titles_list.md`：按序号输出的可读清单，便于人工快速浏览

### 2) `professor_paper_abstracts`

- `*_abstracts.json`：结构化摘要数据，主要字段：
  - `count`：成功提取摘要的论文数
  - `records[]`：每条包含 `pmid`、`title`、`abstract`
- `*_abstracts_list.md`：可读版摘要清单，适合后续复制到分析报告

### 3) `professor_lab_info`

- `*_lab_info.json`：从 PubMed 的 `Affiliation` 字段聚合得到的机构线索：
  - `count_affiliations`：抽取到的单位记录总数
  - `unique_affiliations`：去重后的单位数量
  - `top_affiliations[]`：按出现频次排序的单位与计数
- `*_lab_info_list.md`：可读版单位排名

注意：`lab_info` 是“候选机构线索”，不是唯一实验室真值。同名作者场景下会混入不同机构，需要结合机构关键词进一步过滤。

## 一、配置模板位置

- 论文标题模板：`01_data_collection/data_sources/request_profiles/professor_paper_titles.request.template.yaml`
- 实验室信息模板：`01_data_collection/data_sources/request_profiles/professor_lab_info.request.template.yaml`
- 论文摘要模板：`01_data_collection/data_sources/request_profiles/professor_paper_abstracts.request.template.yaml`

建议填写顺序：

1. 先填 `professor_paper_titles.request.template.yaml`（作者检索词最关键）
2. 再填摘要与实验室模板中的 `titles_json` 输入路径
3. 统一使用同一个 `output_prefix`，便于追踪同一教授的全套结果

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

## 五、执行后核验（建议）

1. 检查标题数量是否合理：
   - `professor_paper_titles/*_titles.json` 的 `count`
2. 抽检摘要质量：
   - `professor_paper_abstracts/*_abstracts_list.md` 前 5 篇是否与教授方向一致
3. 抽检机构一致性：
   - `professor_lab_info/*_lab_info_list.md` 前 10 条是否集中在目标机构

## 六、同名作者去噪建议

如果结果混杂，可把 `ProfessorQuery` 从：

- `Yong-Fei Wang[au]`

收敛为：

- `Yong-Fei Wang[au] AND <机构名>[ad]`
- `Yong-Fei Wang[au] AND 2018:2026[pdat]`
- `Yong-Fei Wang[au] AND <研究关键词>`

示例：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/bootstrap/run_professor_collection.ps1" -ProfessorQuery "Yong-Fei Wang[au] AND Shanghai[ad] AND 2018:2026[pdat]" -OutputPrefix "pubmed_yong_fei_wang_shanghai"
```

## 七、常见问题

- 网络超时 / SSL 握手慢：重试即可，或缩小查询范围
- 结果数量异常少：先检查 `[au]` 拼写，必要时去掉连字符或加入姓名变体
- 机构过于分散：说明同名混入，优先加 `[ad]` 条件再执行
