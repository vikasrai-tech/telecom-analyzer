#!/bin/bash
# verify_setup.sh — Check that all required tools are installed
# Usage: bash verify_setup.sh
# Run this inside WSL2 Ubuntu terminal

# Colors
GREEN='\041:3[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASS=0
FAIL=0
WARN=0

# Helpers
check() {
    local name="$1"
    local cmd="$2"
    local expected="$3"

    printf "%-30s " "$name"
    if eval "$cmd" >/dev/null 2>&1; then
        local version=$(eval "$cmd" 2>&1 | head -n 1)
        echo -e "${GREEN}✓ OK${NC}  →  $version"
        PASS=$((PASS+1))
    else
        echo -e "${RED}✗ MISSING${NC}  →  install: $expected"
        FAIL=$((FAIL+1))
    fi
}

check_python_pkg() {
    local pkg="$1"
    printf "  python: %-22s " "$pkg"
    if python3 -c "import $pkg" 2>/dev/null; then
        local version=$(python3 -c "import $pkg; print(getattr($pkg, '__version__', 'installed'))" 2>/dev/null)
        echo -e "${GREEN}✓ OK${NC}  →  v$version"
        PASS=$((PASS+1))
    else
        echo -e "${RED}✗ MISSING${NC}  →  pip install $pkg"
        FAIL=$((FAIL+1))
    fi
}

section() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ─────────────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}┌─────────────────────────────────────────────────────────┐${NC}"
echo -e "${YELLOW}│  Telecom Analyzer — Environment Verification            │${NC}"
echo -e "${YELLOW}└─────────────────────────────────────────────────────────┘${NC}"

# ── 1. WSL & System ──
section "1. System (WSL2 / Ubuntu)"

printf "%-30s " "WSL2 detection"
if grep -qi microsoft /proc/version 2>/dev/null; then
    echo -e "${GREEN}✓ OK${NC}  →  Running inside WSL2"
    PASS=$((PASS+1))
else
    echo -e "${YELLOW}⚠ WARN${NC}  →  Not inside WSL2 (might be native Linux, OK)"
    WARN=$((WARN+1))
fi

printf "%-30s " "Ubuntu version"
if [ -f /etc/os-release ]; then
    UBUNTU_VER=$(grep VERSION_ID /etc/os-release | cut -d'"' -f2)
    echo -e "${GREEN}✓ OK${NC}  →  Ubuntu $UBUNTU_VER"
    PASS=$((PASS+1))
fi

printf "%-30s " "Available memory"
MEM_GB=$(free -g | awk '/^Mem:/{print $2}')
if [ "$MEM_GB" -ge 10 ]; then
    echo -e "${GREEN}✓ OK${NC}  →  ${MEM_GB} GB available"
    PASS=$((PASS+1))
else
    echo -e "${YELLOW}⚠ WARN${NC}  →  Only ${MEM_GB} GB — update .wslconfig to give 12 GB"
    WARN=$((WARN+1))
fi

# ── 2. Core tools ──
section "2. Core Build Tools"
check "git"           "git --version"           "sudo apt install git"
check "curl"          "curl --version"          "sudo apt install curl"
check "wget"          "wget --version"          "sudo apt install wget"
check "make"          "make --version"          "sudo apt install build-essential"
check "gcc"           "gcc --version"           "sudo apt install build-essential"

# ── 3. Telecom-specific tools ──
section "3. Telecom Tools"
check "tshark"        "tshark --version"        "sudo apt install tshark"

printf "%-30s " "tshark capture permission"
if [ -x "$(which dumpcap)" ] && getcap "$(which dumpcap)" 2>/dev/null | grep -q cap_net; then
    echo -e "${GREEN}✓ OK${NC}  →  Can capture without sudo"
    PASS=$((PASS+1))
else
    echo -e "${YELLOW}⚠ WARN${NC}  →  Run: sudo setcap 'CAP_NET_RAW+eip CAP_NET_ADMIN+eip' \$(which dumpcap)"
    WARN=$((WARN+1))
