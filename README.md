# Xarneshin - Xenon Xray Manager

**Xarneshin** is a powerful, futuristic Flask-based web interface and CLI tool designed to manage Xray configurations seamlessly alongside the [Marzneshin](https://github.com/marzneshin/marzneshin) proxy management system. Built with a sleek, modern UI and packed with advanced features, Xarneshin empowers users to configure, monitor, and optimize Xray instances with ease.

---

## ✨ Features

- **Web Interface**: A responsive, Tailwind CSS-powered dashboard with a futuristic design for managing Xray nodes, inbounds, outbounds, DNS, balancers, and more.
- **CLI Tool**: A robust command-line interface (`xarneshin`) for quick management tasks, including port changes, HTTPS setup, geo file updates, and service control.
- **Dynamic Configuration**: Load and manage Xray settings dynamically via `ports.json`.
- **Advanced DNS Management**: Configure DNS servers with fine-grained control over query strategies, fallback options, and custom presets.
- **Core Version Switching**: Easily switch between Xray core versions with real-time progress updates.
- **System Monitoring**: Overview dashboard with real-time CPU, RAM, disk, and network stats.
- **HTTPS Support**: Secure your Flask app with custom SSL certificates and domain configuration.
- **Integration**: Designed to work seamlessly with Marzneshin's API for node management.

---

## 📢 Support Us!

Love Xarneshin? Join our community and stay updated with the latest features and updates!  
- **Telegram**: [t.me/XenonNet](https://t.me/XenonNet) - Join our channel for news, support, and discussions.  
- **GitHub**: Star this repository and contribute to make Xarneshin even better!  

Your support keeps this project alive—thank you! 🚀

---

## 📦 Installation

Everything is handled by the `install.sh` script—no manual installation or running is required after executing it with the proper permissions. Follow this single command:

### Prerequisites

- Python 3.6+
- `git`, `curl`, `jq`, and `systemd` installed
- Marzneshin installed and running (optional, for full integration)

### Steps

Run this single command to clone the repository and set up Xarneshin:

``` bash
git clone https://github.com/MeXenon/Xarneshin.git ~/Xenon.xray && cd ~/Xenon.xray && chmod +x install.sh && sudo ./install.sh
```
- The command will:
  - Clone the repository to `~/Xenon.xray`.
  - Navigate to the directory.
  - Make `install.sh` executable.

3. **Verify Installation**  
   After the script completes, check the service status:

   sudo systemctl status xarneshin.service

   Access the web interface at `http://<your-server-ip>:<flask-port>` (e.g., `http://192.168.1.100:42689`).

4. **(Optional) Enable HTTPS**  
   Use the CLI to configure HTTPS with your domain and certificates:

   xarneshin
   
   **Select option 7: Configure HTTPS Settings**

---

## 🚀 Usage

### Web Interface
- **Login**: Use your Marzneshin admin credentials to access the dashboard.
- **Manage Nodes**: View and configure Xray settings, including inbounds, outbounds, DNS, and routing rules.
- **Change Core**: Switch Xray versions directly from the interface (local node only).

### CLI Tool
Run
``` bash 
xarneshin
```
in your terminal to access the command-line interface:

xarneshin

**Available Commands:**
- `status`: Show service status and uptime.
- `change-ports`: Modify Flask or panel ports.
- `update-geofiles`: Download geoip/geosite files.
- `restart`: Restart the Xarneshin service.
- `show-address`: Display the access URL.
- `uninstall`: Remove Xarneshin from your system.

For detailed options, run
```bash
xarneshin --help
```
---

## 🙏 Acknowledgments

- [Marzneshin](https://github.com/marzneshin/marzneshin) - The backbone proxy management system.
- [MeXenon](https://github.com/MeXenon) - Lead developer and visionary behind Xarneshin.
- [XenonNet](https://github.com/XenonNet) - Sponsoring
---

**Built with ❤️ by the Xenon Team**  
Join us on [Telegram](https://t.me/XenonNet) and let’s make proxy management awesome together!
