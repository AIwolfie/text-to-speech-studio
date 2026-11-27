#!/usr/bin/env bash
# ==============================================================================
# 🌐 TEXT TO SPEECH STUDIO v2.0 - Web Studio Launcher (macOS & Linux)
# ==============================================================================

set -e
cd "$(dirname "$0")" || exit 1

# ANSI Color Palette
CYAN='\033[38;2;0;210;255m'
PURPLE='\033[38;2;157;78;221m'
GREEN='\033[38;2;0;245;155m'
YELLOW='\033[38;2;255;183;3m'
RED='\033[38;2;255;0;84m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

clear 2>/dev/null || true

echo -e "${CYAN}${BOLD}"
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│                                                                             │"
echo "│   ████████╗████████╗███████╗    ███████╗████████╗██╗   ██╗██████╗ ██╗ ██████╗  │"
echo "│   ╚══██╔══╝╚══██╔══╝██╔════╝    ██╔════╝╚══██╔══╝██║   ██║██╔══██╗██║██╔═══██╗ │"
echo "│      ██║      ██║   ███████╗    ███████╗   ██║   ██║   ██║██║  ██║██║██║   ██║ │"
echo "│      ██║      ██║   ╚════██║    ╚════██║   ██║   ██║   ██║██║  ██║██║██║   ██║ │"
echo "│      ██║      ██║   ███████║    ███████║   ██║   ╚██████╔╝██████╔╝██║╚██████╔╝ │"
echo "│      ╚═╝      ╚═╝   ╚══════╝    ╚══════╝   ╚═╝    ╚═════╝ ╚═════╝ ╚═╝ ╚═════╝  │"
echo "│                                                                             │"
echo "│                     Web Studio Edition (Browser GUI)                        │"
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo -e "${RESET}"

# 1. Detect Python 3
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY_MAJOR=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || true)
        PY_MINOR=$("$cmd" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || true)
        if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}${BOLD}[ERROR]${RESET} Python 3.10+ is required but was not found."
    exit 1
fi

# 2. Venv check
if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    PYTHON_CMD="python"
elif [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    PYTHON_CMD="python"
fi

# 3. Dependencies check
if ! "$PYTHON_CMD" -c "import edge_tts, numpy, imageio_ffmpeg" &>/dev/null; then
    echo -e "${YELLOW}Installing dependencies from requirements.txt...${RESET}"
    "$PYTHON_CMD" -m pip install -r requirements.txt
fi

echo -e "${GREEN}${BOLD}✓ Environment Ready!${RESET}"
echo -e "Starting Web Studio server on: ${CYAN}${BOLD}http://localhost:7860${RESET}"
echo ""

exec "$PYTHON_CMD" web_studio.py "$@"
