# Architecture

This document covers the internal architecture, auto-healing system, technical details, and design decisions of ZeroBlockBridge.

> **Last updated:** 2026-09-14 — 633 tests in 36 files, 100% pass. Since v2.0.0: configurable data directory, explainable command safety, pre-update snapshots routed through `BackupOrchestrator`, Java 25 for MC 26.x, light-mode GUI fixes.

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
   - [Pre-Update Snapshots](#pre-update-snapshots)
   - [Notifications](#notifications)
7. [Threading Model](#threading-model)
8. [Key Invariants](#key-invariants)
9. [Data Directory](#data-directory)
10. [Project Structure](#project-structure)
11. [Technical Details](#technical-details)
12. [Build & Release](#build--release)
13. [Competitive Context](#competitive-context)
14. [Privacy & Service Disclaimer](#privacy--service-disclaimer)

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
- No service or core module imports from `app/ui/` (one documented exception: `bootstrap.resolve_data_dir()` opens the first-run dialog before any window exists).
- Mutating flows (start/stop/backup/restart/snapshot) go through `ZBBManager`. When a UI widget needs one, it receives the manager method as an injected callback (e.g. `ModrinthBrowser(create_snapshot=zbb_manager.create_pre_update_snapshot)`) instead of importing the service.
- Pragmatic exception: UI may import services for read-only/stateless helpers (load properties, list templates, disk usage).

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

**File:** `app/core/core.py` (~656 LOC)

Single source of truth for server lifecycle. Responsibilities:

- Holds references to `ServerRunner`, `Watchdog`, `HeartbeatMonitor`, `LagMonitor`, `CrashReporter`, `PlayitManager`, `VersionManager`, `DiscordWebhookService`.
- Delegates lifecycle, backup, tunnel, and scheduling work to 4 sub-orchestrators (see below). Java resolution (`_resolve_java_bin`, `_auto_install_java`) and process launch (`_launch_server`) stay on the manager and are called by `ServerOrchestrator.start_server()`.
- Does **not** inherit Protocol classes (HAS-A, not IS-A — `ZBBManager` holds orchestrators as attributes).
- `_start_lock` prevents concurrent `start_server()` calls; `_restart_lock` and `_mod_install_lock` guard the `REQUEST_RESTART` / `REQUEST_MOD_INSTALL` handlers.
- `_discord_webhook` is None when no webhook URL is configured (zero overhead); `reload_discord_webhook()` re-creates it after a settings change.

### Key methods

| Method | Delegates to / does |
|--------|-------------|
| `start_server()` | `ServerOrchestrator.start_server()` |
| `stop_server()` | `ServerOrchestrator.stop_server()` (full monitor teardown first) |
| `send_command(cmd)` | `ServerOrchestrator.send_command()` — sanitizer gate |
| `is_running()` | `ServerOrchestrator.is_running()` |
| `create_pre_update_snapshot(name)` | `BackupOrchestrator.create_pre_update_snapshot()` — blocking, call from a worker |
| `start_tunnel()` / `stop_tunnel()` / `reset_tunnel(mode)` | `TunnelOrchestrator` |
| `create_tunnel_for_server(name)` / `get_tunnel_ip()` | `TunnelOrchestrator` |
| `select_server(name)` / `load_server_manually(path)` | Active server selection / import via junction |
| `list_managed_jdks()` / `purge_jdk(v)` / `purge_unused_jdks()` / `purge_crash_reports()` | Storage maintenance (Settings → Storage) |
| `shutdown()` | App exit: stops tick loop, webhook, monitors; tunnel and server teardown in parallel |

Scheduled restarts and mod-dependency installs arrive as `REQUEST_RESTART` / `REQUEST_MOD_INSTALL` events rather than direct calls.

---

## Sub-Orchestrators

**File:** `app/core/orchestrators.py` (~275 LOC)

| Class | Responsibility |
|-------|---------------|
| `ServerOrchestrator` | start/stop, disk-space preflight, command safety gate (`send_command`) |
| `BackupOrchestrator` | Scheduled auto-backup check/run, pre-update snapshots (running-server guard, partial-snapshot discard) |
| `TunnelOrchestrator` | Playit.gg agent lifecycle |
| `SchedulerOrchestrator` | Tick loop: player-count sync, heartbeat tick, restart/backup scheduling |

Manual backup create/restore is done by `BackupManager` from the Backups tab (`server_properties_editor.py`). Protocol classes in `app/core/protocols.py` define structural typing contracts (structural, not inheritance).

### SchedulerOrchestrator tick loop

Runs every 100ms (`ServerTickThread`) while the app is open:
1. Ticks `HeartbeatMonitor` (it decides on its own 60s cadence).
2. Emits `PLAYER_COUNT` only when the count changes (checked 1x/sec — safety-net resync; join/leave already emit).
3. Every `SCHEDULER_CHECK_INTERVAL` (30s): checks `Scheduler.get_status()` — if due, sends countdown warnings and emits `REQUEST_RESTART`.
4. If `status["missed"]` is True (daily-time restart window passed >120s ago), logs WARNING + emits a `NOTIFICATION` toast once per day.
5. Calls `backup_orchestrator._check_auto_backup()` on the same 30s cadence.

---

## EventBus & ServerEvent

**File:** `app/core/server_events.py`

`EventBus` uses `threading.RLock` for thread-safe subscribe/unsubscribe/emit. Listeners are copied before iteration so unsubscriptions during emit are safe.

### Active ServerEvent enum values

| Event | Emitter | Subscribers |
|-------|---------|------------|
| `STARTING` | `ServerRunner` / ZBBManager | Watchdog, UI status bar |
| `READY` | `ServerRunner` (stdout parse) | ZBBManager, Watchdog (stability window), UI |
| `STOPPED` | `ServerRunner` | Watchdog, UI |
| `CRASHED` | `Watchdog` | ZBBManager (`_on_server_crashed`), `CrashReporter` |
| `RESTARTED` | `Watchdog` | — (Discord only, opt-in) |
| `PLAYER_COUNT` | `ServerRunner` join/leave, `SchedulerOrchestrator` resync | UI sidebar |
| `PLAYER_LIST` | `ServerRunner` (stdout parse) | UI player dashboard |
| `ZOMBIE_DETECTED` | `HeartbeatMonitor` | Watchdog |
| `LAG_SPIKE` | `LagMonitor` | UI toast |
| `CONSOLE_LINE` | `ServerRunner`, orchestrators, monitors | UI console, ZBBManager buffer, Heartbeat, LagMonitor |
| `TUNNEL_CONSOLE_LINE` | `PlayitManager` (via ZBBManager callback) | UI tunnel log, ZBBManager buffer |
| `TUNNEL_STATUS` | ZBBManager (`_on_playit_status`) | UI tunnel panel |
| `NOTIFICATION` | Multiple | UI toast system |
| `REQUEST_RESTART` | `SchedulerOrchestrator` | ZBBManager |
| `REQUEST_MOD_INSTALL` | UI (missing-mod toast action) | ZBBManager (`_handle_mod_install_request`) |
| `BACKUP_COMPLETED` | `BackupOrchestrator` (auto-backup, pre-update snapshot) | — (Discord only) |
| `BACKUP_FAILED` | `BackupOrchestrator` | — (Discord only) |

`DiscordWebhookService` additionally subscribes to whichever events the user enabled in Settings → Notifications (see [Discord Webhook](#discord-webhook)).

**Removed:** `TPS_UPDATE` (fake value, removed commit `0b964fd`), `ERROR` (never emitted, removed commit `0b964fd`).

---

## Auto-Healing System

Four coordinated services detect, classify, and recover from server failures.

### Watchdog Service

**File:** `app/services/watchdog.py` (~264 LOC)

Classifies a non-zero exit (checked in this order) from exit code, stderr, and console tail:

| Crash Type | Detection |
|---|---|
| `jvm_config_error` | stderr: "UnsupportedClassVersionError", "Could not find main class" |
| `mod_dependency_error` | console: Fabric/Forge missing-dependency patterns — extracts detail + missing mod IDs |
| `out_of_memory` | stderr: "OutOfMemoryError", "GC overhead limit" |
| `oom_kill` | Exit code 137 / -9 |
| `boot_crash` | Exit code 1, uptime < 5s |
| `runtime_crash` | Exit code 1, uptime ≥ 5s |
| `signal_N` | Other negative exit code (segfault = -11) |
| `exit_N` | Any other exit code |

- **Recovery**: every type retries with backoff, up to `watchdog_max_retries` from the app config (default 3); then auto-restart stops.
- **Backoff**: `base × 2^(n-1)` (base 5s), capped at **3600s** max.
- **Stability reset**: Counter resets after 10 minutes of `READY` uptime.
- **Clean stop**: exit code 0 is logged and resets the counter — no restart. `stop_server()` also tears monitors down before stopping, so the watchdog never sees an intentional stop.
- **Zombie handling**: `_do_restart(context="zombie")` kills the hung process via `runner.stop()` first; the resulting STOPPED is swallowed by `_zombie_kill_pending` (no double CRASHED/restart).
- **Emits**: `CRASHED` (payload: `reason`, `exit_code`, `uptime`, `retry`, `detail`, `missing_mod_ids`), `RESTARTED`.
- **Does NOT emit NOTIFICATION** — only `ZBBManager._on_server_crashed` owns crash notifications (audit CA-01). For `mod_dependency_error` with known IDs it adds `action="mod_dependency_fix"`, which the UI turns into a one-click `REQUEST_MOD_INSTALL`.

### Heartbeat Monitor

**File:** `app/services/heartbeat.py` (~95 LOC)

Detects zombie servers (JVM alive but unresponsive to commands):

- Ticked by the scheduler loop; checks every 60s (`check_interval`). If the console has been silent for 300s (`suspect_after`), sends a `list` probe.
- `_last_probe` set **before** `send_command()` to avoid race condition (HA-02 fix).
- If no console response within 15s (`probe_timeout`) → emits `ZOMBIE_DETECTED`.
- Watchdog subscribes to `ZOMBIE_DETECTED` and triggers auto-restart.

### Lag Monitor

**File:** `app/services/lag_monitor.py` (~49 LOC)

- Matches `"Can't keep up!"` in server console output.
- Sliding window: 5 spikes within 5 minutes → emits `LAG_SPIKE`.
- After emitting, clears spikes — if sustained lag continues, threshold re-triggers.

### CrashReporter

**File:** `app/services/crash_reporter.py` (~135 LOC)

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

**File:** `app/services/sanitizer.py` (~101 LOC)

- **Allowlist**: 80+ known-safe Minecraft commands (op, deop, say, gamemode, etc.).
- **Character filter**: Rejects `;`, `|`, `&`, `` ` ``, `$()`, `${}`, `\n`. `%` is **allowed** (valid in MC commands like `op %USERNAME%`).
- Unknown commands: allowed if they pass the character filter (forward-compatible).
- Commands go to server stdin — not to a shell. `shell=True` is banned.
- **Explainable Safety** (2026-08-03): `is_safe_command()` returns `(bool, BlockedReason | None)` — a `str`-mixin enum (`EMPTY`, `SHELL_METACHARACTERS`, `INJECTION_PATTERN`, `SUSPICIOUS_UNKNOWN`) whose values are the user-facing text. A blocked command emits both a `[Security]`-prefixed `CONSOLE_LINE` and a `NOTIFICATION` warning toast built by `describe_blocked()` (names the command, truncated to 40 chars, newlines collapsed) — no more silent no-op. The console red tint matches the `[Security]` **prefix only**, so player chat containing that text cannot spoof an alert. Settings → General shows the full sorted allowlist read-only, so the claim is user-auditable. Single enforcement point: `ServerOrchestrator.send_command` (the UI no longer duplicates this check).

### Pre-Update Snapshots

**File:** `app/core/orchestrators.py` (`BackupOrchestrator.create_pre_update_snapshot`), `app/services/backup_manager.py`, `app/ui/modrinth_browser.py`

- Mod updates (single-badge and bulk "Update Selected") call `ZBBManager.create_pre_update_snapshot(server_name)` — injected into `ModrinthBrowser` as the `create_snapshot` callback, so the UI never touches `BackupManager` — before any file changes. Ordering lives in the pure helper `_snapshot_then_apply`: snapshot failure aborts the update rather than proceeding without a rollback point.
- The orchestrator refuses a snapshot when the target is the active, running server (locked files), when another backup holds `_backup_in_progress`, and **discards** a snapshot that skipped locked files instead of reporting it as a usable rollback point. Emits `BACKUP_COMPLETED` / `BACKUP_FAILED` like scheduled backups.
- Tagged backups (`{timestamp}__{reason}.zip`) are retention-scoped by `reason` — pruning pre-update snapshots (default cap: 5) can never delete a user's manual/scheduled backups, and vice versa.
- Rollback reuses the existing Backups tab restore flow (`server_properties_editor.py`), which now labels pre-update snapshots ("Pre-Update — ...") instead of introducing a second restore path.

### Notifications

All auto-healing events surface via the **Toast** system (`app/ui/toast.py`):

- Toast `corner_radius=0` (intentional design exception to the `RADIUS_*` token scale).
- `NOTIFICATION` payload: always `{"msg": str, "type": "error"|"warning"|"info"|"success"}`. Never `color` key. Only functional extension: `action` + `missing_mod_ids` (mod dependency fix flow).
- `_on_server_crashed` in `core.py` is the single owner of crash notifications.
- Scheduled restart missed window: `SchedulerOrchestrator` emits `NOTIFICATION` type="warning" (once per day).
- Blocked console command / pre-update snapshot outcome: see sections above.
- Discord Webhook: parallel, opt-in channel — see [Discord Webhook](#discord-webhook).

---

## Threading Model

- All background threads: `daemon=True`.
- UI updates: always via `self.after(0, callback)`.
- `ServerRunner.running`: property backed by `_state_lock` (threading.Lock) — prevents TOCTOU race in Watchdog `_do_restart()`.
- `ServerRunner.connected_players`: all join/leave mutations inside `_players_lock`; cleared in `start()` to prevent stale player data after restart.
- `EventBus`: `threading.RLock` for subscribe/emit.
- `SettingsManager`: double-checked locking, debounced flush (500ms timer).
- `BackupOrchestrator`: `_backup_lock` + `_backup_in_progress` flag prevents a scheduled auto-backup and a pre-update snapshot from running at the same time.
- `ZBBManager.executor`: shared `ThreadPoolExecutor(max_workers=8)`. Work that must block on another job (e.g. the backup before a scheduled restart) uses a dedicated thread instead, to avoid pool starvation.
- `DiscordWebhookService`: single `queue.Queue` worker thread, 2s rate-limit between POSTs.

---

## Key Invariants

These rules must never be violated:

1. **`open()` → `encoding="utf-8"` always** for text files. MOTD with `§` corrupts on Windows without it.
2. **`strptime` on user filenames** → always `try/except ValueError`. Users can drop arbitrary files.
3. **`NOTIFICATION` payload** → always `{"msg": ..., "type": "error"|"warning"|"info"|"success"}`. Never `color` key.
4. **Watchdog must not emit `NOTIFICATION`** → only `_on_server_crashed` in core.py owns crash notifications.
5. **Fabric/Forge installers** → always receive resolved `java_bin` from ZBBManager, never assume `"java"` from PATH.
6. **Atomic file ops** → before reading a file written by another thread, verify `os.path.exists` + `os.path.getsize > 0` with timeout (OS may not flush immediately).
7. **`ServerState` enum lives in `constants.py`** — not in `core.py`, preventing circular imports.
8. **Scheduler missed window** → if daily-time restart target passed >120s ago and `check_due()` returns False, `get_status()["missed"]` is True. Orchestrator logs WARNING + notifies user.
9. **Every spawned child process (Minecraft server, playit agent) dies with ZBB** (`app/core/process_job.py`). Windows: assigned to a Job Object with `KILL_ON_JOB_CLOSE`, so the OS reaps it even on a hard parent death (crash, taskkill, closed console) that skips `atexit`; children of a job member inherit the job — Fabric/Forge's inner java is covered too. Linux: `linux_preexec()` sets `prctl(PR_SET_PDEATHSIG, SIGKILL)` at spawn.
10. **Port preflight before server start** → `ServerRunner.start()` checks the configured port isn't already bound before spawning, failing with a clear toast instead of a Minecraft bind-crash.
11. **Data directory resolved first** → `bootstrap.resolve_data_dir()` runs before `app.core.constants` is imported; nothing may compute `BASE_DIR`-derived paths at import time earlier than that.
12. **Mod updates need a complete rollback point** → no mod file is touched unless `create_pre_update_snapshot` returned a path; partial snapshots are discarded.

---

## Data Directory

**Files:** `app/core/bootstrap.py`, `app/core/constants.py`, `app/ui/first_run_dialog.py`

`BASE_DIR` (parent of `servers/`, `backups/`, `config/`, `bin/`, `.zbb_cache/`) is resolved at startup:

| Mode | `BASE_DIR` |
|------|-----------|
| Running from source | Repo root — no marker, no dialog |
| Frozen build, marker present and writable | Path stored in the marker |
| Frozen build, `servers/` or `config/` already next to the exe | Exe folder, adopted silently (pre-feature installs) |
| Frozen build, first run | First-run dialog: **Standard** (`%LOCALAPPDATA%\ZeroBlockBridge`; Linux `~/ZeroBlockBridge`), **Portable** (next to the exe), or **Custom** |

- The choice is persisted in `install.json` under `%LOCALAPPDATA%\ZeroBlockBridge\` (Linux: `~/.zeroblockbridge/`) and exported as `ZBB_DATA_DIR` before `constants` is imported, which honors that variable first.
- Bundled read-only assets always come from the PyInstaller `_MEIPASS` dir, independent of `BASE_DIR`.
- Settings → Storage shows the active location (with **Open Folder**) and disk usage for Servers, Backups, Java runtimes, Crash reports, and Versions cache, plus **Clear Crash Reports**. Managed JDK purge lives in Settings → Java.

---

## Project Structure

```text
ZeroBlockBridge/
├── app/
│   ├── launcher.py                    # Entry point: resolve data dir, then start UI (~17 LOC)
│   │
│   ├── ui/                            # Presentation Layer — no business logic
│   │   ├── main.py                    # MCTunnelApp: main window, sidebar, hero status bar, console tabs (~1201 LOC)
│   │   ├── server_wizard.py           # 6-step creation wizard (~826 LOC)
│   │   ├── server_properties_editor.py# 7-tab editor: General/World/Network/Advanced/Backups/Automation/Launch (~1091 LOC)
│   │   ├── modrinth_browser.py        # Modrinth browser: search, install, update badges, bulk ops (~1850 LOC)
│   │   ├── players_dashboard.py       # Player management: Online/Whitelist/Operators/Bans tabs (~427 LOC)
│   │   ├── app_settings.py            # Settings dialog: General/Notifications/Java/Storage/About (~754 LOC)
│   │   ├── first_run_dialog.py        # First-launch data directory picker: Standard/Portable/Custom (~174 LOC)
│   │   ├── toast.py                   # Non-blocking notification overlay (~200 LOC)
│   │   ├── icons.py                   # PIL-drawn, theme-tintable icon set — replaces emoji (~210 LOC)
│   │   ├── win_effects.py             # Win11 DWM rounded corners + shadow, no-op elsewhere (~69 LOC)
│   │   └── ui_components.py           # ConsoleWidget, ServerListItem, ToolTip, ZBBDialog, EulaDialog (~673 LOC)
│   │
│   ├── core/                          # Orchestration & Business Logic
│   │   ├── bootstrap.py               # Resolves data dir before any other module reads a path (~86 LOC)
│   │   ├── core.py                    # ZBBManager — central orchestrator (~656 LOC)
│   │   ├── logic.py                   # ServerRunner, Scheduler, BackupScheduler, downloads, metadata, port preflight (~948 LOC)
│   │   ├── orchestrators.py           # Server/Backup/Tunnel/Scheduler orchestrators (~275 LOC)
│   │   ├── provisioning.py            # ServerProvisioner — wizard config -> installed server (jar, scaffold, Java, tunnel)
│   │   ├── logging_setup.py           # Rotating log file + uncaught-exception hooks
│   │   ├── protocols.py               # Protocol classes for structural typing (~41 LOC)
│   │   ├── process_job.py             # Child-process reaping: Windows Job Object / Linux PDEATHSIG (~130 LOC)
│   │   ├── playit_manager.py          # Playit.gg agent (v1.0.10 playitd daemon) lifecycle, DNS recovery (~821 LOC)
│   │   ├── version_manager.py         # Dynamic version fetch (Fill API v3 for Paper), 24h cache (~445 LOC)
│   │   ├── server_events.py           # EventBus + ServerEvent enum (~53 LOC)
│   │   ├── statemanager.py            # Tunnel status debounce (module-level vars, Lock) (~41 LOC)
│   │   ├── app_config.py              # UI tokens: colors, fonts, radii, timeouts (~112 LOC)
│   │   ├── constants.py               # Paths (BASE_DIR), URLs, ServerState enum (~114 LOC)
│   │   └── single_instance.py         # PID lockfile — prevents duplicate instances (~81 LOC)
│   │
│   └── services/                      # Specialized Services & Auto-Healing
│       ├── watchdog.py                # Crash classification & exponential backoff restart (~264 LOC)
│       ├── heartbeat.py               # Zombie detection via /list probe (~95 LOC)
│       ├── lag_monitor.py             # TPS lag detection via sliding window (~49 LOC)
│       ├── crash_reporter.py          # JSON crash diagnostic reports, 50-report FIFO (~135 LOC)
│       ├── discord_webhook.py         # Discord notifications: per-event opt-in, templates, queue worker (~398 LOC)
│       ├── backup_manager.py          # ZIP backup create (reason tags) + atomic restore (~177 LOC)
│       ├── sanitizer.py               # Command allowlist, injection filter, BlockedReason (~101 LOC)
│       ├── java_detector.py           # System Java detection + portable JDK scan (~423 LOC)
│       ├── java_installer.py          # Adoptium download: JRE with JDK fallback (~412 LOC)
│       ├── bytecode_analyzer.py       # JAR bytecode → required Java version (~149 LOC)
│       ├── aikars_flags.py            # Optimal JVM flags by RAM tier (~89 LOC)
│       ├── scaffolder.py              # Server directory + eula + server.properties scaffold (~156 LOC)
│       ├── server_properties.py       # server.properties read/write, world listing/switching (~80 LOC)
│       ├── player_files.py            # ops/bans/whitelist JSON read/write (~47 LOC)
│       ├── template_manager.py        # Wizard server templates (~69 LOC)
│       ├── migration.py               # .zbbpack export/import (~90 LOC)
│       ├── playit_api.py              # Playit.gg REST API v2 client (~466 LOC)
│       ├── modrinth.py                # Modrinth API client, dependency resolution, updates (~508 LOC)
│       ├── mrpack_installer.py        # Modrinth modpack (.mrpack) install (~215 LOC)
│       ├── mod_install_tracker.py     # Installed Modrinth slugs per server (~73 LOC)
│       ├── mod_id_resolver.py         # Crash-log mod IDs → Modrinth slugs (~26 LOC)
│       ├── sha1_validator.py          # SHA1-verified download with retry (~113 LOC)
│       ├── disk_usage.py              # Folder size helpers for Settings → Storage/Java (~38 LOC)
│       ├── console_buffer.py          # Thread-safe console buffer (collections.deque) (~29 LOC)
│       └── settings_manager.py        # App settings singleton, debounced flush (~94 LOC)
│
├── tests/                             # 36 test files, 633 tests, 100% pass
│   ├── conftest.py                    # FakeEmitter (EventBus stub), FakeRunner
│   ├── test_playit_manager.py         # PlayitManager lifecycle (59)
│   ├── test_version_manager.py        # VersionManager fetch + cache (43)
│   ├── test_java_installer.py         # JDK/JRE download, fallback, listing (42)
│   ├── test_sanitizer.py              # Allowlist, injection, BlockedReason, describe_blocked (41)
│   ├── test_orchestrators.py          # All 4 orchestrators incl. pre-update snapshot (33)
│   ├── test_backup_manager.py         # Create/retention/reason tags/restore round-trip (14)
│   └── ... (30 more)
│
├── packaging/                         # PyInstaller specs (Windows, Linux) + exe version metadata
├── tools/                             # bump_version.py, extract_changelog_section.py, gen_theme.py
├── .github/workflows/                 # tests.yml (Win+Linux matrix), build.yml (tag → release)
├── pyproject.toml                     # Project metadata, requires-python>=3.10, deps
├── requirements.txt                   # Exact runtime pins (direct + transitive)
├── requirements-dev.txt               # requirements.txt + pytest/flake8 pins
└── docs/
    ├── ARCHITECTURE.md                # This file
    ├── STANDARDS.md                   # Coding standards & quality criteria
    └── changelog.md                   # Release notes (source for GitHub release bodies)
```

Generated at runtime under the [data directory](#data-directory):

```text
<BASE_DIR>/
├── servers/<server-name>/             # server.jar, server.properties, metadata.json, crash_reports/ (max 50, FIFO)
├── backups/<server-name>/             # YYYY-MM-DD_HH-MM-SS.zip (manual/scheduled), ..._HH-MM-SS__pre_update.zip
├── bin/                               # playitd agent binary + playit.version marker
├── .zbb_cache/jdks/<version>/         # Portable JDK/JRE cache (Adoptium)
└── config/                            # config.json, versions_cache.json
```

---

## Technical Details

### Supported Server Types & Java Mapping

| Java Version | MC Range | Notes |
|---|---|---|
| Java 25 | MC 26.x (year-based versions) | Versions newer than the matrix also get the newest entry |
| Java 21 | MC 1.20.5 – 1.21.x | Also required by Fabric 0.15+ on newer MC |
| Java 17 | MC 1.18 – 1.20.4 | Most common modern range |
| Java 16 | MC 1.17 – 1.17.1 | |
| Java 8 | MC < 1.17 | Legacy servers |

Java auto-downloaded from **Adoptium** to `.zbb_cache/jdks/{version}/` — never modifies system PATH. The installer requests a JRE first (`image_type=jre`, ~45 MB) and falls back to a full JDK (~300 MB) when no JRE exists for that version. Version-picker warnings: orange if detected > required, red block if detected > 21 or < required. Bytecode analyzer (`bytecode_analyzer.py`) extracts required version from the server JAR class files, with a floor of `get_required_java(mc_version)` to prevent Forge shim misdetection.

### Dynamic Version Fetching

`VersionManager` fetches top 100 versions per type:

| Type | API |
|------|-----|
| Vanilla | Mojang manifest |
| Fabric | Fabric Meta API |
| Forge | Forge Promotions API |
| Paper | PaperMC Fill API v3 |
| Purpur | PurpurMC API |

- Cache: `config/versions_cache.json`, auto-refreshed every 24h in background. Falls back to built-in defaults when offline.
- Singleton whose constructor does no I/O: starts from in-memory defaults and loads the disk cache lazily on the first `get_versions()` call, so startup never blocks on disk or network.
- UI freeze fix: `get_versions()` does not block on `thread.join()` — uses callback path to notify when refresh completes.

### Discord Webhook

`DiscordWebhookService` (`app/services/discord_webhook.py`):
- Activated only when `discord_webhook_url` is set; configured in Settings → Notifications. `ZBBManager.reload_discord_webhook()` re-creates the service after a change.
- Per-event opt-in via `webhook_events` (`SETTING_EVENT_KEYS`). Defaults on: crashed, ready, backup_completed, backup_failed. Opt-in: stopped, restarted, zombie_detected, lag_spike, tunnel_online, player_joins. Only enabled events are subscribed.
- Optional per-event description templates with placeholders (`{server}` always available).
- Single `queue.Queue` worker thread, 2s rate-limit between POSTs. `stop()` unsubscribes from the bus.
- Server name resolved via getter (follows the active server). URL is never logged.

### Scheduled Restart Logic

`Scheduler` in `logic.py` supports two modes:

- **Interval** (`type="interval"`): restart every N hours from last run.
- **Daily time** (`type="time"`): restart at HH:MM every day. Check window: 0–120s after target. If >120s past → `get_status()["missed"] = True` → orchestrator warns user.

Warning threshold messages emitted before restart: 1h, 30m, 15m, 1m.

### System Requirements

- **OS**: Windows 10+ / Linux
- **Python**: 3.10 or higher (CI runs 3.11; developed on 3.14)
- **Java**: Auto-managed (Adoptium, Java 8–25)
- **RAM**: 2 GB minimum for ZBB + server (4 GB+ recommended for modded)
- **Disk**: ~37 MB app + ~107 MB per vanilla server + world size

### Dependencies

`pyproject.toml` declares compatible ranges (major-version upper bounds); `requirements.txt` pins the exact tested set, including transitive dependencies, and is what CI and release builds install. `requirements-dev.txt` adds the pinned test/lint tools. Dependabot (`.github/dependabot.yml`) opens weekly update PRs against `dev` for pip and GitHub Actions.

| Package | Purpose |
|---------|---------|
| `customtkinter` | Modern GUI (extends Tkinter) |
| `requests` | HTTP client (downloads, API calls) |
| `Pillow` | Server icon image processing |
| `psutil` | System resource monitoring |
| `packaging` | Version comparison utilities |

---

## Build & Release

- **CI** (`.github/workflows/tests.yml`): blocking `flake8 --select=E9,F63,F7,F82`, non-blocking full lint, then the full test suite, on a Windows + Ubuntu matrix (Python 3.11).
- **Release** (`.github/workflows/build.yml`): triggered by a `v*` tag. Reuses the tests workflow as a gate, writes the tag version into `packaging/version_info.txt` and `AppConfig.APP_VERSION`, builds with PyInstaller from `packaging/ZeroBlockBridge.spec` (Windows) and `packaging/linux.spec`, generates `.sha256` checksums, then publishes `ZeroBlockBridge.exe`, `ZeroBlockBridge-linux`, and their checksums in a GitHub release whose body is extracted from `docs/changelog.md` (`tools/extract_changelog_section.py --strict`).
- Local helpers: `tools/bump_version.py X.Y.Z` (updates `APP_VERSION`, `version_info.txt`, inserts a changelog template — no commit/tag), `tools/gen_theme.py` (regenerates `assets/zbb_theme.json` from CTk's base theme recolored to the palette; keep in sync with `AppConfig`).
- UPX packing is disabled on both specs (antivirus false positives). The Windows exe is not code-signed.

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
| Explainable command safety (visible allowlist + blocked-command toast) | ✅ unique | ❌ (arbitrary amscript) | n/a |
| One-click pre-update snapshot + rollback | ✅ unique | ❌ | n/a |

### High-Priority Gaps (CA-HIGH)

| ID | Feature | Status |
|----|---------|--------|
| CA-H01 | JVM args UI per-server | Done — Launch tab: per-server Java runtime, Aikar's flags toggle, and Custom JVM Flags (`jvm_custom_flags`, applied by `ServerRunner`) |
| CA-H02 | Unified player management (ops+bans+whitelist) | Done — `players_dashboard.py` Online/Whitelist/Operators/Bans tabs |
| CA-H03 | Console search/filter | Done — search bar on Console and Tunnel Log tabs (`main._build_console_search_bar`) |
| CA-H04 | World switching UI | Done — World tab active-world picker (`server_properties.list_worlds` / `set_active_world`) |

---

## Privacy & Service Disclaimer

- **No Data Collection**: ZBB does not collect, store, or transmit personal data or usage telemetry.
- **No remote-control agent**: ZBB has no built-in remote-control or remote-management channel of its
  own — nobody but you can operate this app remotely. Every network call it makes is one of the
  ones listed below, all visible and auditable in `app/services/`.
- **Third-party trust boundary**: some of those calls route through third-party infrastructure that
  ZBB does not control and cannot vouch for. Most notably, enabling **Playit.gg tunneling** routes
  your Minecraft server's traffic through Playit's own relay servers — that's how any tunnel/port-
  forward solution works, not something ZBB adds on top. It's optional, off by default, and you can
  disable it at any time; while it's on, you're trusting Playit's infrastructure for that traffic,
  same as you would with any third-party tunnel provider.
- **External Connections**: Only to services required for operation, each optional except the first
  two (needed to fetch/update server software):
  - **Mojang** — version manifest + server jar downloads
  - **Fabric / Forge / Paper / Purpur APIs** — version lists
  - **Modrinth** — mod/plugin browsing and downloads
  - **Adoptium** — JDK auto-install
  - **Playit.gg** — tunneling (optional, user-enabled — see trust boundary above)
  - **Discord** — webhook notifications (optional, user-configured)
- **User Control**: All server management, backups, tunneling, and webhook operations remain fully under user control.
