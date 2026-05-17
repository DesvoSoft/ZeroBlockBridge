<!-- markdownlint-disable-next-line MD033 -->
<h1 align="center">ZeroBlockBridge</h1>

<!-- markdownlint-disable-next-line MD033 -->
<p align="center">Minecraft Server Management with Built-in Tunneling, Backups & Automation</p>

<!-- markdownlint-disable-next-line MD033 -->
<p align="center">
<!-- markdownlint-disable-next-line MD033 -->
  <img src="assets/logo.png" alt="ZeroBlockBridge Logo" width="350"/>
</p>

ZeroBlockBridge is a desktop application that simplifies Minecraft server creation and management, designed with the intent to provide a user‑friendly interface that can safely turn any computer into a Minecraft server. With Zero Block Bridge, you can easily host a server to play with your friends and community — without the hassle of complex setup, port forwarding or unsafe configurations.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: PolyForm Noncommercial](https://img.shields.io/badge/License-PolyForm_Noncommercial-red.svg)](https://polyformproject.org/licenses/noncommercial/1.0.0/)
[![Version](https://img.shields.io/github/v/release/DesvoSoft/ZeroBlockBridge?color=green)](https://github.com/DesvoSoft/ZeroBlockBridge/releases)

---

## Features

### Server Management

- **Creation & Import**: Guided 3-step wizard for new servers or **Instant Load** for existing folders (via symbolic links).
- **Multi-Version Support**: Vanilla, Fabric, Forge, Paper, and Purpur with dynamic version fetching (100+ versions).
- **Smart Version Caching**: Auto-refreshes every 24h (background) + sync refresh if >2 days stale. Falls back to 15+ popular versions offline. Manual ↻ Refresh button in the wizard.
- **Custom RAM Allocation**: Slider + manual entry with validation (512MB - system max).
- **Server Properties Editor**: Tabbed interface for all settings.
- **Integrated Console**: Send commands directly from the app.
- **Live Monitoring**: Real-time server and tunnel logs in separate tabs.

### Automation & Backups

- **One-Click Backups**: Create and restore ZIP backups instantly.
- **Scheduled Restarts**:
  - Interval mode (every X hours).
  - Daily time mode (specific time like 03:00).
  - Multi-stage warnings (1h, 30m, 15m, 1m, countdown).
  - Automatic success/error notifications.
- **Auto-Management**: Set it and forget it with automated restarts + backups.

### Modrinth Mod Browser

- **Search & Browse**: Search mods/plugins from Modrinth with pagination ("Load More") and loader/version filters.
- **One-Click Install**: Browse mods, select a compatible version via radio buttons, and install directly to your server.
- **Installed Mods Management**: List all installed mods with real icons (async cached from Modrinth) and delete with confirmation.
- **Check Updates**: Scan installed mods against Modrinth API to find available updates, with a dialog showing outdated mods.
- **Icons & Placeholders**: Real mod icons loaded asynchronously with global cache; fallback to colored letter placeholders.

### Tunneling & Sharing

- **Built-in [Playit.gg](https://playit.gg/) Integration**: No port forwarding needed.
- **Manual Tunnel Setup**: Get a Setup Code from Playit.gg and link it instantly.
- **Persistent Sessions**: Your account link persists across app restarts; no need to re-verify.
- **Soft Reset**: Clears tunnels only — keeps agent linked. Click ▶ to create a new tunnel.
- **Full Reset**: Deletes tunnels + unlinks account. Dashboard link provided if agent remains.
- **DNS Recovery Chain**: 3 redundant mechanisms (API poll 60s + stdout regex + create_tunnel) ensure domain assignment never gets stuck.
- **Agent Heartbeat**: Monitors the Playit agent process and auto-restarts it if it dies unexpectedly.

Note: playit.gg is a global proxy that allows anyone to host a server without port forwarding by using tunneling.

### Developer Experience

- **Modern GUI**: Clean dark theme built with CustomTkinter with Neo-Modern design (uniform `corner_radius=12`).
- **JDK Auto-Installer**: Automatically downloads and caches the required JDK from Adoptium if no suitable Java is found.
- **Java Stability Range**: Optimized for Java 17-21 (Blocks > 21 to prevent startup crashes, auto-installs proper version).
- **Event-Driven Architecture**: Decoupled UI and Core via `EventBus` — headless ready.
- **Error Handling**: Comprehensive validation and user feedback with zero bare `except:` blocks.
- **Organized Structure**: Dedicated folders for each server.

### Architecture & Quality

- **Decoupled Core/UI**: `ZBBManager` serves as the single orchestrator. The UI subscribes to events and delegates all I/O to core/services.
- **Single Source of Truth**: Server state flows through `EventBus` (`STARTING`, `READY`, `STOPPED`, `TUNNEL_STATUS`).
- **Thread Safety**: Background threads use `daemon=True`; UI updates via `self.after(0, ...)`.
- **Command Sanitization**: Every console command passes through an allowlist-based sanitizer — no raw shell execution.

---

## Interface Overview

The application features:

- **Sidebar**: Server list with selection.
- **Dashboard**: Server/tunnel controls, auto-restart settings, quick backup.
- **Tabbed Console**: Separate logs for Server and Tunnel output.
- **Console Input**: Send server commands directly from the UI.
- **Properties Editor**: 7 tabs (General, World, Network, Advanced, Backups, Automation, Launch).

---

## Auto-Healing System

ZeroBlockBridge includes built-in resilience through four coordinated services that automatically detect, classify, and recover from server failures.

### Watchdog Service (`app/services/watchdog.py`)

Monitors the server process exit code and console output to detect crashes:

| Crash Type | Detection | Recovery |
|---|---|---|
| `jvm_config_error` | stderr matches "UnsupportedClassVersionError", "Could not find main class", etc. | Retry with backoff |
| `out_of_memory` | stderr matches "OutOfMemoryError", "GC overhead limit" | Retry with backoff |
| `oom_kill` | Exit code 137 or -9 (SIGKILL by OOM killer) | Retry with backoff |
| `boot_crash` | Exit code 1, uptime < 5 seconds | Retry with backoff |
| `runtime_crash` | Exit code 1, uptime >= 5 seconds | Retry with backoff |
| `signal_N` | Negative exit code (segfault = -11, etc.) | Retry with backoff |

- **Retry policy**: Configurable max (default 3), exponential backoff (`base × 2^(n-1)`).
- **Stability reset**: Counter resets after 10 minutes of uptime.
- **Events**: Emits `CRASHED`, `RESTARTED` on the event bus.

### Heartbeat Monitor (`app/services/heartbeat.py`)

Detects zombie servers (Java process alive but unresponsive):

- Sends `list` command every 60 seconds.
- If console goes silent for >5 minutes, sends a probe.
- No response within 15 seconds → classifies as zombie.
- Watchdog subscribes to `ZOMBIE_DETECTED` and triggers auto-restart.

### Lag Monitor (`app/services/lag_monitor.py`)

Tracks server performance degradation in real-time:

- Matches `"Can't keep up!"` and `"Warning: TPS"` console patterns.
- Sliding window counter (default: 5 spikes in 5 minutes).
- Emits `LAG_SPIKE` event and shows toast notification.

### Command Sanitizer (`app/services/sanitizer.py`)

Protects against OS command injection via the console:

- **Allowlist**: 80+ known-safe Minecraft commands (op, deop, say, gamemode, etc.).
- **Character filter**: Rejects `;`, `|`, `&`, `` ` ``, `$()`, `${}`, `\n`.
- **Unknown commands**: Allowed if they pass the character filter (forward-compatible with new Minecraft commands).

### Notifications

All auto-healing events display a **Toast notification** (bottom-right overlay, auto-dismiss after 4 seconds):
- Server crash detected (red)
- Zombie server detected (orange)
- Lag threshold exceeded (orange)
- Retry exhaustion (red)
- Restart attempts (orange)

---

## Quick Start

### Prerequisites

- **Python 3.10+** ([Download](https://www.python.org/downloads/))

> **Java:** No es necesario instalarlo manualmente. El app detecta, descarga y cachea automáticamente el JDK correcto (Adoptium, rango 17-21) según la versión de Minecraft seleccionada.

### Installation

1- **Clone the repository**

```bash
git clone https://github.com/DesvoSoft/ZeroBlockBridge.git
```

2- **Navigate to the project folder**

```bash
cd ZeroBlockBridge
```

3- **Install dependencies**

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

4- **Run the application**

```bash
py app/launcher.py
```

> **Note:** Depending on your operating system and environment configuration, you might need to adjust the command used to run Python. For example, use `py`, `python`, or `python3` as appropriate.

### First Server

1. Click **"Create Server"** in the sidebar.
2. Follow the 3-step wizard to configure your server (includes pre-flight Java check).
3. The wizard shows detailed progress (download, verify, scaffold, bytecode analysis, tunnel setup).
4. After creation, click **"Start Now"** to launch your server immediately.
5. **Optional**: Click **"⚡ Link"** to enable Playit tunneling and play with friends online.

Note: The tunneling feature uses the free third party services from [Playit.GG](http://playit.gg/). The app will guide you to their "Third Party" setup wizard to obtain a Setup Code, which you then paste into the app to securely link your account (One-time process).

---

## Documentation

- **[SKILL.md](docs/SKILL.md)** - AI assistant guidelines for development.
- **[STANDARDS.md](docs/STANDARDS.md)** - Master technical standards and architecture guide.
- **[ROADMAP.md](roadmap.md)** - Development roadmap and phase tracking.

---

## Key Features

### Server Creation Wizard

The wizard guides you through:

1. **Identity**: Server name, custom location, and optional icon.
2. **Engine & Resources**: Choose Vanilla/Fabric/Paper/Purpur/Forge, select version, set RAM.
3. **Rules & World**: Game mode, difficulty, seed, view/simulation distance, auto-install JDK toggle.

### Automated Restarts

Configure from the dashboard or properties editor:

- **Interval Mode**: Restart every X hours.
- **Daily Time Mode**: Restart at a specific time (e.g., 03:00 for 3AM).
- **Warnings**: Players get in-game notifications starting 1 hour before restart.
- **Final Countdown**: A 5-second countdown is announced in-game before shutdown.

### Backups

- **Create**: Dashboard button or Properties → Backups tab.
- **Format**: ZIP archives with timestamp (`backup_YYYYMMDD_HHMMSS.zip`).
- **Restore**: Select backup in properties editor (wipes current server!).
- **Storage**: `backups/<server-name>/`.

### Console Commands

Send any Minecraft command:

```text
say Hello everyone!
op PlayerName
gamemode creative PlayerName
```

Commands appear in the log with `>` prefix and execute immediately.

---

## Privacy & Service Disclaimer

ZeroBlockBridge is designed with simplicity and transparency in mind:

- **No Data Collection**: ZeroBlockBridge is not intended to collect, store, or transmit any personal information or usage data.
- **External Connections**: The app connects only to the services necessary for its operation:
  - **Playit.gg** — tunneling (optional, only if you enable it)
  - **Mojang** — version manifest and server jar downloads
  - **Modrinth** — mod/plugin browsing and downloads
  - **Fabric/Forge/Paper/Purpur APIs** — version fetches
  - **Adoptium** — JDK auto-install
- **User Control**: All server management, backups, and tunneling operations remain fully under the user’s control.

This ensures that your Minecraft server management experience is secure, private, and limited strictly to the features described.

---

## Project Structure

The project follows a clean architecture, separating UI, business logic, and services.

```text
ZeroBlockBridge/
├── app/
│   ├── ui/                        # Presentation Layer (UI only)
│   │   ├── main.py                # Main window, layout, event subscriptions
│   │   ├── server_wizard.py       # 3-step creation wizard
│   │   ├── server_properties_editor.py # Tabbed properties editor
│   │   ├── modrinth_browser.py    # Modrinth mod browser
│   │   └── ui_components.py       # Reusable widgets (Console, ServerList, ToolTip)
│   │
│   ├── core/                      # Orchestration & Business Logic
│   │   ├── core.py                # ZBBManager — central orchestrator
│   │   ├── logic.py               # ServerRunner, Scheduler, file downloads
│   │   ├── constants.py           # File paths, URLs, config constants
│   │   ├── app_config.py          # UI config (colors, fonts, window)
│   │   ├── version_manager.py     # Dynamic version fetching & caching
│   │   ├── server_events.py       # EventBus, ServerEvent definitions
│   │   ├── statemanager.py        # Tunnel status debounce (module)
│   │   ├── scheduler_service.py   # Automated restart logic
│   │   ├── playit_manager.py      # Playit.gg agent lifecycle & tunnel
│   │   └── single_instance.py     # PID lockfile (prevents duplicates)
│   │
│   └── services/                  # Specialized Services & Auto-Healing
│       ├── playit_api.py          # Playit.gg REST API v2 client
│       ├── scaffolder.py          # Server directory scaffolding
│       ├── server_properties.py   # server.properties read/write
│       ├── java_installer.py      # JDK auto-download from Adoptium
│       ├── java_detector.py       # System Java detection + Portable JDK scan
│       ├── bytecode_analyzer.py   # JAR bytecode Java version analysis
│       ├── aikars_flags.py        # Aikars JVM flag calculator
│       ├── console_buffer.py      # Thread-safe console buffer (deque)
│       ├── sanitizer.py           # Command injection prevention
│       ├── watchdog.py            # Crash detection & auto-restart
│       ├── heartbeat.py           # Zombie server detection
│       ├── lag_monitor.py         # TPS lag spike detection
│       ├── backup_manager.py      # ZIP backup create/restore
│       ├── modrinth.py            # Modrinth API client
│       ├── sha1_validator.py      # SHA1 download verification
│       ├── settings_manager.py    # App config read/write (module)
│       └── toast.py               # Non-blocking notification overlay
│
├── .github/
│   └── workflows/
│       ├── tests.yml                # GitHub CI: pytest + flake8
│       └── build.yml                # Build & release on version tags
|
├── requirements.txt               # Project dependencies
│
├── assets/                        # Misc files
│   ├── logo.ico                   # App icon
│   └── logo.png                   # Project logo
|
├── docs/
│   ├── SKILL.md                   # AI assistant guidelines
│   ├── STANDARDS.md               # Technical standards & architecture
│   └── roadmap.md                 # Development roadmap
|
├── servers/                       # (Generated) Per-server directories
│   └── <server-name>/
│       ├── server.jar
│       ├── server.properties
│       └── metadata.json
│
├── backups/                       # (Generated) ZIP backups
│   └── <server-name>/
│       └── YYYY-MM-DD_HH-MM-SS.zip
│
├── bin/                           # (Generated) playit agent binary
│
├── .zbb_cache/                    # (Generated) JDK cache directory
│   └── jdks/
│       └── <version>/
│           ├── bin/
│           │   └── java(.exe)
│           └── ...
│
├── config/                        # (Generated) App configuration
│   ├── config.json
│   └── versions_cache.json
│
└── README.md                      # This file c:
```

---

## Technical Details

### Supported Versions

Zero Block Bridge uses **dynamic version fetching** to support hundreds of Minecraft versions:

- **Vanilla**: Fetches top 100 releases from Mojang API (supports 26.x.x and 1.21.x schemes) with expanded offline defaults.
- **Fabric**: Fetches top 100 stable game versions from Fabric Meta API with latest installer.
- **Forge**: Fetches top 100 versions from Forge Promotions API with recommended/latest builds.
- **Paper**: Fetches top 100 versions from PaperMC API.
- **Purpur**: Fetches top 100 versions from PurpurMC API.
- **Smart Caching**: Auto-refreshes every 24h (background) + sync refresh if >2 days stale. Falls back to expanded defaults if offline.
- **Cache Location**: Stored in `config/versions_cache.json` for offline access.

### System Requirements

- **OS**: Windows/Linux
- **Python**: 3.10 or higher
- **Java**: Auto-managed — the app detects, downloads, and caches the required JDK (Adoptium, range 17-21) based on the Minecraft version. Blocks incompatible versions.
- **RAM**: 2GB minimum (4GB+ recommended for modded servers)
- **Disk**: 37 MB for core app and dependencies + ~107MB per server (vanilla, it might vary for modded servers) + world size

### Dependencies

All required Python packages are listed in `requirements.txt` at the project root:

- **customtkinter** – Modern GUI framework (forks/extends Tkinter).
- **requests** – HTTP client for downloads and API calls.
- **psutil** – System resource monitoring (RAM, processes).
- **Pillow** – Image processing (server icons).

---

## Contributing

Contributing, issues and pull requests are welcome!
Feedback is always appreciated ❤️

---

## License

**ZeroBlockBridge** © 2025-2026 by **DesvoSoft**.

This project is licensed under the **PolyForm Noncommercial License 1.0.0**.

### Restriction

- **No Commercial Use** — You may **not** use this software for any commercial purpose. This includes:
- Selling the software or any modified version of it.
- Using the software as part of a paid hosting service.
- Using the software to support the operations of a for-profit business.

[View Full License Text](https://polyformproject.org/licenses/noncommercial/1.0.0/)

---

## Acknowledgments

- **CustomTkinter**: Modern UI Python framework by Tom Schimansky.
- **Playit.gg**: Free tunneling service for easy multiplayer.
- **Minecraft/Mojang**: For creating an amazing game.

---

## Support

- **Issues**: Report bugs or request features via GitHub Issues.
- **Discussions**: Share your server setups and get help from the community.

---

### Built by a player, for players, Minecraft creators & friends

![Privacy Friendly](https://img.shields.io/badge/Privacy-Friendly-green?style=for-the-badge&logo=shield)
![Community](https://img.shields.io/badge/Made_for-Minecraft_Community-blue?style=for-the-badge&logo=minecraft)
