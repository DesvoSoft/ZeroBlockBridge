# ZeroBlockBridge — Roadmap History (archivo)

Detalle completo de fases/auditorías completadas, archivado de `roadmap.md` el 2026-07-06 para reducir ruido. Referencias de commits e IDs preservadas — consultar aquí si se necesita el detalle línea-por-línea de un fix ya resuelto.

---

## F0-F3: Foundation + Quick Wins + Refactors ✅

### Fase 0: Auditoría Táctica ✅
Auditoría inicial + fixes 0.5.x: retry, port validation (1-65535), dialog grab release (WM_DELETE_WINDOW), watchdog backoff cap 3600s.

### Fase 1: Quick Wins ✅
| # | Tarea | LOC | Estado |
|---|-------|-----|--------|
| 1.1 | statemanager.py — singleton → 3 vars + 2 funciones | -50 | ✅ |
| 1.2 | Fix select_server() duplicado | 1 | ✅ |
| 1.3 | Eliminar mod_provider.py obsoleto | -67 | ✅ |
| 1.4 | CircularBuffer → collections.deque | -32 | ✅ |
| 1.5 | server_events.py — eliminar RLock + EventPayload | -15 | ✅ |
| 1.6 | Eliminar read_properties() alias | -2 | ✅ |
| 1.7 | settings_manager.py — singleton → módulo | -35 | ✅ |

### Fase 2: Bugfixes + Wizard UX ✅
Fix check_java_startup() (JavaDetector), DNS recovery chain (3 mecanismos), TunnelStatusProvider elimina "Starting..." duplicado, fix project_type filter + get_popular_mods(), Playit Link UX collapsible redesign, progress_callback(float) → progress_callback(float, str), mensajes de progreso detallados en wizard, pre-flight Java check en ServerWizard.

### Modrinth Management (F3.10-3.14) ✅
Gestión de mods instalados (lista + delete), paginación "Load More", íconos reales vía URL asíncrona, Check for Updates en UI, selector de versión al instalar.

### Refactors Estructurales (F3.2, 3.3, 3.5, 3.6, 3.8, 3.9) ✅
install_fabric/install_forge → _run_installer(); start_server() helpers extraídos; metadata.json centralizado en get/update_server_meta(); _pre_warm_version_cache() eliminado; _apply_pending_settings() eliminado; Scheduler + SchedulerService fusionados en logic.Scheduler.

### Thread Safety + Tests (F3.15-3.25) ✅
statemanager.py con threading.Lock, settings_manager.py lock en _settings[key]=value, tests Windows compat (tempfile.gettempdir()), type hints en Watchdog/BackupManager/Toast/Heartbeat, tests playit_manager (443 LOC) + heartbeat (61 LOC).

---

## FA-FB: UI + Layout v1.4 ✅

### Fase A: UI + Bugfixes ✅
Copy-IP solo host (sin puerto), toast duplicado eliminado de dashboard, server tag muestra versión MC en sidebar.

### Fase B: Layout Final ✅
Start All eliminado del dashboard; SERVER/TUNNEL secciones con separador; server controls ▶■ movidos a status bar inline; sección SERVER eliminada del dashboard; label TUNNEL eliminado; tunnel padding pady=(4,1); default window 1150×700 min 900×580; mod card hover fix; mod card grid_columnconfigure(1, weight=1); Java detection cache clase-level (JavaDetector._shared_cache).

---

## FIX-P1: 7 Críticos ✅
| # | Bug | Archivo | Fix |
|---|-----|---------|-----|
| C1 | AppConfig.SERVERS_DIR inexistente | server_properties_editor.py | Importar SERVERS_DIR desde constants |
| C2 | EventBus thread-safety (dict race) | server_events.py | RLock en _listeners |
| C3 | settings_manager.init nunca llamado | main.py + settings_manager.py | set_config_dir(CONFIG_DIR) en init |
| C4 | get_agent_id() retorna None | playit_api.py | Optional[str] |
(resto de los 7 críticos ya resueltos, ver commits de la época)

## FIX-P2: Thread Safety + Dead Code ✅
| # | Bug | Archivo | Fix |
|---|-----|---------|-----|
| P2.1 | Lock en _parse_line/_read_output | | |
| P2.2 | version_manager double-join | version_manager.py | _wait_for_background_refresh simplificado |
| P2.3 | core restart race | core.py | _restart_lock con try/finally |
| P2.4 | remove_config_key muerto | core.py | Eliminado |
| P2.5 | stop_all muerto | core.py | Eliminado |
| P2.6 | import Any muerto | server_properties.py | Eliminado |

