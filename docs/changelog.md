# Changelog — ZeroBlockBridge

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Added
- **Application log file** — the app now writes `logs/zbb.log` (rotating, 2 MB × 3) in the data folder, including crashes in background threads and UI callbacks. The released Windows build has no console, so until now every log line was lost. Settings → About has an **Open Logs Folder** button to attach it to bug reports.
- Mods status bar shows a tinted success/error/warning icon; long messages are shortened with the full text on hover.
- **Live server status** — the header reads "Starting… 12s" while the server boots and "Running · 1h 20m" once it is up, shows the server's memory use against its allocation ("RAM 1.3 / 2.0 GB", hidden at narrow window widths) and players as online/max ("2/20").
- **The app remembers where you left off** — window size, position and maximized state, the last selected server and the last console tab are restored on launch (a position on a monitor that is no longer connected is ignored).
- **Console command history** — Up/Down in the command input recall the last 50 commands sent.
- **Backups tab rework** — each backup is a row with its date, a reason chip (Manual, Auto, Pre-update) and size, plus its own Restore and **Delete** buttons; **Open Folder** jumps to the server's backup directory.
- **Installed mod count** — the Mods tab's Installed button shows how many mods/plugins the server has, with an amber dot and "N updates available" tooltip when newer versions exist.
- Servers without an icon get a colored initial tile in the sidebar list.
- **Players tab** (replaces the Player Management window) — one list of every player the server knows (online, joined before, whitelisted, operators, banned) with skin heads, status chips, last seen and playtime, search and filters. Each player has an actions menu: kick or ban with a reason, make operator with a described permission level, whitelist, unban, copy UUID. Players can also be added by name.
- **Player history** — ZBB records when each player was first and last seen and how long they have played, per server.
- Main tabs show icons plus the online player count and the installed mod count.
- **Tunnel Log categories** — the Tunnel Log filter has its own categories (All / Errors / Warnings / Tunnel / Agent) instead of the server console's Security/Players/Server, which never matched tunnel output; raw playitd agent lines are dimmed.

### Changed
- Dependencies are pinned to the exact tested versions (`requirements.txt`, new `requirements-dev.txt`), so CI and release builds install the same packages; Dependabot proposes weekly updates.
- Server creation logic moved out of the main window into a core provisioning module. The progress bar no longer jumps back from 100% to 25% after the download.
- Mod dependency lookups use bulk Modrinth requests instead of two requests per dependency.
- All fonts and colors come from the design tokens (the creation wizard used ad-hoc sizes); text inputs use a themed dialog instead of CustomTkinter's unthemed input box.
- **Mod lists no longer pop in widget by widget** — search pages render behind the "Loading mods" cover until fully drawn, switching between Explore and Installed swaps two ready lists instead of rebuilding them, and installing or uninstalling a mod only redraws that card. Both views share one footer, so the status line stays visible in Installed and the list keeps its size.
- The Mods tab reloads its results (or the Installed list) for the newly selected server when you switch servers.
- The console command input is disabled while the server is stopped, with a hint saying why, instead of accepting commands and answering "Server is not running".
- The header reads "Server: ● Running" / "Tunnel: ● Online" with the labels in gray and only the state colored; the tunnel join address is blue so it stands out as the thing to share.
- Layout alignment pass: server and tunnel start buttons share one right edge and both rows are the same height; the properties editor lines up every "?" badge, impact dot, switch and input in one control column, and its Automation tab uses the same layout as the other tabs; wizard steps 4–6 line up with steps 1–3 and the Rules & Security switches sit on a grid; the Settings cards are visibly raised with the Notifications buttons aligned to them; the Mods search bar and footer use even insets.
- Every dialog uses the same footer buttons: secondary (outlined) next to the primary action on the right. Dialog primary actions use the lime primary color; green is kept for start buttons.
- Outlined buttons use a 2px border (1px borders looked broken around rounded corners).
- Every dialog shows the app icon and a titlebar tinted to match its background, and titlebars follow live Dark/Light switches.
- **Minimal titlebars** — the titlebar no longer draws the app icon or window title (both stay in the taskbar and Alt-Tab); every dialog names itself with a title and subtitle at the top of its body instead.
- Scrollbars only appear when a list or page actually overflows.
- The Mods tab is disabled (with a tooltip) for vanilla servers, which can't load mods or plugins.
- Mod cards: installed mods show an "Installed" button with a menu (update to the newer version when one exists, uninstall) instead of a red Uninstall button; descriptions are limited to two lines; category tags are neutral so the client/server badge stands out.
- The header RAM readout shows memory used ("RAM 2.3 GB"), with a tooltip explaining that the server's RAM setting caps Java's heap, so total usage can be higher.

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
- Scheduled and pre-restart backups were saved as manual backups, so the auto-backup "keep last N" setting also deleted backups you made by hand. Automatic backups are now tagged "auto" and only they are rotated.
- The server stop button jumped next to the server name once the server started.
- Light mode: mod cards were white on a white list and couldn't be told apart.
- The "Loading mods" message went blank as soon as search results arrived, leaving an empty panel while the page was built.
- Settings, Properties, Players and the other dialogs showed CustomTkinter's blue icon instead of the app's.
- Whitelist, operator and ban entries added while the server was stopped were written without a UUID, so the server ignored them on startup. They are now written with the player's real UUID (from the server's user cache, Mojang, or the offline-mode UUID).
- The operator level chosen while the server was running was shown but not applied (`/op` always uses the server's `op-permission-level`); the running-server menu now offers that level and says so.
- Bedrock players joining through Geyser/Floodgate (names starting with ".") were never counted as online.
- Dialogs opened before their window was shown (Server Properties, confirmations) missed the titlebar tint.
- Windows flashed white when opening (the Server Properties editor showed a mostly white frame) before their content drew in; windows now stay invisible until drawn and fade in.

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

