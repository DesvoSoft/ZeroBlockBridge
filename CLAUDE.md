# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run application
py app/launcher.py

# Install dependencies
pip install -r requirements.txt
pip install pytest flake8  # dev tools

# Run all tests
pytest tests/

# Run single test file
pytest tests/test_watchdog.py -v

# Run single test
pytest tests/test_watchdog.py::test_function_name -v

# Lint (critical errors only -- CI gate)
flake8 app/ --select=E9,F63,F7,F82

# Lint (full, non-blocking)
flake8 app/ --exit-zero --max-complexity=10 --max-line-length=127
```

## Architecture

### Layer separation (strict)

```
app/ui/        -> Presentation only. No business logic. No direct service calls.
app/core/      -> Orchestration, EventBus, business logic.
app/services/  -> Specialized services (auto-healing, API clients, utilities).
```

UI never calls services directly. All flows through EventBus:
1. UI emits event -> ZBBManager receives -> delegates to service -> service emits result -> UI updates.
2. Use `events.subscribe()` not `.on()`.
3. UI updates via `self.after(0, ...)` (Tkinter thread safety).

### Central orchestrator: ZBBManager (app/core/core.py)

Single source of truth for server lifecycle. Delegates to 4 sub-orchestrators in `app/core/orchestrators.py`:
- `ServerOrchestrator` -- start/stop/restart
- `BackupOrchestrator` -- ZIP backup create/restore
- `TunnelOrchestrator` -- Playit.gg agent lifecycle
- `SchedulerOrchestrator` -- restart/backup scheduling

Protocol classes in `app/core/protocols.py` define structural typing contracts (HAS-A, not IS-A — ZBBManager does not inherit Protocols).

### EventBus (app/core/server_events.py)

Decouples all components. `ServerEvent` enum: `STATUS_CHANGED`, `CONSOLE_LINE`, `CRASHED`, `ZOMBIE_DETECTED`, `LAG_SPIKE`, `TUNNEL_STATUS`, etc. `TPS_UPDATE` and `ERROR` were removed (dead events).

### Auto-healing system

- `watchdog.py` -- crash detection by exit code + stderr pattern. Exponential backoff restart. Stability resets after 10 min uptime.
- `heartbeat.py` -- zombie detection. Sends `list` every 60s; no response in 15s -> emits `ZOMBIE_DETECTED`.
- `lag_monitor.py` -- TPS lag via `"Can't keep up!"` pattern. Sliding 5-spike/5-min window.
- `sanitizer.py` -- command allowlist (80+ safe MC commands) + character filter (`;|&` etc.).

### Threading rules

- Background threads: `daemon=True`.
- File check before reading: `os.path.exists` + `os.path.getsize > 0` with 5s timeout (OS may not flush before thread event fires).
- `threading.Lock` for shared mutable state.
- `__init__` must init all data attributes before starting threads or subscribing to EventBus.

### Java version management

- MC >= 1.20.5 -> Java 21; MC 1.18-1.20.4 -> Java 17; MC 1.17 -> Java 16; MC < 1.17 -> Java 8.
- JDK auto-downloaded from Adoptium to `.zbb_cache/jdks/{version}/` -- never modifies system PATH.
- `bytecode_analyzer.py` detects required version from server JAR.
- Orange warning if Detected > Required; red block if Detected > 21 or < Required.

### Playit.gg integration

- Agent v0.17.1. Secret arg: `--secret_path` (underscore). Always include `--stdout`.
- `playit_manager.py` manages agent lifecycle; `playit_api.py` is REST v2 client.

### Version fetching

`version_manager.py` fetches top 100 versions from Mojang/Fabric/Forge/Paper/Purpur APIs. Cached to `config/versions_cache.json`, auto-refreshed every 24h. Falls back to defaults if offline.

## Standards

### Logging

```python
logger = logging.getLogger(__name__)  # every module
# No print(). No emojis in log strings.
# Specific exceptions only -- no bare except: pass
```

### Paths

`pathlib.Path` exclusively. No `os.startfile`, no `_winapi`. Platform-agnostic.

### Coding rules from audit (enforce always)

- Every `open()` must include `encoding="utf-8"` — critical on Windows for MOTDs with `§` (bug MA-02).
- `strptime` on user-directory filenames: always `try/except ValueError` — users drop arbitrary files (bug HA-01).
- NOTIFICATION event payload: always `{"msg": ..., "type": "error"|"warning"|"info"}`. Never `color` key (bug MA-04).
- Don't emit `NOTIFICATION` in Watchdog — only `_on_server_crashed` in core.py owns crash notifications (bug CA-01).

### UI components

- Framework: `customtkinter`. Tokens in `app/core/app_config.py`.
- `corner_radius=12` all widgets (Toasts/alerts: `corner_radius=0`).
- Slate-based palette. Roboto (body) / Roboto Medium (headings).
- All buttons need `hover_color`.

### Git workflow

```
main        <- stable releases only
dev         <- integration (all feature merges here)
feature/<name>
```

- Feature branches: `--ff-only` merge into `dev`.
- `dev` -> `main`: release milestones only, full test suite + lint required.
- Commits: English, conventional prefixes (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`). No emojis. No `Co-Authored-By` lines. Git identity must be DesvoSoft / desvox23@gmail.com (already set in local git config).

### Test helpers (conftest.py)

`FakeEmitter` -- in-memory EventBus stub with `subscribe`/`emit`/`unsubscribe`. Avoids real EventBus threading in unit tests. `FakeRunner` -- minimal server runner stub. `tests/test_orchestrators.py` -- 26 tests for all 4 orchestrators using `MagicMock(spec=...)` + FakeEmitter.