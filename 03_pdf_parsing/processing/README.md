# 03_pdf_parsing / processing

目标：把 `02_paper_list_extend` 的扩展论文元数据，进一步转成适合 Step 04 消歧的结构化全文记录。

## 已搭好的环境/配置

1. Python 运行时统一使用项目根 `.venv`
2. `scipdf-parser` 已安装，可用于字段整理
3. `docker-compose.grobid.yml` 已放在当前目录
4. `.env.example` 已给出稳定输入输出路径模板

## 推荐执行顺序

1. 确保已完成 Step 02，得到：
   - `02_paper_list_extend/step_results/<前缀>_expanded_papers.jsonl`
2. 启动 GROBID（当前机器若未安装 Docker，则先安装 Docker Desktop）
3. 再接入你的 `run_step03_pdf_parsing.py`

## 启动命令

```powershell
docker compose -f 03_pdf_parsing/processing/docker-compose.grobid.yml up -d
```

检查服务：

```powershell
Invoke-WebRequest http://localhost:8070/api/isalive
```

## 稳定输入输出

输入：
- `02_paper_list_extend/step_results/<前缀>_expanded_papers.jsonl`

输出建议：
- `03_pdf_parsing/step_results/<前缀>_parsed_papers.jsonl`

输出字段至少保留：
- `paper_id`
- `source`
- `title`
- `abstract`
- `pub_date`
- `authors`
- `sections`
- `affiliations`
- `references`

字段契约已同步到：
- `shared/config/professor_pipeline.io.contract.yaml`

