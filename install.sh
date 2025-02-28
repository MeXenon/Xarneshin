#!/usr/bin/env bash

###############################################################################
#                           ANSI COLOR CONSTANTS                              #
###############################################################################
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
CYAN='\033[0;36m'
NC='\033[0m'

###############################################################################
#                         GLOBAL VARS & FILE PATHS                            #
###############################################################################
INSTALL_DIR="/opt/Xenon.xray"
SOURCE_DIR="/root/Xenon.xray"
ENV_FILE="/etc/opt/marzneshin/.env"
SERVICE_FILE="/etc/systemd/system/xarneshin.service"
CLI_PATH="/usr/local/bin/xarneshin"
PORTS_FILE="$INSTALL_DIR/ports.json"
LOG_FILE="/tmp/xarneshin_install.log"

###############################################################################
#                            SPINNER FUNCTION                                #
###############################################################################
spinner() {
  local pid="$1"
  local spin='-\|/'
  local i=0
  while kill -0 "$pid" 2>/dev/null; do
    i=$(( (i+1) % 4 ))
    printf "\r${CYAN}[Action]${NC} ${GREEN}Installing...${NC} ${spin:$i:1} Please wait..."
    sleep 0.15
  done
  printf "\r\033[K" # Clear the line after spinner stops
}

###############################################################################
#                              CHECK FOR ROOT                                 #
###############################################################################
if [[ $EUID -ne 0 ]]; then
  echo -e "${RED}ERROR: Must run as root.${NC}"
  exit 1
fi

echo -e "${CYAN}[Action]${NC} ${GREEN}Performing initial setup...${NC}"
echo -e "  - Making files ready..."

###############################################################################
#                MOVE /root/Xenon.xray -> /opt/Xenon.xray IF FIRST RUN        #
###############################################################################
if [[ -d "$SOURCE_DIR" && ! -d "$INSTALL_DIR" ]]; then
  mv "$SOURCE_DIR" "$INSTALL_DIR"
  chmod +x "$INSTALL_DIR/assets/xrayc.sh"
elif [[ ! -d "$INSTALL_DIR" ]]; then
  echo -e "${RED}No directory found at $SOURCE_DIR or $INSTALL_DIR. Exiting.${NC}"
  exit 1
fi

###############################################################################
#           INSTALL PYTHON + DEPENDENCIES                                      #
###############################################################################
echo -e "${CYAN}[Action]${NC} ${GREEN}Installing Python and dependencies...${NC}"
echo "Installation logs will be saved to $LOG_FILE"

# Step 1: Try minimal installation
{
  echo -e "  - Attempting minimal installation..." >> "$LOG_FILE"
  apt-get update -y >> "$LOG_FILE" 2>&1 || {
    echo -e "${RED}Failed to update package lists. Check $LOG_FILE for details.${NC}"
    exit 1
  }
  apt-get install -y python3 python3-pip curl jq >> "$LOG_FILE" 2>&1 || {
    echo -e "${RED}Failed to install base packages (python3, pip3, curl, jq). Check $LOG_FILE for details.${NC}"
    exit 1
  }
  pip3 install flask requests cryptography websockets psutil blinker >> "$LOG_FILE" 2>&1
} &
bg_pid=$!
spinner "$bg_pid"
wait "$bg_pid"

