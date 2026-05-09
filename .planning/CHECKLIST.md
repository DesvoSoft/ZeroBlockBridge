# ZeroBlockBridge — CHECKLIST.md

> Checklist paralelo de ejecución. Cada requirement de `PROJECT.md` se desglosa en subtareas verificables.
>
> **Orden de fases:** Cimientos → Auto-Healing → Arquitectura → Ecosistema → Provisioning
>
> La Fase 0 (Investigación) es prerrequisito de conocimiento para Ecosistema y Provisioning. Debe ejecutarse antes o en paralelo con Fase 1 y 2.

---

## Fase 0: Cimientos (Investigación) ✅

> Analizar auto-mcs antes de implementar. Evita reinventar lógica ya probada. **Completado.**

### RES-01 — Cross-platform patterns ✅

- [x] Read auto-mcs `source/launcher.py`: boot pipeline, path resolution, OS detection
- [x] Read auto-mcs `source/core/constants.py`: `run_proc`, `run_detached`, path handling, process spawning
- [x] Document Windows path handling patterns: backslashes, case-insensitivity, admin vs user dirs
- [x] Document process spawning differences: `Popen` args, `creationflags`, signal handling
- [x] Document user data directory resolution per platform
- [x] Produce summary document → `.planning/research/RES-01-cross-platform.md`

### RES-02 — Foundry.py version resolution ✅

- [x] Read auto-mcs `source/core/server/foundry.py` in full
- [x] Document version mapping logic: API endpoints → version list → download URL construction
- [x] Document fallback strategy when API is unreachable or returns unexpected data
- [x] Document SHA1 validation flow (noted: auto-mcs has NO SHA1 validation — gap for PROV-04)
- [x] Document supported server types and their API differences
- [x] Produce implementation spec → `.planning/research/RES-02-foundry-analysis.md`

### RES-03 — Java.py multi-installation detection ✅

- [x] Read auto-mcs `source/core/tools/java.py` in full
- [x] Document detection strategies: PATH scanning, JAVA_HOME, Windows registry, well-known paths
- [x] Document version matching algorithm: `get_supported()` with `version_check` chain
- [x] Document cross-platform differences: registry (Win) vs. alternatives (Linux)
- [x] Document edge cases: symlinks, spaces in path, non-standard installations
- [x] Produce implementation spec → `.planning/research/RES-03-java-detection.md`

### ANALY-01 — Deep-dive synthesis ✅

- [x] Synthesize all findings into a unified specification document
- [x] Map each auto-mcs pattern to its ZBB equivalent (adopt, adapt, skip)
- [x] Identify gaps: patterns auto-mcs has that ZBB still needs
- [x] Identify divergences: decisions where ZBB should differ from auto-mcs
- [x] Document 4 Architecture Decision Records (ADR-001 through ADR-004)
- [x] Produce final spec → `.planning/research/ANALY-01-synthesis.md`

---

## Fase 1: Auto-Healing

### STAB-01 — Single-instance lock

> Tarea rápida que evita corrupción de datos durante el desarrollo. Se ejecuta primero por seguridad.

- [x] Research cross-platform approaches: lockfile (portable), named mutex (Windows), socket
- [x] Implement lockfile mechanism on app startup (write PID to `{appdata}/.zbb.lock`)
- [x] On duplicate launch: detect existing lockfile with running PID, show warning dialog and exit
- [x] Handle stale lockfile: if PID in lockfile is dead, remove and proceed
- [x] Clean up lockfile on graceful app exit
- [ ] Test scenario: double launch, crash + relaunch, simultaneous launch

### AUTO-01 — Watchdog service

