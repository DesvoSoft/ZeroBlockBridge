---
name: zeroblockbridge-development
description: Development guide for ZeroBlockBridge (ZBB). Use for all implementation, bug fixes, and architectural changes.
---

# ZeroBlockBridge — Development Guide

## Project State (2026-07-05)

- **463 tests**, 100% pass, 0 flaky, 0 skipped.
- **Test files**: 24 files.
- **Phases complete**: F0–F6, FA–FB, FIX-P1/P2/P3, F4 (full), P0 (all 7 tasks), EXE-PERF, BUG-AUDIT (18/19), MODS-B, F8, F7.5 (modpack install), CA-H01 (JVM args UI), MODS-SEC (mrpack compat gate + zip-slip guard).
- **Next targets**: CA-H02 (unified player management) → F7 rest (server templates).

---

## Architecture Overview

### Layer Separation (strict, enforced)

```
app/ui/        → Presentation only. No business logic. No direct service calls.
app/core/      → Orchestration, EventBus, business logic.
app/services/  → Specialized services (auto-healing, API clients, utilities).
```

### Central Orchestrator: ZBBManager (`app/core/core.py`)

Single source of truth for server lifecycle. Delegates to 4 sub-orchestrators:
- `ServerOrchestrator` — start/stop/restart, Java resolution, monitor setup
- `BackupOrchestrator` — ZIP backup create + atomic restore, auto-backup check
- `TunnelOrchestrator` — Playit.gg agent lifecycle
- `SchedulerOrchestrator` — restart/backup scheduling (50ms tick loop)

`ZBBManager` does **not** inherit Protocol classes (HAS-A, not IS-A).

### EventBus (`app/core/server_events.py`)

All communication between UI and core flows through `EventBus`. Rules:
- Use `events.subscribe()` — **never** `.on()`.
- UI updates: `self.after(0, callback)` (Tkinter thread safety).
- `NOTIFICATION` payload: always `{"msg": str, "type": "error"|"warning"|"info"}`. Never `"color"` key.
- Only `_on_server_crashed` in `core.py` emits crash notifications. Watchdog never emits `NOTIFICATION`.

---

## Coding Rules (enforce always)

1. **`open()` → `encoding="utf-8"`** for all text files. MOTD with `§` corrupts on Windows otherwise.
2. **`strptime` on user filenames** → always `try/except ValueError`.
3. **No `os.startfile`, no `_winapi`** → use `subprocess` + platform check + `os.symlink`.
4. **No `print()`** → `logging.getLogger(__name__)` in every module.
5. **No bare `except: pass`** → catch specific exceptions, log with context.
6. **All threads `daemon=True`**.
7. **`__init__` initializes all attributes before starting threads or subscribing to EventBus**.
8. **`ServerState` enum in `constants.py`** (not `core.py`) — prevents circular import.
9. **Fabric/Forge installers** always receive resolved `java_bin` from ZBBManager. Never assume `"java"` from PATH.
10. **Scheduler missed window**: daily-time target passed >120s → `get_status()["missed"] = True` → orchestrator warns user via log + NOTIFICATION.
11. **Every spawned child process** (Minecraft server, playit agent) → `assign_to_job(pid)` from `app/core/process_job.py` (Windows Job Object, `KILL_ON_JOB_CLOSE`). Reaps children even on hard parent death (crash, taskkill, closed console) that skips `atexit`. No-op on non-Windows.
12. **Port preflight before spawning the server** — check the configured port isn't already bound (`_port_in_use` in `logic.py`); fail with a clear NOTIFICATION instead of a Minecraft bind-crash.

---

## Java Version Management

| MC Version | Required Java | Notes |
|---|---|---|
| ≥ 1.20.5 | Java 21 | |
| 1.18 – 1.20.4 | Java 17 | Most common |
| 1.17 – 1.17.1 | Java 16 | |
| < 1.17 | Java 8 | Legacy |

- `bytecode_analyzer.py` extracts required Java from JAR class files.
- Floor applied: detected bytecode version can't go below `get_required_java(mc_version)` — prevents Forge shim misdetection (boot class compiled in Java 8).
- JDK auto-downloaded from Adoptium to `.zbb_cache/jdks/{version}/` — **never modifies system PATH**.
- Orange warning if Detected > Required; red block if Detected > 21 or < Required.

