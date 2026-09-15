# ZeroBlockBridge — Technical Standards

This document defines the coding standards, architectural philosophy, and quality criteria for ZeroBlockBridge.
All contributors (human or AI) must adhere to these rules.

> **Last updated:** 2026-09-14 — 633 tests in 36 files, 100% pass.

---

## 1. Architectural Philosophy

### 1.1 Event-Driven & Decoupled

ZBB is built on strict **decoupled architecture**:

- **UI → Core → Services** (one-way). Never the reverse.
- All UI↔Core communication via `EventBus` or `ZBBManager` methods. Mutating flows (start/stop/backup/restart/snapshot) never call services from `app/ui/` — pass the manager method to the widget as a callback when needed (e.g. `ModrinthBrowser(create_snapshot=...)`).
- Pragmatic exception: UI may import services for read-only/stateless helpers (load properties, list templates, disk usage, file dialogs).
- `ZBBManager` is the single orchestrator for server lifecycle. No other component manages lifecycles.
- **Headless-ready**: every feature must work without a GUI (preparatory for CLI/REST API).
- Use `events.subscribe()` — `.on()` is banned.

### 1.2 Platform Neutrality

- `os.startfile` and `_winapi` are banned. Use `subprocess` + platform check.
- Directory links (`logic.create_junction`): Windows uses `cmd /c mklink /J` (a junction needs no admin rights or Developer Mode); elsewhere `os.symlink(src, dst, target_is_directory=True)`. Never `_winapi.CreateJunction`.
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

Always `{"msg": str, "type": "error" | "warning" | "info" | "success"}`. Never `"color"` key.
Only allowed extension is functional, not visual: `action` + `missing_mod_ids` (mod dependency fix flow, consumed by `main._handle_notification`).

### 2.7 Crash Notifications

Only `_on_server_crashed` in `core.py` emits crash `NOTIFICATION` toasts.
Watchdog must never emit `NOTIFICATION` directly.

---

## 3. UI Standards

### 3.1 Framework

`customtkinter` with tokens from `app/core/app_config.py` and the custom theme `assets/zbb_theme.json` (regenerate with `tools/gen_theme.py`; keep widget colors in sync with the tokens).

### 3.2 Corner Radius Scale

Use the tokens, never a literal like `corner_radius=12`:

| Token | Value | Use |
|-------|-------|-----|
| `RADIUS_CARD` | 10 | Frames, cards, panels |
| `RADIUS_BTN` / `RADIUS_INPUT` | 8 | Buttons, entries, option menus |
| `RADIUS_BADGE` | 6 | Pills, badges |

**Documented exceptions:**
- Toasts and alert banners: `corner_radius=0` — intentional square design.
- Circles (status dots, help "?" bubbles, toast icon badges): radius = half the widget size.

Any other literal is a visual regression.

### 3.3 Colors

Use `AppConfig` constants only. Hardcoded color literals (`"green"`, `"white"`, `"gray"`, `"#f97316"`) in widget calls are banned. "Dirt Block" palette — lime green primary, brown secondary, slate backgrounds, **no blue accents**. Tokens are `(light, dark)` tuples where they differ:

| Token | Value | Use |
|-------|-------|-----|
| `COLOR_BG_DARK` | `#0b1120` | Main background (dark) |
| `COLOR_BG_SIDEBAR_DARK` | `#0a0f1c` | Sidebar (dark) |
| `COLOR_BG_CARD_DARK` | `#243044` | Cards/panels (dark) |
| `COLOR_BTN_PRIMARY` | `#65a30d` lime-600 | Primary actions |
| `COLOR_BTN_SECONDARY` | `#92400e` amber-800 (brown) | Secondary actions |
| `COLOR_BTN_SUCCESS` | `#16a34a` green-600 | Start buttons |
| `COLOR_BTN_DANGER` | `#dc2626` red-600 | Stop/destructive |
| `COLOR_BTN_GHOST` | slate-100 / slate-800 | Low-emphasis actions |
| `COLOR_ACCENT_AMBER` | `#d97706` amber-600 | Highlights, warnings |
| `COLOR_STATUS_ONLINE` / `_STARTING` / `_ERROR` | lime-400 / amber-400 / red-400 | Status dots, console tags |
| `COLOR_TEXT_ON_ACCENT` | `#ffffff` | Text/icons on saturated fills (buttons, toasts) |
| `COLOR_TEXT_ON_BRIGHT` | `#0f172a` | Text/icons on bright fills (lime-400 badges) |

