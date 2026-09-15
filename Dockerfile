# ── Base NVIDIA CUDA (includes nvidia-smi and runtime libs) ──────────────────
# Blackwell (RTX 5080 / GB203) requires CUDA 12.8+
FROM nvidia/cuda:12.8.1-base-ubuntu24.04

# ── System ────────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-dev \
        python3-pip \
        lm-sensors \
    && rm -rf /var/lib/apt/lists/*

# Makes 'python' and 'pip' point at the right versions
RUN ln -sf /usr/bin/python3.12 /usr/local/bin/python \
 && ln -sf /usr/bin/python3.12 /usr/local/bin/python3 \
 && ln -sf /usr/bin/pip3       /usr/local/bin/pip

# ── App ───────────────────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .

EXPOSE 9090

CMD ["python", "monitor_server.py"]
