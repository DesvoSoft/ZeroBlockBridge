# ZeroBlockBridge — Roadmap de Desarrollo

> **Última actualización:** 2026-06-19
> **Versión proyecto:** Pre-alpha (desarrollo activo)
> **Test count:** 364 tests, 100% pass, 0 flaky
> **Audit:** 2026-06-19 — 2🔴 6🟡HIGH 5🟡MED 6🔵LOW encontrados, todos catalogados en BUG-AUDIT

---

## Estado Actual (Junio 2026)

### Métricas Clave
| Métrica | Valor |
|---------|-------|
| Archivos Python | 39 app + 19 tests |
| LOC totales (app) | ~7,880 |
| LOC totales (tests) | ~3,007 |
| Tests | 364 pasando, 0 fallos, 0 skipped |
| Type hint coverage | ~28.5% |
| Threads potenciales | ~38 (todos daemon) |
| Dependencias externas | 4 (customtkinter, requests, psutil, Pillow) |

### Foundation Score: 6.6/10 — Sólida con fisuras conocidas
| Dimensión | Nota | Factor limitante |
|-----------|------|-----------------|
| Seguridad | 9/10 | Sin eval, shell=False, sanitizer allowlist, SHA1 |
| Tests | 8/10 | 100% pass, mocks limpios, tmp_path |
| Thread model | 7/10 | Daemon, EventBus RLock, SettingsManager thread-safe |
| Arquitectura | 7/10 | UI→core→services unidireccional, 1 circular dep |
| Config management | 7/10 | SettingsManager OK, config.json sin lock |
| Type hints | 3/10 | ~28.5% tipado, sin mypy en CI |
| Dependencias | 5/10 | Sin pin, sin lockfile, sin pyproject.toml |

---

## Estructura del Plan

