param([string]$msg = "update site")
quarto render
if ($LASTEXITCODE -eq 0) { git add . }
if ($LASTEXITCODE -eq 0) { git commit -m $msg }
if ($LASTEXITCODE -eq 0) { git push }
