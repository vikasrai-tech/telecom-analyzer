#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Telecom Analyzer — One-command demo launcher
# Usage:
#   bash start_demo.sh          → local only (http://localhost:8501)
#   bash start_demo.sh --public → local + public tunnel URL via localtunnel
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PUBLIC=false
[[ "${1:-}" == "--public" ]] && PUBLIC=true

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║      Unified Telecom Analyzer — Demo Launcher        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Start Streamlit in background
echo "▶ Starting dashboard..."
streamlit run src/dashboard/app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false &
APP_PID=$!

# Wait for app to be ready
echo "  Waiting for app to be ready..."
for i in $(seq 1 20); do
    if curl -sf http://localhost:8501/_stcore/health > /dev/null 2>&1; then
        echo "  ✅ App is ready"
        break
    fi
    sleep 1
done

echo ""
echo "  Local URL  : http://localhost:8501"

if $PUBLIC; then
    echo ""
    echo "▶ Starting public tunnel (localtunnel)..."
    npx localtunnel --port 8501 &
    LT_PID=$!
    echo "  (Public URL will appear above — share it with the interviewer)"
fi

echo ""
echo "  Demo files ready for upload:"
echo "    PCAP  → data/raw/test_5g_full.pcap"
echo "    PCAP  → data/raw/ue_attach_10.pcap"
echo "    PCAP  → data/raw/ue_handover_20.pcap"
echo "    KPI   → data/raw/5G_Network_KPI_Sample.xlsx"
echo "    KPI   → data/raw/kpi_10hr_sample.csv"
echo "    Stats → data/samples/du_cu_stats_annotated.csv"
echo ""
echo "  Press Ctrl+C to stop."
echo ""

# Wait for Ctrl+C
trap 'echo ""; echo "Stopping..."; kill $APP_PID 2>/dev/null; ${PUBLIC} && kill $LT_PID 2>/dev/null; exit 0' INT
wait
