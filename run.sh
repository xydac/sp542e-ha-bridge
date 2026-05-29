#!/usr/bin/env bash
# Set up venv (idempotent), load .env, run the bridge (default) or probe.
#
#   ./run.sh           # run the MQTT<->BLE bridge service
#   ./run.sh probe     # run the one-shot protocol probe
#
# MUST run from the Mac's local GUI session (not SSH) — CoreBluetooth needs it.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
    uv venv --python 3.13 .venv
    uv pip install --python .venv/bin/python --quiet bleak "aiomqtt>=2.0"
fi

# Load .env if present (export every KEY=VALUE).
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

if [[ "${1:-}" == "probe" ]]; then
    exec .venv/bin/python probe.py
else
    exec .venv/bin/python bridge.py
fi
