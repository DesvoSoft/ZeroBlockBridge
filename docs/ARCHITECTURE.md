# Architecture

This document covers the internal architecture, auto-healing system, technical details, and design decisions of ZeroBlockBridge.

> **Last updated:** 2026-07-05 — 461 tests, 100% pass. P0 complete, F5 (CrashReporter) + F6 (Discord Webhook) done. Playit agent migrated to v1.0.10 (playitd daemon); Paper API migrated to Fill v3.

---

## Table of Contents

1. [Event-Driven Architecture](#event-driven-architecture)
2. [Layer Separation](#layer-separation)
3. [Central Orchestrator: ZBBManager](#central-orchestrator-zbbmanager)
4. [Sub-Orchestrators](#sub-orchestrators)
5. [EventBus & ServerEvent](#eventbus--serverevent)
6. [Auto-Healing System](#auto-healing-system)
   - [Watchdog Service](#watchdog-service)
   - [Heartbeat Monitor](#heartbeat-monitor)
   - [Lag Monitor](#lag-monitor)
   - [CrashReporter](#crashreporter)
   - [Command Sanitizer](#command-sanitizer)
   - [Notifications](#notifications)
7. [Threading Model](#threading-model)
8. [Key Invariants](#key-invariants)
9. [Project Structure](#project-structure)
10. [Technical Details](#technical-details)
11. [Competitive Context](#competitive-context)
12. [Privacy & Service Disclaimer](#privacy--service-disclaimer)

---

## Event-Driven Architecture

The core and UI are **fully decoupled** via `EventBus`. `ZBBManager` is the single orchestrator; the UI subscribes to events and never performs blocking I/O or calls services directly.

```
UI emits event → ZBBManager receives → delegates to orchestrator/service
                                          → service emits result → UI updates
```

Rules:
- Use `events.subscribe()` — never `.on()`.
- UI updates only via `self.after(0, callback)` (Tkinter thread safety).
- No service or core module imports from `app/ui/`.

---

## Layer Separation

```
app/ui/        → Presentation only. No business logic. No direct service calls.
app/core/      → Orchestration, EventBus, business logic.
app/services/  → Specialized services (auto-healing, API clients, utilities).
```

Dependency direction is strictly one-way: `ui → core → services`. Never the reverse.

---

## Central Orchestrator: ZBBManager

**File:** `app/core/core.py` (~527 LOC)

Single source of truth for server lifecycle. Responsibilities:

- Holds references to `ServerRunner`, `Watchdog`, `HeartbeatMonitor`, `LagMonitor`, `CrashReporter`, `PlayitManager`, `VersionManager`, `DiscordWebhookService`.
- Delegates all operations to 4 sub-orchestrators (see below).
- Does **not** inherit Protocol classes (HAS-A, not IS-A — `ZBBManager` holds orchestrators as attributes).
- `_start_lock` prevents concurrent `start_server()` calls.
- `_restart_lock` prevents concurrent `_handle_restart_request()` calls.
- `_discord_webhook` is None when no webhook URL is configured (zero overhead).

### Key methods

| Method | Delegates to |
|--------|-------------|
| `start_server()` | `ServerOrchestrator.start_server()` |
| `stop_server()` | `ServerOrchestrator.stop_server()` |
| `restart_server()` | `ServerOrchestrator.restart_server()` |
| `create_backup()` | `BackupOrchestrator.create_backup()` |
| `restore_backup()` | `BackupOrchestrator.restore_backup()` |
| `start_tunnel()` | `TunnelOrchestrator.start_tunnel()` |
| `stop_tunnel()` | `TunnelOrchestrator.stop_tunnel()` |
| `schedule_restart()` | `SchedulerOrchestrator._start_tick_loop()` |

---

## Sub-Orchestrators

**File:** `app/core/orchestrators.py` (~224 LOC)

| Class | Responsibility |
|-------|---------------|
| `ServerOrchestrator` | start/stop/restart, Java resolution, monitor setup |
| `BackupOrchestrator` | ZIP backup create/atomic restore, auto-backup check |
| `TunnelOrchestrator` | Playit.gg agent lifecycle |
| `SchedulerOrchestrator` | Restart/backup scheduling tick loop (50ms interval) |

Protocol classes in `app/core/protocols.py` define structural typing contracts (structural, not inheritance).

### SchedulerOrchestrator tick loop

Runs every 50ms while server is online:
1. Emits `PLAYER_COUNT` (rate-limited to 1x/sec via `_last_player_emit` guard).
2. Checks `Scheduler.get_status()` — if `is_due`, emits `REQUEST_RESTART`.
3. If `status["missed"]` is True (daily-time restart window passed >120s ago), emits WARNING log + `NOTIFICATION` toast to user.
4. Calls `backup_orchestrator._check_auto_backup()` every `SCHEDULER_CHECK_INTERVAL`.

---

## EventBus & ServerEvent

**File:** `app/core/server_events.py`

`EventBus` uses `threading.RLock` for thread-safe subscribe/unsubscribe/emit. Listeners are copied before iteration so unsubscriptions during emit are safe.

### Active ServerEvent enum values

| Event | Emitter | Subscribers |
|-------|---------|------------|
| `STARTING` | `ServerOrchestrator` | UI status bar |
| `READY` | `ServerRunner` (stdout parse) | ZBBManager, UI, DiscordWebhook |
| `STOPPED` | `ServerRunner` | ZBBManager, Watchdog, UI |
| `CRASHED` | `Watchdog` | ZBBManager (`_on_server_crashed`), `CrashReporter`, `DiscordWebhook` |
| `RESTARTED` | `Watchdog` | available for future UI subscribers |
| `PLAYER_COUNT` | `SchedulerOrchestrator` tick | UI sidebar |
| `PLAYER_LIST` | `ServerRunner` (stdout parse) | UI player dashboard |
| `ZOMBIE_DETECTED` | `HeartbeatMonitor` | Watchdog |
| `LAG_SPIKE` | `LagMonitor` | UI toast |
| `CONSOLE_LINE` | `ServerRunner` | UI console, ZBBManager buffer |
| `TUNNEL_CONSOLE_LINE` | `PlayitManager` | UI tunnel log, ZBBManager buffer |
| `TUNNEL_STATUS` | `PlayitManager` | ZBBManager, UI tunnel panel |
| `NOTIFICATION` | Multiple | UI toast system |
| `REQUEST_RESTART` | `SchedulerOrchestrator`, Watchdog | ZBBManager |
| `BACKUP_COMPLETED` | `BackupOrchestrator` | UI, DiscordWebhook |
| `BACKUP_FAILED` | `BackupOrchestrator` | UI, DiscordWebhook |

**Removed:** `TPS_UPDATE` (fake value, removed commit `0b964fd`), `ERROR` (never emitted, removed commit `0b964fd`).

---

## Auto-Healing System

Four coordinated services detect, classify, and recover from server failures.

### Watchdog Service

**File:** `app/services/watchdog.py` (~172 LOC)

Monitors server process exit code and stderr to classify crashes:

| Crash Type | Detection | Recovery |
|---|---|---|
| `jvm_config_error` | stderr: "UnsupportedClassVersionError", "Could not find main class" | Retry with backoff |
| `out_of_memory` | stderr: "OutOfMemoryError", "GC overhead limit" | Retry with backoff |
| `oom_kill` | Exit code 137 (Linux OOM kill) | Retry with backoff |
| `boot_crash` | Exit code 1, uptime < 5s | Retry with backoff |
| `runtime_crash` | Exit code 1, uptime ≥ 5s | Retry with backoff |
| `signal_N` | Negative exit code (segfault = -11) | Retry with backoff |

- **Backoff**: `base × 2^(n-1)`, capped at **3600s** max.
- **Stability reset**: Counter resets after 10 minutes of `READY` uptime.
- **Intentional stop guard**: `stop_server()` sets a flag before stopping; Watchdog ignores STOPPED events when flag is set — prevents accidental restart on clean shutdown.
- **Emits**: `CRASHED` (with payload `{"reason": str, "exit_code": int, "retry_attempt": int}`), `RESTARTED`.
- **Does NOT emit NOTIFICATION** — only `ZBBManager._on_server_crashed` owns crash notifications (audit CA-01).

### Heartbeat Monitor

**File:** `app/services/heartbeat.py` (~63 LOC)

Detects zombie servers (JVM alive but unresponsive to commands):

- Watches console output. If silent for >5 minutes, sends a `list` command.
- `_last_probe` set **before** `send_command()` to avoid race condition (HA-02 fix).
- If no console response within 15 seconds → emits `ZOMBIE_DETECTED`.
- Watchdog subscribes to `ZOMBIE_DETECTED` and triggers auto-restart.

### Lag Monitor

**File:** `app/services/lag_monitor.py` (~35 LOC)

- Matches `"Can't keep up!"` in server console output.
- Sliding window: 5 spikes within 5 minutes → emits `LAG_SPIKE`.
- After emitting, clears spikes — if sustained lag continues, threshold re-triggers.

### CrashReporter

**File:** `app/services/crash_reporter.py` (~80 LOC)

Subscribes to `CRASHED` event. On each crash:

1. Snapshots console buffer (last N lines) and stderr buffer.
2. Collects system info (`platform`, RAM, CPU count).
3. Writes JSON report to `servers/<name>/crash_reports/crash_<timestamp>_<uuid>.json`.
4. Rotates to max 50 reports per server (FIFO deletion of oldest).

**Report schema:**
```json
{
  "schema_version": 1,
  "timestamp": "2026-06-24T14:30:22",
  "server": { "name": "...", "version": "1.20.1", "type": "Fabric", "ram": "2G" },
  "crash": { "reason": "out_of_memory", "exit_code": 1, "retry_attempt": 2 },
  "stderr_tail": ["..."],
  "console_tail": ["..."],
  "system_info": { "os": "Windows 10", "ram_gb": 15.9, "cpu_count": 8 },
  "watchdog_state": { "max_retries": 3, "current_retries": 2 }
}
```

### Command Sanitizer

**File:** `app/services/sanitizer.py` (~64 LOC)

- **Allowlist**: 80+ known-safe Minecraft commands (op, deop, say, gamemode, etc.).
- **Character filter**: Rejects `;`, `|`, `&`, `` ` ``, `$()`, `${}`, `\n`. `%` is **allowed** (valid in MC commands like `op %USERNAME%`).
- Unknown commands: allowed if they pass the character filter (forward-compatible).
- Commands go to server stdin — not to a shell. `shell=True` is banned.

### Notifications

All auto-healing events surface via the **Toast** system (`app/ui/toast.py`):

- Toast corner_radius = 0 (intentional design exception to the corner_radius=12 rule).
- `NOTIFICATION` payload: always `{"msg": str, "type": "error"|"warning"|"info"}`. Never `color` key.
- `_on_server_crashed` in `core.py` is the single owner of crash notifications.
- Scheduled restart missed window: `SchedulerOrchestrator` emits `NOTIFICATION` type="warning".
- Discord Webhook: parallel notification channel for CRASHED, READY, BACKUP_COMPLETED, BACKUP_FAILED.

---

## Threading Model

- All background threads: `daemon=True`.
- UI updates: always via `self.after(0, callback)`.
- `ServerRunner.running`: property backed by `_state_lock` (threading.Lock) — prevents TOCTOU race in Watchdog `_do_restart()`.
- `ServerRunner.connected_players`: all join/leave mutations inside `_players_lock`; cleared in `start()` to prevent stale player data after restart.
- `EventBus`: `threading.RLock` for subscribe/emit.
- `SettingsManager`: double-checked locking, debounced flush (500ms timer).
- `BackupOrchestrator`: `_backup_lock` + `_backup_in_progress` flag prevents concurrent backups.
- `DiscordWebhookService`: single `queue.Queue` worker thread, 2s rate-limit between POSTs.

---

## Key Invariants

These rules must never be violated:

1. **`open()` → `encoding="utf-8"` always** for text files. MOTD with `§` corrupts on Windows without it.
2. **`strptime` on user filenames** → always `try/except ValueError`. Users can drop arbitrary files.
3. **`NOTIFICATION` payload** → always `{"msg": ..., "type": "error"|"warning"|"info"}`. Never `color` key.
4. **Watchdog must not emit `NOTIFICATION`** → only `_on_server_crashed` in core.py owns crash notifications.
5. **Fabric/Forge installers** → always receive resolved `java_bin` from ZBBManager, never assume `"java"` from PATH.
6. **Atomic file ops** → before reading a file written by another thread, verify `os.path.exists` + `os.path.getsize > 0` with timeout (OS may not flush immediately).
7. **`ServerState` enum lives in `constants.py`** — not in `core.py`, preventing circular imports.
8. **Scheduler missed window** → if daily-time restart target passed >120s ago and `check_due()` returns False, `get_status()["missed"]` is True. Orchestrator logs WARNING + notifies user.
9. **Every spawned child process (Minecraft server, playit agent) is assigned to a Windows Job Object** (`app/core/process_job.py`, `KILL_ON_JOB_CLOSE`) so the OS reaps it even on a hard parent death (crash, taskkill, closed console) that skips `atexit`. Children spawned by a job member inherit the job automatically — Fabric/Forge's inner java is covered too.
10. **Port preflight before server start** → `ServerRunner.start()` checks the configured port isn't already bound before spawning, failing with a clear toast instead of a Minecraft bind-crash.

---

## Project Structure

```text
ZeroBlockBridge/
├── app/
│   ├── launcher.py                    # Entry point (9 LOC)
│   │
│   ├── ui/                            # Presentation Layer — no business logic
│   │   ├── main.py                    # MCTunnelApp: main window, layout, subscriptions (~1009 LOC)
│   │   ├── server_wizard.py           # 3-step creation wizard (~630 LOC)
│   │   ├── server_properties_editor.py# 7-tab properties editor (~754 LOC)
│   │   ├── modrinth_browser.py        # Modrinth mod browser (~730 LOC)
│   │   ├── players_dashboard.py       # Player management: online list + whitelist (~222 LOC)
│   │   ├── toast.py                   # Non-blocking notification overlay (~159 LOC)
│   │   └── ui_components.py           # ConsoleWidget, ServerListItem (right-click delete menu), ToolTip, Dialog, EulaDialog (~422 LOC)
│   │
│   ├── core/                          # Orchestration & Business Logic
│   │   ├── core.py                    # ZBBManager — central orchestrator (~527 LOC)
│   │   ├── logic.py                   # ServerRunner, Scheduler, downloads, metadata, delete_server, port preflight (~876 LOC)
│   │   ├── orchestrators.py           # ServerOrchestrator, BackupOrchestrator, TunnelOrchestrator, SchedulerOrchestrator (~224 LOC)
│   │   ├── protocols.py               # Protocol classes for structural typing (~36 LOC)
│   │   ├── process_job.py             # Windows Job Object helper — reaps children on hard parent death (~83 LOC)
│   │   ├── playit_manager.py          # Playit.gg agent (v1.0.10 playitd daemon) lifecycle, DNS recovery (~790 LOC)
│   │   ├── version_manager.py         # Dynamic version fetch (Fill API v3 for Paper), 24h cache (~420 LOC)
│   │   ├── server_events.py           # EventBus + ServerEvent enum (~53 LOC)
│   │   ├── statemanager.py            # Tunnel status debounce (module-level vars, Lock)
│   │   ├── app_config.py              # UI tokens: colors, fonts, timeouts (~57 LOC)
│   │   ├── constants.py               # Paths, URLs, ServerState enum (~48 LOC)
│   │   └── single_instance.py         # PID lockfile — prevents duplicate instances (~71 LOC)
│   │
│   └── services/                      # Specialized Services & Auto-Healing
│       ├── watchdog.py                # Crash detection & exponential backoff restart (~172 LOC)
│       ├── heartbeat.py               # Zombie detection via /list probe (~63 LOC)
│       ├── lag_monitor.py             # TPS lag detection via sliding window (~35 LOC)
│       ├── crash_reporter.py          # JSON crash diagnostic reports, 50-report FIFO (~80 LOC)
│       ├── discord_webhook.py         # Discord webhook notifications via queue worker (~80 LOC)
│       ├── backup_manager.py          # ZIP backup create + atomic restore (~153 LOC)
│       ├── sanitizer.py               # Command allowlist + injection char filter (~64 LOC)
│       ├── java_detector.py           # System Java detection + portable JDK scan (~416 LOC)
│       ├── java_installer.py          # JDK auto-download from Adoptium API (~322 LOC)
│       ├── bytecode_analyzer.py       # JAR bytecode → required Java version (~119 LOC)
│       ├── aikars_flags.py            # Optimal JVM flags by RAM tier (~103 LOC)
│       ├── scaffolder.py              # Server directory + eula + server.properties scaffold (~152 LOC)
│       ├── server_properties.py       # server.properties read/write (~59 LOC)
│       ├── playit_api.py              # Playit.gg REST API v2 client (~466 LOC)
│       ├── modrinth.py                # Modrinth API client + mod tracker (~329 LOC)
│       ├── sha1_validator.py          # SHA1-verified download with retry (~117 LOC)
│       ├── console_buffer.py          # Thread-safe console buffer (collections.deque)
│       └── settings_manager.py        # App config singleton read/write, debounced flush
│
├── tests/                             # 24 test files, 461 tests, 100% pass
│   ├── conftest.py                    # FakeEmitter (EventBus stub), FakeRunner
│   ├── test_orchestrators.py          # 26 tests — all 4 orchestrators
│   ├── test_logic.py                  # ServerRunner, Scheduler, normalize, meta (~24 tests)
│   ├── test_crash_reporter.py         # 11 tests
│   ├── test_discord_webhook.py        # 10 tests
│   ├── test_watchdog.py               # Watchdog + backoff
│   ├── test_heartbeat.py              # HeartbeatMonitor
│   ├── test_playit_manager.py         # PlayitManager lifecycle
│   ├── test_version_manager.py        # VersionManager fetch + cache
│   ├── test_java_installer.py         # JDK download + checksum
│   ├── test_backup_scheduler.py       # BackupScheduler (12 tests)
│   ├── test_backup_manager.py         # BackupManager create/restore/retention
│   └── ... (10 more)
│
├── pyproject.toml                     # Project metadata, requires-python>=3.10, deps
├── requirements.txt                   # Pinned minimum versions (5 deps)
├── roadmap.md                         # Development roadmap (local, not published)
├── docs/
│   ├── ARCHITECTURE.md                # This file
│   ├── SKILL.md                       # AI assistant development guide
│   └── STANDARDS.md                   # Coding standards & quality criteria
│
├── servers/                           # (Generated) Per-server data
│   └── <server-name>/
│       ├── server.jar
│       ├── server.properties
│       ├── metadata.json              # {name, version, type, ram, ...}
│       └── crash_reports/             # JSON crash diagnostics (max 50, FIFO)
│
├── backups/                           # (Generated) ZIP backups
│   └── <server-name>/
│       └── YYYY-MM-DD_HH-MM-SS.zip
│
├── app/bin/                           # (Generated) Playit.gg agent binary
├── .zbb_cache/jdks/<version>/         # (Generated) Portable JDK cache (Adoptium)
└── app/config/                        # (Generated) App configuration + version cache
```

---

## Technical Details

### Supported Server Types & Java Mapping

| Java Version | MC Range | Notes |
|---|---|---|
| Java 21 | MC ≥ 1.20.5 | Also required by Fabric 0.15+ on newer MC |
| Java 17 | MC 1.18 – 1.20.4 | Most common modern range |
| Java 16 | MC 1.17 – 1.17.1 | |
| Java 8 | MC < 1.17 | Legacy servers |

JDK auto-downloaded from **Adoptium** to `.zbb_cache/jdks/{version}/` — never modifies system PATH. Bytecode analyzer (`bytecode_analyzer.py`) extracts required version from the server JAR class files, with a floor of `get_required_java(mc_version)` to prevent Forge shim misdetection.

### Dynamic Version Fetching

`VersionManager` fetches top 100 versions per type:

| Type | API |
|------|-----|
| Vanilla | Mojang manifest |
| Fabric | Fabric Meta API |
| Forge | Forge Promotions API |
| Paper | PaperMC API |
| Purpur | PurpurMC API |

- Cache: `config/versions_cache.json`, auto-refreshed every 24h in background.
- Lazy init: `VersionManager` instantiated on first use (not in `ZBBManager.__init__`) to avoid blocking startup.
- UI freeze fix: `get_versions()` does not block on `thread.join()` — uses callback path to notify when refresh completes.

### Discord Webhook

`DiscordWebhookService` (`app/services/discord_webhook.py`):
- Activated only when `discord_webhook_url` is set in `SettingsManager`.
- Single `queue.Queue` worker thread, 2s rate-limit between POSTs.
- Subscribes to: `CRASHED` (red embed), `READY` (green), `BACKUP_COMPLETED` (blue), `BACKUP_FAILED` (orange).
- URL is never logged.
- Configured via `SettingsManager().set("discord_webhook_url", "https://...")`.

### Scheduled Restart Logic

`Scheduler` in `logic.py` supports two modes:

- **Interval** (`type="interval"`): restart every N hours from last run.
- **Daily time** (`type="time"`): restart at HH:MM every day. Check window: 0–120s after target. If >120s past → `get_status()["missed"] = True` → orchestrator warns user.

Warning threshold messages emitted before restart: 1h, 30m, 15m, 1m.

### System Requirements

- **OS**: Windows 10+ / Linux
- **Python**: 3.10 or higher (tested on 3.14)
- **Java**: Auto-managed (Adoptium, Java 8–21)
- **RAM**: 2 GB minimum for ZBB + server (4 GB+ recommended for modded)
- **Disk**: ~37 MB app + ~107 MB per vanilla server + world size

### Dependencies

Defined in `pyproject.toml` and `requirements.txt`:

| Package | Purpose |
|---------|---------|
| `customtkinter>=5.2.2` | Modern GUI (extends Tkinter) |
| `requests>=2.33.1` | HTTP client (downloads, API calls) |
| `Pillow>=12.2.0` | Server icon image processing |
| `psutil>=7.2.2` | System resource monitoring |
| `packaging>=26.0` | Version comparison utilities |

---

## Competitive Context

Analysis vs **auto-mcs** (Python server manager) and **Prism Launcher** (Qt client) — 2026-06-23.

### ZBB Unique Differentiators

| Feature | ZBB | auto-mcs | Prism |
|---------|-----|---------|-------|
| Heartbeat zombie detection | ✅ unique | ❌ | ❌ |
| TPS lag sliding window | ✅ unique | ❌ | ❌ |
| Exponential backoff recovery | ✅ documented | basic | ❌ |
| Bytecode Java floor analysis | ✅ unique | ❌ | ❌ |
| Scheduler (restart + backup) | ✅ | ✅ | ❌ |
| Tunnel integration | ✅ Playit.gg | ✅ Playit.gg | ❌ |
| Discord webhook | ✅ | ✅ | ❌ |
| Crash diagnostic JSON | ✅ unique | ❌ | ❌ |

### Pending High-Priority Gaps (CA-HIGH)

| ID | Feature | Target file |
|----|---------|------------|
| CA-H01 | JVM args UI per-server | `logic.py`, `server_properties_editor.py` |
| CA-H02 | Unified player management (ops+bans+whitelist) | `players_dashboard.py` |
| CA-H03 | Console search/filter | `ui_components.py` (ConsoleWidget) |
| CA-H04 | World switching UI | `server_properties_editor.py` |

See `roadmap.md → COMPETITIVE-ANALYSIS` for full table, effort estimates, and execution order.

---

## Privacy & Service Disclaimer

- **No Data Collection**: ZBB does not collect, store, or transmit personal data or usage telemetry.
- **External Connections**: Only to services required for operation:
  - **Playit.gg** — tunneling (optional, user-enabled)
  - **Mojang** — version manifest + server jar downloads
  - **Modrinth** — mod/plugin browsing and downloads
  - **Fabric / Forge / Paper / Purpur APIs** — version lists
  - **Adoptium** — JDK auto-install
  - **Discord** — webhook notifications (optional, user-configured)
- **User Control**: All server management, backups, tunneling, and webhook operations remain fully under user control.