fi

# ── 4. Python ──
section "4. Python Environment"
check "python3"       "python3 --version"       "should be 3.11+"
check "pip"           "pip --version"           "comes with python"
check "conda"         "conda --version"         "install Miniconda"

printf "%-30s " "active conda env"
if [ -n "$CONDA_DEFAULT_ENV" ] && [ "$CONDA_DEFAULT_ENV" != "base" ]; then
    echo -e "${GREEN}✓ OK${NC}  →  $CONDA_DEFAULT_ENV"
    PASS=$((PASS+1))
else
    echo -e "${YELLOW}⚠ WARN${NC}  →  No project env active. Run: conda activate telecom"
    WARN=$((WARN+1))
fi

# ── 5. Python packages ──
section "5. Python Packages"
echo "(only checks if 'telecom' env is active or packages installed globally)"
echo ""
check_python_pkg "streamlit"
check_python_pkg "pandas"
check_python_pkg "numpy"
check_python_pkg "sklearn"
check_python_pkg "torch"
check_python_pkg "pyshark"
check_python_pkg "faiss"
check_python_pkg "ollama"
check_python_pkg "mlflow"

# ── 6. Docker ──
section "6. Docker"
check "docker"        "docker --version"        "install Docker Desktop with WSL2 integration"

printf "%-30s " "docker daemon running"
if docker info >/dev/null 2>&1; then
    echo -e "${GREEN}✓ OK${NC}  →  Daemon reachable"
    PASS=$((PASS+1))
else
    echo -e "${RED}✗ NOT RUNNING${NC}  →  Start Docker Desktop on Windows"
    FAIL=$((FAIL+1))
fi

# ── 7. Ollama (LLM) ──
section "7. Ollama (Local LLM)"
check "ollama"        "ollama --version"        "curl -fsSL https://ollama.com/install.sh | sh"

printf "%-30s " "ollama service running"
if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo -e "${GREEN}✓ OK${NC}  →  Service reachable"
    PASS=$((PASS+1))
else
    echo -e "${RED}✗ NOT RUNNING${NC}  →  Run in another terminal: ollama serve"
    FAIL=$((FAIL+1))
fi

printf "%-30s " "phi3:mini model"
if ollama list 2>/dev/null | grep -q "phi3"; then
    SIZE=$(ollama list 2>/dev/null | grep phi3 | awk '{print $3 $4}')
    echo -e "${GREEN}✓ OK${NC}  →  Downloaded ($SIZE)"
    PASS=$((PASS+1))
else
    echo -e "${RED}✗ MISSING${NC}  →  Run: ollama pull phi3:mini"
    FAIL=$((FAIL+1))
fi

# ── 8. VS Code ──
section "8. VS Code (optional from CLI)"
check "code"          "code --version"          "install VS Code on Windows + WSL extension"

# ── Summary ──
section "Summary"
TOTAL=$((PASS + FAIL + WARN))
echo ""
echo -e "  ${GREEN}✓ Passed:${NC}  $PASS"
echo -e "  ${YELLOW}⚠ Warned:${NC}  $WARN"
echo -e "  ${RED}✗ Failed:${NC}  $FAIL"
echo -e "  ─────────────"
echo -e "    Total checks: $TOTAL"
echo ""

if [ $FAIL -eq 0 ] && [ $WARN -eq 0 ]; then
    echo -e "${GREEN}🎉 Everything looks good. You are ready to start coding!${NC}"
    echo ""
    echo "Next step:"
    echo "  cd ~/projects/telecom-analyzer"
    echo "  streamlit run src/dashboard/app.py"
elif [ $FAIL -eq 0 ]; then
    echo -e "${YELLOW}⚠ Setup is functional but has warnings. Review them above.${NC}"
else
    echo -e "${RED}✗ Some required components are missing. Fix the failures above first.${NC}"
fi
echo ""
