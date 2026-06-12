#!/bin/bash
# 真实 HAR 回归（本地专用，HAR 与基准都不进 git）。
# 首次运行建立基准快照；之后每次运行与基准逐字节 diff。
# 渲染输出有意变更后，用 --rebase 重建基准。
set -uo pipefail
cd "$(dirname "$0")/.."

HARS=(
  "$HOME/Desktop/智谱/归档/060501zhipu-ai.feishu.cn.har"
  "$HOME/Desktop/智谱/归档/060502zhipu-ai.feishu.cn.har"
  "$HOME/Desktop/智谱/归档/060503zhipu-ai.feishu.cn.har"
  "$HOME/Desktop/智谱/归档/tmp/060301zhipu-ai.feishu.cn.har"
  "$HOME/Desktop/智谱/归档/tmp/zhipu-ai.feishu.cn.har"
)
REF="${TMPDIR:-/tmp}/feishu-whiteboard-har-ref"
RUN="${TMPDIR:-/tmp}/feishu-whiteboard-har-run"

[ "${1:-}" = "--rebase" ] && rm -rf "$REF"
mkdir -p "$REF"
rm -rf "$RUN" && mkdir -p "$RUN"

fail=0
for har in "${HARS[@]}"; do
  name=$(basename "$har" .har)
  [ -f "$har" ] || { echo "skip (缺文件): $name"; continue; }
  if [ ! -d "$REF/$name" ]; then
    python3 scripts/process_har.py "$har" --out "$REF/$name" > /dev/null 2>&1
    echo "baseline created: $name"
    continue
  fi
  python3 scripts/process_har.py "$har" --out "$RUN/$name" > /dev/null 2>&1
  if diff -rq "$REF/$name" "$RUN/$name" > /dev/null 2>&1; then
    echo "OK:   $name"
  else
    echo "DIFF: $name"
    diff -rq "$REF/$name" "$RUN/$name" | head -10
    fail=1
  fi
done
exit $fail