if [[ $? -ne 0 ]]; then
  echo -e "  - Minimal installation failed, attempting robust fallback..."
  # Step 2: Robust fallback
  {
    echo -e "  - Starting robust fallback..." >> "$LOG_FILE"
    apt-get update -y && apt-get upgrade -y >> "$LOG_FILE" 2>&1 || {
      echo -e "${RED}Failed to update/upgrade system packages in fallback. Check $LOG_FILE.${NC}"
      exit 1
    }
    apt-get install -y python3-pip python3-dev python3-venv build-essential libssl-dev libffi-dev python3-setuptools >> "$LOG_FILE" 2>&1 || {
      echo -e "${RED}Failed to install development packages in fallback. Check $LOG_FILE.${NC}"
      exit 1
    }
    apt-get purge -y python3-blinker >> "$LOG_FILE" 2>&1 || {
      echo -e "${YELLOW}Warning: Could not purge python3-blinker, continuing anyway...${NC}" | tee -a "$LOG_FILE"
    }
    pip3 install --break-system-packages flask requests cryptography websockets psutil blinker >> "$LOG_FILE" 2>&1 || {
      echo -e "${RED}Failed to install Python dependencies even with robust fallback. Check $LOG_FILE for details.${NC}"
      exit 1
    }
  } &
  bg_pid=$!
  spinner "$bg_pid"
  wait "$bg_pid"
  if [[ $? -eq 0 ]]; then
    echo -e "  - Successfully installed dependencies using robust fallback method."
  fi
else
  echo -e "  - Successfully installed dependencies with minimal method."
fi

echo -e "  - Done installing dependencies."

###############################################################################
#                    DETERMINE MARZNESHIN PANEL PORT & PROTOCOL              #
###############################################################################
echo -e "\n${CYAN}[Action]${NC} ${GREEN}Determining main panel settings from $ENV_FILE...${NC}"
PANEL_PORT_DEFAULT=8000
panel_use_https=false

if [[ -f "$ENV_FILE" ]]; then
  raw_port=$(grep '^UVICORN_PORT' "$ENV_FILE" | sed -E 's/.*UVICORN_PORT[[:space:]]*=[[:space:]]*([0-9]+).*/\1/')
  if [[ "$raw_port" =~ ^[0-9]+$ ]]; then
    panel_port="$raw_port"
    echo -e "  - Found Marzneshin's panel port: ${GREEN}$panel_port${NC}"
  else
    panel_port="$PANEL_PORT_DEFAULT"
    echo -e "  - Could not parse UVICORN_PORT. Using default: ${GREEN}$panel_port${NC}"
  fi

  # Check SSL settings
  ssl_cert=$(grep -E "^\s*UVICORN_SSL_CERTFILE\s*=" "$ENV_FILE" | grep -v "^\s*#")
  ssl_key=$(grep -E "^\s*UVICORN_SSL_KEYFILE\s*=" "$ENV_FILE" | grep -v "^\s*#")
  if [[ -n "$ssl_cert" && -n "$ssl_key" ]]; then
    panel_use_https=true
    echo -e "  - Detected HTTPS for panel (SSL cert and key present)"
  else
    echo -e "  - No SSL settings found. Using HTTP for panel"
  fi
else
  panel_port="$PANEL_PORT_DEFAULT"
  echo -e "  - No .env found. Using default panel port: ${GREEN}$panel_port${NC} and HTTP"
fi

###############################################################################
#                     CONFIGURE XARNESHIN FLASK PORT                          #
###############################################################################
echo -e "\n-------- Configuring Flask port"
echo -e "${BLUE}Choose Xarneshin Flask port:${NC}"
echo -e "${GREEN}1${NC}- Set a random port (Recommended)"
echo -e "${GREEN}2${NC}- Set a custom port"
read -p "Please enter your choice [1 or 2, default=2]: " choice
if [[ -z "$choice" ]]; then
  choice=2
fi

if [[ "$choice" == "1" ]]; then
  flask_port=$(( (RANDOM % 45535 ) + 20000 ))
  echo -e "  - Using random port: ${GREEN}$flask_port${NC}"
else
  read -p "Enter custom Flask port: " user_port
  if [[ -z "$user_port" ]]; then
    user_port=42689
  fi
  flask_port="$user_port"
  echo -e "  - Using custom port: ${GREEN}$flask_port${NC}"
fi

mkdir -p "$INSTALL_DIR"

# Write JSON with panel protocol
cat <<EOF > "$PORTS_FILE"
{
  "panel_port": $panel_port,
  "flask_port": $flask_port,
  "panel_use_https": $panel_use_https,
  "use_https": false,
  "domain": "",
  "cert_file": "",
  "key_file": ""
}
EOF

