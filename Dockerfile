# ── Stage 1: Python dependencies ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpcap-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install torch CPU-only first (avoids downloading the huge CUDA build)
RUN pip install --no-cache-dir \
    torch==2.5.1+cpu \
    torchvision==0.20.1+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# Install remaining requirements (torch/torchvision already satisfied)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# tshark is needed by pyshark for PCAP parsing
# Accept Wireshark EULA non-interactively
RUN echo "wireshark-common wireshark-common/install-setuid boolean false" \
        | debconf-set-selections && \
    apt-get update && apt-get install -y --no-install-recommends \
    tshark \
    libpcap0.8 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Copy application source
COPY src/       ./src/
COPY data/      ./data/
COPY scripts/   ./scripts/
COPY .streamlit/ ./.streamlit/

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "src/dashboard/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]
