#!/usr/bin/env bash
# Full local stack: Python bootstrap (ML + agent plugins + Playwright + PDF), then
#   demo API :8000, BFF :8001, Vite :5173.
# From repo root:  ./scripts/startup.sh
# Fast iteration:  STARTUP_QUICK=1 ./scripts/startup.sh  (servers only, skip heavy prep)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  . "$ROOT/.venv/bin/activate"
fi

# Map OS env (USE_FIXTURES, tokens) into the demo server — same as most shell workflows.
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT/.env" || true
  set +a
fi

export AGENT_BACKEND="${AGENT_BACKEND:-hybrid}"
export PIP_NO_INPUT=1

# VITE_DEV_FAKE_AUTH (root .env): SPA skips Auth0; BFF needs JWT bypass unless you set AUTH0_BYPASS yourself.
_vfa="$(printf %s "${VITE_DEV_FAKE_AUTH:-}" | tr "[:upper:]" "[:lower:]")"
if [[ "$_vfa" == "1" || "$_vfa" == "true" || "$_vfa" == "yes" || "$_vfa" == "on" ]]; then
  if [[ -z "${AUTH0_BYPASS:-}" ]]; then
    export AUTH0_BYPASS=1
    echo "[startup] VITE_DEV_FAKE_AUTH is on and AUTH0_BYPASS was unset → AUTH0_BYPASS=1 for BFF (:8001)"
  fi
fi
unset _vfa

# --- optional: install LangChain plugin for AGENT_BACKEND=langchain (not required for hybrid)
if [[ "${STARTUP_INSTALL_LANGCHAIN_PLUGIN:-0}" == "1" ]]; then
  echo "[startup] optional: LangChain agent plugin (large)…"
  pip install -e "$ROOT/plugins/langchain_plugin[langchain]" 2>/dev/null || true
fi

# --- quick mode: only long-running services (use when deps and browsers are already set up)
if [[ "${STARTUP_QUICK:-0}" == "1" ]]; then
  echo "[startup] STARTUP_QUICK=1 — skipping pip, Playwright, PDF prerender, ML smoke"
  STARTUP_SKIP_PIP=1
  STARTUP_SKIP_PLAYWRIGHT=1
  STARTUP_SKIP_PDF_PRERENDER=1
  STARTUP_SKIP_ML_SMOKE=1
fi

need_pip=0
if [[ "${STARTUP_SKIP_PIP:-0}" != "1" ]]; then
  if ! python3 -c "import overfished_ml" 2>/dev/null; then
    need_pip=1
  elif ! python3 -c "import overfished_fetch_plugin" 2>/dev/null; then
    need_pip=1
  elif ! python3 -c "from overfished_api.main import app" 2>/dev/null; then
    need_pip=1
  fi
fi
if (( need_pip )); then
  echo "[startup] installing / repairing Python stack (map API + overfished-ml + BFF[ml] + Fetch plugin)…"
  pip install -r "$ROOT/backend/requirements.txt"
  pip install -e "$ROOT/ml"
  pip install -e "$ROOT/api[ml,dev]"
  pip install -e "$ROOT/plugins/fetch_plugin"
fi

# --- Playwright: Chromium for Jinja2 → HTML/PDF (backend/documents/render.py)
if [[ "${STARTUP_SKIP_PLAYWRIGHT:-0}" != "1" ]]; then
  if python3 -c "import playwright" 2>/dev/null; then
    echo "[startup] Playwright: ensuring Chromium (Jinja2 → HTML/PDF for case files under backend/documents/…)"
    python3 -m playwright install chromium
  else
    echo "[startup] warn: playwright not importable — case PDFs may need: pip install -r backend/requirements.txt"
  fi
fi

# --- ML: quick in-process RNN / BiLSTM + ensemble smoke (same stack as BFF /ml/sequence, no HTTP)
if [[ "${STARTUP_SKIP_ML_SMOKE:-0}" != "1" ]]; then
  if python3 -c "import overfished_ml" 2>/dev/null; then
    echo "[startup] ML: synthetic sequence report smoke (torch + overfished-ml)…"
    cd "$ROOT" && python3 - <<'PY' || true
import sys
from overfished_ml.sequence.report import build_sequence_report, synthetic_events_dataframe
from overfished_ml.sequence.train import TrainingConfig
cfg = TrainingConfig(
    seq_len=4, batch_size=4, epochs=1, hidden_dim=32, val_fraction=0.25, top_k=3
)
r = build_sequence_report(dataframe=synthetic_events_dataframe(), config=cfg)
assert "rnn" in r and "bilstm" in r
print("  sequence smoke OK (rnn/bilstm/ensemble path exercised)", file=sys.stderr)
PY
  else
    echo "[startup] warn: overfished_ml not installed — BFF /ml/sequence will not be available"
  fi
fi

# --- PDF: pre-render the demo IUU case family into backend/output/ (served as /static)
if [[ "${STARTUP_SKIP_PDF_PRERENDER:-0}" != "1" ]]; then
  echo "[startup] PDF: rendering demo case documents (Jinja2 + Playwright)…"
  (cd "$ROOT/backend" && python3 -m documents.render) || {
    echo "[startup] warn: PDF prerender failed — on-demand /case/.../documents will try again; check Playwright."
  }
fi

cleanup() {
  local ec=$?
  [[ -n "${BFF_PID:-}" ]] && kill "$BFF_PID" 2>/dev/null || true
  [[ -n "${DEMO_PID:-}" ]] && kill "$DEMO_PID" 2>/dev/null || true
  [[ -n "${FE_PID:-}" ]] && kill "$FE_PID" 2>/dev/null || true
  exit "$ec"
}
trap cleanup EXIT INT TERM

echo "[startup] demo API (map, fixtures) → http://127.0.0.1:8000"
(
  cd "$ROOT/backend"
  exec uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
) &
DEMO_PID=$!

echo "[startup] BFF (Auth0, /agent, /ml, plugins: ${AGENT_BACKEND}) → http://127.0.0.1:8001"
(
  cd "$ROOT/api"
  exec uvicorn overfished_api.main:app --reload --host 0.0.0.0 --port 8001
) &
BFF_PID=$!

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "[startup] installing frontend dependencies…"
  (cd "$ROOT/frontend" && npm install)
fi

echo "[startup] Vite dev server → http://127.0.0.1:5173 (proxies /api → :8000, /agentapi → :8001)"
(
  cd "$ROOT/frontend"
  exec npm run dev
) &
FE_PID=$!

# Block until all children exit (e.g. Ctrl+C triggers trap and kills the rest).
wait
