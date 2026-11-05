#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a
source "$DIR/agents.env"
set +a
exec python3 "$DIR/runtime.py" start web "$@"
