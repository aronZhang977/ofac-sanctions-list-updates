#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python scripts/setup_email.py
fi
exec python3 scripts/setup_email.py