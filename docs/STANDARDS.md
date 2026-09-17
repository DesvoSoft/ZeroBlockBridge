# ZeroBlockBridge — Technical Standards

This document defines the coding standards, architectural philosophy, and quality criteria for ZeroBlockBridge.
All contributors (human or AI) must adhere to these rules.

> **Last updated:** 2026-09-16 — 800 tests in 44 files, 100% pass.

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

Use `AppConfig` constants only. Hardcoded color literals (`"green"`, `"white"`, `"gray"`, `"#f97316"`) in widget calls are banned. "Dirt Block" palette — lime green primary, brown secondary, slate backgrounds, **no blue accents** (single exception: `COLOR_ADDRESS`, the tunnel join address, so the thing to share stands out). Tokens are `(light, dark)` tuples where they differ:

| Token | Value | Use |
|-------|-------|-----|
| `COLOR_BG_DARK` | `#0b1120` | Main background (dark) |
| `COLOR_BG_SIDEBAR_DARK` | `#0a0f1c` | Sidebar (dark) |
| `COLOR_BG_CARD_DARK` | `#243044` | Cards/panels (dark) |
| `COLOR_BTN_PRIMARY` | `#65a30d` lime-600 | Primary actions |
| `COLOR_BTN_SECONDARY` | `#92400e` amber-800 (brown) | Secondary actions |
| `COLOR_BTN_SUCCESS` | `#16a34a` green-600 | Start buttons only — dialog confirms use `COLOR_BTN_PRIMARY` |
| `COLOR_BTN_DANGER` | `#dc2626` red-600 | Stop/destructive |
| `COLOR_BTN_GHOST` | slate-100 / slate-800 | Low-emphasis actions |
| `COLOR_ACCENT_AMBER` | `#d97706` amber-600 | Highlights, warnings |
| `COLOR_STATUS_ONLINE` / `_STARTING` / `_ERROR` | lime-400 / amber-400 / red-400 | Status dots, console tags |
| `COLOR_TEXT_ON_ACCENT` | `#ffffff` | Text/icons on saturated fills (buttons, toasts) |
| `COLOR_TEXT_ON_BRIGHT` | `#0f172a` | Text/icons on bright fills (lime-400 badges) |
| `COLOR_BADGE_*` (`BG`/`TEXT`, `NEUTRAL_`, `DANGER_`, `WARNING_`) | pairs | Chips/pills (e.g. backup reason: Manual neutral, Auto lime, Pre-update amber) |
| `COLOR_ADDRESS` | blue-600 / blue-400 | Tunnel join address and its copy button — nothing else |

Elevation comes from background contrast, not borders — cards use `border_width=0`. Borders are reserved for outline buttons, selection rings (selected server row), and the toast accent edge.

**Always check both modes.** The theme's default button `text_color` is white in light *and* dark, so any button on a light-in-light-mode fill (`COLOR_BTN_GHOST`, `"transparent"`) must set `text_color=AppConfig.COLOR_TEXT_PRIMARY` — otherwise it renders white-on-white in light mode.

### 3.4 Typography

Every font comes from an `AppConfig.FONT_*` token — never `ctk.CTkFont(size=...)` or a literal `(family, size)` tuple (`tests/test_ui_design_tokens.py` enforces this):

- Body: **Segoe UI Variable Text** — `FONT_BODY` 13, `FONT_LABEL` 13 bold (form labels), `FONT_CAPTION` 12 (hints, tooltips), `FONT_BODY_SMALL` 11, `FONT_MICRO` 10
- Headings/Titles: **Segoe UI Variable Display**, bold — `FONT_TITLE` 20, `FONT_HEADING` 18, `FONT_HEADING_SMALL` 14, `FONT_SUBHEADING` 13, `FONT_LABEL_SMALL` 12 (compact buttons), `FONT_BADGE` 11, `FONT_MICRO_BOLD` 10, `FONT_STAT` 22 (large numbers)
- Console/code: **Cascadia Mono** — `FONT_MONO` 12, `FONT_MONO_SMALL` 11

Colors follow the same rule: no raw `"#rrggbb"` in `app/ui` outside `icons.py`.

Roboto is not installed on stock Windows — never use it.

### 3.5 Buttons & Icons

- All buttons must define `hover_color`. No button without explicit hover feedback.
- Icons come from `app/ui/icons.py` — `icon(name, size, color)`, PIL-drawn, antialiased, theme-tintable. **Never use emoji** as button/label icons (Tk renders them misaligned and untintable).
- Icon-only buttons need a `ToolTip`.
- Status severity is an explicit `kind` (`success`/`error`/`warning`) rendered with a tinted icon — never a leading ✓/✗/⚠ glyph in the text.
- Outlined buttons: `border_width=AppConfig.BORDER_BTN` (2). 1px CTk borders break up around rounded corners.
- A disabled action button switches to `COLOR_BTN_GHOST` fill (and `COLOR_TEXT_PRIMARY` text), so it doesn't read as clickable (Send, Install Selected, Update/Delete (n)).
- Row labels mirror each other: a gray label plus a colored state ("Server: ● Running", "Tunnel: ● Online").
- Selected vs running server: the dashboard, tabs and dialogs follow `MCTunnelApp.viewed_server`; `ZBBManager.current_server` stays the server that runs (monitors, scheduler, watchdog and history depend on it). Never repoint `current_server` while a server runs — select it only when nothing runs, or right before starting.
- Log widgets declare their own filter categories: `ConsoleWidget` (server: Errors/Warnings/Security/Players/Server) and `TunnelLogWidget` (Errors/Warnings/Tunnel/Agent) via `FILTERS`, `_FILTER_GROUPS` and a `_line_tag` override.
- Tabs of the main `console_tabs` carry an icon (`_TAB_ICONS`) and, where useful, a live count in the button text ("Mods (9)"); the tab *name* stays the plain key.
- Only create a container frame when it will have children: an empty `CTkFrame` requests 200×200 and inflates its row.

