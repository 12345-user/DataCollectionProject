param(
  [Parameter(Mandatory = $true)][string]$ExpandedPapers,
  [Parameter(Mandatory = $true)][string]$LabInfo,
  [Parameter(Mandatory = $true)][string]$TargetName,
  [string]$Prefix = "professor"
)

$ErrorActionPreference = "Stop"

$python = ".\.venv\Scripts\python.exe"

$step04Out = "04_author_disambiguation/step_results/${Prefix}_step03_disambiguated_papers.jsonl"
$step05Out = "05_keyword_entity/step_results/${Prefix}_step04_keyword_entity.jsonl"
$step06PaperOut = "06_domain_clustering/step_results/${Prefix}_step05_paper_domains.jsonl"
$step06DomainsOut = "06_domain_clustering/step_results/${Prefix}_step05_domains.json"

& $python "04_author_disambiguation/processing/run_step04_author_disambiguation.py" `
  --expanded-papers $ExpandedPapers `
  --lab-info $LabInfo `
  --target-name $TargetName `
  --output $step04Out `
  --threshold 0.5

& $python "05_keyword_entity/processing/run_step05_keyword_entity.py" `
  --input $step04Out `
  --output $step05Out `
  --min-identity-score 0.5 `
  --top-n 12 `
  --keybert-model "sentence-transformers/all-MiniLM-L6-v2" `
  --local-files-only

& $python "06_domain_clustering/processing/run_step06_domain_clustering.py" `
  --input $step05Out `
  --paper-domains-output $step06PaperOut `
  --domains-output $step06DomainsOut `
  --model "sentence-transformers/all-MiniLM-L6-v2" `
  --local-files-only

Write-Host "DONE"
Write-Host $step04Out
Write-Host $step05Out
Write-Host $step06PaperOut
Write-Host $step06DomainsOut