---

## Auto-Healing System

### Watchdog (`app/services/watchdog.py`)

- Crash types: `jvm_config_error`, `out_of_memory`, `oom_kill`, `boot_crash`, `runtime_crash`, `signal_N`.
- Exponential backoff restart, **capped at 3600s**.
- Stability reset after 10 min uptime.
- **Never emits NOTIFICATION** — crash notifications owned by `_on_server_crashed` in `core.py`.

### Heartbeat (`app/services/heartbeat.py`)

- Sends `/list` every 60s. If no console response in 15s → emits `ZOMBIE_DETECTED`.
- `_last_probe` set **before** `send_command()` (prevents false zombie from race).

### LagMonitor (`app/services/lag_monitor.py`)

- Detects `"Can't keep up!"` pattern. Sliding window: 5 spikes in 5 min → `LAG_SPIKE`.

### CrashReporter (`app/services/crash_reporter.py`)

- Subscribes to `CRASHED`. Writes JSON report to `servers/<name>/crash_reports/`.
- Max 50 reports per server (FIFO rotation). No new dependencies (stdlib only).

### Discord Webhook (`app/services/discord_webhook.py`)

- Active only when `SettingsManager().get("discord_webhook_url")` is non-empty.
- Single queue.Queue worker, 2s rate-limit between POSTs.
- Events: `CRASHED` (red), `READY` (green), `BACKUP_COMPLETED` (blue), `BACKUP_FAILED` (orange).
- URL never logged.

---

## Playit.gg Integration

