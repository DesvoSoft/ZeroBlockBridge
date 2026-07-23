# Changelog — ZeroBlockBridge

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

---

## [2.0.0] — 2026-07-10

### Added
- **Settings 2.0** — 5-tab dialog (General/Notifications/Java/Storage/About). Theme selector, Discord webhook event checkboxes, managed JDKs with purge, disk usage by category, crash report purge.
- **Light theme** — Full light/dark/system theme support across the app. Live theme flip, 38 color tokens.
- **Players dashboard** — Ops/bans/whitelist management as a tabbed view.
- **Server templates** — Save/load/list/delete reusable server configs, selectable in the creation wizard. 4 built-in templates.
- **.zbbpack migration** — Export/import a server as a single portable archive (ZIP-slip guarded, disk space checked).
- **Modrinth browser overhaul** — Async icon loading, bulk install feedback, status messaging.
- **Discord webhooks** — Optional notifications for crash/ready/backup/player events, with per-event custom message templates.
- **Auto-healing** — Crash watchdog with exponential-backoff restart, zombie detection (console-silence probe), lag-spike monitoring.
- **Java auto-management** — JDK/JRE auto-download per server (JRE preferred, ~45 MB vs ~300 MB JDK fallback), required-version detection from bytecode + version map.
- **Server creation wizard** — Summary/review step before creation, with an optional "start server after creation" toggle.
- **Console UX** — Search with highlight + jump-to-next-match, colored lines by category (errors, warnings, joins/leaves, `[Server]` system lines).
- **World management** — List/switch active world per server.
- **Linux support (experimental)** — Native binary via PyInstaller, Docker GUI/binary images and compose profiles, process reaping (`prctl` PDEATHSIG), Forge `run.sh` detection, Playit force-kill and filesystem socket path.
- **Mod dependency resolution** — Installing a mod now resolves its required Modrinth dependencies and prompts once to install them together; incompatible-with-installed mods are surfaced as a warning.
- **Mod update badges** — Installed-mods view background-checks for updates and shows a one-click update badge per outdated mod.
- **Test suite** — 572 automated tests (pytest), flake8-clean.

### Changed
- Server creation wizard reorganized into 6 steps (Identity, Engine+Version, Resources, Rules&Security, World&Network, Summary).
- "Load Existing Folder" / "Import .zbbpack" merged into a single "Add Server" menu.
- Build packaging unified: `ZeroBlockBridge.spec` / `linux.spec` are now the single source of truth for both local and CI builds (previously CI used separate raw PyInstaller flags that had drifted from the specs).
- Minimum supported Python raised to 3.10 (matches CI and Docker validation).
- `APP_VERSION` in `app/core/app_config.py` is now the single source of truth for the displayed version.

### Fixed
- **Linux Java auto-install** — Adoptium serves `.tar.gz` on Linux/mac (previously the installer only handled `.zip`, breaking auto Java installation on native Linux).
- Playit `_parse_line` race causing a double `TUNNEL_STATUS` emit.
- `JavaDetector` shared cache going stale across long sessions (now 5-minute TTL).
- Numerous UI stability fixes: rounded-corner toplevels, theme-flip tag reapplication, wizard RAM slider/step3 layout, Modrinth status feedback silently dropped, start/stop and tunnel start/stop buttons no longer show both enabled/disabled side by side.

### Validation
- 572 tests passing on Windows (pytest, flake8 clean).
- Tests passing on Ubuntu 22.04 LTS (Docker, Python 3.10.12, OpenJDK 17).
- Local PyInstaller build from `ZeroBlockBridge.spec` smoke-tested (clean launch, no missing-asset errors).

---

*For detailed phase-by-phase history (pre-2.0 development), see `docs/roadmap-history.md`.*