### 3.6 Dialogs & Windows

- Confirmations/info/text input: `ZBBDialog.confirm()` / `ZBBDialog.info()` / `ZBBDialog.ask_string()` from `ui_components.py`. Never `tkinter.messagebox` or `ctk.CTkInputDialog` (native gray dialog clashes with the dark theme). Only exception: the single-instance warning shown before the app window exists.
- Every `CTkToplevel`: call `apply_rounded_corners(window)` from `app/ui/win_effects.py` (Win11 native corners + shadow; no-op elsewhere). It also sets the app icon (CTkToplevel otherwise swaps in CustomTkinter's blue logo ~200ms after creation) and tints the titlebar with the window's `fg_color`, re-applied on every Dark/Light switch. Pass `caption_color=(light, dark)` to tint with something else (the main window uses the sidebar color).
- Windows: derive dialogs from `ui_components.ZBBToplevel` (never bare `ctk.CTkToplevel`) — it calls `hide_until_drawn`, which keeps the window transparent until no widget has been reconfigured for 50ms, then fades it in (a plain toplevel flashes white and fills in widget by widget). The main window calls `hide_until_drawn` at startup.
- Header: `dialog_header(parent, title, subtitle)` from `ui_components.py` at the top of every dialog body. Titlebars draw no icon or title (`hide_titlebar_caption`, applied by `apply_rounded_corners`), so the body header is the only visible name.
- Menus: `themed_menu(parent)` returns a `ui_components.PopupMenu` (never `tk.Menu`, a native Win32 menu that ignores the theme): `add_command(label, command, icon_name=...)`, `add_separator()`, `add_cascade(label, menu)` (opens in place with a Back row), `add_danger_command(menu, label, command, icon_name=...)` for red destructive items, then `tk_popup(x, y)`. Give either all items of a menu an icon or none — spacers keep labels aligned, but mixed menus look unfinished.
- Footer buttons: `dialog_buttons(parent, primary_text, on_primary, secondary_text, on_secondary, danger=..., primary_colors=...)` from `ui_components.py` — right-aligned, primary action rightmost, outlined secondary beside it. Don't hand-build dialog footers.

### 3.7 Layout

- Long descriptive text must wrap to its container's live width (bind `<Configure>` and update `wraplength`, e.g. `AppSettingsDialog._wrap_to_card`) — a fixed `wraplength` clips once a scrollbar or DPI scaling eats into the width.
- Check the minimum window size (`AppConfig.MIN_WIDTH` × `MIN_HEIGHT`, 900×580). Below `SIDEBAR_COMPACT_BELOW` the sidebar shrinks to `SIDEBAR_WIDTH_COMPACT`.
- In rows that can clip from the right (badge rows), put status before decoration.
- Show values the way users think about them: `Yes`/`No`, not `True`/`False`; server.properties keys via `property_label()` ("Spawn NPCs", not "Spawn Npcs").
- **Alignment**: controls stacked in one panel share a right edge. Settings rows use a fixed-width control column (`server_properties_editor._CONTROL_WIDTH`, help/impact columns with `minsize`) so every card lines up; text-less switches use `_bare_switch()` (CTkSwitch otherwise reserves an empty label column); sibling rows (server/tunnel) use identical insets and heights.
- Scrollable areas use `ui_components.ScrollableFrame` (not `ctk.CTkScrollableFrame` directly): it hides the scrollbar while the content fits.
- A scrollable frame holding aligned content uses `corner_radius=0` — a rounded one insets its content by the radius and shifts it off the column of the widgets above/below.
- Readouts that don't fit at compact width (below `SIDEBAR_COMPACT_BELOW`) are hidden rather than squeezed (e.g. the header RAM label).

### 3.8 UI Thread Safety

Never read widgets from a background thread. Always `self.after(0, lambda: self.widget.configure(...))`.

### 3.9 Rendering Long Lists Without Pop-in

Each CTk widget is several native windows that draw themselves on `<Configure>`, i.e. after layout, one by one. Rules for lists of cards/rows (`modrinth_browser.py` is the reference):

- Build rows **under a cover** (an overlay styled like the empty list) or **beneath** the visible list, lay them out in small batches (`update_idletasks()` per batch keeps a spinner animating), and reveal only after the last batch is drawn (`ModrinthBrowser._reveal_when_drawn`).
- Switch views by stacking ready frames in one grid cell and `tkraise`-ing the wanted one. Never `grid_remove()`/`grid()` a populated list: re-mapping redraws every widget visibly.
- Keep geometry stable across views (shared footer in the same slot), so a switch doesn't resize the list.
- When one item changes (install/uninstall/delete), replace that row only — create the new row in the same grid cell, then destroy the old one.
- Show a loading message immediately for network loads and don't reset it when the data arrives; delay it (`delay_spinner=True`) only for local refreshes that are usually instant.
- Verify with an external capture (another process calling `PrintWindow` on the window); frames grabbed from inside the Tk loop stall with it and misrepresent what the user sees.

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

**Current dev state:** v2.0.0 + unreleased features above. 800 tests.

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
