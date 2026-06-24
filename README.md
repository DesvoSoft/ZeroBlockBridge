<!-- markdownlint-disable-next-line MD033 -->
<h1 align="center">ZeroBlockBridge</h1>

<!-- markdownlint-disable-next-line MD033 -->
<p align="center">Minecraft Server Management with Built-in Tunneling, Backups & Automation</p>

<!-- markdownlint-disable-next-line MD033 -->
<p align="center">
<!-- markdownlint-disable-next-line MD033 -->
  <img src="assets/logo.png" alt="ZeroBlockBridge Logo" width="350"/>
</p>

ZeroBlockBridge is a desktop application that simplifies Minecraft server creation and management, designed with the intent to provide a user‑friendly interface that can safely turn any computer into a Minecraft server. Host a server to play with friends and community — without complex setup, port forwarding or unsafe configurations.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Version](https://img.shields.io/github/v/release/DesvoSoft/ZeroBlockBridge?color=green)](https://github.com/DesvoSoft/ZeroBlockBridge/releases)

---

## Features

- **Server Management**: 3-step wizard, multi-version (Vanilla/Fabric/Forge/Paper/Purpur), smart caching, RAM allocation, properties editor, integrated console, player management dashboard with whitelist controls.
- **Automation & Backups**: One-click ZIP backups, scheduled restarts (interval or daily time), multi-stage warnings with countdown, auto-backup scheduler.
- **Performance Monitoring**: Lag spike detection, server heartbeat monitoring.
- **Modrinth Mod Browser**: Search, filter, one-click install, manage installed mods, check updates against Modrinth API.
- **Tunneling**: Built-in Playit.gg integration, persistent sessions, soft/full reset, DNS recovery chain, agent heartbeat, circuit breaker with exponential backoff.
- **Auto-Healing**: Watchdog (crash detection + JSON crash reports), heartbeat (zombie detection), lag monitor, command sanitizer, disk space pre-flight check — see [ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Developer Experience**: JDK auto-installer (bytecode analysis detects required version), event-driven architecture, thread safety, zero bare `except:` blocks.

---

## Quick Start

### Prerequisites

- **Python 3.10+** ([Download](https://www.python.org/downloads/))
- **Java**: Not required manually. The app automatically detects, downloads, and caches the correct JDK (Adoptium, range 17-21) based on the selected Minecraft version.

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/DesvoSoft/ZeroBlockBridge.git
   ```

2. **Navigate to the project folder**
   ```bash
   cd ZeroBlockBridge
   ```

3. **Install dependencies**

   Create a virtual environment (recommended):

   **Windows:**
   ```bash
   py -m venv venv
   .\venv\Scripts\activate
   ```

   **Linux/macOS:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

   Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**
   ```bash
   py app/launcher.py
   ```

   > Depending on your OS, you might need `python` or `python3` instead of `py`.

### First Server

1. Click **"Create Server"** in the sidebar.
2. Follow the 3-step wizard (identity, engine/resources, rules/world).
3. The wizard shows detailed progress (download, verify, scaffold, bytecode analysis, tunnel setup).
4. After creation, click **"Start Now"** to launch your server.
5. **Optional**: Click **"⚡ Link"** to enable Playit tunneling and play with friends online.

---

## Project Structure

```
ZeroBlockBridge/
├── app/
│   ├── ui/              # Presentation layer (main window, wizard, editors, browser)
│   ├── core/             # Orchestration & business logic (ZBBManager, EventBus, logic)
│   └── services/         # Specialized services (watchdog, heartbeat, backups, API clients)
├── docs/                 # Documentation
├── assets/               # App icon and logo
├── servers/              # (Generated) per-server directories
├── backups/              # (Generated) ZIP archives
├── bin/                  # (Generated) playit agent binary
├── .zbb_cache/           # (Generated) JDK cache
└── config/               # (Generated) app configuration
```

---

## Documentation

- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** — Auto-healing system, technical details, architecture overview.
- **[STANDARDS.md](docs/STANDARDS.md)** — Master technical standards and architecture guide.
- **[ROADMAP.md](roadmap.md)** — Development roadmap and phase tracking (local-only, untracked from repo).

---

## Contributing

Contributions, issues, and pull requests are welcome!

---

## License

**ZeroBlockBridge** © 2025-2026 by **DesvoSoft**.

Licensed under the **GNU Affero General Public License v3.0** — free software, copyleft.

[View Full License Text](https://www.gnu.org/licenses/agpl-3.0)

---

## Support

- **Issues**: Report bugs or request features via [GitHub Issues](https://github.com/DesvoSoft/ZeroBlockBridge/issues).
- **Discussions**: Share setups and get help from the community.

---

### Built by a player, for players, Minecraft creators & friends

![Privacy Friendly](https://img.shields.io/badge/Privacy-Friendly-green?style=for-the-badge&logo=shield)
![Community](https://img.shields.io/badge/Made_for-Minecraft_Community-blue?style=for-the-badge&logo=minecraft)
