#!/usr/bin/env bash
# 一鍵跑完整個流程：產生優化前 / 優化後模擬 log → 分類 → 儀表板
# 用法：./run.sh            （預設 30 天）
#       ./run.sh 60 0.002   （60 天，爬蟲規模 ×2）
set -euo pipefail
cd "$(dirname "$0")"
DAYS="${1:-30}"
SCALE="${2:-0.001}"

python3 lab/generate_logs.py --scenario baseline  --days "$DAYS" --bot-scale "$SCALE" --start 2026-09-01 --out output/baseline.log
python3 lab/generate_logs.py --scenario optimized --days "$DAYS" --bot-scale "$SCALE" --start 2026-10-01 --out output/optimized.log
python3 lab/classify.py output/baseline.log  --label 優化前 --out output/baseline.json
python3 lab/classify.py output/optimized.log --label 優化後 --out output/optimized.json
python3 lab/report.py output/optimized.json --compare output/baseline.json --out output/dashboard.html

echo
echo "完成。打開 output/dashboard.html 就能看到儀表板。"
