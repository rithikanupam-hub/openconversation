#!/usr/bin/env bash
# OpenConversation M1: LiveKit server + translator agent + web page, all on this Mac.
#   ./run_lk.sh   then open http://127.0.0.1:8765/lk
# Ctrl-C stops all three.
cd "$(dirname "$0")"
LOGS="${LOGS:-logs}"
mkdir -p "$LOGS"
pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null; }
trap cleanup EXIT INT TERM

# 1. LiveKit server (dev keys devkey/secret), only reachable from this Mac
livekit-server --dev --bind 127.0.0.1 > "$LOGS/livekit.log" 2>&1 &
pids+=($!)

# 2. Web server for the page and access tokens; it loads no models (the agent does)
LINGOSYNC_NO_WARMUP=1 .venv/bin/python -m uvicorn backend.server:app --host 127.0.0.1 --port "${PORT:-8765}" \
  > "$LOGS/web.log" 2>&1 &
pids+=($!)

# 3. Translator agent: loads the models once, joins the room, translates everyone who speaks
sleep 2
.venv/bin/python -m backend.lk_agent 2>&1 | tee "$LOGS/agent.log" &
pids+=($!)

echo "Open http://127.0.0.1:${PORT:-8765}/lk once the agent says it joined the room."
wait