Elevation comes from background contrast, not borders — cards use `border_width=0`. Borders are reserved for outline buttons, selection rings (selected server row), and the toast accent edge.

**Always check both modes.** The theme's default button `text_color` is white in light *and* dark, so any button on a light-in-light-mode fill (`COLOR_BTN_GHOST`, `"transparent"`) must set `text_color=AppConfig.COLOR_TEXT_PRIMARY` — otherwise it renders white-on-white in light mode.

### 3.4 Typography

Use the `AppConfig.FONT_*` tokens:

- Body: **Segoe UI Variable Text** (`FONT_BODY` 13, `FONT_BODY_SMALL` 11)
- Headings/Titles: **Segoe UI Variable Display**, bold (`FONT_HEADING` 18, `FONT_HEADING_SMALL` 14, `FONT_TITLE` 20)
- Console/code: **Cascadia Mono** (`FONT_MONO` 12)

Roboto is not installed on stock Windows — never use it.

### 3.5 Buttons & Icons

- All buttons must define `hover_color`. No button without explicit hover feedback.
- Icons come from `app/ui/icons.py` — `icon(name, size, color)`, PIL-drawn, antialiased, theme-tintable. **Never use emoji** as button/label icons (Tk renders them misaligned and untintable).
- Icon-only buttons need a `ToolTip`.

### 3.6 Dialogs & Windows

- Confirmations/info: `ZBBDialog.confirm()` / `ZBBDialog.info()` from `ui_components.py`. Never `tkinter.messagebox` (native gray dialog clashes with the dark theme). Only exception: the single-instance warning shown before the app window exists.
- Every `CTkToplevel`: call `apply_rounded_corners(window)` from `app/ui/win_effects.py` (Win11 native corners + shadow; no-op elsewhere).

### 3.7 Layout

- Long descriptive text must wrap to its container's live width (bind `<Configure>` and update `wraplength`, e.g. `AppSettingsDialog._wrap_to_card`) — a fixed `wraplength` clips once a scrollbar or DPI scaling eats into the width.
- Check the minimum window size (`AppConfig.MIN_WIDTH` × `MIN_HEIGHT`, 900×580). Below `SIDEBAR_COMPACT_BELOW` the sidebar shrinks to `SIDEBAR_WIDTH_COMPACT`.
- In rows that can clip from the right (badge rows), put status before decoration.
- Show values the way users think about them: `Yes`/`No`, not `True`/`False`; server.properties keys via `property_label()` ("Spawn NPCs", not "Spawn Npcs").

### 3.8 UI Thread Safety

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
| 1.x series | `v1.3.0`, `v1.4` | ✅ Released |
| F11 UI 2.0 + mod deps/update badges | `v2.0.0` | ✅ Released 2026-07-10 |
| Data directory + explainable safety + pre-update snapshots | next minor | On `dev`, tracked under `[Unreleased]` in `docs/changelog.md` |

Release process: `python tools/bump_version.py X.Y.Z`, fill in the changelog section, merge `dev` → `main`, tag `vX.Y.Z` — the build workflow gates on tests and publishes binaries with release notes taken from the changelog.

**Current dev state:** v2.0.0 + unreleased features above. 633 tests.

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

### Testing UI code

UI modules are not driven through Tk in tests. Extract decision logic into module-level pure helpers or static methods and test those (e.g. `modrinth_browser._snapshot_then_apply`, `_filter_updates_for_selection`, `ConsoleWidget._line_tag`).

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
| Visual Consistency | 20 pts | -5 per `corner_radius` literal outside the token scale / documented exceptions |
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

# 4. corner_radius literals (review each: must be a documented exception)
grep -rn "corner_radius=[0-9]" app/ui/ | grep -v "corner_radius=0"

# 5. Native dialogs (only the single-instance warning may remain)
grep -rn "messagebox" app/

# 6. Full test suite
pytest tests/ -q

# 7. Visual pass: screenshot every window/tab in Dark AND Light, plus the main window at 900x580
```

**Current score (2026-09-14): 97/100** — F401 clean, no banned patterns, no color/radius literals outside documented exceptions. Known deduction: `_kill_orphan_processes` (`main.py`) swallows `Exception` without logging on app exit (commented as intentional, but still breaks §2.2).
