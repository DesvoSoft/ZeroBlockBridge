# Changelog — ZeroBlockBridge

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Added
- **Application log file** — the app now writes `logs/zbb.log` (rotating, 2 MB × 3) in the data folder, including crashes in background threads and UI callbacks. The released Windows build has no console, so until now every log line was lost. Settings → About has an **Open Logs Folder** button to attach it to bug reports.
- Mods status bar shows a tinted success/error/warning icon; long messages are shortened with the full text on hover.

### Changed
- Dependencies are pinned to the exact tested versions (`requirements.txt`, new `requirements-dev.txt`), so CI and release builds install the same packages; Dependabot proposes weekly updates.
- Server creation logic moved out of the main window into a core provisioning module. The progress bar no longer jumps back from 100% to 25% after the download.
- Mod dependency lookups use bulk Modrinth requests instead of two requests per dependency.
- All fonts and colors come from the design tokens (the creation wizard used ad-hoc sizes); text inputs use a themed dialog instead of CustomTkinter's unthemed input box.

### Fixed
- A server that failed to launch because Java could not be started stayed stuck on "Starting" with no error.
- Servers whose jar needs a newer Java than the Minecraft version implies were re-scanned on every start instead of caching the result.
- A truncated `server.jar` could not be replaced by the real jar during setup.
- The zombie-server check could treat unrelated plugin or chat lines as an answer to its `list` probe.
- Playit: a full reset left the account marked as linked if `playit.toml` was locked by OneDrive or an antivirus; an HTML 401 response did not count toward detecting a revoked secret.
- Discord notifications could queue without limit during a crash loop or with an unreachable webhook.
- Opening a dialog from the creation wizard or the properties editor made that window stop being modal.
- Toast badges rendered as pills instead of circles, and single-line messages were centered.
- Long Mods status messages pushed the page controls out of view at small window sizes.

## [2.1.0] — 2026-09-16

### Added
- **Configurable data directory** — first-run dialog offers Standard (`%LOCALAPPDATA%`), Portable (next to the exe), or Custom location; choice persists via a marker file, resolved before any other module reads a path.
- **Explainable command safety** — blocked console commands now surface a warning toast naming the rejected command and why (e.g. ``Blocked `op x; rm -rf /`: contains shell metacharacters``), `[Security]` console lines get a distinct red tint, and Settings → General lists the full allowlisted command set read-only.
- **One-click pre-update snapshot + rollback** — mod updates (single or bulk) take a full-server backup before touching any files; a failed snapshot aborts the update instead of proceeding blind. Pre-update snapshots are labeled in the Backups tab and share the existing restore flow.
- **Java detection is now a visible moment, not backend trivia** — creating a server shows "Detected Minecraft 1.20.4 → requires Java 17", names the exact release being installed ("Installing Temurin 17.0.9+9…") instead of a bare version number, and calls out the rare case where bytecode analysis disagrees with the standard version mapping.
- **Console log filter** — a category dropdown (All / Errors / Warnings / Security / Players / Server) on both the Console and Tunnel Log tabs, on top of the existing search. Lines stay in the buffer while hidden, so switching back to "All" is instant.
- **Branded titlebar (Windows 11)** — the native titlebar now matches the app's own theme colors instead of default Windows gray/black.
- **Toast and dialog entrance animation** — notifications slide up while fading in; confirmation dialogs fade in on open.

### Changed
- Removed a redundant, architecture-violating client-side command-safety check in `main.py`; `ServerOrchestrator.send_command` is now the single enforcement point.
- Command sanitizer returns a typed `BlockedReason` instead of free-form strings.
- Backups gained a `reason` tag (`manual` vs `pre_update`) with per-reason retention, so automated pre-update snapshots can never prune a user's manual/scheduled backups.
- Mod updates now require the server to be stopped: a running server locks files, so the snapshot would be incomplete. A snapshot that skipped locked files is discarded instead of being offered as a rollback point.
- Mods tab now builds itself on first visit instead of at every app startup — faster launch.
- Privacy & Service Disclaimer reworded: states plainly that ZBB has no remote-control agent of its own, and separately calls out the trust boundary when Playit.gg tunneling is enabled (that traffic runs through Playit's infrastructure, not ZBB's).
- Deleting a server, installing/removing mods, and importing a modpack are now correctly blocked (or moved off the UI thread) while the server is running or the world is large, instead of risking a locked-file error or a frozen window.

### Fixed
- Player chat containing `[Security]` could render as a red ZBB security alert in the console; only lines emitted by ZBB with that prefix are highlighted now.
- **Minecraft 26.x now requires Java 25.** Year-based versions (26.1, 26.2, …) fell through to a Java 17 default, so the wizard announced the wrong Java and Fabric/Forge setup pre-downloaded an unneeded Java 17 runtime.
- Light mode: Cancel, Back, Refresh, Export, Browse and other secondary buttons rendered white-on-white; switches had an invisible knob.
- Settings → General: the Console Command Safety description and allowlist were cut off instead of wrapping.
- Server properties: `generate-structures`, `sync-chunk-writes` and `prevent-proxy-connections` showed a raw `true` text field instead of a switch; labels now read "Spawn NPCs", "Server IP", "PvP", "RCON" instead of "Spawn Npcs", "Server Ip", "Pvp", "Rcon".
- Wizard summary shows `Yes`/`No` and "Auto (Java 25)" instead of `True`/`False`/`auto`; Back uses the same chevron icon as Next.
- Mods tab at minimum window size: the sidebar narrows to give the browser room, and the "Installed" badge is no longer the first thing clipped.
- The app icon now shows correctly in the taskbar and titlebar — it previously fell back to the default Python icon both in the installed app and when run from source.
- Toast notifications could overlap or land in the wrong spot when more than one window had notifications open at once, or when messages wrapped to different heights; a notification flood is now capped instead of piling up unreadable past the top of the window.
- A wide range of stability hardening from a full internal audit: scheduled restarts, auto-backups, and crash/zombie detection could — under specific rare timing or a malformed config value — silently stop working for the rest of a session with no visible error; several race conditions around starting the server, starting the Playit tunnel, and concurrent downloads that could corrupt state; whitelist/operator/ban changes could occasionally be lost to a conflicting write; backup restore could fail entirely when the server and the system temp folder are on different drives; several settings/config files now save atomically so a crash mid-write can't corrupt them.

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

