# 🖥️ SYS//MONITOR

> Real-time hardware dashboard for Ubuntu Server — accessible from anywhere via Tailscale, built to stay out of your GPU's way.

A self-hosted monitoring tool that combines a lightweight Python backend with a pure-HTML/JS dashboard to display live CPU, RAM, GPU (NVIDIA), temperature, disk, and network metrics — updated every 5 seconds, with up to 5 minutes of scrolling history.

<p align="center">
  <img alt="Stack" src="https://img.shields.io/badge/Stack-aiohttp%20%2B%20psutil%20%2B%20nvidia--smi-blue?style=for-the-badge">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge">
  <img alt="Status" src="https://img.shields.io/badge/Status-Stable-success?style=for-the-badge">
</p>

---

## 📦 How it works

A minimal `aiohttp` server runs as an `idle`-priority systemd service and exposes a `/metrics` JSON endpoint. The dashboard — a single HTML file served by the same process — polls that endpoint every 5 seconds and renders everything client-side with vanilla Canvas charts. No frameworks, no Node, no build step.

```
Ubuntu Server
├── monitor_server.py   ←  aiohttp backend  (port 9090)
│     ├── /             →  serves index.html
│     ├── /metrics      →  JSON snapshot of all hardware readings
│     └── /health       →  {"status": "ok"}
└── static/index.html   ←  dashboard (pure HTML/CSS/JS)

Tailscale network
└── http://<tailscale-ip>:9090   ←  fixed address, accessible anywhere
```

On each poll the backend collects:

1. **CPU** — total usage %, per-core %, current frequency, physical/logical core count
2. **Temperatures** — all sensors exposed by `lm-sensors` / `psutil`
3. **Load average** — 1 / 5 / 15 minute
4. **Memory** — used, available, total (GB), swap %
5. **GPU (NVIDIA)** — utilization, VRAM used/total, temperature, fan speed, power draw/limit, graphics and memory clocks (via `nvidia-smi`)
6. **Disks** — per-partition usage for all mounted filesystems
7. **Network** — cumulative bytes sent/received, packet counts

---

## 🧰 What's under the hood

| Component | Library / tool |
|-----------|----------------|
| Async HTTP server | [`aiohttp`](https://docs.aiohttp.org) |
| Hardware readings | [`psutil`](https://psutil.readthedocs.io) |
| Temperature sensors | `lm-sensors` + `psutil.sensors_temperatures()` |
| GPU metrics | `nvidia-smi` (subprocess, CSV output) |
| Charts & UI | Vanilla Canvas API — zero dependencies |
| Service management | `systemd` (idle CPU/IO priority) |
| Remote access | [Tailscale](https://tailscale.com) MagicDNS / fixed IP |

The dashboard keeps the last **60 samples** (5 minutes at 5 s/poll) in memory and redraws all charts on every update and on window resize.

---

## 📋 Prerequisites

- **Python 3.10+**
- `lm-sensors` installed and configured (`sudo sensors-detect`)
- NVIDIA drivers + `nvidia-smi` in `$PATH` (for GPU metrics)
- Tailscale installed on both server and client (for remote access)

---

## 🚀 Quick start

### Install

```bash
# Clone / copy the project
sudo cp -r server-monitor/ /opt/server-monitor
cd /opt/server-monitor

# Create a virtual environment
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Run manually

```bash
source /opt/server-monitor/venv/bin/activate
python3 monitor_server.py
# → http://localhost:9090
```

### Install as a systemd service (auto-start on boot)

```bash
sudo cp systemd/server-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now server-monitor

# Check status
sudo systemctl status server-monitor

# Follow logs
journalctl -u server-monitor -f
```

### Access from anywhere

```bash
# Find your server's Tailscale IP
tailscale ip -4
```

Then open `http://<tailscale-ip>:9090` on any device in your Tailscale network. If MagicDNS is enabled:

```
http://<hostname>.tail-xxxx.ts.net:9090
```

---

## ⚙️ Configuration

All options are at the top of `monitor_server.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `9090` | Listen port |
| `CORS_ORIGIN` | `*` | CORS header — restrict to your Tailscale CIDR if desired |

The poll interval and history length live in `static/index.html`:

| Constant | Default | Description |
|----------|---------|-------------|
| `POLL_MS` | `5000` | Milliseconds between each `/metrics` fetch |
| `HISTORY_MAX` | `60` | Number of samples kept in memory (60 × 5 s = 5 min) |

---

## 📊 Dashboard panels

| Panel | Metrics shown |
|-------|---------------|
| **CPU Usage** | Total %, current frequency, sparkline history, load average (1/5/15 min) |
| **Per-Core Load** | Vertical bar for each logical core, color-coded by load level |
| **Temperatures** | All `lm-sensors` readings with heat-bar and color threshold (green → amber → red) |
| **Memory** | RAM % with sparkline, used/total GB, available GB, swap % |
| **GPU** | Core utilization %, VRAM bar, temperature, fan speed, power draw, graphics/memory clocks |
| **GPU History** | 5-minute sparkline overlay for GPU utilization and VRAM usage |
| **Disks** | Per-partition usage bar for every mounted filesystem |
| **Network I/O** | Cumulative MB sent/received, packet counts, dual-line sparkline |

Color thresholds (applied to CPU, RAM, disk, GPU, and temperatures):

| Range | Color |
|-------|-------|
| < 75 % | Green |
| 75 – 90 % | Amber |
| ≥ 90 % | Red |

---

## 📁 Project structure

```
server-monitor/
├── monitor_server.py          # aiohttp backend + metrics collectors
├── static/
│   └── index.html             # Dashboard (HTML + CSS + JS, single file)
├── systemd/
│   └── server-monitor.service # systemd unit (idle priority)
├── requirements.txt
└── README.md
```

---

## ⚡ Performance impact

The service is designed to be invisible to GPU-intensive workloads.

| Component | Estimated cost |
|-----------|----------------|
| `aiohttp` idle | ~5 MB RAM, ~0 % CPU |
| `psutil` read per poll | < 1 ms |
| `nvidia-smi` query per poll | ~10 ms, negligible |
| systemd CPU scheduler | `CPUSchedulingPolicy=idle` |
| systemd I/O scheduler | `IOSchedulingClass=idle` |

The OS will preempt the monitor process instantly in favor of any real workload.

---

## ⚠️ Limitations

- **No authentication.** The dashboard is open to anyone on your Tailscale network. Tailscale ACLs are your access control layer.
- **GPU support is NVIDIA-only.** AMD/Intel GPU metrics are not implemented.
- **Network counters are cumulative** (since last boot), not per-interval throughput.
- **No persistent storage.** History is kept in the browser tab's memory; closing the tab resets the charts.

---

## 🛣️ Roadmap

- [ ] Per-interval network throughput (MB/s in / out)
- [ ] AMD GPU support via `rocm-smi`
- [ ] Process table — top N processes by CPU/RAM
- [ ] Configurable alert thresholds with browser notifications
- [ ] Optional basic auth for non-Tailscale deployments

---

## 📜 License

MIT — see `LICENSE` file.

## 👤 Author

**Cassiano Ribeiro Carneiro** — [@cassianorcarneiro](https://github.com/cassianorcarneiro)

---

### 🤖 AI Assistance Disclosure

The architecture, implementation, and dashboard design of this project were developed in collaboration with [Claude](https://www.anthropic.com/claude) by Anthropic. All project direction, requirements, and intellectual authorship remain the work of the repository author and are governed by the project's license.

---

> *Built for anyone who's ever SSH'd into a training run at 2 AM wondering if the GPU is on fire.*
