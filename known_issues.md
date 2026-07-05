# Known Issues (Persistent) — 2026-07-04

Tracking doc for bugs that survived a first fix attempt or need dedicated investigation. Not part of roadmap.md phase tracking — pull items into roadmap once a fix is scoped.

## Priority order (blocking → annoying)

### 1. 🔴 Server creation fails in packaged .exe (Fabric install)

**Symptom (source run, fixed):**
```
[Error] Installation failed: [WinError 5] Access is denied
```
**Symptom (packaged .exe, still failing after fix #1):**
```
[Error] Failed to create server 'test'. Check terminal for details.
```

**Fixes applied so far:**
- `498de06` — retry installer subprocess spawn on transient WinError 5/32 (OneDrive/AV lock theory).
- `a9eab3e` — anchor `BASE_DIR` to the .exe's real directory instead of `__file__`, which in a PyInstaller onefile build resolves inside the per-launch `sys._MEIPASS` temp extraction dir (wiped on exit, heavily AV-scanned — servers/config/bin were being written and executed from there).

**Update 2026-07-04 (source run):** WinError 5 reproduced in source run on *first* JDK download. Real root cause found: `JdkManager.ensure_java` returned the JDK cache **directory** (`.zbb_cache/jdks/jdk17`) instead of the `java.exe` path on a fresh download — spawning a directory raises WinError 5. Cached runs returned the binary correctly, which is why only first-run installs failed. Fixed on dev: `ensure_java` now resolves and returns the actual binary (raises `JdkError` and purges the dir if extraction produced no binary).

**Status:** Root cause (#2, BASE_DIR) is the more likely real fix — not yet validated against a rebuilt .exe (build itself blocked by stale running processes locking `dist\ZeroBlockBridge.exe`, resolved by killing PIDs before rebuild). **Needs re-test**: rebuild via `rebuild_exe.bat`, run the fresh exe, attempt Fabric server creation, confirm it succeeds and `servers/` now lives next to the .exe (not disappearing after process exit).

**If still failing after BASE_DIR fix:** need the actual traceback — `[Error] Failed to create server '{name}'. Check terminal for details.` means `success` came back `False` with no exception (see `app/ui/main.py:673-674`), so the real failure is swallowed somewhere in `logic.create_server` / `install_fabric` returning `None`/`False` silently. Add a file-based log handler (no console window in windowed .exe build — `logging.basicConfig` currently only logs to stdout, invisible to GUI users) so failures are diagnosable without a source checkout.

**Confirmed via source run (`py app/launcher.py`), same server config (Fabric, MC 26.2):** creation itself **succeeds** cleanly —
```
[INFO] [app.services.scaffolder] Scaffolding complete for .../app/servers/test 2
[INFO] [app.services.bytecode_analyzer] Bytecode analyzer: Main-Class 'net.minecraft.bundler.Main' requires Java 25 (class v69)
[INFO] [app.ui.main] Server Info for Mod Search: test 2 | MC: 26.2 | Loader: fabric
```
No WinError 5, no install failure. This narrows the bug to **packaged .exe only** — supports the BASE_DIR/_MEIPASS theory (#2 fix) as the actual cause, since source runs never touch `_MEIPASS`. Re-test specifically against the rebuilt .exe to confirm.

---

### 2. 🔴 Playit tunnel: agent secret invalid loop

**Symptom:**
```
[Playit] No tunnel for port 25565. Creating via API...
[Playit] API Error: Cannot create tunnel: no agent_id available. Ensure playit is linked.
[Playit] Version check failed ([WinError 216] This version of %1 is not compatible with the version of Windows you're running...). Redownloading...
[Playit] Downloading agent v0.17.1 ...
[Playit] Launching tunnel agent...
[Playit] Invalid secret, do you want to reset (Y/n)?
[Playit] ERROR: Agent secret invalid. Use 'Reset Tunnel' to re-link.
[System] Clearing tunnels...
... (repeats — reset does not actually re-link, just clears and relaunches with the same invalid secret)
```

**Two distinct bugs bundled here:**

1. **WinError 216** — "this version of %1 is not compatible with the version of Windows" on the downloaded `playit-windows-x86_64-signed.exe`. Classic architecture mismatch (e.g. ARM64 Windows running an x86_64 binary without emulation enabled, or a corrupted/incomplete download). Confirm host CPU arch; check if download is corrupted (partial write) vs genuinely wrong binary.
2. **Invalid secret not actually resolved by "Reset Tunnel"** — agent reports `playit.toml` secret invalid, user resets, agent relaunches, immediately hits the *same* invalid secret again. Reset flow (`Clearing tunnels... Cleaning up remote tunnels... Stopping agent... Tunnels cleared. Agent stays linked.`) does not regenerate/re-link the secret — "Agent stays linked" is the bug: it should force a fresh claim/link when the existing secret is rejected by the API, not just clear tunnels and keep reusing the dead secret.

**Status:** Bug 2 (invalid secret loop) **fixed on dev** (2026-07-04), 4 changes in `playit_manager.py` / `playit_api.py`:
1. Secret validated against API before agent launch (`secret_rejected()` — only definitive 401/403 blocks; network errors don't block offline starts).
2. `_dns_polling_loop` stops after 3 consecutive 401/403 (tracked via `PlayitApiClient.consecutive_auth_failures`) instead of polling every 5s forever.
3. `reset(mode="soft")` escalates to `full` when `_auth_failed` — deletes `playit.toml`, unlinks, forces fresh re-link (was the "Agent stays linked" bug).
4. `InvalidAgentKey` stdout line now routed to auth-failure branch (was wrongly treated as "0 tunnels" and triggered tunnel creation with the dead key).

Needs field re-test with a stale secret to confirm the escalation UX.

**Update 2026-07-04 — agent migrated v0.17.1 → v1.0.10 (playitd).** Field report: fresh account, agent linked OK, tunnel created via API but `alloc.status` stuck `pending` forever; v0.17.1 agent looped on "register queued" and threw "got unexpected response from register request". playit retired the standalone CLI agent — v1.0 release assets ship the `playitd` daemon (the Windows exe asset IS playitd.exe). Migration changes: flags are now `--secret-path`/`--socket-path` (hyphens), no `--stdout` (daemon logs to stderr, already merged into the stdout pipe), custom IPC socket `@zbb-playitd` (namespaced form; raw `\\.\pipe\...` path was rejected by the daemon's bind), no `version` subcommand (installed version tracked in `bin/playit.version` marker; download smoke test is `--help`), tunnel-ensure moved from the dead "agent has 0 tunnels" stdout trigger to the DNS polling loop (3rd poll).

**Still unresolved server-side:** with a validated v1.0.10 daemon connected (`playit connected; tunnels loaded ... account_status="verified"`), the tunnel STILL stayed pending (verified live 2026-07-04, tunnel 79a78c0e). Minimal legacy `tunnels/create` payloads also stay pending; new `/v1/tunnels/create` rejects agent-key requests with "failed to parse body" (likely web-session only). Down-detector shows a cluster of playit "Failed to connect to tunnel" reports around 2026-07-01 — suspected playit-side allocation backlog/incident. Next isolation step: create a tunnel manually in the playit dashboard for the ZeroBlockBridge agent; if it allocates, ZBB picks it up via API polling; if it also hangs pending, it's 100% playit-side. Bug 1 (WinError 216) fixed on dev 2026-07-04: download now goes to a temp file (`agent_download.tmp`), gets a size check (>= 1 MB), a `playit version` smoke test, then atomic `os.replace` into `playit.exe`. A truncated or arch-incompatible download is never installed — `ensure_binary` returns False with a clear console message (WinError 216 reported as CPU architecture mismatch) instead of entering the infinite redownload cycle. Needs field re-test on the affected machine.

**Confirmed via source run log (`app.services.playit_api`):** the loop is a hard **`InvalidAgentKey` (HTTP 401)** on every rundata call, both primary and fallback agent-id lookups, repeating every ~5s indefinitely with no backoff-and-give-up or auto re-link:
```
[WARNING] [app.services.playit_api] Failed to get agent id via rundata: Playit API returned HTTP 401: {"status":"error","data":{"type":"auth","message":"InvalidAgentKey"}}
[WARNING] [app.services.playit_api] Fallback agent_id detection failed: Playit API returned HTTP 401: {"status":"error","data":{"type":"auth","message":"InvalidAgentKey"}}
```
This confirms the stored `playit.toml` secret/agent key is stale/invalid at the API level (not just the local CLI's own "Invalid secret" prompt) — the fix needs to detect a persistent 401 on agent-id lookup and force a fresh link/claim flow (delete `playit.toml`, restart the claim URL flow) rather than retrying the same dead key forever. Also needs a retry cap/backoff — currently polls every ~5s with no upper bound visible in the log.

---

### 3. 🟡 No persisted log file for packaged .exe

Cross-cutting blocker for diagnosing #1 and #2 in the field: `logging.basicConfig` (app/ui/main.py:920) has no `FileHandler`, and the windowed (`console=False`) .exe has no visible stdout. Any `logger.error(...)` traceback is invisible to a user running the packaged build — they can only report what's shown in the in-app console widget, which is a curated `[System]/[Error]` message, not the real exception.

**Fix scope:** add a rotating `FileHandler` (e.g. `CONFIG_DIR / "logs" / "zbb.log"`) alongside the existing `basicConfig`, so field bug reports can include the real traceback.
