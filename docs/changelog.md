# Changelog — ZeroBlockBridge

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

---

## [0.9.0-pre] — 2026-07-10

### Added
- **Linux native binary** — `Dockerfile.linux` multi-stage build: PyInstaller compiles `zeroblockbridge` (15MB self-contained binary) inside Docker, produces minimal 450MB runtime image (Ubuntu 22.04 + JRE 17 + Tk libs). No Python needed in runtime. `linux.spec` for PyInstaller config.
- **Docker GUI deployment** — `Dockerfile.gui` (multi-stage, 491MB) for full Python+Tk GUI via X11 forwarding.
- **Docker compose profiles** — `docker-compose.yml` with two services: `zbb-gui` (Python GUI) and `zbb-linux` (native binary). `start-zbb-gui.bat` one-click launcher with mode selector (1=GUI, 2=Binary). Auto-detects VcXsrv, host IP, builds + runs.
- **Linux process reaping** — `process_job.py` rewritten with `linux_preexec()`: `prctl(PR_SET_PDEATHSIG, SIGKILL)` + parent PID re-check post-fork. Prevents orphaned MC server / playitd processes when ZBB crashes on Linux.
- **Linux Forge detection** — `install_forge()` now detects `run.sh` alongside `run.bat`, enabling Forge Modern installation on Linux.
- **Linux Playit force-kill** — `_kill_stray_by_name()` uses `psutil.process_iter` + `pkill -9 -f playit` fallback. Shared between `stop(force=True)` and `_atexit_stop()`.
- **Linux Playit socket path** — Filesystem path (`CONFIG_DIR/zbb-playitd.sock`) on Linux, abstract namespace (`@zbb-playitd`) on Windows.
- **JavaDetector cache TTL** — `_shared_cache` expires after 5 minutes via `time.monotonic()`. Prevents stale JVM list across long sessions.
- **Sidebar accent line** — 3px `COLOR_ACCENT_GREEN` left border on selected `ServerListItem`.
- **Tunnel collapse fix** — Tunnel status row collapses properly when server offline + playit linked.
- **Sidebar tooltips** — All sidebar buttons (Create Server, Add Server, Settings, Link Playit) show tooltips on hover.
- **Test suite** — 560 tests passing (558 passed + 2 skipped Windows-only on Linux Docker).

### Changed
- `process_job.py` — Full rewrite (83 → 139 LOC). `assign_to_job()` for Windows Job Objects, `linux_preexec()` for Linux.
- `logic.py` — `_popen_kwargs()` static method on `ServerRunner`, `install_forge()` run.sh check, `import platform`.
- `playit_manager.py` — `_kill_stray_by_name()`, socket path platform branch, preexec_fn on Popen.
- `docker-compose.yml` — Two services: `zbb-gui` (Python+Tk, 491MB) and `zbb-linux` (native binary, 450MB).
- `start-zbb-gui.bat` — Now supports both modes: GUI (X11 forwarding) and Binary (native Linux). Auto-detects VcXsrv + host IP.

### Fixed
- **A3-B05: Playit `_parse_line` race** — DNS check moved inside `_lock` to prevent double-emit `TUNNEL_STATUS`.
- **A2-P03: JavaDetector stale cache** — 5-minute TTL prevents serving outdated JVM list.

### Validation
- 560 tests passing on Windows (pytest, flake8 clean)
- 558 tests passing on Ubuntu 22.04 LTS (Docker, Python 3.10.12, OpenJDK 17)
- Linux native binary: 15MB self-contained, builds via PyInstaller in Docker multi-stage
- Docker images: GUI=491MB, Binary=450MB
- 2 skipped: Windows-only `is_pid_alive` tests (expected on Linux)

---

## [0.8.0-pre] — 2026-07-07

### Added
- **F15: Light theme** — 38 `AppConfig` color tokens as `(light, dark)` tuples. `resolve_color()` bridge for Tk-native consumers. Theme selector functional (Dark/Light/System). Live theme flip works.
- **F14: App Settings** — 5-tab dialog (General/Notifications/Java/Storage/About). Theme selector, webhook event checkboxes, managed JDKs with purge, disk usage by category, crash report purge.
- **F13: Java installer** — JRE preferred with JDK fallback (~45 MB vs ~300 MB per version). `_query_assets` + `_fetch_asset_info` pipeline.
- **MODS-UX** — Async icon loading (no prefetch block), bulk install feedback, status label, installed view batching.
- **UI-AUDIT-2** — `apply_rounded_corners` on 5 missing toplevels. PlayersDashboard, SPE, Wizard, Toast polish.
- **Templates** — `template_manager.py` (save/load/list/delete). 4 default templates. Selector in wizard Step 2.
- **Migration** — `migration.py` export/import `.zbbpack`. ZIP slip guard, disk space check, progress callback.
- **Players** — `player_files.py` (ops/bans/whitelist). `PlayersDashboard` as `CTkTabview`.
- **Console** — Search highlight + jump-to-next-match. Search bar in Console + Tunnel Log tabs.
- **World** — `list_worlds`/`get_active_world`/`set_active_world` + dropdown in World tab.

### Changed
- Wizard reorganized 4 → 5 steps (Identity, Engine+Version, Resources, Rules&Security, World&Network).
- Java selection interactive in wizard Step 3 (radio: detected vs recommended).
- "Load Existing Folder" / "Import .zbbpack" merged into single "Add Server" menu.
- Modrinth Browser: green accent only on Install/Selected/Installed badge. Combos/search/toggle to lime tokens.

### Fixed
- Wizard truncamiento de RAM y saturación de step3.
- `VersionManager._refresh_versions` → `refresh_versions()` (AttributeError).
- Console Next button re-searches when text changed.
- 36 tuple-anidation sites that crashed UI at instantiation.
- `ConsoleWidget._set_appearance_mode` re-applies tags on theme flip.
- Modrinth `_set_status` was `pass` — ~40 feedback messages silenced.

---

## [0.7.0-pre] — 2026-07-05

### Added
- **Job-object reaping** — Windows `Job Object` for MC server process tree.
- **Server delete** — Right-click context menu option.
- **First-run EULA** — Consent dialog on first launch.
- **Heartbeat / zombie detection** — Console silence probe + timeout.
- **Discord webhook** — Optional notifications for crash/ready/backup/player events.

### Fixed
- Paper Fill API v3 migration.
- Playitd orphaned agents reaping.
- Duel-session tunnel noise.
- Slow I/O and callbacks outside locks.
- Heartbeat events firing outside lock.

---

*For detailed phase history, see `docs/roadmap-history.md`.*
