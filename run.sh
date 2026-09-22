#!/usr/bin/env bash
# Start LingoSync AI. First run downloads the models (~2.5 GB) from Hugging Face.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  uv venv .venv -p 3.12 && uv pip install --python .venv/bin/python -r requirements.txt
fi
exec .venv/bin/python -m uvicorn backend.server:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8765}" "$@"
