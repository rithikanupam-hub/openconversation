#!/usr/bin/env bash
# Start LingoSync AI. First run downloads the models (~2.5 GB) from Hugging Face.
#   ./run.sh          laptop only: http://127.0.0.1:8765
#   ./run.sh --phone  also reachable from a phone on the same Wi-Fi over HTTPS
#                     (phone browsers only allow the microphone on https pages)
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  uv venv .venv -p 3.12 && uv pip install --python .venv/bin/python -r requirements.txt
fi
PORT="${PORT:-8765}"

if [ "$1" = "--phone" ]; then
  shift
  IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)"
  [ -n "$IP" ] || { echo "No Wi-Fi IP found; connect the Mac to Wi-Fi first." >&2; exit 1; }
  mkdir -p certs
  # Self-signed certificate for this IP, regenerated when the Mac's IP changes.
  if [ ! -f certs/cert.pem ] || [ "$(cat certs/ip 2>/dev/null)" != "$IP" ]; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=LingoSync" \
      -addext "subjectAltName=IP:$IP,IP:127.0.0.1,DNS:localhost" \
      -keyout certs/key.pem -out certs/cert.pem 2>/dev/null
    echo "$IP" > certs/ip
  fi
  echo
  echo "  On your phone (same Wi-Fi) open:  https://$IP:$PORT"
  echo "  The browser warns about the certificate once: tap 'Show details' / 'Advanced' → visit anyway."
  echo
  exec .venv/bin/python -m uvicorn backend.server:app --host 0.0.0.0 --port "$PORT" \
    --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem "$@"
fi

exec .venv/bin/python -m uvicorn backend.server:app --host "${HOST:-127.0.0.1}" --port "$PORT" "$@"
