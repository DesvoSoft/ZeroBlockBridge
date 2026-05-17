# Architecture

This document covers the internal architecture, auto-healing system, technical details, and design decisions of ZeroBlockBridge.

---

## Table of Contents

1. [Event-Driven Architecture](#event-driven-architecture)
2. [Interface Overview](#interface-overview)
3. [Auto-Healing System](#auto-healing-system)
   - [Watchdog Service](#watchdog-service-appserviceswatchdogpy)
   - [Heartbeat Monitor](#heartbeat-monitor-appservicesheartbeatpy)
   - [Lag Monitor](#lag-monitor-appserviceslag_monitorpy)
   - [Command Sanitizer](#command-sanitizer-appservicessanitizerpy)
   - [Notifications](#notifications)
4. [Project Structure](#project-structure)
5. [Technical Details](#technical-details)
   - [Supported Versions](#supported-versions)
   - [System Requirements](#system-requirements)
   - [Dependencies](#dependencies)
6. [Privacy & Service Disclaimer](#privacy--service-disclaimer)

---

## Event-Driven Architecture

The core and UI are decoupled via `EventBus`. `ZBBManager` serves as the single orchestrator, delegating all I/O to core/services modules. The UI subscribes to events and never performs blocking I/O directly.

- **Single Source of Truth**: Server state flows through `EventBus` (`STARTING`, `READY`, `STOPPED`, `TUNNEL_STATUS`).
- **Thread Safety**: Background threads use `daemon=True`; UI updates via `self.after(0, ...)`.
- **Command Sanitization**: Every console command passes through an allowlist-based sanitizer — no raw shell execution.

---

## Interface Overview

The application features:

- **Sidebar**: Server list with selection.
- **Dashboard**: Tunnel controls, auto-restart settings, quick backup (server start/stop merged into status bar).
- **Tabbed Console**: Console, Tunnel Log, and Mods (Modrinth Browser) tabs.
- **Console Input**: Send server commands directly from the UI.
- **Properties Editor**: 7 tabs (General, World, Network, Advanced, Backups, Automation, Launch).
- **Modrinth Mod Browser**: Search mods/plugins with pagination, loader/version filters, one-click install, and update checks.

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
│   └── roadmap.md                 # (local-only) Development roadmap
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
├── app/bin/                       # (Generated) playit agent binary
│
├── .zbb_cache/                    # (Generated) JDK cache directory
│   └── jdks/
│       └── <version>/
│           ├── bin/
│           │   └── java(.exe)
│           └── ...
│
├── app/config/                    # (Generated) App configuration
│   ├── config.json
│   └── versions_cache.json
│
└── README.md
```

---

## Technical Details

### Supported Versions

ZeroBlockBridge uses **dynamic version fetching** to support hundreds of Minecraft versions:

- **Vanilla**: Fetches top 100 releases from Mojang API (supports 26.x.x and 1.21.x schemes) with expanded offline defaults.
- **Fabric**: Fetches top 100 stable game versions from Fabric Meta API with latest installer.
- **Forge**: Fetches top 100 versions from Forge Promotions API with recommended/latest builds.
- **Paper**: Fetches top 100 versions from PaperMC API.
- **Purpur**: Fetches top 100 versions from PurpurMC API.
- **Smart Caching**: Auto-refreshes every 24h (background) + sync refresh if >2 days stale. Falls back to expanded defaults if offline.
- **Cache Location**: Stored in `config/versions_cache.json` for offline access.

### System Requirements

- **OS**: Windows / Linux
- **Python**: 3.10 or higher
- **Java**: Auto-managed — the app detects, downloads, and caches the required JDK (Adoptium, range 17-21) based on the Minecraft version. Blocks incompatible versions.
- **RAM**: 2 GB minimum (4 GB+ recommended for modded servers)
- **Disk**: ~37 MB for core app + ~107 MB per server (vanilla) + world size

### Dependencies

All required Python packages are listed in `requirements.txt`:

- **customtkinter** — Modern GUI framework (forks/extends Tkinter).
- **requests** — HTTP client for downloads and API calls.
- **psutil** — System resource monitoring (RAM, processes).
- **Pillow** — Image processing (server icons).

---

## Privacy & Service Disclaimer

ZeroBlockBridge is designed with simplicity and transparency in mind:

- **No Data Collection**: ZeroBlockBridge is not intended to collect, store, or transmit any personal information or usage data.
- **External Connections**: The app connects only to the services necessary for its operation:
  - **Playit.gg** — tunneling (optional, only if you enable it)
  - **Mojang** — version manifest and server jar downloads
  - **Modrinth** — mod/plugin browsing and downloads
  - **Fabric / Forge / Paper / Purpur APIs** — version fetches
  - **Adoptium** — JDK auto-install
- **User Control**: All server management, backups, and tunneling operations remain fully under the user's control.
