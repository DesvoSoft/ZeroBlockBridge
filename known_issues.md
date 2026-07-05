# Known Issues (Persistent) — 2026-07-05

Tracking doc for bugs that survived a first fix attempt or need dedicated investigation. Not part of roadmap.md phase tracking — pull items into roadmap once a fix is scoped.

All previously tracked issues below are **resolved and verified** as of 2026-07-05. Kept for history/context on recurring failure classes (orphan processes, external API breakage). Delete entries once confidence is high they won't regress.

## Resolved

### 1. Server creation failed on first JDK download (WinError 5 / Access is denied)

Root cause: `JdkManager.ensure_java` returned the JDK cache **directory** instead of the `java.exe` path on a fresh download — spawning a directory raises WinError 5. Cached runs returned the binary correctly, masking the bug on second+ runs.

Fixed (`eaae0eb`): `ensure_java` resolves and returns the actual binary via `_find_java_binary`, raising `JdkError` if extraction produced no binary.

### 2. Playit tunnel stuck in "pending" allocation forever

playit.gg retired the standalone CLI agent (v0.17.1). All v1.0 release assets ship the `playitd` daemon instead — a full architecture rewrite, not a drop-in update.

Migration (`bc05c3f`, `3348e0c`): agent bumped to v1.0.10. Flags now hyphenated (`--secret-path`, `--socket-path`), no `--stdout` (daemon logs to stderr into the same pipe), Windows IPC socket needs the namespaced `@zbb-playitd` form (raw `\\.\pipe\...` is rejected at bind time), no `version` subcommand (tracked via `bin/playit.version` marker, `--help` used as install smoke test). Tunnel-ensure trigger moved from the dead "agent has 0 tunnels" stdout line to the 3rd DNS-polling iteration.

Verified live end-to-end: agent links, tunnel allocates a public address, players connect through it.

### 3. Orphan `playitd` surviving app close — duel-session log flapping

Symptom: `tunnel_count` flapping 1→0→1→0 every ~6s, `SessionNotSetup` reconnect spam. Root cause: an orphaned `playitd` from a previous session and the newly launched one fighting over the same account.

Fixed (`3348e0c`): `_kill_stale_agents()` kills any process matching the tracked binary path before launch, plus a Windows Job Object (`KILL_ON_JOB_CLOSE`) assigned to the spawned process so the OS reaps it even on a hard parent death that skips `atexit` (crash, taskkill, closed console). Extracted to shared `app/core/process_job.py`, applied to both the playit agent and the Minecraft server process (see #5).

### 4. Paper API returning 410 Gone

`api.papermc.io/v2` was retired. Migrated (`d085f42`) to Fill API v3 (`fill.papermc.io/v3`) — different response shape (`versions[].version.id`, `downloads["server:default"].url`), requires a descriptive `User-Agent` header.

### 5. "FAILED TO BIND TO PORT" crash on server start (Address already in use)

Root cause: same orphan-process class as #3, but for the Minecraft server itself — a `java.exe` from a previous session survived a hard app kill and kept holding the port.

Fixed (`c1a43af`): Job Object reaping applied to `ServerRunner.start()` (children inherit the job, so Fabric/Forge's inner java is covered too), plus a preflight port-in-use check before spawning — fails fast with a clear toast ("Port X is already in use by another process") instead of a cryptic crash ~5-30s into startup.