## FIX-P3: Whitelist + TPS + Wizard Security ✅
| # | Tarea | Archivo | Fix |
|---|-------|---------|-----|
| P3.1 | Whitelist toggle no persiste server.properties | players_dashboard.py | _toggle_whitelist() llama save_server_properties(); switch carga estado real |
| P3.2 | TPS máximo 10 (debe ser 20) | orchestrators.py | Tick loop sleep 100ms → 50ms (20Hz) |
| P3.3 | Wizard Step 3 sin settings de seguridad | server_wizard.py, scaffolder.py | 8 campos: enforce-whitelist, pvp, online-mode, max-players, spawn-protection, enable-command-block, allow-flight, enforce-secure-profile |

---

## F4: Auto-Backup Scheduler ✅
Backend: BackupScheduler modelo (enabled, interval_hours, retention_count, mode, last_run) en logic.py; SchedulerOrchestrator._start_tick_loop check backup due.
UI: Automation tab con switch enable/disable, spinboxes interval_hours (1-168, default 24) y retention_count (1-30, default 5), countdown "Next backup in ~Xh Ym" (self.after 60s recursivo), modo selector full/world-only. Backups tab con info + botón "Run Backup Now". 11 tests en test_backup_scheduler.py, 100% pass. Verificado 2026-07-04.

---

## P0: Foundation Hardening ✅ COMPLETO
- **P0.1** Tests para Orchestrators — 26 tests, MagicMock(spec=...) + FakeEmitter
- **P0.2/P0.3** F4 UI Automation + Backups tabs — ver F4 arriba
- **P0.4** Pin Dependencies + pyproject.toml — requirements.txt pinneado, pyproject.toml creado, `pip install -e .` verificado (Python 3.14.3), requires-python ampliado a `>=3.12,<3.15`
- **P0.5** Fix Circular Dependency core↔orchestrators — ServerState movido, Protocol IS-A → HAS-A
- **P0.6** Suscribir CRASHED Event — `_on_server_crashed` en `_setup_monitors()`, NOTIFICATION tipo error + crash_history en metadata.json
- **P0.7** Clean Up Dead Imports — 9 archivos limpiados (BackupScheduler, Path, load/save_server_properties, atexit/Dict/Any/List, re, field), flake8 F401=0 verificado 2026-07-04

### REFACT-1: Refactors estructurales — ⏸️ POSPUESTO (YAGNI para pre-alpha 1 developer)
- R1-01: Launch pipeline start_server() como steps funcionales (_step_check_disk, _step_read_meta, _step_scaffold, _step_resolve_java, _step_launch) — orchestrators.py, ~70 LOC + ~40 tests, riesgo bajo, prerequisito R1-02
- R1-02: JavaResolver — extraer _resolve_java_bin a service — core.py → services/java_resolver.py, ~80 LOC + ~50 tests, riesgo bajo
- Orden: R1-02 → R1-01. Revisitar cuando equipo crezca o start_server/_resolve_java_bin necesiten cambios de feature.

---

## F5: Crash Report Collector ✅
CrashReporter (app/services/crash_reporter.py) — subscribe CRASHED, snapshotea console buffer, escribe JSON en `servers/<name>/crash_reports/`. Schema: timestamp, server info, crash info, stderr/console tail, system info. Límite 50 reportes (rotación FIFO). Integrado en ZBBManager._setup_monitors(). 11 tests, 373 total. Implementado 2026-06-24.

## F6: Discord Webhook ✅
DiscordWebhookService (app/services/discord_webhook.py) — EventBus subscriber, queue.Queue + worker thread único, rate-limit 2s. Settings `discord_webhook_url` + `discord_notify_on`. Activo solo si hay URL configurada. URL no se loggea ni expone. 10 tests, 409 total (commit 4edafcc). Implementado 2026-06-24.

## MODS-B: Modrinth Browser Mejoras ✅
_resolve_server_context() + _require_server() helpers extraídos; MC version + loader filter dropdowns; update count badge; Installed Mods inline (toggle en search bar); sort options (relevance/downloads/follows/newest/updated); hover fix (bind solo en card frame); NR-10 constantes migradas a AppConfig; paginación clásica Prev/Next 20 results/page; import .mrpack (CA-M04, mrpack_installer.py). 410 tests (commit 11b02f6). Implementado 2026-06-24.

