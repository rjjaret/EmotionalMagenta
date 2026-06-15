#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

LOG_FILE="runtime_5min.log"
TEST_DURATION_SECONDS="${TEST_DURATION_SECONDS:-300}"
INT_GRACE_SECONDS="${INT_GRACE_SECONDS:-8}"
TERM_GRACE_SECONDS="${TERM_GRACE_SECONDS:-5}"

wait_for_exit_with_timeout() {
	local pid="$1"
	local timeout_seconds="$2"
	local elapsed=0

	while kill -0 "$pid" 2>/dev/null; do
		if [[ "$elapsed" -ge "$timeout_seconds" ]]; then
			return 1
		fi
		sleep 1
		elapsed=$((elapsed + 1))
	done

	return 0
}

pkill -f collider_emotion_bridge.py || true
pkill -x collider_em || true
pkill -f "python main.py" || true

defaults delete com.google.collider_em Collider_EmotionPrompt 2>/dev/null || true
defaults delete com.google.collider_em Collider_EmotionState 2>/dev/null || true

source .venv/bin/activate
rm -f "$LOG_FILE"

python main.py > "$LOG_FILE" 2>&1 &
APP_PID=$!

sleep "$TEST_DURATION_SECONDS"

kill -INT "$APP_PID" 2>/dev/null || true
if ! wait_for_exit_with_timeout "$APP_PID" "$INT_GRACE_SECONDS"; then
	kill -TERM "$APP_PID" 2>/dev/null || true
	if ! wait_for_exit_with_timeout "$APP_PID" "$TERM_GRACE_SECONDS"; then
		kill -KILL "$APP_PID" 2>/dev/null || true
	fi
fi

wait "$APP_PID" 2>/dev/null || true

echo "LOG_FILE=$LOG_FILE"