###############################################################################
#                        CREATE SYSTEMD SERVICE                               #
###############################################################################
echo -e "\n${CYAN}[Action]${NC} ${GREEN}Creating systemd service: $SERVICE_FILE...${NC}"

cat << EOF > "$SERVICE_FILE"
[Unit]
Description=Xarneshin Flask App
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/xenon.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xarneshin.service
systemctl restart xarneshin.service

###############################################################################
#                        CREATE XARNESHIN CLI TOOL                            #
###############################################################################
echo -e "${CYAN}[Action]${NC} ${GREEN}Creating Xarneshin CLI tool...${NC}"

cat << 'EOS' > "$CLI_PATH"
#!/usr/bin/env bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
CYAN='\033[0;36m'
NC='\033[0m'

INSTALL_DIR="/opt/Xenon.xray"
PORTS_FILE="$INSTALL_DIR/ports.json"
SERVICE="xarneshin.service"
ENV_FILE="/etc/opt/marzneshin/.env"

declare -A GEOFILES=(
  ["https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat"]="geoip.dat"
  ["https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat"]="geosite.dat"
  ["https://github.com/chocolate4u/Iran-v2ray-rules/releases/latest/download/geoip.dat"]="geoip_IR.dat"
  ["https://github.com/chocolate4u/Iran-v2ray-rules/releases/latest/download/geosite.dat"]="geosite_IR.dat"
  ["https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/geoip.dat"]="geoip_RU.dat"
  ["https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/geosite.dat"]="geosite_RU.dat"
)

function get_ipv4() {
  curl -4 -s ifconfig.me
}

function get_uptime() {
  if ! systemctl is-active --quiet "$SERVICE"; then
    echo "N/A"
    return
  fi
  local start_ts=$(systemctl show "$SERVICE" -p ActiveEnterTimestamp --value)
  if [[ -z "$start_ts" ]]; then
    echo "N/A"
    return
  fi
  local start_sec=$(date -d "$start_ts" +%s 2>/dev/null)
  local now_sec=$(date +%s)
  if [[ -z "$start_sec" || "$start_sec" -gt "$now_sec" ]]; then
    echo "N/A"
    return
  fi
  local diff=$(( now_sec - start_sec ))
  local dd=$(( diff / 86400 ))
  local rr=$(( diff % 86400 ))
  local hh=$(( rr / 3600 ))
  rr=$(( rr % 3600 ))
  local mm=$(( rr / 60 ))
  local ss=$(( rr % 60 ))
  local out=""
  if [[ $dd -gt 0 ]]; then out+="${dd}d,"; fi
  if [[ $hh -gt 0 ]]; then out+="${hh}h,"; fi
  if [[ $mm -gt 0 ]]; then out+="${mm}m,"; fi
  out+="${ss}s"
  echo "$out"
}

function get_mode() {
  if [[ ! -f "$PORTS_FILE" ]]; then
    echo "Unknown"
    return
  fi
  local use_https=$(jq -r '.use_https' "$PORTS_FILE" 2>/dev/null)
  if [[ "$use_https" == "true" ]]; then
    echo "HTTPS"
  else
    echo "HTTP"
  fi
}

function get_panel_mode() {
  if [[ ! -f "$PORTS_FILE" ]]; then
    echo "Unknown"
    return
  fi
  local panel_use_https=$(jq -r '.panel_use_https' "$PORTS_FILE" 2>/dev/null)
  if [[ "$panel_use_https" == "true" ]]; then
    echo "HTTPS"
  else
    echo "HTTP"
  fi
}

