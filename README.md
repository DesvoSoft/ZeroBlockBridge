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

---

## Features

### Server Management

- **Creation Wizard**: 6-step guided setup with preview and validation.
- **Multi-Version Support**: Vanilla, Fabric, and Forge with dynamic version fetching (hundreds of versions).
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

### Tunneling & Sharing

- **Built-in [Playit.gg](https://playit.gg/) Integration**: No port forwarding needed.
- **One-Click Tunnel Setup**: Auto-opens claim link in browser.
- **Public IP Display**: Share the provided public address.
- **Stable Agent**: Pinned to v0.16.5 for maximum reliability.

Note: playit.gg is a global proxy that allows anyone to host a server without port forwarding by using tunneling.

### Developer Experience

- **Modern GUI**: Clean dark theme built with CustomTkinter.
- **Cross-Platform Sound**: Reliable notifications on Windows and Linux.
- **Java Stability Range**: Optimized for Java 17-21 (Blocks > 21 to prevent startup crashes).
- **Error Handling**: Comprehensive validation and user feedback.
- **Organized Structure**: Dedicated folders for each server.

---

## Interface Overview

The application features:

- **Sidebar**: Server list with selection.
- **Dashboard**: Server/tunnel controls, auto-restart settings, quick backup.
- **Tabbed Console**: Separate logs for Server and Tunnel output.
- **Console Input**: Send server commands directly from the UI.
- **Properties Editor**: 6 tabs (General, World, Network, Advanced, Backups, Automation).

---

## Auto-Healing System (Fase 1)

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
- **Java 17+** ([Download](https://www.java.com/en/download/))

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

```bash
py -m venv venv
.\venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

4- **Run the application**

```bash
py launcher.py
```

> **Note:** Depending on your operating system and environment configuration, you might need to adjust the command used to run Python. For example, use `py`, `python`, or `python3` as appropriate.

### First Server

1. Click **"Create Server"** in the sidebar.
2. Follow the 6-step wizard to configure your server.
3. Select the server from the list.
4. The server will automatically start, initialize the core files (world, logs, mods), and stop by itself.
5. Click **"Start"** to launch your fully configured server.
6. **Optional**: Enable tunneling to play with friends online.

Note: The tunneling feature uses the free third party services from [Playit.GG](http://playit.gg/). The app will lead to their website and the respecitve dashboard to connect the agent, the tunnel, and to confirm your shearable IP (One time process).

---

## Documentation

- **[USAGE.md](docs/USAGE.md)** - Complete user guide with all features.
- **[TESTING.md](docs/TESTING.md)** - Test cases and verification steps.

---

## Key Features

### Server Creation Wizard

The wizard guides you through:

1. **Type & Name**: Choose Vanilla/Fabric/Forge and select Minecraft version, then name your server.
2. **RAM**: Use slider or type exact MB value (with validation).
3. **World Settings**: Seed, game mode, difficulty, view distance, simulation distance.
4. **Server Icon**: Upload custom PNG/JPG icon (optional, resized to 64x64).
5. **Location**: View save location (custom paths coming soon).
6. **Review**: Confirm all settings before creation.

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

- **No External Connections**: The software does not connect to any external services other than the free tunneling services provided by [Playit.gg](https://playit.gg).
- **No Data Collection**: ZeroBlockBridge is not intended to collect, store, or transmit any personal information or usage data.
- **User Control**: All server management, backups, and tunneling operations remain fully under the user’s control.

This ensures that your Minecraft server management experience is secure, private, and limited strictly to the features described.

---

## Project Structure

The project follows a clean architecture, separating UI, business logic, and services.

```text
ZeroBlockBridge/
├── app/
│   ├── main.py                    # Main application, UI layout, and coordination
│   ├── logic.py                   # Core business logic & Sound Utility
│   ├── constants.py               # File paths, URLs, and configuration constants
│   ├── app_config.py              # UI configuration (colors, fonts, window settings)
│   ├── version_manager.py         # Dynamic version fetching, caching, and URL resolution
│   ├── server_events.py           # Event system for server state notifications
│   ├── scheduler_service.py       # Handles the logic for automated restarts
│   ├── playit_manager.py          # Manages the playit.gg tunneling agent
│   ├── server_wizard.py           # UI and logic for the 6-step creation wizard
│   ├── server_properties_editor.py # UI for the server properties editor
│   ├── ui_components.py           # Reusable UI widgets (console, list items)
│   ├── single_instance.py         # PID lockfile to prevent duplicate app instances
│   │
│   └── services/                  # Auto-Healing & Utility Services
│       ├── __init__.py
│       ├── watchdog.py            # Crash detection, classification & auto-restart
│       ├── heartbeat.py           # Zombie server detection via periodic probes
│       ├── lag_monitor.py         # TPS lag spike detection with sliding window
│       ├── sanitizer.py           # OS command injection prevention
│       └── toast.py               # Non-blocking notification overlay
│
├── requirements.txt               # Project dependencies for pip
│
├── assets/                        # Other misc files
│   ├── notification.wav           # Notification sound effect
|   ├── icon.ico                   # App icon
|   └── logo.png                   # Project logo
|
├── docs/
│   ├── USAGE.md                   # User guide
|   └── TESTING.md                 # Test documentation
|
├── servers/                       # (Generated) Created servers are stored here
│   └── <server-name>/
│       ├── server.jar
│       ├── server.properties
│       └── metadata.json          # Stores RAM, scheduler config, and wizard settings
│
├── backups/                       # (Generated) Server backups stored here
│   └── <server-name>/
│       └── YYYY-MM-DD_HH-MM-SS.zip
│
├── bin/                           # (Generated) Binaries like the playit agent
│
├── config/                        # (Generated) Playit.gg agent configuration
│   ├── config.json                # (Generated) App-level configuration
│   └── versions_cache.json        # (Generated) Cached Minecraft versions
│
└── README.md                      # This file c:
```

---

## Technical Details

### Supported Versions

Zero Block Bridge uses **dynamic version fetching** to automatically support hundreds of Minecraft versions:

- **Vanilla**: Fetches top 20 latest releases from Mojang API (e.g., 1.21.1, 1.20.1, 1.19.4) + popular versions (1.18.2, 1.16.5, 1.12.2, 1.8.9, etc.)
- **Fabric**: Fetches top 20 stable game versions from Fabric Meta API with latest installer
- **Forge**: Fetches top 50 versions from Forge Promotions API with recommended/latest builds
- **Auto-Update**: Version cache refreshes every 24 hours automatically
- **Cache Location**: Stored in `config/versions_cache.json` for offline access

### System Requirements

- **OS**: Windows/Linux
- **Python**: 3.10 or higher
- **Java**: 17-21 (Stability range enforced: block if > 21 or < required).
- **RAM**: 2GB minimum (4GB+ recommended for modded servers)
- **Disk**: 37 MB for core app and dependencies + ~107MB per server (vanilla, it might vary for modded servers) + world size

### Dependencies

All required Python packages are listed in `requirements.txt` at the project root. The dependencies are:

- **customtkinter** – Modern graphical user interface framework for Python.
- **requests** – Handles HTTP requests for downloading server files and updates.
- **psutil** – Provides system information (CPU, RAM, processes) for resource management.
- **packaging** – Utilities for version parsing and dependency handling.
- **playsound==1.2.2** – Lightweight library for playing notification sounds.
- **Pillow** – Image processing library, used for server icon feature.

---

## Contributing

Contributing, issues and pull requests are welcome!
Feedback is always appreciated ❤️

---

## License

**ZeroBlockBridge** © 2025 by **DesvoSoft**.

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

- **Documentation**: See [docs/USAGE.md](docs/USAGE.md) for detailed instructions.
- **Issues**: Report bugs or request features via GitHub Issues.
- **Discussions**: Share your server setups and get help from the community.

---

### Built by a player, for players, Minecraft creators & friends

![Privacy Friendly](https://img.shields.io/badge/Privacy-Friendly-green?style=for-the-badge&logo=shield)
![Community](https://img.shields.io/badge/Made_for-Minecraft_Community-blue?style=for-the-badge&logo=minecraft)
