#!/bin/bash
# 重新生成 golden 基准。仅在渲染输出有意变更、且人工目检过 diff 后使用。
set -euo pipefail
cd "$(dirname "$0")"

python3 fixtures/make_synthetic.py
TMP=$(mktemp -d)
python3 ../scripts/process_har.py fixtures/synthetic.har --out "$TMP/synthetic" --extract-related-images > /dev/null
rm -rf golden && mkdir -p golden
cp "$TMP/synthetic"/*.simple.svg "$TMP/synthetic"/index.md "$TMP/synthetic"/summary.json golden/
rm -rf "$TMP"
echo "golden 已重生成: $(ls golden | tr '\n' ' ')"
echo "提醒: git diff 目检后再提交"