function short_status() {
  systemctl is-active --quiet "$SERVICE"
  local active=$?
  local status_str
  if [[ $active -eq 0 ]]; then
    status_str="${GREEN}Running${NC}"
  else
    status_str="${RED}Not Running${NC}"
  fi
  local up=$(get_uptime)
  local mode=$(get_mode)
  local panel_mode=$(get_panel_mode)
  echo -e "${GREEN}Xarneshin Manager${NC}"
  echo -e "Xarneshin Mode Protocol:  [${CYAN}$mode${NC}]"
  echo -e "Marzneshin Mode Protocol: [${CYAN}$panel_mode${NC}]"
  echo -e "Status:                   [${status_str}]"
  echo -e "Uptime:                   [${CYAN}$up${NC}]"
}

function detail_status() {
  systemctl status "$SERVICE" --no-pager
}

function show_access_address() {
  if [[ ! -f "$PORTS_FILE" ]]; then
    echo -e "${RED}ports.json not found!${NC}"
    return
  fi
  local flask_port=$(jq -r '.flask_port' "$PORTS_FILE")
  local use_https=$(jq -r '.use_https' "$PORTS_FILE")
  local domain=$(jq -r '.domain' "$PORTS_FILE")
  local ip4=$(get_ipv4)
  local proto="http"
  local host="$ip4"
  if [[ "$use_https" == "true" && -n "$domain" ]]; then
    proto="https"
    host="$domain"
  fi
  if [[ -z "$ip4" ]]; then
    echo -e "${YELLOW}Cannot detect IPv4 automatically.${NC}"
  else
    echo -e "${GREEN}Access URL:${NC} $proto://$host:$flask_port"
  fi
}

function change_ports_submenu() {
  while true; do
    echo -e "${BLUE}\nChange Ports${NC}"
    echo -e "${GREEN}0)${NC} Back"
    echo -e "${GREEN}1)${NC} Automatically fetch Marzneshin panel port from .env"
    echo -e "${GREEN}2)${NC} Change Xarneshin Flask port"
    read -p "Choose [0-2, default=2]: " cchoice
    if [[ -z "$cchoice" ]]; then
      cchoice=2
    fi
    case "$cchoice" in
      0) return ;;
      1)
        if [[ ! -f "$ENV_FILE" ]]; then
          echo -e "${RED}$ENV_FILE not found!${NC}"
          continue
        fi
        local raw_port=$(grep '^UVICORN_PORT' "$ENV_FILE" | sed -E 's/.*UVICORN_PORT[[:space:]]*=[[:space:]]*([0-9]+).*/\1/')
        if [[ "$raw_port" =~ ^[0-9]+$ ]]; then
          local cur_flask_port=$(jq -r '.flask_port' "$PORTS_FILE")
          local use_https=$(jq -r '.use_https' "$PORTS_FILE")
          local panel_use_https=$(jq -r '.panel_use_https' "$PORTS_FILE")
          local domain=$(jq -r '.domain' "$PORTS_FILE")
          local cert_file=$(jq -r '.cert_file' "$PORTS_FILE")
          local key_file=$(jq -r '.key_file' "$PORTS_FILE")
          cat <<EOF > "$PORTS_FILE"
{
  "panel_port": $raw_port,
  "flask_port": $cur_flask_port,
  "panel_use_https": $panel_use_https,
  "use_https": $use_https,
  "domain": "$domain",
  "cert_file": "$cert_file",
  "key_file": "$key_file"
}
EOF
          echo -e "${GREEN}Updated panel_port to $raw_port${NC}"
          systemctl restart "$SERVICE"
        else
          echo -e "${YELLOW}Could not parse UVICORN_PORT from $ENV_FILE${NC}"
        fi
        ;;
      2)
        echo -e "${BLUE}\nChange Xarneshin Flask port${NC}"
        echo -e "${GREEN}0)${NC} Back"
        echo -e "${GREEN}1)${NC} Random port"
        echo -e "${GREEN}2)${NC} Manual port"
        read -p "Choose [0-2, default=2]: " fchoice
        if [[ -z "$fchoice" ]]; then
          fchoice=2
        fi
        case "$fchoice" in
          0) continue ;;
          1)
            local new_flask_port=$(( (RANDOM % 45535 ) + 20000 ))
            echo -e "${GREEN}Random Flask port chosen: $new_flask_port${NC}"
            ;;
          2)
            read -p "Enter Flask port: " new_flask_port
            if [[ ! "$new_flask_port" =~ ^[0-9]+$ ]]; then
              echo -e "${RED}Invalid numeric input.${NC}"
              continue
            fi
            ;;
          *) echo -e "${RED}Invalid choice.${NC}"; continue ;;
        esac
        local cur_panel_port=$(jq -r '.panel_port' "$PORTS_FILE")
        local use_https=$(jq -r '.use_https' "$PORTS_FILE")
        local panel_use_https=$(jq -r '.panel_use_https' "$PORTS_FILE")
        local domain=$(jq -r '.domain' "$PORTS_FILE")
        local cert_file=$(jq -r '.cert_file' "$PORTS_FILE")
        local key_file=$(jq -r '.key_file' "$PORTS_FILE")
        cat <<EOF > "$PORTS_FILE"
{
  "panel_port": $cur_panel_port,
  "flask_port": $new_flask_port,
  "panel_use_https": $panel_use_https,
  "use_https": $use_https,
  "domain": "$domain",
  "cert_file": "$cert_file",
  "key_file": "$key_file"
}
EOF
        echo -e "${GREEN}Flask port changed to $new_flask_port${NC}"
        echo -e "${GREEN}Restarting Xarneshin...${NC}"
        systemctl restart "$SERVICE"
        show_access_address
        ;;
      *) echo -e "${RED}Invalid choice.${NC}" ;;
    esac
  done
}

