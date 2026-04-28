param(
  [Parameter(Mandatory = $true)][string]$ExpandedPapers,
  [Parameter(Mandatory = $true)][string]$LabInfo,
  [Parameter(Mandatory = $true)][string]$TargetName,
  [string]$Prefix = "professor"
)

$ErrorActionPreference = "Stop"

$python = ".\.venv\Scripts\python.exe"

$step03Out = "03_author_disambiguation/step_results/${Prefix}_step03_disambiguated_papers.jsonl"
$step04Out = "04_keyword_entity/step_results/${Prefix}_step04_keyword_entity.jsonl"
$step05PaperOut = "05_domain_analysis/step_results/${Prefix}_step05_paper_domains.jsonl"
$step05DomainsOut = "05_domain_analysis/step_results/${Prefix}_step05_domains.json"
$step05WordcloudTermsOut = "05_domain_analysis/step_results/${Prefix}_step05_wordcloud_terms.json"
$step05WordcloudImageOut = "05_domain_analysis/step_results/${Prefix}_step05_wordcloud.png"

& $python "03_author_disambiguation/processing/run_step03_author_disambiguation.py" `
  --expanded-papers $ExpandedPapers `
  --lab-info $LabInfo `
  --target-name $TargetName `
  --output $step03Out `
  --threshold 0.5

& $python "04_keyword_entity/processing/run_step04_keyword_entity.py" `
  --input $step03Out `
  --output $step04Out `
  --min-identity-score 0.5 `
  --top-n 12 `
  --keybert-model "sentence-transformers/all-MiniLM-L6-v2" `
  --local-files-only

& $python "05_domain_analysis/processing/run_step05_domain_analysis.py" `
  --input $step04Out `
  --paper-domains-output $step05PaperOut `
  --domains-output $step05DomainsOut `
  --wordcloud-terms-output $step05WordcloudTermsOut `
  --wordcloud-image-output $step05WordcloudImageOut `
  --model "sentence-transformers/all-MiniLM-L6-v2" `
  --local-files-only

Write-Host "DONE"
Write-Host $step03Out
Write-Host $step04Out
Write-Host $step05PaperOut
Write-Host $step05DomainsOut
Write-Host $step05WordcloudTermsOut
Write-Host $step05WordcloudImageOut