## F8: Bulk Mod Operations ✅
Multi-select + batch delete/update (Installed + búsqueda), `apply_update()`. F7.5 (modpack one-click install) implementado junto con F8: búsqueda project_type=modpack → `download_version_to()` + `install_mrpack()`. Implementado 2026-07-01.

---

## EXE-PERF: .exe Startup/Shutdown Performance ✅ COMPLETO
Bugs reproducidos en release 1.4 (.exe PyInstaller). Todos los 6 fixes aplicados (commits 026d13e → e683436):

| # | Fix | Archivo | Estado |
|---|-----|---------|--------|
| EXE-01 | `_threads` join interno → `shutdown(wait=True, cancel_futures=True)` | core/core.py | ✅ `4bfefe8` |
| EXE-02 | Shutdown executor UI en `on_close` | ui/main.py | ✅ `026d13e` |
| EXE-03 | Kill explícito de subprocesos antes de `destroy()` | ui/main.py | ✅ `026d13e` |
| EXE-04 | VersionManager lazy init (no en __init__) | core/version_manager.py | ✅ `61a103a` |
| EXE-05 | Eliminar `sys.exit(0)` de `on_close` | ui/main.py | ✅ `026d13e` |
| EXE-06 | `shutdown()` en thread separado, no bloquea mainloop Tk | ui/main.py | ✅ `026d13e` |

Criterio de aceptación cumplido: cierre <2s sin server, <6s con server corriendo, zero terminales flash, ventana <1s al iniciar, on_close no bloquea mainloop.

---

## BUG-AUDIT — 2026-06-19 — ✅ 18/19 resueltos

Audit completo de codebase, 19 issues. Severidades: 🔴 CRITICAL 2/2, 🟡 HIGH 6/6, 🟡 MEDIUM 5/5, 🔵 LOW 5/6 resueltos.

Fixes clave: CA-01 double toast crash (watchdog + core.py) → `6b00462`; CA-02 java hardcodeado en installers → `3117759`; JAVA-FLOOR bytecode shim Java8 → `a4a909c`; HA-01 strptime crash en backups → `146553a`; HA-02 TOCTOU running=False → `ea4c3ff`; HA-03 stop→restart race → `2fee336`; HA-04 auto-backup gated por restart scheduler → `ceb6882`; HA-05/06 ServerRunner.running property + connected_players lock → `3e17fd3`; MA-01 countdown salta 1 → `a0186bc`; MA-05 missed restart sin log → `91c0ce2`; LA-01/02/04/05 → `91c0ce2`/`9ffa2a9`.

**Único pendiente:** LA-06 (`core/logic.py:736-740` get_server_ram/set_server_ram) — confirmado NO es dead code, sigue usado por SPE. No requiere acción.

---

## NR: No-Roadmap — Hallazgos inspección 2026-06-22 ✅ (mayoría resuelta)

Origen: revisión profunda UI/core durante modernización visual. NR-01/02/09/DASH resueltos (commit e37cc0a). NR-03/06/07/08 resueltos (sesión 2026-06-23). NR-04/05 (java detector thread, modrinth error state) y NR-10 (palette deuda modrinth_browser.py) — verificar si siguen pendientes antes de re-priorizar; no confirmados en roadmap principal.

---

## AUDIT-2: Auditoría profunda core+services — 2026-06-22 ✅ (mayoría resuelta)

Inspección completa de core/logic.py, orchestrators.py, protocols.py, playit_manager.py, statemanager.py, services/.

**Resueltos:** A2-B03 (restore_backup atomic swap, `9ffa2a9`), A2-B04 (forge stale detection regex, `e37cc0a`), A2-B06/A2-P01 (PLAYER_COUNT diff guard, `e37cc0a`), A2-B07/A2-P02 (TPS_UPDATE eliminado, `0b964fd`), A2-A01 (import en medio eliminado, P0.7), A2-A03 (statemanager → TunnelStatusDebouncer clase con lock), A2-D01 (modrinth check_updates vía _request con json_body).

**Confirmados stack:** customtkinter/requests/Pillow pinneados sin upper bound (decisión deliberada); Python bajado a 3.12 LTS (`winget install Python.Python.3.12`, venv recreado con `py -3.12 -m venv .venv`).

**Sin resolver (bajo impacto, on-radar):** A2-B01 (player count lock), A2-B02 (eula.txt encoding), A2-B05 (atexit guard — nota: ya resuelto según AUDIT-3 A3-B... revisar duplicado), A2-A02 (_probe_java privado — resuelto en AUDIT-3 A3-A02), A2-A04 (Protocol expone métodos privados), A2-D02 (import re en hot path), A2-D03 (_zip_worker double-threading — resuelto, ver LA-01), ~~A2-P03 (JavaDetector cache sin TTL)~~ ✅ Resuelto 2026-07-10 (EASY-WINS session), A2-P04 (get_versions freeze — resuelto en AUDIT-3 A3-A05).