- Agent v1.0.10 (`playitd` daemon binary — the Windows release asset IS playitd.exe, a full rewrite of the retired v0.17.x CLI agent). Args: `--secret-path` + `--socket-path` (hyphens — v0.17's underscore flags are gone). Socket uses namespaced form `@zbb-playitd` (raw `\\.\pipe\` paths are rejected at bind). No `--stdout` flag — playitd logs to stderr, merged into the same pipe. No `version` subcommand — installed version tracked in `bin/playit.version` marker file; `--help` used as the install smoke test.
- DNS recovery: 3 independent mechanisms — `create_tunnel()` polls 15s, `_dns_polling_loop()` polls 60s more (tunnel-ensure now triggers on its 3rd iteration, since the old "agent has 0 tunnels" stdout line no longer appears), `_parse_line()` extracts domain from stdout regex.
- **Do NOT modify the DNS recovery chain** — breaking any of the 3 mechanisms causes tunnel status to stay "Starting..." indefinitely.
- `statemanager.py`: module-level vars + `threading.Lock` for tunnel status debounce (200ms).

---

## Dynamic Version Fetching

`VersionManager` (`app/core/version_manager.py`) fetches top 100 versions per type (Vanilla, Fabric, Forge, Paper, Purpur). Cached to `config/versions_cache.json`, auto-refreshed every 24h. Falls back to defaults if offline.
- Lazy init: instantiated on first use, not in `ZBBManager.__init__`.
- `get_versions()` does NOT block on `thread.join()` — uses callback to notify caller when refresh completes.

---

## ThreadPoolExecutor

`ZBBManager.executor` — 8 workers, `ThreadPoolExecutor`. Shutdown in `on_close` via `shutdown(wait=True, cancel_futures=True)`.

---

## Backup System

`BackupManager` (`app/services/backup_manager.py`):
- **Atomic restore**: temp dir → extract → rename to final path (swap). If extraction fails, rollback from temp.
- `strptime` parsing on filenames: always `try/except ValueError` (users can drop arbitrary files in backup dirs).
- Retention: `_apply_retention(count)` deletes oldest ZIPs over limit.

`BackupScheduler` (in `app/core/logic.py`): `enabled`, `interval_hours`, `retention_count`, `mode`, `last_run`. Persisted in `metadata.json`.

---

## Scheduler Missed Window

`Scheduler.get_status()` returns:
```python
{"is_due": bool, "remaining_seconds": float | None, "missed": bool}
```
`missed=True` when `type="time"` and target passed >120s ago. Orchestrator emits `logger.warning` + `NOTIFICATION` toast.

---

## Key Files Quick Reference

| File | Purpose |
|------|---------|
| `app/core/core.py` | ZBBManager — start_server, shutdown, _on_server_crashed, _init_discord_webhook |
| `app/core/logic.py` | ServerRunner, Scheduler, downloads, get/update_server_meta, migrate_legacy_metadata |
| `app/core/orchestrators.py` | 4 sub-orchestrators, tick loop, missed-window detection |
| `app/core/server_events.py` | EventBus, ServerEvent enum |
| `app/core/constants.py` | BASE_DIR, SERVERS_DIR, CONFIG_DIR, JDK_CACHE_DIR, ServerState enum |
| `app/core/app_config.py` | AppConfig: colors, fonts, timeouts, SCHEDULER_CHECK_INTERVAL |
| `app/services/watchdog.py` | Crash detection, exponential backoff, intentional-stop guard |
| `app/services/crash_reporter.py` | JSON crash reports, 50-report FIFO |
| `app/services/discord_webhook.py` | Discord notifications, queue worker, 2s rate-limit |
| `app/services/backup_manager.py` | ZIP backups, atomic restore, retention |
| `app/services/sanitizer.py` | Command allowlist, injection char filter |
| `app/ui/main.py` | MCTunnelApp: layout, subscriptions, on_close |
| `app/ui/server_properties_editor.py` | 7-tab properties + automation + backups editor |
| `tests/conftest.py` | FakeEmitter, FakeRunner |
| `pyproject.toml` | Project metadata, Python>=3.10, 5 pinned deps |

---

## Run Commands

```bash
# Run app
py app/launcher.py

# Tests
pytest tests/ -q
pytest tests/test_watchdog.py -v
pytest tests/test_watchdog.py::TestWatchdog::test_backoff_cap -v
pytest tests/ -x -q   # fail-fast

# Lint (CI gate — must be 0)
flake8 app/ --select=E9,F63,F7,F82

# Dead imports (must be 0)
flake8 app/ --select=F401

# Full lint (non-blocking)
flake8 app/ --exit-zero --max-complexity=10 --max-line-length=127

# Syntax check single file
python -m py_compile app/core/core.py

# Install in editable mode
pip install -e .
```

---

## What NOT To Do

- No `Co-Authored-By` in commits. No Claude name in git history.
- No confirmation prompts before committing or editing — just do it.
- No README or docs files unless explicitly requested.
- No refactoring beyond task scope. Three similar lines beats a premature abstraction.
- No `print()`. Logger only.
- No `os.startfile`, no `_winapi`.
- No bare `except: pass`. Specific exceptions + logging.
- No `TPS_UPDATE` or `ERROR` ServerEvent — both removed as dead events.
- No `wait_for_jar_ready` — function removed (dead code, no callers).
- No `_jar_ready_events` dict — removed entirely.

---

## Errors to Avoid (Learned from Audits)

1. Thread for fast operations (<50ms) — overhead > work. Use direct call.
2. Inline import to "avoid circular" without moving the enum to constants.
3. `open()` without `encoding` — Windows locale bites MOTDs.
4. Hardcoded `"java"` in subprocess calls — must use resolved `java_bin`.
5. Singleton `__new__` pattern — Python modules are already singletons.
6. `TaskKill /F` before `process.wait()` — causes console flash on Windows.
7. Blocking `thread.join()` in `get_versions()` — freezes wizard UI for 4s.
8. `check_due()` daily-time mode silently skips window if tick is >120s late — now detected and warned.

---

## Roadmap Summary

See `roadmap.md` for full detail. Current state:

| Block | Status |
|-------|--------|
| F0–F3 (Foundation + Refactors) | ✅ |
| FA–FB (UI Layout v1.4) | ✅ |
| FIX-P1/P2/P3 (Critical bugs) | ✅ |
| F4 (Auto-Backup Scheduler, full) | ✅ |
| P0 (Foundation Hardening, all 7) | ✅ |
| EXE-PERF (6 startup/shutdown bugs) | ✅ |
| BUG-AUDIT 2026-06-19 (18/19) | ✅ |
| AUDIT-3 validation (all items) | ✅ |
| F5 (Crash Reporter, 11 tests) | ✅ |
| F6 (Discord Webhook, 10 tests) | ✅ |
| MODS-B (Modrinth improvements) | ⏳ |
| CA-HIGH (competitive gaps) | ⏳ |
| F7–F11 (Templates, Migration, Linux, UI 2.0) | ⏳ |
