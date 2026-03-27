#!/bin/bash
MSG=${1:-"update site"}
quarto render && git add . && git commit -m "$MSG" && git push
