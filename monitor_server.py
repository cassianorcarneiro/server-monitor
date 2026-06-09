#!/usr/bin/env python3
"""
Server Hardware Monitor - Backend
Lightweight metrics server using aiohttp + psutil + nvidia-smi
"""

import asyncio
import json
import subprocess
import time
import os
from pathlib import Path
from datetime import datetime
from aiohttp import web
import psutil

# ── Configuration ────────────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 9090
CORS_ORIGIN = "*"           # Restrict to your Tailscale CIDR if desired
STATIC_DIR = Path(__file__).parent / "static"

# ── Network rate state ───────────────────────────────────────────────────────
# Guarda a última leitura para calcular taxa (KB/s) entre chamadas.
_net_last: dict = {}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: list[str]) -> str | None:
    """Run a subprocess safely; return stdout or None on error."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=3
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def get_cpu_metrics() -> dict:
    freq = psutil.cpu_freq()
    temps = {}
    try:
        sensor_data = psutil.sensors_temperatures()
        for name, entries in sensor_data.items():
            for e in entries:
                label = e.label or name
                if label not in temps or e.current > temps[label]:
                    temps[label] = round(e.current, 1)
    except Exception:
        pass

    return {
        "usage_percent": psutil.cpu_percent(interval=None),
        "usage_per_core": psutil.cpu_percent(interval=None, percpu=True),
        "freq_current_mhz": round(freq.current, 0) if freq else None,
        "freq_max_mhz": round(freq.max, 0) if freq else None,
        "count_logical": psutil.cpu_count(logical=True),
        "count_physical": psutil.cpu_count(logical=False),
        "temperatures": temps,
    }


def get_memory_metrics() -> dict:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        "total_gb": round(vm.total / 1e9, 2),
        "used_gb": round(vm.used / 1e9, 2),
        "available_gb": round(vm.available / 1e9, 2),
        "percent": vm.percent,
        "swap_total_gb": round(sw.total / 1e9, 2),
        "swap_used_gb": round(sw.used / 1e9, 2),
        "swap_percent": sw.percent,
    }


def get_disk_metrics() -> list[dict]:
    # Dentro de um container Docker o disco raiz aparece como fstype='overlay'.
    # Usamos all=True para que ele seja incluído, mas bloqueamos overlay em
    # qualquer outro mountpoint (são artefatos do runtime do container).
    SKIP_FSTYPES = {
        "tmpfs", "devtmpfs", "devpts", "sysfs", "proc",
        "cgroup", "cgroup2", "pstore", "securityfs", "debugfs",
        "tracefs", "hugetlbfs", "mqueue", "nsfs", "bpf",
        "fusectl", "fuse", "squashfs", "ramfs",
    }

    seen_devices: set[str] = set()
    disks = []

    for part in psutil.disk_partitions(all=True):
        mp = part.mountpoint

        # overlay só é válido no mountpoint raiz do container
        if part.fstype == "overlay" and mp != "/":
            continue

        # ignorar filesystems virtuais/especiais
        if part.fstype in SKIP_FSTYPES:
            continue

        # mountpoint deve ser um diretório (bind-mounts de .so são arquivos)
        if not os.path.isdir(mp):
            continue

        # desduplicar por device (mesmo LV montado em vários pontos)
        dev = part.device
        if dev in seen_devices:
            continue
        seen_devices.add(dev)

        try:
            usage = psutil.disk_usage(mp)
        except (PermissionError, OSError):
            continue

        # ignorar partições menores que 1 MB (artefatos de container / EFI vars)
        if usage.total < 1_000_000:
            continue

        disks.append({
            "device": dev,
            "mountpoint": mp,
            "fstype": part.fstype,
            "total_gb": round(usage.total / 1e9, 2),
            "used_gb": round(usage.used / 1e9, 2),
            "free_gb": round(usage.free / 1e9, 2),
            "percent": usage.percent,
        })

    return disks


def get_network_metrics() -> dict:
    global _net_last
    net = psutil.net_io_counters()
    now = time.time()

    if _net_last:
        dt = max(now - _net_last["ts"], 0.001)  # evita divisão por zero
        sent_kbps = max(round((net.bytes_sent - _net_last["sent"]) / dt / 1024, 2), 0.0)
        recv_kbps = max(round((net.bytes_recv - _net_last["recv"]) / dt / 1024, 2), 0.0)
    else:
        # Primeira leitura: ainda não há intervalo para calcular taxa
        sent_kbps = 0.0
        recv_kbps = 0.0

    _net_last = {"ts": now, "sent": net.bytes_sent, "recv": net.bytes_recv}

    return {
        "sent_kbps": sent_kbps,
        "recv_kbps": recv_kbps,
        "bytes_sent_total_mb": round(net.bytes_sent / 1e6, 2),
        "bytes_recv_total_mb": round(net.bytes_recv / 1e6, 2),
        "packets_sent": net.packets_sent,
        "packets_recv": net.packets_recv,
    }


def get_gpu_metrics() -> list[dict] | None:
    """Query NVIDIA GPU stats via nvidia-smi."""
    query = (
        "index,name,temperature.gpu,utilization.gpu,"
        "utilization.memory,memory.total,memory.used,memory.free,"
        "power.draw,power.limit,fan.speed,clocks.current.graphics,clocks.current.memory"
    )
    out = _run([
        "nvidia-smi",
        f"--query-gpu={query}",
        "--format=csv,noheader,nounits",
    ])
    if not out:
        return None

    gpus = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 13:
            continue

        def safe_float(v):
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        gpus.append({
            "index": int(parts[0]),
            "name": parts[1],
            "temperature_c": safe_float(parts[2]),
            "utilization_gpu_pct": safe_float(parts[3]),
            "utilization_memory_pct": safe_float(parts[4]),
            "memory_total_mb": safe_float(parts[5]),
            "memory_used_mb": safe_float(parts[6]),
            "memory_free_mb": safe_float(parts[7]),
            "power_draw_w": safe_float(parts[8]),
            "power_limit_w": safe_float(parts[9]),
            "fan_speed_pct": safe_float(parts[10]),
            "clock_graphics_mhz": safe_float(parts[11]),
            "clock_memory_mhz": safe_float(parts[12]),
        })
    return gpus if gpus else None


def get_uptime() -> dict:
    boot = psutil.boot_time()
    uptime_s = time.time() - boot
    days = int(uptime_s // 86400)
    hours = int((uptime_s % 86400) // 3600)
    minutes = int((uptime_s % 3600) // 60)
    return {
        "boot_timestamp": boot,
        "uptime_seconds": int(uptime_s),
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "human": f"{days}d {hours}h {minutes}m",
    }


def get_load_average() -> dict:
    load = os.getloadavg()
    return {
        "1min": round(load[0], 2),
        "5min": round(load[1], 2),
        "15min": round(load[2], 2),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

async def handle_metrics(request: web.Request) -> web.Response:
    """Main metrics endpoint — called every 5 s by the dashboard."""
    payload = {
        "timestamp": datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"),
        "timestamp_unix": time.time(),
        "cpu": get_cpu_metrics(),
        "memory": get_memory_metrics(),
        "disks": get_disk_metrics(),
        "network": get_network_metrics(),
        "gpu": get_gpu_metrics(),
        "uptime": get_uptime(),
        "load_average": get_load_average(),
    }
    return web.Response(
        text=json.dumps(payload),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": CORS_ORIGIN},
    )


async def handle_index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text='{"status":"ok"}', content_type="application/json")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/metrics", handle_metrics)
    app.router.add_get("/health", handle_health)
    app.router.add_static("/static", STATIC_DIR, show_index=False)
    return app


if __name__ == "__main__":
    print(f"[monitor] Starting on http://{HOST}:{PORT}")
    app = create_app()
    # Warm up cpu_percent (first call always returns 0.0)
    psutil.cpu_percent(interval=0.1)
    web.run_app(app, host=HOST, port=PORT, access_log=None)
