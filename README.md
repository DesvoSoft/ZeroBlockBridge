<!-- markdownlint-disable-next-line MD033 -->
<h1 align="center">ZeroBlockBridge</h1>

<!-- markdownlint-disable-next-line MD033 -->
<p align="center">Minecraft Server Management with Built-in Tunneling, Backups & Automation</p>

<!-- markdownlint-disable-next-line MD033 -->
<p align="center">
<!-- markdownlint-disable-next-line MD033 -->
  <img src="assets/logo.png" alt="ZeroBlockBridge Logo" width="350"/>
</p>

<!-- markdownlint-disable-next-line MD033 -->
<p align="center">
<!-- markdownlint-disable-next-line MD033 -->
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10+-blue.svg" />
<!-- markdownlint-disable-next-line MD033 -->
  <img alt="License: AGPL v3" src="https://img.shields.io/badge/License-AGPL_3.0-blue.svg" />
<!-- markdownlint-disable-next-line MD033 -->
  <img alt="Latest release" src="https://img.shields.io/github/v/release/DesvoSoft/ZeroBlockBridge?color=green" />
<!-- markdownlint-disable-next-line MD033 -->
  <img alt="Made for the Minecraft Community" src="https://img.shields.io/badge/Made_for-Minecraft_Community-blue?logo=minecraft" />
</p>

<!-- markdownlint-disable-next-line MD033 -->
<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#documentation">Documentation</a>
</p>

---

## About

ZeroBlockBridge is a desktop app for creating and managing Minecraft servers — a friendly interface that turns any computer into a server, so you can play with friends without complex setup, port forwarding, or unsafe configurations.

---

## Dashboard Preview

<p align="center">
  <img width="1166" height="739" alt="screenshot-dashboard" src="https://github.com/user-attachments/assets/453023ea-6b98-4e36-8915-fce5418bf029" />
</p>

---

## Features

- **Guided Server Creation** — 6-step wizard covering every major flavor (Vanilla/Fabric/Forge/Paper/Purpur), with templates, RAM allocation, and an integrated console with search and colored log lines.
- **Zero-Config Tunneling** — Built-in Playit.gg integration gets you a persistent, shareable join URL — no port forwarding or router setup required.
- **Auto-Healing** — Watchdog crash recovery with JSON crash reports, zombie detection, lag-spike monitoring, and command sanitization keep a server running unattended. See [ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **One-Click Backups & Scheduling** — Scheduled restarts and backups with countdown warnings, plus `.zbbpack` export/import to move a server between machines.
- **Integrated Mod Browser** — Search, install, and update mods/plugins straight from Modrinth, with automatic client-only filtering and a one-click Optimizer Bundle per loader.
- **Zero Java Hassle** — Detects the required Java version per server and auto-installs the matching JDK — no manual installs, no version mismatches.

*Also included: Discord notifications, light/dark/system theming, and experimental Linux support.*

---

## Quick Start

### Option A: Download the app

1. Grab the latest build from the [Releases page](https://github.com/DesvoSoft/ZeroBlockBridge/releases/latest) — `ZeroBlockBridge-windows.exe` (Linux build also available, experimental).
2. Run it, then jump straight to [First Server](#first-server) below.

> **Windows SmartScreen warning?** That's expected. I'm a student and independent developer, and this executable isn't code-signed — signing certificates cost money I can't justify yet. Windows flags any unsigned `.exe` from an unrecognized publisher, regardless of whether it's safe. Click **"More info" → "Run anyway"** to proceed, or if you'd rather verify for yourself first, the full source is public — read it, or build it yourself with Option B below.

### Option B: Run from source

#### Prerequisites

- **Python 3.10+** ([Download](https://www.python.org/downloads/)) — on Windows, remember to check **"Add python.exe to PATH"** during install.
- **Java**: nothing to install by hand — ZeroBlockBridge grabs and caches the right JDK for you automatically.

Verify Python is installed and on PATH before continuing:
```bash
py --version
```
> If that fails, try `python --version`. If both fail, reinstall Python and make sure "Add to PATH" was checked.

#### Installation

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

   **Linux:**
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

#### Troubleshooting

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

---

## License

**ZeroBlockBridge** © 2025-2026 by **DesvoSoft**.

Licensed under the **GNU Affero General Public License v3.0** — free software, copyleft.

[View Full License Text](https://www.gnu.org/licenses/agpl-3.0)

---

## Support

Found a bug or have a feature request? [Open an issue](https://github.com/DesvoSoft/ZeroBlockBridge/issues). Pull requests are welcome.

---

### Built by a player for players & friends
