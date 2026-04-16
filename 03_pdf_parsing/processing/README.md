# 03_pdf_parsing / processing

这里放 Step 03 的解析脚本与容器/运行封装。

建议做法：
1. 把 Step 02 的论文列表映射到 PDF 获取策略（下载/缓存/跳过）
2. 调用 `GROBID`（Docker）抽取结构化信息
3. 用 `scipdf_parser` 做统一字段整理
4. 写入 `step_results/*.json`（供 Step 04 消歧使用）

后续你可以接入 CLI，例如：
- `run_03_pdf_parsing.py --input <jsonl> --output-prefix <...>`

