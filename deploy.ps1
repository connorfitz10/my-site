param([string]$msg = "update site")
quarto render && git add . && git commit -m $msg && git push
