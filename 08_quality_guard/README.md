# 08_quality_guard

Step08 对每次查询后的全链路结果做本地质量守卫检查（无付费 API/token）。

## 覆盖检查

- 数据完整性：关键文件是否存在、关键字段是否缺失
- 链接性：`step02 -> step03 -> step04 -> step05` 的 `paper_id` 贯通关系
- 脏数据：空标题、无效发布日期、结构异常
- 领域可读性：过滤表意不清主题命名
- 词云完整性：Step05 的词云 terms/json 与 png 是否生成
- 管道完整性：是否出现中间步骤空结果

## 本地依赖

- 必需：Python 标准库
- 可选增强：`pandera[pandas]`（Schema 校验增强）

```powershell
.\.venv\Scripts\python.exe -m pip install "pandera[pandas]"
```

## 执行

```powershell
.\.venv\Scripts\python.exe "08_quality_guard/processing/run_step08_quality_guard.py" `
  --prefix "pubmed_hsien_da_huang" `
  --output-json "08_quality_guard/step_results/pubmed_hsien_da_huang_step08_quality_report.json" `
  --output-md "08_quality_guard/step_results/pubmed_hsien_da_huang_step08_quality_report.md"
```

