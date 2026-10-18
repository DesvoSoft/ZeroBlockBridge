# Roadmap

Iterative plan agreed on 2026-10-13. Each item ships as its own `feature/<name>` branch and PR to `dev`, held to the Definition of Done in [STANDARDS.md §8](STANDARDS.md#8-definition-of-done-per-iteration) (`tools/qa_gate.py` READY, independent review, regression tests, visual pass). Releases (`dev` → `main`) only with the owner's go-ahead.

## Released in 2.3.0 (2026-10-15)

| # | Item | PR |
|---|------|----|
| 0 | Per-user Windows install (shortcuts, Apps entry, uninstall), first-launch data-folder bug fix, wizard modpack/world import, QA gate | #14 |
| 1 | Atomic metadata/config writes, folder-import engine/version detection, parallel modpack downloads, verified `.part` downloads | #15 |
| 2a | Close to tray or exit (don't ask again), clean process exit, real cancel of server creation, `.part` backups | #16 |
| 2b | Imported world's Minecraft version checked against the server (`level.dat`) | #18 |
| 3 | NeoForge servers, modpacks, mods, folder import; CurseForge worlds link in the wizard | #19 |
| — | Fixes from the manual test of the packaged `.exe`: built-in templates shipped, exit and window-close errors, BOM-tolerant install marker | #20 |

## Manual test of the packaged `.exe` (2026-10-15, CI build of `dev` @ 91042bd)

Passed on Windows 11, clean machine:
- **Install:** exe in `%LOCALAPPDATA%\Programs`, Start menu and Desktop shortcuts (OneDrive-redirected Desktop), Apps entry, `install.json`. Nothing was written next to the downloaded file.
- **First run:** EULA, then a Vanilla 26.3 server created in about a minute with Java 25 downloaded, started to Done.
- **Window and tray:**
  - Close to tray keeps the server running; tray Open restores the window.
  - Exit stops the server cleanly and leaves no process.
  - Opening the app again while it runs says where it is.
- **Update:** opening the download again offers Open installed app, or Update to X when it is newer.
- **Uninstall:** refused while the app runs; afterwards it removes the exe, shortcuts and Apps entry, keeps servers and settings, and a reinstall reuses the data folder.

Not covered: SmartScreen (a `gh`-downloaded file has no Mark-of-the-Web), and a real version-to-version update (both builds were 2.2.0, so the installed version was edited in `install.json`).

## Next: languages and the Qt UI (decided 2026-10-15)

CustomTkinter's rendering problems are structural (every widget is a Tk canvas; about 17% of UI code and ~50 private-API uses exist only to work around it), so the UI moves to **PySide6 (Qt Widgets)**, subject to a spike. The Python core and its tests stay as they are. Each screen is translated to Spanish as it is ported, so the CustomTkinter screens are never translated twice.

| # | Item | Notes |
|---|------|-------|
| 8a | i18n foundation and language at install | **Part 1 in review** (`feature/i18n-foundation`): i18n module, catalogs + tooling, OS language detection, picker on the first setup page, persistence (marker / portable settings / Settings → General), Spanish for the pre-app dialogs, EULA, close dialog, tray and single-instance message, locale-aware formatting. **Part 2 in review** (`feature/i18n-core-messages`): label/key separation (console and Settings tabs, theme, player filters, Modrinth sort, schedule mode, property impact, tunnel status, crash reasons, blocked-command reasons, Java dropdown, explicit console line kinds) and Spanish for the core/services messages (notifications, exceptions, progress). Scope: Dependency-free i18n module, gettext `.po` catalogs in `assets/locales`, Babel extraction, plural and locale-aware formatting helpers. Separate display labels from internal keys (console/settings tabs, theme, player filters, sort options, BlockedReason, crash reason codes, tunnel-log tagging). Language picker on the first setup page (default: Windows UI language), stored in `install.json` (portable: the data folder's settings) and in Settings → General. Spanish for setup/update/uninstall dialogs, core messages and notifications. |
| 8a-2 | Discord messages in Spanish | **In review** (`feature/discord-language`): setting `discord_language` (auto = app language / en / es), default embeds, test message, durations and plurals rendered with an explicit catalog (`i18n.catalog`), independent of the UI language; custom templates never translated; Settings → Notifications → Message language. |
| 8b | UI-agnostic API seam over the core | **Part A done** (PR #25, `feature/api-seam`): `app/api` facade (servers, console, tunnel, players, backups, mods, Java, settings, storage), event subscriptions through a UI-supplied dispatcher, task handles with progress and cancellation; mod file deletes/installs/modpacks/icons moved from the Modrinth browser into `app/services/mod_content.py` / `mod_icons.py` behind a mods/plugins-only delete guard; "open folder" in one place; main window and Modrinth browser switched to the API. **Part B in review** (`feature/api-seam-b`): server-properties catalog in `app/api/property_catalog.py`; players panel, Settings dialog, wizard and properties editor on the API (new `players`, `config`, `creation` areas; backups, Java, settings and storage extended); `AppApi.legacy_manager` removed; every screen held to API-only imports by a test. Scope: Commands, queries and events with tests; move logic out of screens (Modrinth browser file deletes/downloads, folder opening). |
| 8c | Qt spike (2 days) | **Done: GO with conditions** (`spike/qt`, draft PR; results in [QT-SPIKE.md](QT-SPIKE.md)): dialogs open in 26–74 ms with no white flash (CustomTkinter 120–370 ms, flashes), exe 30.9 MiB (CustomTkinter 23.0), cold start 1.54 s vs 2.41 s, es/en correct at 150 % (emulated). Conditions: real 150 %/mixed-DPI check, port first-run/setup/EULA dialogs before dropping tkinter, Linux Qt build in CI, LGPL notices. Planned: Server list, live console, tray, one wizard dialog, dark/light, Spanish from the same catalog. Passes if: dialog opens < 100 ms with no flash, exe ≤ 60 MB, startup ≤ current + 1 s, correct at 150% scaling with Spanish text. Otherwise repeat with pywebview. |
| 8d | Screen-by-screen migration behind `--ui=qt` | Main window/console/tray → server list/header → wizard → properties → settings and setup dialogs → players → Modrinth browser. One PR per group, Spanish included. Remove CustomTkinter at parity. |

## Later

| # | Item | Notes |
|---|------|-------|
| 4 | Onedir packaging + in-app auto-update | Faster startup, fewer antivirus hits; update from GitHub releases with `.sha256` verification. |
| 5 | Code signing | SignPath (free for OSS) or Azure Trusted Signing; needs an owner account. |
| 6 | Modrinth modpack search inside the wizard | Modrinth API already integrated. |
| 7 | Bedrock crossplay bundle | Geyser + Floodgate, one click on Paper/Fabric. |
| 9 | UI smoke-test harness | Script the wizard/dialog screenshots used for visual passes (pytest-qt once the Qt UI exists). |

## Known follow-ups

From the manual `.exe` test (UX, not blocking):
- Opening the app again while it runs shows a message; it should bring the running window to the front.
- The EULA dialog opens in the screen's top-left corner instead of centred.
- An empty server list has no empty state pointing to Create New Server.
- The wizard's version list has nothing selected by default.
- Game mode and difficulty show lowercase ("survival", "normal").
- Vanilla servers get `mods/` and `plugins/` folders they can't use.
- The zombie-check `list` probe and its reply show in the user's console.

Other:
- Forge 1.7.10-style version strings for pinned loaders.
- Quilt servers/modpacks (still unsupported).
- `tests/test_orchestrators.py::test_start_blocked_when_no_server_selected` leaks an unhandled thread exception warning.
- Split the largest modules (`modrinth_browser.py`, `main.py`, `logic.py`) opportunistically.

## Decided not to do

- **In-app CurseForge browsing**: the CurseForge API needs an approved key that can't live in a public repo. The wizard links to the CurseForge world catalogue instead, and downloaded world `.zip`s are imported directly.
