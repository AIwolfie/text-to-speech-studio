#!/usr/bin/env bash
# ==============================================================================
# 🎙️ TEXT TO SPEECH STUDIO v2.0 - macOS & Linux Launcher
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

# Clear screen for fresh studio feel
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
echo "│                  Next-Gen Neural AI Voice Creation Suite                    │"
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo -e "${RESET}"

# 1. Detect Python 3
echo -e "${DIM}[1/4] Detecting Python runtime...${RESET}"
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY_VER=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
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
    echo -e "Please install Python from: ${CYAN}https://www.python.org/downloads/${RESET}"
    exit 1
fi
echo -e "${GREEN}  ✓ Found Python ${PY_VER} (${PYTHON_CMD})${RESET}"

# 2. Virtual Environment Management (Optional Auto-Venv)
echo -e "${DIM}[2/4] Verifying virtual environment...${RESET}"
if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    PYTHON_CMD="python"
    echo -e "${GREEN}  ✓ Activated existing virtual environment (.venv)${RESET}"
elif [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    PYTHON_CMD="python"
    echo -e "${GREEN}  ✓ Activated existing virtual environment (venv)${RESET}"
else
    echo -e "${DIM}  • Running in standard environment${RESET}"
fi

# 3. Verify Tkinter (Required for Desktop GUI)
echo -e "${DIM}[3/4] Checking GUI display framework (Tkinter)...${RESET}"
if ! "$PYTHON_CMD" -c "import tkinter" &>/dev/null; then
    echo -e "${YELLOW}${BOLD}[WARNING]${RESET} Tkinter is not installed on your system."
    echo -e "To install Tkinter:"
    echo -e "  • Ubuntu/Debian: ${CYAN}sudo apt-get install python3-tk${RESET}"
    echo -e "  • Fedora:        ${CYAN}sudo dnf install python3-tkinter${RESET}"
    echo -e "  • Arch Linux:    ${CYAN}sudo pacman -S tk${RESET}"
    echo -e "  • macOS (Brew):  ${CYAN}brew install python-tk${RESET}"
    echo ""
    echo -e "Starting Web Studio instead? Press [W] for Web Studio or [Q] to quit:"
    read -r -n 1 choice
    echo ""
    if [[ "$choice" =~ ^[Ww]$ ]]; then
        exec "$PYTHON_CMD" web_studio.py
    else
        exit 1
    fi
fi
echo -e "${GREEN}  ✓ Tkinter GUI framework ready${RESET}"

# 4. Check Core Dependencies
echo -e "${DIM}[4/4] Checking neural TTS dependencies...${RESET}"
if ! "$PYTHON_CMD" -c "import edge_tts, numpy, imageio_ffmpeg" &>/dev/null; then
    echo -e "${YELLOW}  Installing dependencies from requirements.txt...${RESET}"
    "$PYTHON_CMD" -m pip install -r requirements.txt
fi
echo -e "${GREEN}  ✓ Core dependencies verified${RESET}"

echo ""
echo -e "${PURPLE}${BOLD}┌─────────────────────────────────────────────────────────────────────────────┐${RESET}"
echo -e "${PURPLE}${BOLD}│${RESET}  ${GREEN}●${RESET} Launching Desktop Studio Interface...                              ${PURPLE}${BOLD}│${RESET}"
echo -e "${PURPLE}${BOLD}└─────────────────────────────────────────────────────────────────────────────┘${RESET}"
echo ""

# Launch Desktop GUI
exec "$PYTHON_CMD" tts_gui.py "$@"
