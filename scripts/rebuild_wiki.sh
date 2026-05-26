#!/bin/bash
# Full wiki rebuild script with logging
set -e
cd "$(dirname "$0")/.."

LOG="data/wiki/rebuild.log"
mkdir -p data/wiki

echo "=== Wiki rebuild started at $(date) ===" > "$LOG"

set +e
PYTHONUNBUFFERED=1 uv run python -m src.wiki.diary_generation --clean >> "$LOG" 2>&1
EXIT_CODE=$?
set -e

echo "=== Wiki rebuild finished at $(date), exit=$EXIT_CODE ===" >> "$LOG"
exit $EXIT_CODE