- [x] Research Java process exit codes and crash patterns (OOM, segfault, etc.) — *from RES-01/RES-03*
- [x] Create `app/services/watchdog.py` with Watchdog class
- [x] Implement crash detection via subprocess exit_code monitoring
- [x] **AUTO-01.1**: Capture stderr from subprocess to differentiate JVM errors (Java not found, wrong version) from Minecraft crashes
- [x] **AUTO-01.2**: Classify crashes as "Boot Crash" (<5s lifetime) vs "Runtime Crash" (≥5s lifetime) — different diagnosis and recovery
- [x] Implement OOM detection via console output pattern matching
- [x] Implement configurable max retries (default 3, configurable 0–10)
- [x] Implement auto-restart with exponential backoff between retries
- [x] Implement retry counter reset: if server stays stable >10 min, reset counter to 0
- [x] Integrate with ARCH-02 event bus (emit `ServerCrashed`, `ServerRestarted`)
- [ ] Add retry counter with persistence to avoid infinite loops across restarts
- [x] Add user notification (toast/dialog) on crash with retry count
- [x] Write unit tests: crash detection, retry logic, backoff, counter reset after stability, max retries exceeded, boot vs runtime crash classification

### AUTO-02 — Command sanitizer

- [ ] Research OS command injection vectors in bash and powershell contexts
- [x] Create `app/services/sanitizer.py` with CommandSanitizer class
- [x] Implement allowlist of known-safe Minecraft commands (op, deop, say, gamemode, etc.)
- [x] Implement character-level filter: reject `;`, `|`, `&&`, `` ` ``, `$()`, `$(`, `%`
- [x] Implement Minecraft command parser — allow unknown commands that pass char filter
- [x] Integrate sanitizer into console input pipeline (hook before subprocess stdin)
- [x] Write unit tests: known safe commands pass, injection payloads blocked, edge cases

### AUTO-03 — Lag detection

- [x] Create `app/services/lag_monitor.py` with LagMonitor class
- [x] Implement regex matcher for "Can't keep up!" and "Warning: TPS" patterns
- [x] Implement sliding window counter (e.g. N spikes in M minutes → threshold exceeded)
- [x] Implement configurable threshold (spike count + time window)
- [ ] Implement auto-restart trigger via ARCH-02 event when threshold exceeded
- [x] Add user notification on lag-triggered restart
- [x] Write unit tests: pattern matching, window counting, false positive rejection

### AUTO-04 — Heartbeat check (Zombie detection)

> Detects servers where the Java process is alive but unresponsive (no console output, no player join for N minutes).

- [x] Create heartbeat monitor: send `list` command every 60s, expect response within 10s
- [x] Track last console output timestamp; if silent >5 min, mark suspect
- [x] On suspect: send test command, if no response within 15s, classify as "Zombie"
- [x] Auto-restart zombie servers
- [x] Add user notification on zombie detection
- [x] Integrate with ARCH-02 event bus (emit `ServerZombieDetected`)
- [ ] Write unit tests: heartbeat timeout, zombie classification, recovery

---

## Fase 2: Arquitectura

### ARCH-01 — Extract server lifecycle ✅

> Esta es la tarea más riesgosa porque toca el núcleo del monolito. Se extrae por capas, no todo a la vez.

- [x] Define `BaseServer` abstract interface: start, stop, restart, status, send_command, get_console
- [x] Create `app/core.py` with `ZBBManager` class skeleton
- [x] Refactor `ServerRunner` in `logic.py` to use unified `EventBus`
- [x] Extract subprocess.Popen logic from logic.py into `app/services/process_runner.py`
- [x] Implement process_runner.py: PID tracking, kill, exit_code callback, stdout reader thread
- [x] Move process management (subprocess.Popen, PID tracking, kill) into ServerLifecycle
- [x] Move restart scheduling logic (interval + daily time) into ZBBManager
- [x] Move server status tracking (running, stopped, crashed, starting) into ZBBManager
- [x] Move console I/O (stdin pipe, stdout reader thread) into ServerLifecycle
- [x] Implement Observer pattern: ServerLifecycle emits status changes, UI subscribes without coupling
- [x] Refactor main.py to delegate all lifecycle operations to ZBBManager
- [x] Verify ALL existing functionality unchanged (manual smoke test)
- [x] Write unit tests: start, stop, restart, status transitions, process_runner, edge cases

### ARCH-02 — Typed event system ✅

- [x] Design all event types: `ServerCrashed`, `PlayerJoined`, `PlayerLeft`, `ServerReady`, `ServerStopped`, `NOTIFICATION`, `CONSOLE_LINE`, `STATUS_CHANGED`, `REQUEST_RESTART`
- [x] Create `app/server_events.py` with EventBus class and typed dataclasses
- [x] Implement pub/sub: `subscribe(event_type, handler)`, `emit(event)`, `unsubscribe(token)`
- [x] Implement thread-safe emission (RLock)
- [ ] Implement optional event filtering (subscribe with predicate)
- [x] Migrate existing UI callbacks (main.py status updates) to event handlers
- [x] Decouple UI callbacks (Toasts, Console) from core services using NOTIFICATION/CONSOLE_LINE
- [ ] Add event logging for debugging (emit → log structured message)
- [ ] Write unit tests: subscribe/emit/unsubscribe, multiple handlers, no-op on no handlers

### ARCH-03 — Circular buffer console ✅

- [x] Research CustomTkinter CTkTextbox performance with large content
- [x] Create `app/services/console_buffer.py` with CircularBuffer class (max 1000 lines, FIFO)
- [x] Implement O(1) append and O(n) read operations
- [x] Implement overflow behavior: oldest lines dropped when full
- [x] Implement line indexing for partial reads (e.g. last N lines)
- [x] Integrate with existing console UI widget (replace direct Textbox append)
- [x] Verify memory usage stable over simulated 48-hour session
- [x] Write unit tests: append, overflow, order preservation, empty buffer, partial read

### ARCH-04 — Lazy console rendering 🚧

- [x] Detect window minimize state (CustomTkinter event binding)
- [x] Pause text widget updates when window is minimized
- [x] Buffer incoming lines in memory while paused
- [x] On window restore: batch-render buffered lines (max 100 to avoid UI freeze)
- [ ] Verify CPU usage drops to near-zero when window minimized during server activity

### CONV-01 — Structured logging

- [ ] Audit all `print()` calls in `app/` directory
- [ ] Replace each with `logging.getLogger(__name__).info/warning/error/debug`
- [ ] Configure root logger: structured format `[YYYY-MM-DD HH:MM:SS] [LEVEL] [module] message`
- [ ] Add JSON-friendly format option for critical paths (startup, crash, restart)
- [ ] Ensure log levels used correctly: DEBUG (verbose), INFO (normal), WARNING (recoverable), ERROR (failure)
- [ ] Remove or redirect existing raw log file writes to structured format
- [ ] Verify no `print()` remains in app/ (grep check)

---

## Fase 3: Ecosistema

> ⚠️ **Prerrequisito:** Haber completado Fase 0 (RES-02 y ANALY-01) para tener specs de Foundry API.

### ECO-01 — Paper server type

- [ ] Consult spec from ANALY-01 for Paper API endpoints
- [ ] Add "Paper" to server type enum / selection dropdown in creation wizard
- [ ] Implement PaperVersionProvider: MC version → latest Paper build resolution
- [ ] Implement PaperDownloadProvider: download jar + SHA1 verification
- [ ] Test Paper server creation, startup, and playability
- [ ] Verify Paper-specific features work (e.g. `paper.yml` generation)

### ECO-02 — Purpur server type

- [ ] Consult spec from ANALY-01 for Purpur API endpoints
- [ ] Add "Purpur" to server type enum / selection dropdown
- [ ] Implement PurpurVersionProvider: MC version → latest Purpur build resolution
- [ ] Implement PurpurDownloadProvider: download jar + SHA1 verification
- [ ] Test Purpur server creation, startup, and playability

### ECO-03 — Modrinth integration

- [ ] Research Modrinth API v2: search, project detail, version listing, version download
- [ ] Create `app/services/modrinth.py` with ModrinthClient class
- [ ] Implement search endpoint: query → results with mod name, description, author
- [ ] Implement version listing per mod: filter by MC version and mod loader
- [ ] Implement download + install: download to `mods/` folder, handle conflicts
- [ ] Implement update checking: installed mod → latest available version comparison
- [ ] Add mod search UI (integrate into server settings or dedicated tab)
- [ ] Handle rate limiting (429) and network errors gracefully with retry + notification
- [ ] Write unit tests: search, download, version listing, error handling

### ECO-04 — Playit.gg API Mastery

> **Reference:** auto-mcs `source/core/tools/playit.py` — API-based tunnel management via `api.playit.gg`
>
> Current ZBB `playit_manager.py` only downloads/launches the CLI agent. ECO-04 adds programmatic control of tunnels and account linking via the Playit REST API.

- [ ] Research Playit API: auth flow (setup code → secret key), tunnel CRUD, agent registration
- [ ] Create `app/services/playit_api.py` with PlayitApiClient class:
  - `link_account(setup_code)` — exchange setup code for secret key via auto-mcs worker pattern, write `playit.toml`
  - `initialize()` — load secret key, register agent, retrieve tunnels
  - `create_tunnel(port, protocol)` — create tunnel via `tunnels/create` endpoint
  - `list_tunnels()` — retrieve all tunnels via `tunnels/list` endpoint
  - `delete_tunnel(tunnel_id)` — remove tunnel via `tunnels/delete` endpoint
  - `get_tunnel(port)` — find tunnel by local port, recycle oldest if limit exceeded
- [ ] Implement tunnel cache (JSON file, resilient to API failures)
- [ ] Implement per-server tunnel claiming (`tunnel.in_use` flag)
- [ ] Integrate with existing `PlayitManager`: use `PlayitApiClient` for tunnel operations, keep agent lifecycle
- [ ] Add agent key input and link flow to tunnel setup UI
- [ ] Write unit tests: auth flow, tunnel CRUD, cache fallback

---

## Fase 4: Provisioning

> ⚠️ **Prerrequisito:** Haber completado Fase 0 (RES-03 y ANALY-01) para tener specs de Java detection y version matching.

### PROV-01 — Java version detection

- [ ] Consult spec from ANALY-01 for Java detection patterns from auto-mcs
- [ ] Create `app/services/java_detector.py` with JavaDetector class
- [ ] Implement Windows registry scan: `HKLM\SOFTWARE\JavaSoft\Java Runtime Environment`
- [ ] Implement PATH scan: `java -version` for each `java`/`java.exe` in PATH
- [ ] Implement `JAVA_HOME` environment variable detection
- [ ] Implement well-known paths scan: `C:\Program Files\Java\`, `/usr/lib/jvm/`, etc.
- [ ] Implement version string parsing: extract major.minor from `java -version` output
- [ ] Build MC version → required Java version mapping table
- [ ] Integrate with server creation wizard: auto-select matching Java, show warning if none found
- [ ] Write unit tests: registry parsing, version string parsing, path detection

### PROV-02 — Server directory scaffolding

- [ ] Define directory structure template: `server/`, `mods/`, `config/`, `plugins/`, `logs/`, `backups/`
- [ ] Create scaffolding function in server lifecycle
- [ ] Generate `eula.txt` = `true` after user accepts EULA in wizard
- [ ] Generate start script (`.bat` for Windows, `.sh` for Linux) with correct Java path + flags
- [ ] Generate `server.properties` with safe defaults (online-mode, port, etc.)
- [ ] Generate `zbb_metadata.json` for ZBB tracking (type, version, created date, java path)
- [ ] Integrate with server creation wizard (run scaffolding after download)

### PROV-03 — Build-tools analysis

- [ ] Analyze auto-mcs Spigot build-tools integration approach
- [ ] Document: time cost (~30 min per build), disk usage, Java requirement for build
- [ ] Document pros: official binaries, latest patches; cons: slow, resource-heavy, fragile
- [ ] Make decision: use precompiled Paper/Purpur binaries OR implement build-tools
- [ ] Update PROJECT.md → Out of Scope or Active with decision outcome

### PROV-04 — SHA1 validation

- [ ] Consult spec from ANALY-01 for SHA1 validation flow from foundry.py
- [ ] Implement SHA1 checksum verification function in download pipeline
- [ ] Implement retry on checksum mismatch: re-download up to 3 attempts
- [ ] Implement fallback: if SHA1 not provided by API, log WARNING and proceed
- [ ] Add user notification on persistent download corruption after 3 retries
- [ ] Integrate with all downloaders: Vanilla, Fabric, Forge, Paper, Purpur
- [ ] Write unit tests: checksum match, mismatch triggers retry, max retries exceeded

### PROV-05 — Aikars Flags

- [ ] Document Aikars flag rules: RAM → JVM argument mapping (4G, 6G, 8G, 10G+)
- [ ] Create `app/services/aikars_flags.py` with AikarsFlags class
- [ ] Implement flag calculator: input RAM in GB → output JVM args string
- [ ] Integrate with server startup command builder (add flags to java invocation)
- [ ] Integrate with UI-01: allow override in Advanced View
- [ ] Write unit tests: each RAM tier produces correct flags, edge cases (2G, 12G)

### INTEG-03 — Java Version Matcher

- [ ] Consult spec from ANALY-01 for version matching approach
- [ ] Build version compatibility matrix (MC → Java): {<1.17: Java 8/16, 1.17–1.20.4: Java 17, ≥1.20.6: Java 21}
- [ ] Check Java version before server start (hook in start pipeline)
- [ ] Block start with clear, user-friendly error message on mismatch
- [ ] Suggest actionable fix: "Select Java X from dropdown" or "Select MC version Y"
- [ ] Integrate with PROV-01 (use detected Java list for suggestion dropdown)
- [ ] Write unit tests: all version tier matches, mismatch blocked, no JDK found handled

### REND-01 — Pre-warm cache

- [ ] Create background task runner module in app bootstrap
- [ ] Implement async fetch of Mojang version manifest on startup (use threading, non-blocking)
- [ ] Implement async fetch of Fabric/Forge/Paper/Purpur manifests
- [ ] Implement cache with TTL: write to temp JSON, refresh if older than 1 hour
- [ ] Implement staleness handling: if cache hit but TTL expired, serve stale + refresh in background
- [ ] Ensure non-blocking: wizard opens instantly even if fetch is in progress
- [ ] Handle network errors gracefully: serve cache if available, show toast if no cache + network down

### UI-01 — Advanced View toggle

- [ ] Add toggle switch or "Advanced" button in server creation/settings view
- [ ] Define advanced section contents: Aikars Flags editor, Java path selector, raw file editor
- [ ] Hide advanced section by default (visible only when toggle is active)
- [ ] Implement Aikars Flags overrides in advanced view (text field for custom JVM args)
- [ ] Implement manual Java binary selector (file picker filtered to java/java.exe)
- [ ] Implement raw file editor (list of server files, open in editor, save changes)
- [ ] Persist toggle preference across app restarts (config file or registry)

---

## Summary

| Phase | Requirements | Subtasks | Status |
|-------|-------------|----------|--------|
| 0. Cimientos ✅ | RES-01, RES-02, RES-03, ANALY-01 | ~23 | ✅ Completed |
| 1. Auto-Healing | STAB-01, AUTO-01, AUTO-02, AUTO-03, AUTO-04 | ~44 | ✅ Implemented (core + toasts) |
| 2. Arquitectura | ARCH-01, ARCH-02, ARCH-03, ARCH-04, CONV-01 | ~37 | 🚧 In Progress |
| 3. Ecosistema | ECO-01, ECO-02, ECO-03, ECO-04 | ~28 | 🔲 Not started |
| 4. Provisioning | PROV-01–05, INTEG-03, REND-01, UI-01 | ~40 | 🔲 Not started |
| **Total** | **23 requirements** | **~172 subtasks** | **~100 / 172 ✅** |

---

*Last updated: 2026-05-09 — ARCH-01, ARCH-02, and ARCH-03 completed. ARCH-04 (Lazy rendering) in progress. Preparing for Phase 3 (Ecosistema).*
