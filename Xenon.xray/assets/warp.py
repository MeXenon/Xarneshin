#!/usr/bin/env python3
import os
import sys
import platform
import subprocess
import requests
import json
import re
import stat
import time

VERSION = "2.2.24"

def get_asset_name():
    sysname = platform.system()
    machine = platform.machine()
    arch_map = {
        "x86_64": "amd64",
        "AMD64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
        "armv7l": "armv7",
        "i386": "386",
        "i686": "386",
    }
    if sysname == "Linux":
        os_part = "linux"
    elif sysname == "Darwin":
        os_part = "darwin"
    elif sysname == "Windows":
        os_part = "windows"
    else:
        sys.exit(1)
    arch = arch_map.get(machine, "amd64")
    asset = f"wgcf_{VERSION}_{os_part}_{arch}"
    if sysname == "Windows":
        asset += ".exe"
    return asset

def download_wgcf(bin_path):
    asset = get_asset_name()
    url = f"https://github.com/ViRb3/wgcf/releases/download/v{VERSION}/{asset}"
    try:
        r = requests.get(url, stream=True)
    except Exception:
        sys.exit(1)
    if r.status_code != 200:
        sys.exit(1)
    with open(bin_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    if platform.system() != "Windows":
        os.chmod(bin_path, os.stat(bin_path).st_mode | stat.S_IEXEC)

def run_cmd(cmd, binary):
    full_cmd = f"{binary} {cmd}"
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(1)
    return result.stdout.strip()

def remove_old_configs():
    for f in ["wgcf-account.toml", "wgcf-profile.conf"]:
        if os.path.exists(f):
            os.remove(f)

def parse_wgcf_profile(conf_path="wgcf-profile.conf"):
    if not os.path.exists(conf_path):
        sys.exit(1)
    conf = {}
    current_section = None
    with open(conf_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
                conf[current_section] = {}
            elif "=" in line and current_section:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key in ["Address", "AllowedIPs"]:
                    if "," in value:
                        value = [v.strip() for v in value.split(",")]
                    else:
                        value = [value]
                conf[current_section][key] = value
    return conf

def build_xray_outbound(conf):
    iface = conf.get("Interface", {})
    peer = conf.get("Peer", {})
    secretKey = iface.get("PrivateKey", "")
    addresses = iface.get("Address", [])
    warp_pubkey = peer.get("PublicKey", "")
    allowed_ips = peer.get("AllowedIPs", [])
    endpoint = peer.get("Endpoint", "")
    try:
        mtu = int(iface.get("MTU", "1280"))
    except:
        mtu = 1280
    return {
        "tag": "Warp",
        "protocol": "wireguard",
        "settings": {
            "mtu": mtu,
            "secretKey": secretKey,
            "address": addresses,
            "workers": 4,
            "domainStrategy": "ForceIPv4",
            "reserved": [],
            "peers": [
                {
                    "publicKey": warp_pubkey,
                    "allowedIPs": allowed_ips,
                    "endpoint": endpoint,
                    "keepAlive": 0
                }
            ],
            "noKernelTun": False
        }
    }

def main():
    if platform.system() == "Windows":
        binary = "wgcf.exe"
        bin_path = binary
    else:
        binary = "./wgcf"
        bin_path = "wgcf"
    if not os.path.exists(bin_path):
        download_wgcf(bin_path)
    remove_old_configs()
    run_cmd("register --accept-tos", binary)
    run_cmd("generate", binary)
    time.sleep(1)
    conf = parse_wgcf_profile("wgcf-profile.conf")
    if "Peer" not in conf or "PublicKey" not in conf["Peer"]:
        sys.exit(1)
    outbound = build_xray_outbound(conf)
    print(json.dumps(outbound, indent=2))

if __name__ == "__main__":
    main()
