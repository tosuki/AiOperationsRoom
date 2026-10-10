#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8765}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$REPO_DIR/.venv/bin/python"
URL="http://127.0.0.1:$PORT"

if [[ ! -x "$PYTHON" ]]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON="$(command -v python3)"
    else
        echo "Erro: Python não encontrado." >&2
        exit 1
    fi
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Erro: A porta $PORT já está em uso." >&2
    exit 1
fi

(cd "$REPO_DIR" && "$PYTHON" -m backend.cli serve --port "$PORT") &
SERVER_PID=$!

READY=0
for _ in {1..30}; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        break
    fi
    if curl -s -o /dev/null -w "%{http_code}" "$URL/api/health" 2>/dev/null | grep -q "200"; then
        READY=1
        break
    fi
    sleep 0.5
done

if [[ "$READY" -ne 1 ]]; then
    echo "Erro: O servidor não respondeu em $URL." >&2
    exit 1
fi

if [[ "${NO_BROWSER:-0}" != "1" ]]; then
    if command -v open >/dev/null 2>&1; then
        open "$URL"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL"
    fi
fi

echo "AI Operations Room iniciado em $URL (PID $SERVER_PID)."