---

## AUDIT-3: Validación externa de auditoría — 2026-06-24 ✅ (mayoría resuelta)

Reporte de auditoría externa, validado item-por-item contra código real.

**Resueltos:** A3-B01 (encoding UTF-8 en version_manager cache), A3-B02 (TPS_UPDATE falso eliminado del enum), A3-B03 (PLAYER_COUNT rate-limit 1x/seg en tick loop), A3-B04 (backup restore atomic swap + _zip_worker eliminado), A3-A01 (_winapi.CreateJunction → os.symlink), A3-A02 (probe_java público), A3-A03 (Protocol IS-A → HAS-A, junto con P0.5), A3-A05 (version_manager freeze eliminado), A3-M01 (ServerEvent.ERROR eliminado, RESTARTED/BACKUP_COMPLETED/BACKUP_FAILED documentados como hooks futuros), A3-M02 (migrate_legacy_metadata() en bootstrap).

**Pendientes (bajo impacto, oportunísticos — solo si se toca el archivo):**
- ~~A3-B05~~ ✅ Resuelto 2026-07-10 (EASY-WINS session) — check DNS movido dentro del lock
- A3-A04 — `core.py:104-259` 4 inline imports de update_server_meta/SERVERS_DIR (workarounds circular dep), mover al top cuando se toque el archivo

**YAGNI excluidos:** countdown UX, jar_events leak negligible, thread pools (28 threads OK en hardware actual), PlayitManager callbacks vs EventBus (funcional, refactor invasivo sin ganancia), statemanager globals (ya no aplica, resuelto), settings_manager singleton (funciona bien, debounced flush thread-safe), legacy Dict/List typing, Python 3.14 (decisión de release no bug).

---

## Handover — Sesión 2026-06-23 (2)

Branch `dev`, commits sesión 1: `e37cc0a` → `a4a909c` → `6a2308c` → `3117759` → `4af2325`.

Resuelto en sesión 1+2: NR-DASH/01/02/09, A2-B04, A2-B06/D02, JAVA-FLOOR, CA-02, MA-02/A2-B02 (encoding utf-8 en 7 open() de logic.py), A2-B05 (_atexit_stop try/except), NR-03/06/07/08, modrinth TclError (winfo_exists guard).

**Notas técnicas conservadas:**
- Commits siempre `git -c user.name="DesvoSoft" -c user.email="desvox23@gmail.com"`. Nunca co-author, nunca Claude como contributor.
- PowerShell heredoc: `@'...'@` con `'@` en columna 0. Bash `<<'EOF'` no funciona en PS.
- `rtk` no disponible en PS — usar git/commands directos, RTK solo en Bash.
- `os.startfile` prohibido por CLAUDE.md — siempre subprocess con platform-check.
- Versión de Forge en metadata: `"version": "26.2"` en metadata.json es versión del loader Forge, no MC version. Deuda: wizard debería guardar `"mc_version"` separado.
- `test_server` (Vanilla 1.20.1, Java 17 portable) funciona correctamente.

---

## EASY-WINS: Bug fixes + UI polish — 2026-07-10 ✅

Sesión enfocada en high-confidence fixes y mejoras visuales identificadas en el roadmap como "easy wins" (<5 hrs total, riesgo bajo).

### Fixes (3)

| ID | Archivo | Problema | Fix |
|----|---------|---------|-----|
| A3-B05 | `core/playit_manager.py:704` | `_parse_line` check `self._api_dns or self._stdout_dns` ejecutado **fuera** del lock — bajo concurrencia (2 lectores de stdout+polling), ambos pasan el guard y emiten TUNNEL_STATUS dos veces | Early-return check movido **dentro** del `with self._lock:` block. 3 líneas cambiadas. |
| A2-P03 | `services/java_detector.py` | `_shared_cache` class-level sin TTL — si el usuario instala Java mientras la app está abierta, `detect_all()` nunca lo ve (cache infininto) | `_shared_cache_time: float` + `_CACHE_TTL = 300.0` (5 min). `detect_all()` usa `time.monotonic()` para expirar. Se re-escanea automáticamente sin `force_refresh`. |
| A2-A02 | `services/java_detector.py` | `_probe_java` privado importado desde `logic.py:20` — acoplamiento frágil | **Confirmado resuelto**: `probe_java()` wrapper público ya existe en línea 201. No requiere cambio. |