function change_panel_protocol() {
  while true; do
    echo -e "${BLUE}\nConfigure Panel Protocol${NC}"
    echo -e "${GREEN}0)${NC} Back"
    echo -e "${GREEN}1)${NC} Use HTTPS for panel (insecure mode, bypass SSL verification)"
    echo -e "${GREEN}2)${NC} Use HTTP for panel"
    read -p "Choose [0-2, default=2]: " pchoice
    if [[ -z "$pchoice" ]]; then
      pchoice=2
    fi
    case "$pchoice" in
      0) return ;;
      1 | 2)
        local current_config=$(cat "$PORTS_FILE")
        local panel_port=$(jq -r '.panel_port' "$PORTS_FILE")
        local flask_port=$(jq -r '.flask_port' "$PORTS_FILE")
        local use_https=$(jq -r '.use_https' "$PORTS_FILE")
        local domain=$(jq -r '.domain' "$PORTS_FILE")
        local cert_file=$(jq -r '.cert_file' "$PORTS_FILE")
        local key_file=$(jq -r '.key_file' "$PORTS_FILE")
        if [[ "$pchoice" == "1" ]]; then
          cat <<EOF > "$PORTS_FILE"
{
  "panel_port": $panel_port,
  "flask_port": $flask_port,
  "panel_use_https": true,
  "use_https": $use_https,
  "domain": "$domain",
  "cert_file": "$cert_file",
  "key_file": "$key_file"
}
EOF
          echo -e "${GREEN}Panel protocol set to HTTPS (insecure mode)${NC}"
        else
          cat <<EOF > "$PORTS_FILE"
{
  "panel_port": $panel_port,
  "flask_port": $flask_port,
  "panel_use_https": false,
  "use_https": $use_https,
  "domain": "$domain",
  "cert_file": "$cert_file",
  "key_file": "$key_file"
}
EOF
          echo -e "${GREEN}Panel protocol set to HTTP${NC}"
        fi
        systemctl restart "$SERVICE"
        break
        ;;
      *) echo -e "${RED}Invalid choice.${NC}" ;;
    esac
  done
}

