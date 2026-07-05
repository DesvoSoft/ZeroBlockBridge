# ZeroBlockBridge — Technical Standards

This document defines the coding standards, architectural philosophy, and quality criteria for ZeroBlockBridge.
All contributors (human or AI) must adhere to these rules.

> **Last updated:** 2026-07-05 — 461 tests, 100% pass.

---

## 1. Architectural Philosophy

### 1.1 Event-Driven & Decoupled

ZBB is built on strict **decoupled architecture**:

- **UI → Core → Services** (one-way). Never the reverse.
- All UI↔Core communication via `EventBus`. No direct service calls from `app/ui/`.
- `ZBBManager` is the single orchestrator for server lifecycle. No other component manages lifecycles.
- **Headless-ready**: every feature must work without a GUI (preparatory for CLI/REST API).
- Use `events.subscribe()` — `.on()` is banned.

### 1.2 Platform Neutrality

- `os.startfile` and `_winapi` are banned. Use `subprocess` + platform check.
- Directory symlinks: `os.symlink(src, dst, target_is_directory=True)` — never `_winapi.CreateJunction`.
- Paths: `pathlib.Path` exclusively (or `os.path.join` where pathlib isn't available).

### 1.3 Lean Engineering

- No feature unless it solves a problem the user encounters at least once per session.
- Three similar lines beats a premature abstraction.
- No error handling for scenarios that can't happen. Trust framework guarantees.
- No half-finished implementations. No `# TODO: fix later` left in production code.

---

## 2. Code Quality Rules

### 2.1 Imports

- All imports at **module top** (PEP 8). Inline imports only to break confirmed circular dependencies — document why with a comment.
- No unused imports. `flake8 --select=F401` must return zero violations.
- `from typing import Dict, List` is dead weight in Python 3.9+. Use `dict[str, ...]` and `list[...]`.

### 2.2 Exceptions

**Strictly prohibited:** `except: pass` and bare `except Exception: pass` without logging.

Every `except` block must:
1. Catch the most specific exception type possible.
2. Call `logger.warning()` or `logger.exception()` with context.
3. Document in a comment if swallowing is intentional (destructor cleanup, atexit, etc.).

```python
# Correct
try:
    data = json.loads(raw)
except json.JSONDecodeError as e:
    logger.warning("Failed to parse server metadata: %s", e)
    data = {}

# Wrong — never do this
try:
    data = json.loads(raw)
except:
    pass
```

### 2.3 Logging

- Every module: `logger = logging.getLogger(__name__)`.
- No `print()` in production code.
- No emojis in log strings.
- Use `%`-formatting in log calls (not f-strings) — avoids wasteful string construction when log level is disabled:
  ```python
  logger.warning("Invalid port: %s", port)   # correct
  logger.warning(f"Invalid port: {port}")     # wasteful
  ```
- Log levels:
  - `DEBUG`: Detailed diagnostics.
  - `INFO`: Milestones and confirmations.
  - `WARNING`: Recoverable unexpected behavior, missed windows, fallback paths.
  - `ERROR`: Non-recoverable failures needing attention.

### 2.4 File I/O

- Every `open()` for text must include `encoding="utf-8"`. Critical on Windows with non-UTF8 locale — MOTD with `§` characters corrupts otherwise.
- `strptime` on user-directory filenames: always wrap in `try/except ValueError`. Users drop arbitrary files.
- Atomic file operations: before reading a file written by another thread, verify `os.path.exists` + `os.path.getsize > 0` with a 5s timeout loop.

### 2.5 Threading

- All background threads: `daemon=True`.
- Shared mutable state: always protect with `threading.Lock`.
- UI thread: only reads, never blocks. All I/O and computation in worker threads.
- `self.after(0, callback)` for all UI updates from background threads.
- `__init__` must initialize all data attributes before starting threads or subscribing to EventBus.

### 2.6 NOTIFICATION Payload

Always `{"msg": str, "type": "error" | "warning" | "info"}`. Never `"color"` key.

### 2.7 Crash Notifications

Only `_on_server_crashed` in `core.py` emits crash `NOTIFICATION` toasts.
Watchdog must never emit `NOTIFICATION` directly.

---

## 3. UI Standards

### 3.1 Framework

`customtkinter` with tokens from `app/core/app_config.py`.

### 3.2 Corner Radius Rule

`corner_radius=12` on all widgets.
**Documented exceptions** (must not be changed):
- `toast.py`: `corner_radius=0` — intentional square design.
- Modal alerts: `corner_radius=0`.

Any value other than 12 (or documented 0) is a visual regression.

### 3.3 Colors

Use `AppConfig` constants only. Hardcoded color literals (`"green"`, `"white"`, `"gray"`, `"#f97316"`) in widget calls are banned. "Dirt Block" palette:

| Token | Value | Use |
|-------|-------|-----|
| `COLOR_BG_DARK` | `#111827` | Main background |
| `COLOR_BG_SIDEBAR_DARK` | `#0f172a` | Sidebar |
| `COLOR_BG_CARD_DARK` | `#1e293b` | Cards/panels |
| `COLOR_ACCENT_AMBER` | `#d97706` | Highlights, warnings |
| `COLOR_BTN_SUCCESS` | lime-400 | Start buttons |
| `COLOR_BTN_DANGER` | red | Stop/destructive |

### 3.4 Typography

- Body: Roboto
- Headings/Titles: Roboto Medium

### 3.5 Buttons

All buttons must define `hover_color`. No button without explicit hover feedback.

### 3.6 UI Thread Safety

Never read widgets from a background thread. Always `self.after(0, lambda: self.widget.configure(...))`.

---

## 4. Git Workflow

### Branch Hierarchy

```
main        ← Production releases only
  └─ dev    ← Integration branch (all feature merges here)
       └─ feature/<name>   ← Feature branches from dev
```

### Rules

1. Feature branches from `dev`, merged back via `--ff-only`.
2. `dev` → `main` only at release milestones, full test suite + lint required.
3. Commits: English, conventional prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `perf:`.
4. No emojis in commit messages or branch names.
5. No `Co-Authored-By` lines. No Claude name anywhere in git history.
6. Git identity: `DesvoSoft / desvox23@gmail.com` (already set in local config).
7. Every merge to `dev` must pass full test suite.

### Release Milestones

| Milestone | Tag | Condition |
|-----------|-----|-----------|
| F0–F4 complete | `v1.0.0-beta` | F4 UI done, test suite green |
| F5 + F6 + P0 complete | `v1.0.0-rc` | ✅ Achieved (dev) |
| MODS-B + CA-HIGH | `v1.1.0` | After mod browser improvements |
| F11 UI 2.0 | `v2.0.0` | Full UI redesign |

**Current dev state:** v1.0.0-rc equivalent. F0–F6 + P0 complete. 461 tests.

---

## 5. Testing

### Running Tests

```bash
# Full suite
pytest tests/ -q

# Single file
pytest tests/test_watchdog.py -v

# Single test
pytest tests/test_watchdog.py::TestWatchdog::test_backoff_cap -v

# Fail-fast
pytest tests/ -x -q

# Syntax check after editing a file
python -m py_compile app/core/core.py
```

### Test Helpers (`tests/conftest.py`)

- `FakeEmitter`: in-memory EventBus stub with `subscribe`/`emit`/`unsubscribe` + `events` list for assertions. Avoids real EventBus threading in unit tests.
- `FakeRunner`: minimal `ServerRunner` stub.

### Test Standards

- Mock `get_server_meta` and `update_server_meta` — never write real metadata files in unit tests.
- Use `tmp_path` (pytest fixture) for all temporary file operations.
- `MagicMock(spec=ZBBManager)` for orchestrator tests — prevents accidental attribute creation.
- No `time.sleep()` in tests longer than 0.2s unless unavoidable (use threading.Event instead).
- Cross-platform: use `tempfile.gettempdir()` not `/tmp/`.

---

## 6. Lint Gate (CI)

Must pass before any commit to `dev`:

```bash
flake8 app/ --select=E9,F63,F7,F82
```

Zero tolerance — these are syntax errors, undefined names, undefined imports, and undefined `__all__`.

Full lint (non-blocking, for review):

```bash
flake8 app/ --exit-zero --max-complexity=10 --max-line-length=127
```

Dead import check (must also be zero):

```bash
flake8 app/ --select=F401
```

---

## 7. Quality Score

Before each release milestone, audit ensures a **Health Score > 90/100**:

| Category | Max | Deduction |
|----------|-----|-----------|
| Dead Code | 25 pts | -5 per orphan import/function/stub |
| Error Handling | 25 pts | -10 per bare `except: pass` without logging |
| Visual Consistency | 20 pts | -5 per non-12 `corner_radius` (undocumented) |
| Documentation | 15 pts | -5 per broken path or stale claim in docs/ |
| Platform Neutrality | 15 pts | -5 per `os.startfile` / `_winapi` usage |

### Certification Steps

```bash
# 1. Syntax gate
flake8 app/ --select=E9,F63,F7,F82 --statistics

# 2. Dead imports
flake8 app/ --select=F401

# 3. Banned patterns
grep -rn "os.startfile\|_winapi\|except:\s*pass\|except Exception:\s*pass" app/

# 4. corner_radius violations (manual review of UI files)
grep -rn "corner_radius" app/ui/ | grep -v "12\|= 0"

# 5. Full test suite
pytest tests/ -q
```

**Current score (2026-07-05): 97/100** — known deductions: LA-06 (get/set_server_ram thin wrappers still used by SPE; scheduled for future inline).