### UI — F11 Bloque B completo (4 items)

| # | Tarea | Archivo | Detalle |
|---|-------|---------|---------|
| 11.B1 | Sidebar accent line | `ui_components.py:333` | Selected item border cambia de `COLOR_BTN_PRIMARY` a `COLOR_ACCENT_GREEN` (lime-800) — verde "tierra" en vez de verde primario genérico |
| 11.B2 | Server list items como cards | `ui_components.py` | **Confirmado**: `ServerListItem` ya implementa cards con dot de estado, nombre bold, version/type, hover — implementado en sesiones anteriores |
| 11.B3 | Dashboard tunnel collapsed when offline | `main.py:966` | `on_tunnel_status` ahora colapsa (pack_forget) IP display, buttons, y setup frame cuando status es Offline y agent está linked. Solo queda "Tunnel: ● Offline". Se expande al pasar a Online/Starting/Error |
| 11.B4 | Status bar topbar | `main.py:183` | **Confirmado**: status bar ya usa `fg_color=(COLOR_BG_CARD_LIGHT, COLOR_BG_CARD_DARK)` diferenciado del main bg |

### UI — F11.D6: Tooltips (4 buttons)

Añadidos `ToolTip()` a los 4 botones sidebar que les faltaban:
- `btn_create_server` → "Create a new Minecraft server"
- `btn_add_server` → "Import or load an existing server"
- `btn_app_settings` → "Application settings"
- `btn_toggle_setup` → "Link Playit account"

Los 9 botones de status bar + tunnel ya tenían tooltips de sesiones anteriores.

### Resultado

- **560 tests pass** (was 544 — 16 tests adicionales de sesiones previas no contabilizadas)
- **flake8 clean** (critical errors only)
- **4 archivos modificados**: `playit_manager.py`, `java_detector.py`, `ui_components.py`, `main.py`

---

## F10: Cross-Platform Linux — 2026-07-10 ✅

Auditoría completa de platform-specific code identificó 2 Critical + 4 Borderline items. Todos resueltos.

### Fixes (4)

| # | Archivo | Problema | Fix |
|---|---------|---------|-----|
| 10.1 | `process_job.py` + `logic.py` + `playit_manager.py` | No process reaping en Linux — Windows usa Job Objects, Linux no-op. Children (MC server, playitd) quedan huérfanos si parent crash | `linux_preexec()`: `prctl(PR_SET_PDEATHSIG, SIGKILL)` + parent PID re-check post-fork (guarda race fork→setsid). Integrado via `preexec_fn` en ambos Popen sites: `ServerRunner._popen_kwargs()` + `PlayitManager._start_internal()` |
| 10.2 | `logic.py:438` | `install_forge()` solo check `run.bat` — Linux solo tiene `run.sh` → retorna `None` | Añadido `os.path.exists(run.sh)` check |
| 10.3 | `playit_manager.py` | Force-kill no tiene fallback Linux — `taskkill /IM` es Windows-only. Si psutil falla, playitd queda vivo | `_kill_stray_by_name()` shared: Windows→taskkill, Linux→psutil process_iter kill + `pkill -9 -f playit` fallback. Usado en `stop(force=True)` y `_atexit_stop()` |
| 10.4 | `playit_manager.py:346` | Socket path `@zbb-playitd` es abstract namespace — puede no funcionar en todos los playitd builds Linux | Windows: `@zbb-playitd` (named pipe). Linux: `CONFIG_DIR/zbb-playitd.sock` (filesystem socket) |

### Items confirmados ya safe

- `single_instance.py`: `os.kill(pid, 0)` fallback funciona en Linux ✅
- `win_effects.py`: no-op en Linux ✅
- `java_detector.py`: Linux well-known paths cubiertos ✅
- `java_installer.py`: `_chmod_plusx` en Linux ✅
- `create_junction()`: `os.symlink` en Linux ✅
- `open_in_file_manager`: `xdg-open` fallback ✅
- `constants.py`: `subprocess_flags()` retorna `{}` en Linux ✅

### Archivos modificados

- `app/core/process_job.py` — reescrito completo (120→145 LOC)
- `app/core/logic.py` — `_popen_kwargs()` + `install_forge()` run.sh check + `import platform`
- `app/core/playit_manager.py` — `_kill_stray_by_name()`, socket path, preexec_fn

### Resultado

- **560 tests pass**, flake8 clean
- F10 marcado como ✅ en roadmap.md
