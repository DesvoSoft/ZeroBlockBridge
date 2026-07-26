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

## Dashboard Preview

<p align="center">
  <img width="1166" height="739" alt="screenshot-dashboard" src="https://github.com/user-attachments/assets/453023ea-6b98-4e36-8915-fce5418bf029" />
</p>

---

## Features

- **Server Management**: 6-step creation wizard with a summary/review step, multi-version (Vanilla/Fabric/Forge/Paper/Purpur), server templates, smart caching, RAM allocation, properties editor, integrated console with search and colored log lines, player management dashboard with whitelist controls, right-click server deletion.
- **Automation & Backups**: One-click ZIP backups, scheduled restarts (interval or daily time), multi-stage warnings with countdown, auto-backup scheduler, `.zbbpack` export/import for moving a server between machines.
- **Performance Monitoring**: Lag spike detection, server heartbeat monitoring.
- **Modrinth Mod Browser**: Search, filter, one-click install, manage installed mods, check updates against Modrinth API. Automatically excludes client-only mods from results and badges mods that also work client-side, so you only see content that actually runs on your server. Loader-aware Optimizer Bundle (Fabric or Forge) for one-click performance tuning.
- **Tunneling**: Built-in Playit.gg integration, persistent sessions, soft/full reset, DNS recovery chain, agent heartbeat, circuit breaker with exponential backoff.
- **Auto-Healing**: Watchdog (crash detection + JSON crash reports), heartbeat (zombie detection), lag monitor, command sanitizer, disk space pre-flight check — see [ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Notifications**: Optional Discord webhooks with per-event custom message templates (crash/ready/backup/player events).
- **Theming**: Light, dark, and system theme, fully applied across the UI.
- **Linux Support (experimental)**: Native binary via PyInstaller.
- **Developer Experience**: JDK auto-installer (bytecode analysis detects required version), event-driven architecture, thread safety, zero bare `except:` blocks.

---

## Quick Start

### Prerequisites

- **OS**: Windows 10/11 (fully supported), Linux (experimental).
- **Python 3.10+** ([Download](https://www.python.org/downloads/)) — during install, on Windows, check **"Add python.exe to PATH"**.
- **Git** ([Download](https://git-scm.com/downloads)) — only needed to clone the repo; skip it if you download the ZIP instead.
- **~1 GB free disk space** — the app auto-downloads a JDK (Adoptium) and, per server you create, the Minecraft server jar.
- **Java**: Not required manually. The app automatically detects, downloads, and caches the correct JDK (Adoptium, range 8-21) based on the selected Minecraft version.

Verify Python is installed and on PATH before continuing:
```bash
py --version
```
> If that fails, try `python --version`. If both fail, reinstall Python and make sure "Add to PATH" was checked.

### Installation

1. **Get the source**

   Clone with git:
   ```bash
   git clone https://github.com/DesvoSoft/ZeroBlockBridge.git
   cd ZeroBlockBridge
   ```
   No git? [Download the ZIP](https://github.com/DesvoSoft/ZeroBlockBridge/archive/refs/heads/main.zip), extract it, then open a terminal in that folder.

2. **Create and activate a virtual environment** (recommended, keeps dependencies isolated)

   **Windows (PowerShell):**
   ```powershell
   py -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
   > If you get an error about execution policies, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, then retry the activate command.

   **Windows (cmd.exe):**
   ```bat
   py -m venv venv
   .\venv\Scripts\activate.bat
   ```

   **Linux/macOS:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

   Your prompt should now be prefixed with `(venv)`.

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**
   ```bash
   py app/launcher.py
   ```
   > Depending on your OS, you might need `python` or `python3` instead of `py`.

   The ZeroBlockBridge window should open within a few seconds. If nothing opens and the terminal shows an error, see [Troubleshooting](#troubleshooting) below.

### First Server

1. Click **"Create Server"** in the sidebar.
2. Follow the 6-step wizard (identity, engine/version, resources, rules/security, world/network, summary) — optionally tick **"Start server after creation"** on the summary step.
3. The wizard shows detailed progress (download, verify, scaffold, bytecode analysis, tunnel setup). This step needs internet access and can take a few minutes on the first run.
4. If you didn't check "start after creation", click **"Start Now"** when prompted to launch your server.
5. **Optional**: Click **"⚡ Link"** to enable tunneling via [Playit.gg](https://playit.gg), a third-party service. Skip this if you already forward ports yourself.
   - First time only: this opens a browser to link a free Playit.gg account — takes under a minute, no server restart needed after.
   - Useful if you don't know how to safely open ports on your router/firewall — Playit tunnels the connection for you, no port forwarding required.
   - Gives you a shareable join URL that stays the same even when your server is offline, so friends can bookmark it once.

### Troubleshooting

- **`'py' is not recognized` / `'python' is not recognized`**: Python isn't on PATH. Reinstall Python and check "Add python.exe to PATH", or use the full path to `python.exe`.
- **`pip install` fails on a package**: Upgrade pip first — `py -m pip install --upgrade pip` — then retry.
- **Antivirus flags or deletes the downloaded JDK/server jar**: These are legitimate downloads from Adoptium/Mojang/Fabric/Forge; add an exclusion for the `.zbb_cache/` and `servers/` folders if this happens.
- **PowerShell blocks `Activate.ps1`**: See the execution-policy note above.

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

## License

**ZeroBlockBridge** © 2025-2026 by **DesvoSoft**.

Licensed under the **GNU Affero General Public License v3.0** — free software, copyleft.

[View Full License Text](https://www.gnu.org/licenses/agpl-3.0)

---

## Contributing & Support

Found a bug or have a feature request? [Open an issue](https://github.com/DesvoSoft/ZeroBlockBridge/issues). Pull requests are welcome.

---

### Built by a player, for players, Minecraft creators & friends

![Community](https://img.shields.io/badge/Made_for-Minecraft_Community-blue?style=for-the-badge&logo=minecraft)
