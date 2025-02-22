#!/bin/bash
# Xcore chngr
if [ "$EUID" -ne 0 ]; then
  echo '{"status": "error", "message": "Please run as root."}' > /dev/stdout
  exit 1
fi

if [ "$#" -lt 1 ]; then
  echo '{"status": "error", "message": "Usage: xrayc.sh -list <n> OR xrayc.sh v<version>"}' > /dev/stdout
  exit 1
fi

# Handle -list command
if [ "$1" = "-list" ]; then
  if [ "$#" -ne 2 ]; then
    echo '{"status": "error", "message": "Usage: xrayc.sh -list <n>"}' > /dev/stdout
    exit 1
  fi
  count="$2"
  if ! [[ "$count" =~ ^[0-9]+$ ]]; then
    echo '{"status": "error", "message": "List count must be an integer."}' > /dev/stdout
    exit 1
  fi
  if ! command -v jq >/dev/null 2>&1; then
    apt-get update >/dev/null && apt-get install -y jq >/dev/null
  fi
  releases_json=$(curl -s https://api.github.com/repos/XTLS/Xray-core/releases)
  echo "$releases_json" | jq -r 'map(select(.prerelease==false and .draft==false)) | .[].tag_name' | head -n "$count"
  exit 0
fi

# Update command with version
selected_version="$1"
if [[ ! "$selected_version" =~ ^v ]]; then
  echo '{"status": "error", "message": "Version must start with '\''v'\'' (e.g., v1.8.23)."}' > /dev/stdout
  exit 1
fi

# Progress message function with timestamp, explicit flush, and adjustable delay
progress() {
  local timestamp=$(date +%s.%N)
  stdbuf -oL echo "{\"progress\": $1, \"message\": \"$2\", \"timestamp\": \"$timestamp\"}" > /dev/stdout
  sync  
  sleep 0.5  
}

export LC_ALL=C
export PYTHONUNBUFFERED=1

# Det CPU architecture
arch=$(uname -m)
if [[ "$arch" == "x86_64" ]]; then
  file_name="Xray-linux-64.zip"
elif [[ "$arch" == "aarch64" || "$arch" == "arm64" ]]; then
  file_name="Xray-linux-arm64.zip"
else
  echo '{"status": "error", "message": "Unsupported CPU architecture."}' > /dev/stdout
  exit 1
fi

progress 10 "Initializing update for Xray core $selected_version..."

# Prep directory
progress 15 "Preparing working directory..."
mkdir -p /var/lib/marznode/data
cd /var/lib/marznode/data || { echo '{"status": "error", "message": "Cannot change directory."}' > /dev/stdout; exit 1; }

# C/D tools (unzip and wget)
progress 20 "Checking required tools..."
tools_missing=false
if command -v unzip >/dev/null 2>&1; then
  progress 22 "unzip is already installed, skipping..."
else
  tools_missing=true
fi
if command -v wget >/dev/null 2>&1; then
  progress 24 "wget is already installed, skipping..."
else
  tools_missing=true
fi

if [ "$tools_missing" = true ]; then
  progress 25 "Installing missing tools (unzip, wget)..."
  apt-get update >/dev/null
  [ ! "$(command -v unzip)" ] && apt-get install -y unzip >/dev/null
  [ ! "$(command -v wget)" ] && apt-get install -y wget >/dev/null
else
  progress 25 "All required tools are present, proceeding..."
fi

# Download Xray core
download_url="https://github.com/XTLS/Xray-core/releases/download/${selected_version}/${file_name}"
progress 30 "Downloading $file_name..."
wget -q "$download_url" -O "$file_name" 2>/dev/null
if [ $? -ne 0 ]; then
  echo '{"status": "error", "message": "Download failed."}' > /dev/stdout
  exit 1
fi

progress 40 "Extracting $file_name..."
unzip -o "$file_name" >/dev/null && rm -f "$file_name"
if [ ! -f "xray" ]; then
  echo '{"status": "error", "message": "xray binary not found after unzipping."}' > /dev/stdout
  exit 1
fi

start_time=$(date +%s)
progress 60 "Updating xray binary..."
if ! cp xray /var/lib/marznode/xray 2> cp_err.log; then
  if grep -q "Text file busy" cp_err.log; then
    progress 65 "xray binary is busy, stopping services..."
    marzneshin down >/dev/null 2>&1
    sleep 2
    progress 70 "Force-killing processes using xray..."
    fuser -k /var/lib/marznode/xray >/dev/null 2>&1
    sleep 2
    cp xray /var/lib/marznode/xray 2> cp_err.log || { echo '{"status": "error", "message": "Failed to update xray binary after forced termination."}' > /dev/stdout; rm -f cp_err.log; exit 1; }
  else
    err_msg=$(cat cp_err.log)
    rm -f cp_err.log
    echo "{\"status\": \"error\", \"message\": \"cp error: $err_msg\"}" > /dev/stdout
    exit 1
  fi
fi
rm -f cp_err.log
chmod +x /var/lib/marznode/xray

# Update d-compose
docker_compose_file="/etc/opt/marzneshin/docker-compose.yml"
if [ ! -f "$docker_compose_file" ]; then
  echo '{"status": "error", "message": "docker-compose file not found."}' > /dev/stdout
  exit 1
fi

progress 80 "Updating docker-compose configuration..."
sed -i '/^  marznode:/,/^  [^ ]/{
/XRAY_ASSETS_PATH:/d
/XRAY_EXECUTABLE_PATH:/d
}' "$docker_compose_file"

sed -i '/^  marznode:/,/^  [^ ]/{
/^    environment:/a\
      XRAY_EXECUTABLE_PATH: "/var/lib/marznode/xray"\
      XRAY_ASSETS_PATH: "/var/lib/marznode/data"
}' "$docker_compose_file"

# Restart services
progress 90 "Restarting marzneshin services..."
temp_log=$(mktemp)
marzneshin restart > "$temp_log" 2>&1 &
restart_pid=$!
while true; do
  if grep -q "INFO:     Uvicorn running on https://0.0.0.0:8000" "$temp_log"; then
    break
  fi
  sleep 1
done
end_time=$(date +%s)
kill $restart_pid 2>/dev/null
duration=$((end_time - start_time))
rm -f "$temp_log"

progress 100 "Core update completed."
stdbuf -oL echo "{\"status\": \"success\", \"done\": true, \"duration\": $duration}" > /dev/stdout
sync  
exit 0