0. [✅ F0-F3: Foundation + Quick Wins + Refactors](#f0-f3-foundation--quick-wins--refactors)
1. [✅ FA-FB: UI + Layout v1.4](#fa-fb-ui--layout-v14)
2. [✅ FIX-P1: 7 Críticos](#fix-p1-7-críticos)
3. [✅ FIX-P2: Thread Safety + Dead Code](#fix-p2-thread-safety--dead-code)
4. [✅ FIX-P3: Whitelist + TPS + Wizard Security](#fix-p3-whitelist--tps--wizard-security)
5. [✅ F4: Auto-Backup (backend + UI)](#f4-auto-backup-scheduler)
6. [⬆️ **P0: Foundation Hardening — PRIORIDAD MÁXIMA**](#p0-foundation-hardening)
7. [⬆️ **BUG-AUDIT: 19 issues del audit 2026-06-19**](#bug-audit--2026-06-19)
8. [▶️ F5: Crash Report Collector](#f5-crash-report-collector)
9. [▶️ F6: Discord Webhook](#f6-discord-webhook)
10. [▶️ MODS-B: Modrinth Browser Mejoras](#mods-b-modrinth-browser-mejoras)
11. [⏸️ F8: Bulk Mod Operations](#f8-bulk-mod-operations)
12. [⏸️ F7: Server Templates + Modpacks](#f7-server-templates--modpacks)
13. [⏸️ F9-F11: Migration, Linux, UI 2.0](#f9-f11-migration-linux-ui-20)

---

## F0-F3: Foundation + Quick Wins + Refactors ✅

### Fase 0: Auditoría Táctica ✅
| Tarea | Estado |
|-------|--------|
| Análisis import graph (38 archivos, ~6,200 LOC) | ✅ |
| Thread audit (24 spawns, 6 innecesarios) | ✅ |
| I/O map (metadata.json leído en 8+ lugares) | ✅ |
| Security scan (sanitizer OK, sin SQL) | ✅ |
| Memory baseline (~35-45 MB idle) | ✅ |
| Identificación sobreingeniería (46 hallazgos, 14 alto impacto) | ✅ |
| Script de profiling generado | ✅ |

### Fase 0.5: Corrección de Críticos ✅
| # | Tarea | Estado |
|---|-------|--------|
| 0.5.1 | Backup: ZIP de respaldo ANTES de restaurar | ✅ |
| 0.5.2 | Sanitizer: `%` no debe estar bloqueado | ✅ |
| 0.5.3 | JDK: SHA-256 vs SHA-512 detection + no retry | ✅ |
| 0.5.4 | Port validation: negativos fuera (1-65535) | ✅ |
| 0.5.5 | Dialog grab release (WM_DELETE_WINDOW) | ✅ |
| 0.5.6 | Watchdog backoff con límite 3600s | ✅ |

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
| # | Tarea | Estado |
|---|-------|--------|
| 2.1 | Fix check_java_startup() — usar JavaDetector | ✅ |
| 2.2 | DNS recovery chain (3 mecanismos) | ✅ |
| 2.3 | TunnelStatusProvider elimina "Starting..." duplicado | ✅ |
| 2.4 | Fix project_type filter + get_popular_mods() | ✅ |
| 2.5 | Playit Link UX collapsible redesign | ✅ |
| 2.6 | progress_callback(float) → progress_callback(float, str) | ✅ |
| 2.7 | Mensajes de progreso detallados en wizard | ✅ |
| 2.8 | Pre-flight Java check en ServerWizard | ✅ |
| 2.9 | Botón "▶ Start Now" post-creación | ✅ |
| 2.10 | Status badge por tipo de Java | ✅ |
| 2.11 | Remote agent cleanup (gate key_valid eliminado) | ✅ |
| 2.12 | Pre-download JDK durante wizard | ✅ |
| 2.13 | Reset UI fijo (skip_debounce) | ✅ |
| 2.14 | Soft reset tunnel | ✅ |

### Modrinth Management (F3.10-3.14) ✅
| # | Tarea | Estado |
|---|-------|--------|
| 3.10 | Gestión de mods instalados (lista + delete) | ✅ |
| 3.11 | Paginación "Load More" en búsqueda | ✅ |
| 3.12 | Íconos reales de mods vía URL asíncrona | ✅ |
| 3.13 | Check for Updates en UI | ✅ |
| 3.14 | Selector de versión al instalar | ✅ |

### Refactors Estructurales (F3.2, 3.3, 3.5, 3.6, 3.8, 3.9) ✅
| # | Tarea | Estado |
|---|-------|--------|
| 3.2 | install_fabric + install_forge → _run_installer() | ✅ |
| 3.3 | start_server() — extraer helpers | ✅ |
| 3.5 | Centralizar metadata.json en get/update_server_meta() | ✅ |
| 3.6 | Eliminar _pre_warm_version_cache() de bootstrap | ✅ |
| 3.8 | Eliminar _apply_pending_settings() | ✅ |
| 3.9 | Scheduler + SchedulerService — fusionar en logic.Scheduler | ✅ |

### Thread Safety + Tests (F3.15-3.25) ✅
| # | Tarea | Estado |
|---|-------|--------|
| 3.15 | statemanager.py — threading.Lock + asignación directa | ✅ |
| 3.16 | settings_manager.py — _settings[key]=value dentro del lock | ✅ |
| 3.17 | Tests Windows compat — /tmp/ → tempfile.gettempdir() | ✅ |
| 3.18 | Type hints — Watchdog, BackupManager, Toast, Heartbeat, etc | ✅ |
| 3.19 | Tests playit_manager (443 LOC) | ✅ |
| 3.20 | Tests heartbeat (61 LOC) | ✅ |
| 3.22 | Tests single_instance (71 LOC) | ✅ |
| 3.23 | Safe Init audit — init antes de subscriptions/threads | ✅ |
| 3.24 | .on() deprecation check — sin remanentes | ✅ |
| 3.25 | Cross-platform test isolation — mock sys.platform etc | ✅ |

---

## FA-FB: UI + Layout v1.4 ✅

### Fase A: UI + Bugfixes ✅
| # | Tarea | Estado |
|---|-------|--------|
| A.1 | Toast corner_radius=0 para consistencia visual | ✅ |
| A.2 | Copy-IP solo muestra host (sin puerto) | ✅ |
| A.3 | Toast duplicado eliminado de dashboard | ✅ |
| A.4 | Server tag muestra versión MC en sidebar | ✅ |

### Fase B: Layout Final ✅
| # | Tarea | Estado |
|---|-------|--------|
| B.1 | Start All eliminado del dashboard | ✅ |
| B.2 | SERVER/TUNNEL secciones con separador | ✅ |
| B.3 | Server controls ▶ ■ movidos a status bar (inline) | ✅ |
| B.4 | Sección SERVER eliminada del dashboard | ✅ |
| B.5 | Label TUNNEL eliminado (tunnel_frame va directo) | ✅ |
| B.6 | Tunnel padding pady=(4, 1) | ✅ |
| B.7 | Default window 1150×700, min 900×580 | ✅ |
| B.8 | Mod card hover corregido (fg_color inicial explícito) | ✅ |
| B.9 | Mod card grid_columnconfigure(1, weight=1) | ✅ |
| B.10 | Java detection cache clase-level (JavaDetector._shared_cache) | ✅ |

---

## FIX-P1: 7 Críticos ✅
| # | Bug | Archivo | Fix |
|---|-----|---------|-----|
| C1 | AppConfig.SERVERS_DIR inexistente | server_properties_editor.py | Importar SERVERS_DIR desde constants |
| C2 | EventBus thread-safety (dict race) | server_events.py | RLock en _listeners |
| C3 | settings_manager.init nunca llamado | main.py + settings_manager.py | set_config_dir(CONFIG_DIR) en init |
| C4 | get_agent_id() retorna None (-> str) | playit_api.py | Optional[str], None handling en callers |
| C5 | _jdk_source race en start_server | core.py | _start_lock protege start_server() |
| C6 | _winapi.CreateJunction en core | logic.py + core.py + main.py | create_junction() helper cross-platform |
| C7 | server.properties sin encoding utf-8 | server_properties.py + editor | encoding=utf-8 en todos los open() |

## FIX-P2: Thread Safety + Dead Code ✅
| # | Tarea | Archivo | Fix |
|---|-------|---------|-----|
| P2.1 | playit_manager locks | playit_manager.py | Lock en _parse_line/_read_output |
| P2.2 | version_manager double-join | version_manager.py | _wait_for_background_refresh simplificado |
| P2.3 | core restart race | core.py | _restart_lock con try/finally |
| P2.4 | remove_config_key muerto | core.py | Eliminado |
| P2.5 | stop_all muerto | core.py | Eliminado |
| P2.6 | import Any muerto | server_properties.py | Eliminado |

## FIX-P3: Whitelist + TPS + Wizard Security ✅
| # | Tarea | Archivo | Fix |
|---|-------|---------|-----|
| P3.1 | Whitelist toggle no persiste a server.properties | players_dashboard.py | _toggle_whitelist() llama save_server_properties(); switch carga estado real |
| P3.2 | TPS máximo 10 (debe ser 20) | orchestrators.py | Tick loop sleep 100ms → 50ms (20Hz) |
| P3.3 | Wizard Step 3 sin settings de seguridad | server_wizard.py, scaffolder.py | 8 campos: enforce-whitelist, pvp, online-mode, max-players, spawn-protection, enable-command-block, allow-flight, enforce-secure-profile |

---

## F4: Auto-Backup Scheduler ⚠️ PARCIAL

**Objetivo:** Backups automáticos programables por servidor, con gestión de retención.

### Backend ✅ (completado)
| # | Tarea | Archivo | LOC | Estado |
|---|-------|---------|-----|--------|
| 4.1 | BackupScheduler modelo datos (enabled, interval_hours, retention_count, mode, last_run) | logic.py:684+ | ~40 | ✅ |
| 4.2 | SchedulerOrchestrator._start_tick_loop check backup due | orchestrators.py:159-204 | ~30 | ✅ |
| 4.3 | Retención automática — BackupManager._apply_retention() | backup_manager.py:83 | ~20 | ✅ |
| 4.4 | Mutex backup-in-progress (_backup_lock, _backup_in_progress) | core.py:64-65, orchestrators.py:128-134 | ~15 | ✅ |
| 4.7 | Eventos BACKUP_COMPLETED / BACKUP_FAILED | server_events.py:24-25 | ~5 | ✅ |
| 4.8 | Tests (12 tests: defaults, persistence, is_due, mark_run, set_config, seconds_until_next) | tests/test_backup_scheduler.py | ~200 | ✅ |

### UI ❌ (NO iniciado)
| # | Tarea | Archivo | LOC est. | Esfuerzo | Estado |
|---|-------|---------|----------|----------|--------|
| **4.5** | **Auto-Backups section en Automation tab** | server_properties_editor.py:257-303 | ~80 | 1.5-2 hrs | ❌ |
| **4.6** | **Next backup countdown en Backups tab** | server_properties_editor.py:188+ | ~30 | 0.5 hrs | ❌ |

**Detalle 4.5:** En `setup_automation_tab()`, añadir una CardFrame "Auto-Backups" con:
- Switch enable/disable (wired a `BackupScheduler.set_config(enabled=...)`)
- Spinbox `interval_hours` (1-168, default 24)
- Spinbox `retention_count` (1-30, default 5)
- Label "Next backup in ~Xh Ym" que se actualiza cada 30s via `self.after()`
- Modo selector: "full" (world+config) vs "world-only" (opcional)

**Detalle 4.6:** En `setup_backups_tab()`, añadir un frame informativo arriba:
- "Auto-Backup: Enabled / Disabled"
- "Next backup: ~Xh Ym" (update cada 30s vía `after()`)
- Botón "Run Backup Now" que dispara backup manual

**Criterio de aceptación:**
- [ ] Usuario puede activar/desactivar auto-backup por servidor
- [ ] Usuario puede configurar intervalo (horas) y retención
- [ ] La UI muestra countdown al próximo backup
- [ ] Countdown se actualiza en vivo (sin recargar diálogo)
- [ ] Todos los cambios persisten a metadata.json
- [ ] Tests existentes (12) siguen pasando

---

## P0: Foundation Hardening ⬆️ PRIORIDAD MÁXIMA

**Objetivo:** Endurecer la base antes de añadir nuevas features. Sin esto, cualquier feature nueva se construye sobre terreno frágil.

**Racionalidad:** La auditoría estratégica reveló 6 áreas que pueden causar regresiones o bloquear el progreso. Se resuelven antes de F5+.

**Orden de ejecución:** El orden importa — hacer tests primero da seguridad para refactorizar.

### P0.1: Tests para Orchestrators 🔴🔴🔴

| Campo | Detalle |
|-------|---------|
| **Archivo destino** | `tests/test_orchestrators.py` (nuevo) |
| **LOC estimado** | ~250-350 |
| **Esfuerzo** | 2-3 hrs |
| **Riesgo** | 🟡 Medio (requiere entender mocking de ZBBManager) |

**Qué testear:**
- `ServerOrchestrator`: start_server (success + fail), stop_server (running + already stopped), restart_server, handle_server_crash, zombie detection
- `BackupOrchestrator`: _check_auto_backup (due + not due + enabled + disabled), backup_in_progress mutex, event emission
- `TunnelOrchestrator`: start_tunnel, stop_tunnel, is_tunnel_active, reset_tunnel (soft + full)
- `SchedulerOrchestrator`: tick_loop iteration, scheduler check interval, backup overdue detection

**Mocking strategy:**
- `ZBBManager` → `MagicMock(spec=...)` con FakeEventBus
- `EventBus` → `FakeEmitter` (ya existe en conftest.py)
- `ServerRunner` → `FakeRunner` (ya existe en conftest.py)
- Evitar `threading.Thread` real — mockear o usar callbacks síncronos
- Usar `pytest.mark.timeout(2)` para loops que podrían colgar

**Criterio de aceptación:**
- [ ] 20+ tests que cubren todos los orchestrators
- [ ] 100% pass en Windows y Linux
- [ ] Mock de ZBBManager sin llamadas reales a I/O
- [ ] Tests detectan correctamente estados erróneos

**Nota para devs/agentes:**
```python
# Patrón recomendado para testear orchestrators:
class FakeZBBManager:
    def __init__(self):
        self.events = FakeEmitter()
        self.backup_manager = MagicMock()
        # ... etc

def test_server_orchestrator_start_success():
    zbb = FakeZBBManager()
    orch = ServerOrchestrator(zbb, "myserver")
    orch.start_server()
    assert orch.is_running is True
    zbb.events.assert_emitted(ServerEvent.SERVER_STARTED)
```

### P0.2: F4 UI — Automation Tab ✅ (Completar 4.5)

Ver [detalle en F4.5](#detalle-45). Es la prioridad #2 porque el backend ya está listo y solo falta enchufar UI.

### P0.3: F4 UI — Backups Tab ✅ (Completar 4.6)

Ver [detalle en F4.6](#detalle-46).

### P0.4: Pin Dependencies + pyproject.toml

| Campo | Detalle |
|-------|---------|
| **Archivos** | `requirements.txt`, `pyproject.toml` (nuevo) |
| **LOC estimado** | ~30 |
| **Esfuerzo** | 1-1.5 hrs |
| **Riesgo** | 🟢 Bajo |

**Qué hacer:**
```toml
[project]
name = "zeroblockbridge"
version = "1.4.0"
requires-python = ">=3.10"
dependencies = [
    "customtkinter>=5.2.0",
    "requests>=2.28.0",
    "psutil>=5.9.0",
    "Pillow>=9.0.0",
]
```

```txt
# requirements.txt
customtkinter>=5.2.0
requests>=2.28.0
psutil>=5.9.0
Pillow>=9.0.0
```

**Criterio de aceptación:**
- [ ] `pip install -e .` funciona
- [ ] `python -m app.launcher` funciona desde cualquier directorio
- [ ] Todas las dependencias tienen versión mínima
- [ ] Python mínimo especificado (3.10)
- [ ] Tests pasan después del cambio

### P0.5: Fix Circular Dependency core↔orchestrators

| Campo | Detalle |
|-------|---------|
| **Archivos** | `core/core.py`, `core/orchestrators.py`, `core/constants.py` o `core/protocols.py` |
| **LOC estimado** | ~10 (mover enum) + ~20 (eliminar lazy imports) |
| **Esfuerzo** | 30 min |
| **Riesgo** | 🟡 Medio (cambiar imports puede romper si no se actualizan referencias) |

**Qué hacer:**
1. Mover `class ServerState(enum.Enum)` de `core.py` a `constants.py` o `protocols.py`
2. Actualizar imports en `core.py` y `orchestrators.py` para importar desde la nueva ubicación
3. Eliminar los `from app.core.core import ServerState` inline en `orchestrators.py`
4. Reemplazar con `from app.core.constants import ServerState` al tope del archivo

**Criterio de aceptación:**
- [ ] `from app.core.orchestrators import ServerOrchestrator` funciona sin error de import circular
- [ ] `python -c "import app; print('OK')"` funciona (test de import graph completo)
- [ ] Todos los tests pasan
- [ ] No hay imports inline de `ServerState` en ningún archivo

### P0.6: Suscribir CRASHED Event

| Campo | Detalle |
|-------|---------|
| **Archivos** | `core/core.py` (ZBBManager._setup_monitors), `services/watchdog.py` |
| **LOC estimado** | ~20 |
| **Esfuerzo** | 30 min |
| **Riesgo** | 🟢 Bajo |

**Qué hacer:**
Actualmente Watchdog emite `ServerEvent.CRASHED` con payload `{reason, exit_code, uptime, retry_count}` pero nadie lo escucha. Añadir suscriptor en `ZBBManager._setup_monitors()` que:
1. Registre el crash en metadata.json (`crash_history` array, últimos 10)
2. Emita `ServerEvent.NOTIFICATION` con mensaje de crash (para que la UI muestre toast)
3. (Opcional) Escriba log level ERROR

**Criterio de aceptación:**
- [ ] `CRASHED` event tiene al menos 1 suscriptor
- [ ] Al crash, aparece toast/notification en UI
- [ ] Crash se registra en metadata.json
- [ ] Tests existentes de watchdog no se rompen

### P0.7: Clean Up Dead Imports

| Campo | Detalle |
|-------|---------|
| **Archivos** | Múltiples (ver lista) |
| **LOC** | ~10 líneas eliminadas |
| **Esfuerzo** | 30 min |
| **Riesgo** | 🟢 Muy bajo |

**Imports muertos identificados:**
| Archivo | Import |
|---------|--------|
| `core/core.py:6` | `import auto` (de Enum) |
| `core/version_manager.py:8` | `from pathlib import Path` |
| `services/heartbeat.py:5` | `from typing import Any` |
| `services/backup_manager.py:5` | `import tempfile` |
| `services/modrinth.py:15` | `import shutil` |
| `ui/modrinth_browser.py:10` | `import io` |
| `ui/ui_components.py:5` | `import webbrowser` |

**Criterio de aceptación:**
- [ ] `flake8 app/ --select=F401` reporta 0 unused imports
- [ ] Todos los tests pasan

---

## F5: Crash Report Collector

**Objetivo:** Ante cada crash detectado por Watchdog, escribir un archivo JSON diagnóstico con toda la información del servidor, sistema, y cola de consola.

**Dependencia:** P0.6 (CRASHED subscriber) — sin él, no hay trigger.

### Tareas
| # | Tarea | Archivo | LOC | Esfuerzo |
|---|-------|---------|-----|----------|
| 5.1 | Crear `CrashReporter` — subscribe a CRASHED, snapshotea console buffer, escribe JSON en `servers/<name>/crash_reports/` | `app/services/crash_reporter.py` (nuevo) | ~80 | 1 hr |
| 5.2 | Integrar en `ZBBManager._setup_monitors()` | `core.py` | ~5 | 10 min |
| 5.3 | Tests | `tests/test_crash_reporter.py` | ~100 | 1 hr |

### Formato del reporte
```json
{
  "schema_version": 1,
  "timestamp": "2026-06-14T14:30:22",
  "server": { "name": "MyServer", "version": "1.20.1", "type": "Fabric", "ram": "2G" },
  "crash": { "reason": "out_of_memory", "exit_code": 1, "retry_attempt": 2 },
  "stderr_tail": ["Exception in thread...", "..."],
  "console_tail": ["[14:30:20] [System] Starting server...", "..."],
  "system_info": { "os": "Windows 10", "ram_gb": 15.9, "cpu_count": 8 },
  "watchdog_state": { "max_retries": 3, "current_retries": 2 }
}
```

### Nota para devs/agentes
- El `console_buffer.py` tiene `CircularBuffer` (deque de 500 líneas) — acceder via `console_tail()` o similar
- No añadir nuevas dependencias — `json`, `datetime`, `platform`, `uuid` son stdlib
- El reporte debe escribirse ANTES de que Watchdog intente restart (si hay retry)
- Usar `server_events.py` ServerEvent.CRASHED payload

### Criterio de aceptación
- [ ] Reporte JSON escrito en `servers/<name>/crash_reports/` al emitirse CRASHED
- [ ] Reporte contiene server info, crash info, stderr tail, console tail, system info
- [ ] No se interrumpe si el directorio crash_reports no existe (crearlo)
- [ ] Límite de 50 reportes máximos por servidor (rotación FIFO)
- [ ] Tests con CRASHED event mock + temp dir

---

## F6: Discord Webhook

**Objetivo:** Enviar notificaciones a Discord vía webhook cuando ocurran eventos del servidor.

**Dependencia:** P0 completo (para tener base sólida).

### Tareas
| # | Tarea | Archivo | LOC | Esfuerzo |
|---|-------|---------|-----|----------|
| 6.1 | Crear `DiscordWebhookService` — EventBus subscriber, formatea mensajes, POST asíncrono con queue.Queue + worker único + rate-limit | `app/services/discord_webhook.py` (nuevo) | ~60 | 1 hr |
| 6.2 | Añadir `discord_webhook_url` + `discord_notify_on` a user settings | `settings_manager.py` | ~10 | 15 min |
| 6.3 | Integrar en `ZBBManager.__init__()` (solo si hay URL configurada) | `core.py` | ~5 | 10 min |
| 6.4 | Tests | `tests/test_discord_webhook.py` | ~80 | 45 min |

### Diseño thread-safe
```python
class DiscordWebhookService:
    def __init__(self, events: EventBus):
        self._queue: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        events.subscribe(ServerEvent.CRASHED, self._on_event)
        events.subscribe(ServerEvent.SERVER_READY, self._on_event)
        # etc

    def _run(self):
        while True:
            event, payload = self._queue.get()
            # Rate limit: max 1 msg per 2s
            self._post_to_discord(event, payload)
            time.sleep(2)
```

### Nota para devs/agentes
- `requests` ya existe como dependencia — POST simple con `requests.post(url, json={"content": msg})`
- No exponer la webhook URL en logs nunca
- Rate-limit mínimo 2s entre mensajes para evitar rate-limit de Discord
- Solo eventos importantes: CRASHED, SERVER_READY, BACKUP_COMPLETED, BACKUP_FAILED

### Criterio de aceptación
- [ ] Mensaje POST a Discord webhook cuando ocurre evento configurado
- [ ] Worker único secuencial (queue.Queue) sin thread exhaustion
- [ ] Rate-limit 2s entre mensajes
- [ ] Silencio si no hay URL configurada (0 overhead)
- [ ] URL no se loggea ni expone

---

## MODS-B: Modrinth Browser Mejoras

**Objetivo:** Refinar el Modrinth Browser con filtros, mejor UX, y pequeños refactors. No es Fase 8 (bulk operations) — son mejoras puntuales nivel B.

**Dependencia:** P0.1 (test orchestrators) + P0.5 (circular dep) — ideal tener base sólida antes de tocar UI.

### Tareas
| # | Tarea | Archivo | LOC | Esfuerzo | Riesgo |
|---|-------|---------|-----|----------|--------|
| M.1 | Extract `_resolve_server_context(server_name)` helper | `modrinth_browser.py` | ~10 extraídos de ~30 repetidos | 30 min | 🟢 |
| M.2 | Extract `_require_server()` guard | `modrinth_browser.py` | ~5 | 15 min | 🟢 |
| M.3 | MC version filter dropdown en búsqueda | `modrinth_browser.py` | ~40 | 1 hr | 🟡 |
| M.4 | Loader filter (Fabric/Forge/Quilt/NeoForge) | `modrinth_browser.py` | ~30 | 45 min | 🟡 |
| M.5 | Update count badge en sidebar/label | `modrinth_browser.py` + `main.py` | ~20 | 30 min | 🟢 |
| M.6 | "Installed Mods" inline en pestaña Mods | `modrinth_browser.py` | ~50 | 1 hr | 🟡 |
| M.7 | Sort options (by name, by last updated, relevance) | `modrinth_browser.py` + `modrinth.py` | ~30 | 45 min | 🟢 |
| M.8 | Fix hover dead code / redundant refresh checks | `modrinth_browser.py` | ~15 | 30 min | 🟢 |

### Detalles

**M.1: `_resolve_server_context()`**
```python
# Antes: 7 funciones que empiezan con:
server_name = self._current_server
if not server_name: return
meta = get_server_meta(server_name)
if not meta: return
server_type = meta.get("type", "vanilla")
server_version = meta.get("version", "")
```
→ Extraer a helper que retorna `(server_name, server_type, server_version)` o `None`

**M.3-M.4: Filtros en búsqueda**
- Añadir `CTkComboBox` para MC version (cargado desde VersionManager)
- Añadir `CTkComboBox` para loader (Fabric, Forge, Quilt, NeoForge, Any)
- Pasar como parámetros a `ModrinthClient.search_mods()`
- La API de Modrinth soporta `facets` filtering: `facets=[["categories:fabric"],["versions:1.20.1"]]`

**M.5: Update badge**
- En `main.py`, al construir el botón Mods, añadir badge si hay updates
- O en `modrinth_browser.py` título de pestaña
- Llamar `check_updates()` al seleccionar servidor y mostrar count

**M.6: Installed Mods inline**
- Añadir scrollable frame arriba en Modrinth Browser
- Siempre visible, muestra mods instalados con icono + nombre + versión
- Botón "Uninstall" inline (sin diálogo)
- Actualizar al instalar/desinstalar

### Criterio de aceptación
- [ ] Filtros funcionan: al seleccionar versión/loader, búsqueda se refiltra
- [ ] Update badge visible (incluso si 0, para confirmar que funciona)
- [ ] Installed mods inline muestra mods actuales
- [ ] Helpers extraídos sin cambiar comportamiento
- [ ] Sin imports circulares añadidos

---

## F8: Bulk Mod Operations

**Objetivo:** Operaciones masivas sobre mods instalados.

**Dependencia:** MODS-B (para tener la UI de mods estable).

| # | Tarea | LOC | Esfuerzo |
|---|-------|-----|----------|
| 8.1 | Multi-select checkboxes en installed mods list | ~40 | 1 hr |
| 8.2 | Botón "Update Selected" — batch download | ~50 | 1.5 hrs |
| 8.3 | Botón "Delete Selected" — batch delete con confirm | ~30 | 45 min |
| 8.4 | Botón "Install Multiple" desde search results | ~40 | 1 hr |
| 8.5 | Progress bar batch ("Installing 3/5 mods...") | ~30 | 45 min |
| 8.6 | Tests | ~100 | 1 hr |

---

## F7: Server Templates + Modpacks

**Dependencia:** F8 (bulk mod ops) — reutiliza batch download infra.

| # | Tarea | LOC | Esfuerzo |
|---|-------|-----|----------|
| 7.1 | Definir formato JSON template | doc | 30 min |
| 7.2 | TemplateManager — save/load/list/delete | ~100 | 2 hrs |
| 7.3 | Template selector en ServerWizard Step 2 | ~50 | 1 hr |
| 7.4 | Save as template desde Properties Editor | ~30 | 45 min |
| 7.5 | Modpack support — auto-descargar mods de Modrinth | ~60 | 1.5 hrs |
| 7.6 | Templates por defecto (Lite SMP, Modded Fabric, Vanilla+, Paper Performance) | ~20 | 30 min |
| 7.7 | Tests | ~80 | 1 hr |

---

## F9-F11: Migration, Linux, UI 2.0

### F9: Server Migration (.zbbpack)
| # | Tarea | Esfuerzo |
|---|-------|----------|
| 9.1 | Export — ZIP con world + config + metadata (sin JAR, sin JDK) | 2 hrs |
| 9.2 | Import — descomprimir, re-descargar JAR, re-scaffold | 2 hrs |
| 9.3 | Mod list en manifest → re-descargar de Modrinth | 1.5 hrs |
| 9.4 | UI botón Export en Dashboard/Properties | 1 hr |
| 9.5 | UI Import wizard | 1.5 hrs |
| 9.6 | Tests | 1.5 hrs |

### F10: Cross-Platform Linux
| # | Tarea | Riesgo |
|---|-------|--------|
| 10.1 | platform_utils.py — open_directory(path) unificado | 🟢 |
| 10.2 | platform_utils.py — create_link(src, dst) unificado | 🟢 |
| 10.3 | SIGTERM handler en PlayitManager | 🟡 |
| 10.4 | stop() con wait(timeout=5) + kill() en Linux | 🟡 |
| 10.5 | single_instance.py verificar captura de SIGTERM | 🟢 |

### F11: UI/UX — ZBB 2.0
| # | Tarea | Riesgo |
|---|-------|--------|
| 11.1-11.5 | ServerWizard rediseñado (pre-flight, progreso, resumen, templates, start now) | 🟡 |
| 11.6-11.10 | ServerPropertiesEditor rediseñado (4 tabs, SettingsField, inline validation) | 🟠 |
| 11.11-11.17 | Layout + Console (sidebar colapsable, dashboard compacto, console search) | 🟡 |
| 11.18-11.20 | Performance dashboard, dark/light mode, tooltips | 🟠 |

---

## Resumen de Fases

| Fase | Descripción | LOC cambio | Prioridad | Estado |
|------|-------------|-----------|-----------|--------|
| **F0-F3** | Foundation + Refactors + Tests | -200 / +300 | 🥇 | ✅ |
| **FA-FB** | UI + Layout Final v1.4 | ~150 | 🥇 | ✅ |
| **FIX-P1** | 7 Critical Bugs | -50 / +80 | 🥇 | ✅ |
| **FIX-P2** | Thread Safety + Dead Code | -20 / +40 | 🥇 | ✅ |
| **FIX-P3** | Whitelist + TPS + Wizard Security | ~100 | 🥇 | ✅ |
| **F4** | Auto-Backup Scheduler | +150 | 🥇 | ⚠️ (backend ✅, UI ❌) |
| **P0** | Foundation Hardening | ~+400 | 🥇 | ⬆️ **AHORA** |
| **F5** | Crash Report Collector | +80 | 🥇 | ⏳ (tras P0) |
| **F6** | Discord Webhook | +60 | 🥈 | ⏳ |
| **MODS-B** | Modrinth Browser Mejoras | +200 | 🥈 | ⏳ |
| **F8** | Bulk Mod Operations | +200 | 🥈 | ⏳ |
| **F7** | Server Templates + Modpacks | +350 | 🥈 | ⏳ |
| **F9** | Server Migration (.zbbpack) | +250 | 🥉 | ⏳ |
| **F10** | Cross-Platform (Linux) | +80 | 🥉 | ⏳ |
| **F11** | UI/UX — ZBB 2.0 | +300 | 🥉 | ⏳ |

### Orden de Ejecución Recomendado

```
F0-F3 ✅ → FA-FB ✅ → FIX-P1/P2/P3 ✅ → F4 (backend) ✅
                                              ↓
                                       F4 (UI) ✅ ← P0.2 + P0.3
                                              ↓
                                    ┌──── P0.1 (orchestrator tests) ────┐
                                    │         P0.4 (pin deps)           │
                                    │         P0.5 (circular dep)       │
                                    │         P0.6 (CRASHED sub) ✅     │
                                    │         P0.7 (dead imports) ✅     │
                                    └───────────┬───────────────────────┘
                                                 ↓
                                      BUG-AUDIT (19 issues, 2026-06-19)
                                                 ↓
                              ┌──────────────────┼──────────────────┐
                              ↓                  ↓                  ↓
                           F5 (Crash)        F6 (Discord)      MODS-B
                              ↓                  ↓                  ↓
                           F8 (Bulk Mods) ←──────┴────── MODS-B da base
                              ↓
                           F7 (Templates) ←── reusa bulk download
                              ↓
                           F9 (Migration) ←── reusa template format
                              ↓
                     F10 (Linux) + F11 (UI 2.0)
```

---

## BUG-AUDIT — 2026-06-19

Audit completo de codebase. 19 issues encontrados. Ningún fix aplicado aún.

### 🔴 CRITICAL (2)

| ID | Archivo | Líneas | Problema | Fix |
|----|---------|--------|---------|-----|
| ~~CA-01~~ | ~~`services/watchdog.py`~~ | ~~105-108, 121-124 + `core/core.py:329`~~ | ~~Double toast por crash — Watchdog emite `NOTIFICATION` Y `_on_server_crashed` emite otra. Usuario ve 2 popups por crash.~~ | ✅ FIXED `6b00462` |
| CA-02 | `core/logic.py` | ~206 | Installer usa `"java"` hardcodeado, no el JDK resuelto. Fabric/Forge falla con "java not found" aunque ZBB ya descargó JDK correcto. | Aceptar `java_bin` param en `_run_installer`, pasar bin resuelto desde caller. |

### 🟡 HIGH (6)

| ID | Archivo | Líneas | Problema | Fix |
|----|---------|--------|---------|-----|
| ~~HA-01~~ | ~~`services/backup_manager.py`~~ | ~~109, 125~~ | ~~`strptime` crash si hay archivos non-timestamp en carpeta de backups (ej. `notes.zip`).~~ | ✅ FIXED `146553a` |
| ~~HA-02~~ | ~~`core/logic.py`~~ | ~~530~~ | ~~TOCTOU: `self.running = False` seteado antes de emitir `STOPPED`. Watchdog puede leer `running=False` sin que evento haya disparado.~~ | ✅ FIXED `ea4c3ff` |
| HA-03 | `core/orchestrators.py` | 74-77 | Stop intencional puede triggear restart del Watchdog. `stop_server` setea OFFLINE síncronamente; thread de output emite `STOPPED` después, Watchdog lo ve. | Clearear `_listening` flag en Watchdog ANTES de `runner.stop()`. |
| ~~HA-04~~ | ~~`core/orchestrators.py`~~ | ~~202~~ | ~~Auto-backup nunca corre si restart scheduler está desactivado — `_check_auto_backup()` está dentro del `if status:` del restart scheduler.~~ | ✅ FIXED `ceb6882` |
| HA-05 | `services/watchdog.py` | ~147 | Race en `_do_restart`: chequea `runner.running` sin lock antes de `start()`. Secuencias ZOMBIE+STOPPED rápidas pueden causar doble-start. | Agregar lock alrededor del chequeo + start. |
| HA-06 | `core/logic.py` | 558-571 | `connected_players` no se limpia al parar server. En restart via `_do_restart` (mismo objeto), retiene jugadores stale. | Llamar `self.connected_players.clear()` en `start()`. |

### 🟡 MEDIUM (5)

| ID | Archivo | Líneas | Problema | Fix |
|----|---------|--------|---------|-----|
| ~~MA-01~~ | ~~`core/core.py`~~ | ~~393-395~~ | ~~Countdown omite `1` — salta 2→NOW.~~ | ✅ FIXED `a0186bc` |
| MA-02 | `core/logic.py` | 64-65, 591 | `open()` sin `encoding="utf-8"` en lectura/escritura de config y eula.txt. MOTD con `§` se corrompe en Windows con locale no-UTF8. | Agregar `encoding="utf-8"` a todos los `open()`. |
| MA-03 | `ui/server_properties_editor.py` | 256-344, ~660 | `save_automation()` siempre llamada aunque Automation tab nunca fue visitada — backup config silenciosamente no guardada. | Inicializar variables de automation tab con defaults o siempre crear widgets. |
| ~~MA-04~~ | ~~`services/watchdog.py`~~ | ~~105, 121~~ | ~~NOTIFICATION payload inconsistente: watchdog usa `color` key, resto del codebase usa `type` key. Uno silenciosamente ignorado por toast handler.~~ | ✅ FIXED `6b00462` (removed with CA-01) |
| MA-05 | `core/logic.py` | 620-643 | Si scheduler tick es lento >120s post-target, restart silenciosamente skipeado. Sin log. | Emitir warning log cuando target time es missed. |

### 🔵 LOW / INFO (6)

| ID | Archivo | Líneas | Problema |
|----|---------|--------|---------|
| LA-01 | `services/backup_manager.py` | 60-63 | Thread spawneado solo para hacer zip síncronamente (join inmediato). Threading overhead sin beneficio. |
| LA-02 | `core/logic.py` | 23-24 | `_jar_ready_events` dict crece sin límite — un `threading.Event` por `server_dir` nunca limpiado. |
| LA-03 | `core/server_events.py` | 3 | Dead imports: `Dict`, `List` de `typing` — unused desde Python 3.9+. |
| LA-04 | `core/orchestrators.py` | 40-41 | Fallbacks hardcodeados `mc_version="1.20.1"`, `required_java=21` sin log warning cuando metadata falta. |
| LA-05 | `core/orchestrators.py` | 157-159 | Guard `if self.manager._tick_running: return` silencioso — debería loggear warning. |
| LA-06 | `core/logic.py` | 736-740 | Dead code: `get_server_ram` / `set_server_ram` thin wrappers usados solo por el editor. Candidatos a inline o eliminar en próximo refactor. |

### Status

| Severidad | Total | Resueltos | Pendientes |
|-----------|-------|-----------|-----------|
| 🔴 CRITICAL | 2 | 1 | 1 |
| 🟡 HIGH | 6 | 2 | 4 |
| 🟡 MEDIUM | 5 | 2 | 3 |
| 🔵 LOW | 6 | 0 | 6 |
| **TOTAL** | **19** | **5** | **14** |

---

## Notas para Devs y Agentes

### Reglas de Oro
1. **Sin sobreingeniería**: Si se puede hacer con 3 funciones, no se necesita una clase
2. **364 tests deben pasar siempre**: `python -m pytest tests/ -q` antes de cada commit
3. **Cross-platform**: `sys.platform == "win32"` y `platform.system()` guards obligatorios
4. **Sin merge commits**: Solo fast-forward o squash merges
5. **Commits atómicos**: Un commit = un cambio lógico completo

### Dependencias Circulares Conocidas
- `core.py` ↔ `orchestrators.py` — ver P0.5 para fix
- No crear nuevas dependencias circulares

### Eventos Huérfanos (no suscritos)
- `ServerEvent.CRASHED` — sin subscriber (ver P0.6)
- `ServerEvent.RESTARTED` — sin subscriber
- `ServerEvent.ERROR` — sin subscriber, nunca emitido (dead code candidate)

### Errores Comunes a Evitar
1. No usar `bare except:` — siempre especificar excepción
2. No hardcodear `C:\` paths — usar `platform.system()` guards
3. No usar `shell=True` en subprocess — siempre pasar lista de args
4. No importar dentro de funciones para evitar circulares — mejor mover el enum a constants.py
5. No crear threads para I/O rápido (<50ms) — el overhead del thread es mayor
6. Todo `open()` lleva `encoding="utf-8"` — Windows con locale no-UTF8 corrompe MOTDs con `§` (audit MA-02)
7. `strptime` sobre nombres de archivo del usuario: siempre `try/except ValueError` — usuarios pueden soltar archivos arbitrarios (audit HA-01)
8. NOTIFICATION payload: siempre `{"msg": ..., "type": "error"|"warning"|"info"}` — nunca `color` key (audit MA-04)
9. Watchdog NO emite `NOTIFICATION` — solo `_on_server_crashed` en core.py es dueño de notificaciones de crash (audit CA-01)
10. Installers (Fabric/Forge): pasar el JDK resuelto por ZBB, nunca asumir `"java"` del sistema (audit CA-02)

### Testing
```powershell
python -m pytest tests/ -v           # Full suite (364 tests)
python -m pytest tests/ -x -q        # Fail-fast, quiet
python -m pytest tests/test_X.py -v  # Single file
python -m py_compile app/ruta.py     # Syntax check after edit
```

### Branch Strategy
- `main` — producción, estable
- `dev` — integración (fast-forward desde main)
- `feature/<nombre>` — feature branches, eliminar tras merge

---

## Decisiones Arquitectónicas Vigentes

| Decisión | Detalle |
|----------|---------|
| **EventBus sobre callbacks** | Servicios emiten eventos, no reciben callbacks en constructor |
| **Módulos > clases singleton** | Los módulos de Python ya son singletons |
| **progress_callback(float, str)** | Siempre incluir texto descriptivo |
| **Carga eager para diálogos** | No lazy loading en ServerPropertiesEditor |
| **Java: System first, download fallback** | Detectar Java local antes de descargar JDK |
| **DNS recovery chain (3 mecanismos)** | NO MODIFICAR — API poll + stdout regex + create_tunnel |
| **Layout final** | Server controls inline en status bar, dashboard solo separator + tunnel |
| **Window 1150×700** | Suficiente para status bar right items |

---

## Feature Matrix

| Feature | Complejidad | Nuevas deps | Archivos nuevos | LOC est. | Depende de |
|---------|-------------|-------------|-----------------|----------|-----------|
| F4 UI (completar) | Baja | 0 | 0 | +110 | F4 backend ✅ |
| Orchestrator Tests | Media | 0 | 1 | +300 | — |
| Pin Dependencies | Baja | 0 | 1 | +30 | — |
| Crash Report Collector | Baja | 0 | 1 | +80 | P0.6 |
| Discord Webhook | Muy baja | 0 | 1 | +60 | P0 |
| MODS-B | Media | 0 | 0 | +200 | P0.1 |
| Bulk Mod Operations | Media | 0 | 0 | +200 | MODS-B |
| Server Templates | Media-alta | 0 | 1 | +350 | F8 |
| Server Migration | Media | 0 | 1 | +250 | F7 |
| Cross-Platform Linux | Baja | 0 | 1 | +80 | P0 |
| UI 2.0 | Alta | 0 | 0 | +300 | F10 |

Todas las features requieren **0 nuevas dependencias externas**.

---

## Glosario de Términos

| Término | Definición |
|---------|-----------|
| **ZBB** | Zero Block Bridge (abreviatura interna) |
| **MCTunnelApp** | Clase principal de UI (main.py) |
| **ZBBManager** | Orquestador central (core.py) |
| **ServerRunner** | Subprocess Java del servidor (logic.py) |
| **PlayitManager** | Gestión del agente Playit (playit_manager.py) |
| **EventBus** | Sistema de eventos pub/sub (server_events.py) |
| **ServerEvent** | Enumeración de tipos de evento |
| **Orchestrator** | Sub-orquestador de lifecycle (Server, Backup, Tunnel, Scheduler) |
| **Pre-flight check** | Verificación de requisitos ANTES de operación |
| **FakeRunner / FakeEmitter** | Test doubles en conftest.py |
