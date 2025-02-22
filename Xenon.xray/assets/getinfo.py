#!/usr/bin/env python3
"""
this is gonna get overview's information:)
"""

from flask import Blueprint, jsonify, request, session
import subprocess
import re
import datetime
import json
import asyncio
import websockets
import time
import psutil

getinfo_bp = Blueprint('getinfo', __name__, url_prefix='/getinfo')

def run_command(command):
    try:
        output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
        return output.decode('utf-8').strip(), None
    except subprocess.CalledProcessError as e:
        return None, e.output.decode('utf-8').strip()

def format_timedelta(td):
    total_seconds = int(td.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hr{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} min{'s' if minutes != 1 else ''}")
    if seconds or not parts:
        parts.append(f"{seconds} s")
    return " ".join(parts)

@getinfo_bp.route('/container/<container_name>/uptime', methods=['GET'])
def container_uptime(container_name):
    command = f"docker inspect --format='{{{{.State.StartedAt}}}}' {container_name}"
    output, error = run_command(command)
    if error:
        return jsonify({"error": f"Error getting uptime for container '{container_name}': {error}"}), 500
    try:
        started_at_str = output.strip("'").rstrip("Z")
        if '.' in started_at_str:
            date_part, frac = started_at_str.split('.')
            frac = frac[:6]
            started_at_str = f"{date_part}.{frac}"
        started_at = datetime.datetime.fromisoformat(started_at_str)
        now = datetime.datetime.utcnow()
        uptime = now - started_at
        return jsonify({
            "container": container_name,
            "started_at": output,
            "uptime_seconds": int(uptime.total_seconds()),
            "uptime_formatted": format_timedelta(uptime)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@getinfo_bp.route('/full-uptime', methods=['GET'])
def full_uptime():
    container_names = ["marzneshin-marznode-1", "marzneshin-marzneshin-1", "marzneshin-db-1"]
    start_times = []
    for name in container_names:
        command = f"docker inspect --format='{{{{.State.StartedAt}}}}' {name}"
        output, error = run_command(command)
        if error:
            continue
        try:
            ts_str = output.strip("'").rstrip("Z")
            if '.' in ts_str:
                date_part, frac = ts_str.split('.')
                frac = frac[:6]
                ts_str = f"{date_part}.{frac}"
            started_at = datetime.datetime.fromisoformat(ts_str)
            start_times.append(started_at)
        except Exception:
            continue
    if not start_times:
        return jsonify({
            "earliest_start": "",
            "full_uptime_seconds": 0,
            "full_uptime_formatted": "0 s"
        })
    earliest = min(start_times)
    now = datetime.datetime.utcnow()
    uptime = now - earliest
    return jsonify({
        "earliest_start": earliest.isoformat() + "Z",
        "full_uptime_seconds": int(uptime.total_seconds()),
        "full_uptime_formatted": format_timedelta(uptime)
    })

async def get_latest_xray_started(uri, timeout=2):
    latest = None
    try:
        async with websockets.connect(uri) as websocket:
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                    if "Xray" in msg and "started" in msg:
                        latest = msg
                except asyncio.TimeoutError:
                    break
    except Exception as e:
        raise e
    return latest

@getinfo_bp.route('/xray-uptime', methods=['GET'])
def xray_uptime():

    node_id = request.args.get("node_id", "1")
    token = session.get("token")
    if not token:
        return jsonify({"error": "No token found in session"}), 401
    ws_uri = f"ws://127.0.0.1:8000/api/nodes/{node_id}/xray/logs?interval=1&token={token}"
    try:
        latest_message = asyncio.run(get_latest_xray_started(ws_uri))
        if not latest_message:
            return jsonify({"error": "No Xray startup message found via websocket"}), 500
        match = re.search(r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+).*Xray.*started', latest_message)
        if not match:
            return jsonify({"error": "Could not parse timestamp from startup message"}), 500
        timestamp_str = match.group(1)
        core_start = datetime.datetime.strptime(timestamp_str, "%Y/%m/%d %H:%M:%S.%f")
        now = datetime.datetime.utcnow()
        uptime = now - core_start
        return jsonify({
            "xray_start": core_start.isoformat() + "Z",
            "xray_uptime_seconds": int(uptime.total_seconds()),
            "xray_uptime": format_timedelta(uptime)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@getinfo_bp.route('/system-usage', methods=['GET'])
def system_usage():
    try:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory().percent
        swap = psutil.swap_memory().percent
        disk = psutil.disk_usage('/').percent
        return jsonify({
            "cpu_percent": cpu,
            "memory_percent": memory,
            "swap_percent": swap,
            "disk_percent": disk
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@getinfo_bp.route('/os-uptime', methods=['GET'])
def os_uptime():
    try:
        boot_time = psutil.boot_time()
        now = time.time()
        uptime_seconds = int(now - boot_time)
        uptime = datetime.timedelta(seconds=uptime_seconds)
        return jsonify({
            "os_uptime_seconds": uptime_seconds,
            "os_uptime_formatted": format_timedelta(uptime)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@getinfo_bp.route('/network-stats', methods=['GET'])
def network_stats():
    try:
        initial = psutil.net_io_counters()
        time.sleep(1)
        final = psutil.net_io_counters()
        upload_speed = final.bytes_sent - initial.bytes_sent
        download_speed = final.bytes_recv - initial.bytes_recv
        total = psutil.net_io_counters()
        tcp_connections = len(psutil.net_connections(kind='tcp'))
        udp_connections = len(psutil.net_connections(kind='udp'))
        
        # Retrieve only the primary global IP addresses using external lookup
        ipv4, ipv4_error = run_command("curl -4 -s ifconfig.me")
        ipv6, ipv6_error = run_command("curl -6 -s ifconfig.me")
        if ipv4_error:
            ipv4 = None
        if ipv6_error:
            ipv6 = None

        return jsonify({
            "upload_speed_bps": upload_speed,
            "download_speed_bps": download_speed,
            "total_bytes_sent": total.bytes_sent,
            "total_bytes_recv": total.bytes_recv,
            "tcp_connections": tcp_connections,
            "udp_connections": udp_connections,
            "ipv4": ipv4,
            "ipv6": ipv6
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@getinfo_bp.route('/container/<container_name>/restart', methods=['POST'])
def restart_container(container_name):
    command = f"docker restart {container_name}"
    output, error = run_command(command)
    if error:
        return jsonify({"error": f"Error restarting container '{container_name}': {error}"}), 500
    return jsonify({
        "message": f"Container '{container_name}' restarted successfully.",
        "output": output
    })

@getinfo_bp.route('/full-restart', methods=['POST'])
def full_restart():
    command = "marzneshin restart"
    output, error = run_command(command)
    if error:
        return jsonify({"error": f"Error performing full restart: {error}"}), 500
    container = "marzneshin-marzneshin-1"
    expected_pattern = r"INFO:\s+Uvicorn running on http://"
    timeout = 60  # seconds
    start_time = datetime.datetime.utcnow()
    while True:
        logs, err = run_command(f"docker logs {container} --tail 100")
        if logs and re.search(expected_pattern, logs):
            break
        if (datetime.datetime.utcnow() - start_time).total_seconds() > timeout:
            return jsonify({"error": "Timeout waiting for Uvicorn startup log"}), 500
        time.sleep(2)
    return jsonify({
        "message": "Full Marzneshin stack restarted successfully.",
        "output": output
    })