function change_https_settings() {
  while true; do
    echo -e "${BLUE}\nConfigure HTTPS Settings${NC}"
    echo -e "${GREEN}0)${NC} Back"
    echo -e "${GREEN}1)${NC} Enable HTTPS"
    echo -e "${GREEN}2)${NC} Disable HTTPS (switch to HTTP)"
    read -p "Choose [0-2, default=2]: " hchoice
    if [[ -z "$hchoice" ]]; then
      hchoice=2
    fi
    case "$hchoice" in
      0) return ;;
      1)
        local current_config=$(cat "$PORTS_FILE")
        local panel_port=$(jq -r '.panel_port' "$PORTS_FILE")
        local flask_port=$(jq -r '.flask_port' "$PORTS_FILE")
        local panel_use_https=$(jq -r '.panel_use_https' "$PORTS_FILE")
        read -p "Enter domain or IP (e.g., example.com or 192.168.1.100): " domain
        read -p "Enter path to certificate file (e.g., /path/to/cert.pem): " cert_file
        read -p "Enter path to private key file (e.g., /path/to/private.key): " key_file
        if [[ -n "$domain" && -f "$cert_file" && -f "$key_file" ]]; then
          cat <<EOF > "$PORTS_FILE"
{
  "panel_port": $panel_port,
  "flask_port": $flask_port,
  "panel_use_https": $panel_use_https,
  "use_https": true,
  "domain": "$domain",
  "cert_file": "$cert_file",
  "key_file": "$key_file"
}
EOF
          echo -e "${GREEN}HTTPS enabled with domain: $domain${NC}"
        else
          echo -e "${RED}Invalid input or files not found. No changes made.${NC}"
          echo "$current_config" > "$PORTS_FILE"
          continue
        fi
        systemctl restart "$SERVICE"
        show_access_address
        break
        ;;
      2)
        local current_config=$(cat "$PORTS_FILE")
        local panel_port=$(jq -r '.panel_port' "$PORTS_FILE")
        local flask_port=$(jq -r '.flask_port' "$PORTS_FILE")
        local panel_use_https=$(jq -r '.panel_use_https' "$PORTS_FILE")
        cat <<EOF > "$PORTS_FILE"
{
  "panel_port": $panel_port,
  "flask_port": $flask_port,
  "panel_use_https": $panel_use_https,
  "use_https": false,
  "domain": "",
  "cert_file": "",
  "key_file": ""
}
EOF
        echo -e "${GREEN}Switched to HTTP${NC}"
        systemctl restart "$SERVICE"
        show_access_address
        break
        ;;
      *) echo -e "${RED}Invalid choice.${NC}" ;;
    esac
  done
}

function update_geofiles_cmd() {
  while true; do
    echo -e "${BLUE}\nUpdate Geo Files${NC}"
    echo -e "${GREEN}0)${NC} Back"
    echo -e "${GREEN}1)${NC} Use default directory (/var/lib/marznode)"
    echo -e "${GREEN}2)${NC} Use custom directory"
    read -p "Choose [0-2, default=1]: " gfchoice
    if [[ -z "$gfchoice" ]]; then
      gfchoice=1
    fi
    case "$gfchoice" in
      0) return ;;
      1 | 2)
        local target_directory="/var/lib/marznode"
        if [[ "$gfchoice" == "2" ]]; then
          read -p "Enter custom directory path: " custom_dir
          if [[ -n "$custom_dir" ]]; then
            target_directory="$custom_dir"
          fi
        fi
        mkdir -p "$target_directory"
        echo -e "${GREEN}Downloading geo files into: $target_directory${NC}"
        for url in "${!GEOFILES[@]}"; do
          local filename="${GEOFILES[$url]}"
          local dest="$target_directory/$filename"
          echo -e "Downloading ${YELLOW}$url${NC} to ${GREEN}$dest${NC}"
          curl -L -s --fail "$url" -o "$dest" && {
            echo -e "   ${GREEN}Success${NC}"
          } || {
            echo -e "   ${RED}Failed to download: $url${NC}"
          }
        done
        echo -e "${GREEN}All geo file downloads completed (where successful).${NC}"
        break
        ;;
      *) echo -e "${RED}Invalid choice.${NC}" ;;
    esac
  done
}

