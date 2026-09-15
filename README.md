# 🖥️ Server Monitor

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
| Service management | Docker Compose (systemd unit also available — see Quick start) |
| Remote access | [Tailscale](https://tailscale.com) MagicDNS / fixed IP |

The dashboard keeps the last **60 samples** (5 minutes at 5 s/poll) in memory and redraws all charts on every update and on window resize.

---

## 📋 Prerequisites

- `lm-sensors` installed and configured on the **host** (`sudo sensors-detect`) — this populates `/sys/class/hwmon`, which the container reads read-only regardless of which install method you use below
- NVIDIA drivers on the host (for GPU metrics)
- Tailscale installed on both server and client (for remote access)

**Docker install additionally needs:** Docker Engine + Compose plugin, and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) configured for Docker.

**Manual install additionally needs:** Python 3.10+.

---

## 🚀 Quick start

### Docker (recommended — this is how the author runs it)

```bash
# Clone / copy the project
git clone <your-repo-url> /opt/server-monitor
cd /opt/server-monitor

docker compose up -d --build
```

```bash
# Check status
docker compose ps

# Follow logs
docker compose logs -f
```

The container uses `network_mode: host` (see `docker-compose.yaml`) so it can read the host's real network interfaces rather than a virtual one — `ports:` is not used, and the dashboard is reachable directly at `http://<host-ip>:9090` once the container is up. GPU access is provided via the NVIDIA Container Toolkit; `/dev/dri` is also passed through for a possible future Intel iGPU metrics path, though nothing reads it yet.

To update after pulling new code:

```bash
git pull
docker compose up -d --build
```

### Alternative: run without Docker

Prefer a plain systemd service instead of a container:

```bash
# Clone / copy the project
sudo cp -r server-monitor/ /opt/server-monitor
cd /opt/server-monitor

# Create a virtual environment
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Run it directly:

```bash
source /opt/server-monitor/venv/bin/activate
python3 monitor_server.py
# → http://localhost:9090
```

Or install it as a systemd service (auto-start on boot):

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

The page can be installed as an app (Chrome's "Install as app" / Android and iOS "Add to Home Screen") and will use its own icon rather than a generic one, via `static/manifest.json`.

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
├── generate_icons.py          # Regenerates the icon set below from the same design
├── Dockerfile                 # NVIDIA CUDA base image (Blackwell needs CUDA 12.8+)
├── docker-compose.yaml        # GPU passthrough, host networking, sensor mount
├── .dockerignore
├── static/
│   ├── index.html             # Dashboard (HTML + CSS + JS, single file)
│   ├── manifest.json          # Lets "Install as app" / "Add to Home Screen" use a real icon
│   ├── favicon.ico            # Tab-icon fallback for browsers without SVG favicon support
│   ├── icon-192.png
│   ├── icon-512.png
│   └── apple-touch-icon.png
├── systemd/
│   └── server-monitor.service # Alternative to Docker: a plain systemd unit
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
| CPU priority | idle (`SCHED_IDLE`), self-applied at startup |
| I/O priority | idle (`IOPRIO_CLASS_IDLE`), self-applied at startup |

The OS will preempt the monitor process instantly in favor of any real workload — regardless of whether it's running under Docker, systemd, or started by hand, since the process requests idle priority for itself rather than relying on the launcher to set it (see `_lower_own_priority()` in `monitor_server.py`). The systemd unit's own `CPUSchedulingPolicy=idle` / `IOSchedulingClass=idle` are harmless alongside this — asking twice for the same thing — kept there for anyone reading the unit file who wants the guarantee spelled out at that layer too.

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
