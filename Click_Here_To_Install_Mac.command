#!/usr/bin/env bash
set -euo pipefail

export LANG="${LANG:-en_US.UTF-8}"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

on_error() {
    local exit_code=$?
    echo ""
    echo "========================================================================"
    echo "  JurisAtlas Setup could not complete (exit code: ${exit_code})."
    echo "  Please check the message above and your internet connection."
    echo "  Help & troubleshooting: https://jurisatlas.github.io"
    echo "========================================================================"
    echo ""
    if [ -t 0 ] || [ -r /dev/tty ]; then
        read -r -p "Press Return to close this window... " _ < /dev/tty || true
    fi
    exit "${exit_code}"
}
trap on_error ERR

echo "========================================================================"
echo "  JurisAtlas v2.0 — Official Legal Sources for Your AI Assistant"
echo "  Read-Only | Free (MIT) | Never touches personal files"
echo "========================================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JA_DIR="${HOME}/Library/Application Support/JurisAtlas/cli"
mkdir -p "${JA_DIR}"

# Copy bundled installer files to persistent cache so deleting Downloads ZIP never breaks setup
if [ -f "${SCRIPT_DIR}/jurisatlas_cli.py" ]; then
    cp -f "${SCRIPT_DIR}/jurisatlas_cli.py" "${JA_DIR}/jurisatlas_cli.py"
    if [ -f "${SCRIPT_DIR}/jurisatlas_i18n.py" ]; then
        cp -f "${SCRIPT_DIR}/jurisatlas_i18n.py" "${JA_DIR}/jurisatlas_i18n.py"
    fi
    if [ -f "${SCRIPT_DIR}/pyproject.toml" ]; then
        cp -f "${SCRIPT_DIR}/pyproject.toml" "${JA_DIR}/pyproject.toml"
    fi
fi

export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"

if ! command -v uv >/dev/null 2>&1; then
    if ! command -v curl >/dev/null 2>&1; then
        echo "[ERROR] 'curl' is required to install the uv package runner, but was not found."
        exit 1
    fi
    echo "Installing lightweight uv package runner..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "[ERROR] 'uv' was not found on PATH after installation."
    exit 1
fi

echo "Preparing isolated Python 3.12 runtime (with bundled GUI support)..."
MANAGED_PY="$(uv python find --managed-python 3.12 2>/dev/null || true)"
if [ -z "${MANAGED_PY}" ]; then
    uv python install 3.12
    MANAGED_PY="$(uv python find --managed-python 3.12)"
fi

if [ ! -x "${MANAGED_PY}" ]; then
    echo "[ERROR] Managed Python 3.12 binary could not be located."
    exit 1
fi

echo "Launching JurisAtlas Setup Window..."
echo ""
if [ -f "${JA_DIR}/jurisatlas_cli.py" ]; then
    "${MANAGED_PY}" "${JA_DIR}/jurisatlas_cli.py" "$@"
else
    if ! command -v uvx >/dev/null 2>&1; then
        echo "[ERROR] 'uvx' not found and jurisatlas_cli.py is missing next to this launcher."
        echo "Tip: Extract the entire ZIP folder before double-clicking this file."
        exit 1
    fi
    uvx --python "${MANAGED_PY}" --from https://github.com/jurisatlas/cli/archive/refs/heads/main.zip jurisatlas "$@"
fi