function restart_cmd() {
  echo -e "${BLUE}Restarting $SERVICE...${NC}"
  systemctl restart "$SERVICE"
}

function uninstall_cmd() {
  echo -ne "${RED}Are you sure you want to uninstall Xarneshin? (y/N): ${NC}"
  read answer
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    echo -e "${RED}Uninstalling Xarneshin...${NC}"
    systemctl stop "$SERVICE"
    systemctl disable "$SERVICE"
    rm -f /etc/systemd/system/xarneshin.service
    systemctl daemon-reload
    echo -e "${RED}Removing $INSTALL_DIR...${NC}"
    rm -rf "$INSTALL_DIR"
    echo -e "${RED}Removing $0...${NC}"
    rm -f /usr/local/bin/xarneshin
    echo -e "${GREEN}Done.${NC}"
  else
    echo -e "${YELLOW}Uninstall canceled.${NC}"
  fi
}

function menu() {
  while true; do
    short_status
    echo -e "──────────────────────────────"
    echo -e "${GREEN}1)${NC} Show Service detailed status"
    echo -e "${GREEN}2)${NC} Change Ports"
    echo -e "${GREEN}3)${NC} Update Geo Files"
    echo -e "${GREEN}4)${NC} Restart"
    echo -e "${GREEN}5)${NC} Show Access address"
    echo -e "${GREEN}6)${NC} Uninstall"
    echo -e "${GREEN}7)${NC} Configure HTTPS Settings"
    echo -e "${GREEN}8)${NC} Configure Panel Protocol"
    echo -e "${GREEN}9)${NC} Exit"
    read -p "Choose [1-9]: " choice
    case "$choice" in
      1) detail_status ;;
      2) change_ports_submenu ;;
      3) update_geofiles_cmd ;;
      4) restart_cmd ;;
      5) show_access_address ;;
      6) uninstall_cmd ; return ;;
      7) change_https_settings ;;
      8) change_panel_protocol ;;
      9) echo -e "${GREEN}Bye.${NC}"; break ;;
      *) echo -e "${RED}Invalid choice.${NC}" ;;
    esac
  done
}

if [[ $# -eq 0 ]]; then
  menu
  exit 0
fi

case "$1" in
  status) short_status ;;
  detail) detail_status ;;
  change-ports) change_ports_submenu ;;
  update-geofiles) update_geofiles_cmd ;;
  restart) restart_cmd ;;
  show-address) show_access_address ;;
  uninstall) uninstall_cmd ;;
  *) echo -e "${YELLOW}Usage: xarneshin [status|detail|change-ports|update-geofiles|restart|show-address|uninstall]${NC}" ;;
esac
EOS

chmod +x "$CLI_PATH"

###############################################################################
#                            FINAL INSTALL REPORT                             #
###############################################################################
ipv4=$(curl -4 -s ifconfig.me)
echo -e "\n${CYAN}[Action]${NC} ${GREEN}Installation complete!${NC}  Here’s the summary:\n"
printf "  ${BLUE}Service name${NC}:    xarneshin.service\n"
printf "  ${BLUE}CLI command${NC}:     xarneshin\n"
printf "  ${BLUE}Main panel port${NC}: $panel_port\n"
printf "  ${BLUE}Flask port${NC}:      $flask_port\n"
printf "  ${BLUE}Global IPv4${NC}:     $ipv4\n"
printf "  ${BLUE}Access URL${NC}:      ${GREEN}http://$ipv4:$flask_port${NC}\n"
echo -e "  ${YELLOW}Note:${NC} For secure access (recommended), enable HTTPS using '${GREEN}xarneshin${NC}' CLI (option 7) with your domain and certificates.\n"
echo -e "  ${YELLOW}Installation logs:${NC} Check $LOG_FILE if you encountered issues during installation.\n"
