# ZeroBlockBridge — Roadmap de Desarrollo

> **Última actualización:** 2026-05-22

---

## Estructura del Plan

- [Fase 0-2: Completado ✅](#fase-0-auditoría-táctica)
- [Fase 3: Foundation — Refactors + Thread Safety](#fase-3-foundation--refactors--thread-safety)
- [Fase 4: Auto-Backup Scheduler](#fase-4-auto-backup-scheduler)
- [Fase 5: Crash Report Collector](#fase-5-crash-report-collector)
- [Fase 6: Discord Webhook](#fase-6-discord-webhook)
- [Fase 7: Server Templates + Modpacks](#fase-7-server-templates--modpacks)
- [Fase 8: Bulk Mod Operations](#fase-8-bulk-mod-operations)
- [Fase 9: Server Migration (.zbbpack)](#fase-9-server-migration-zbbpack)
- [Fase 10: Cross-Platform (Linux)](#fase-10-cross-platform-linux)
- [Fase 11: UI/UX — ZBB 2.0](#fase-11-uiux--zbb-20)
- [Resumen de Fases](#resumen-de-fases)

---

## Fase 0: Auditoría Táctica ✅

**Objetivo:** Entender el código base a fondo antes de modificar nada.

| Tarea | Estado |
|-------|--------|
| Análisis de import graph (38 archivos, ~6,200 LOC) | ✅ |
| Thread audit (24 spawns, 6 innecesarios) | ✅ |
| I/O map (metadata.json leído en 8+ lugares) | ✅ |
| Security scan (sanitizer OK, sin SQL) | ✅ |
| Memory baseline (~35-45 MB idle) | ✅ |
| Identificación sobreingeniería (46 hallazgos, 14 alto impacto) | ✅ |
| Script de profiling generado | ✅ |

## Fase 0.5: Corrección de Críticos ✅

| # | Tarea | Estado |
|---|-------|--------|
| 0.5.1 | Backup: ZIP de respaldo ANTES de restaurar | ✅ |
| 0.5.2 | Sanitizer: `%` no debe estar bloqueado | ✅ |
| 0.5.3 | JDK: SHA-256 vs SHA-512 detection + no retry | ✅ |
| 0.5.4 | Port validation: negativos fuera (1-65535) | ✅ |
| 0.5.5 | Dialog grab release (WM_DELETE_WINDOW) | ✅ |
| 0.5.6 | Watchdog backoff con límite 3600s | ✅ |

## Fase 1: Quick Wins ✅

| # | Tarea | LOC | Estado |
|---|-------|-----|--------|
| 1.1 | statemanager.py — singleton → 3 vars + 2 funciones | -50 | ✅ |
| 1.2 | Fix select_server() duplicado | 1 | ✅ |
| 1.3 | Eliminar mod_provider.py obsoleto | -67 | ✅ |
| 1.4 | CircularBuffer → collections.deque | -32 | ✅ |
| 1.5 | server_events.py — eliminar RLock + EventPayload | -15 | ✅ |
| 1.6 | Eliminar read_properties() alias | -2 | ✅ |
| 1.7 | settings_manager.py — singleton → módulo | -35 | ✅ |

## Fase 2: Bugfixes + Wizard UX ✅

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
| **Modrinth Management (3.10-3.14)** | | ✅ |
| 3.10 | Gestión de mods instalados (lista + delete) | ✅ |
| 3.11 | Paginación "Load More" en búsqueda | ✅ |
| 3.12 | Íconos reales de mods vía URL asíncrona | ✅ |
| 3.13 | Check for Updates en UI | ✅ |
| 3.14 | Selector de versión al instalar | ✅ |
| **Refactors adicionales (3.2, 3.3, 3.5, 3.6, 3.8, 3.9)** | | ✅ |
| 3.2 | install_fabric + install_forge → _run_installer() | ✅ |
| 3.3 | `start_server()` — extraer helpers `_auto_install_java()` y `_launch_server()` | ✅ |
| 3.5 | Centralizar metadata.json en get/update_server_meta() | ✅ |
| 3.6 | Eliminar _pre_warm_version_cache() de bootstrap | ✅ |
| 3.8 | Eliminar _apply_pending_settings() | ✅ |
| 3.9 | `Scheduler` + `SchedulerService` — fusionar en `logic.Scheduler` | ✅ |

---

## Fase A: UI + Bugfixes ✅

**Objetivo:** Pulir UX y corregir bugs visuales post-F3.

| # | Tarea | Estado |
|---|-------|--------|
| A.1 | Toast corner_radius=0 para consistencia visual | ✅ |
| A.2 | Copy-IP solo muestra host (sin puerto) | ✅ |
| A.3 | Toast duplicado eliminado de dashboard | ✅ |
| A.4 | Server tag muestra versión MC en sidebar | ✅ |

## Fase B: Layout Final ✅

**Objetivo:** Layout definitivo de la aplicación — status bar, dashboard compacto, tunnel.

| # | Tarea | Estado |
|---|-------|--------|
| B.1 | Start All eliminado del dashboard | ✅ |
| B.2 | SERVER/TUNNEL secciones con separador | ✅ |
| B.3 | Server controls ▶ ■ movidos a status bar (inline con ⚪ Offline + Select + ⚙) | ✅ |
| B.4 | Sección SERVER eliminada del dashboard | ✅ |
| B.5 | Label TUNNEL eliminado (tunnel_frame va directo) | ✅ |
| B.6 | Tunnel padding pady=(4, 1) | ✅ |
| B.7 | Default window 1150×700, min 900×580 | ✅ |
| B.8 | Mod card hover corregido (fg_color inicial explícito) | ✅ |
| B.9 | Mod card grid_columnconfigure(1, weight=1) | ✅ |
| B.10 | Java detection cache clase-level (JavaDetector._shared_cache) | ✅ |

## FIX-P1: 7 Críticos Corregidos ✅

| # | Bug | Archivo | Fix |
|---|-----|---------|-----|
| C1 | AppConfig.SERVERS_DIR inexistente | `server_properties_editor.py` | Importar SERVERS_DIR desde constants |
| C2 | EventBus thread-safety (dict race) | `server_events.py` | RLock en _listeners |
| C3 | settings_manager.init nunca llamado | `main.py` + `settings_manager.py` | set_config_dir(CONFIG_DIR) en init |
| C4 | get_agent_id() retorna None (-> str) | `playit_api.py` | Optional[str], None handling en callers |
| C5 | _jdk_source race en start_server | `core.py` | _start_lock protege start_server() |
| C6 | _winapi.CreateJunction en core | `logic.py` + `core.py` + `main.py` | create_junction() helper cross-platform |
| C7 | server.properties sin encoding utf-8 | `server_properties.py` + `server_properties_editor.py` | encoding=utf-8 en todos los open() |

## FIX-P2: Thread Safety + Dead Code ✅

| # | Tarea | Archivo | Fix |
|---|-------|---------|-----|
| P2.1 | playit_manager locks | `playit_manager.py` | Lock en _parse_line/_read_output, nested locks eliminados |
| P2.2 | version_manager double-join | `version_manager.py` | _wait_for_background_refresh simplificado |
| P2.3 | core restart race | `core.py` | _restart_lock con try/finally |
| P2.4 | remove_config_key muerto | `core.py` | Eliminado (~9 LOC) |
| P2.5 | stop_all muerto | `core.py` | Eliminado (~4 LOC) |
| P2.6 | import Any muerto | `server_properties.py` | Eliminado |

---

## Fase 3: Foundation — Refactors + Thread Safety + Tests ✅

**Objetivo:** Completar refactors pendientes y corregir bug risks de concurrencia identificados en la revisión de código. **Completada en su totalidad — 375 tests pasan.**

### 3A. Refactors Estructurales Pendientes (del plan original)

| # | Tarea | Archivos | LOC saved | Riesgo |
|---|-------|----------|-----------|--------|
| 3.3 | `start_server()` — extraer `_auto_install_java()` + `_launch_server()` ✅ | `core.py` | ~80 | 🟠 |
| 3.4 | `on_tunnel_status()` — refactor a state machine, eliminar pack_forget/pack *(skipped — marginal)* | `main.py:658-735` | ~20 | 🟡 |
| 3.7 | `PlayitManager` — test de guardia sintáctica `--secret_path` (no `--secret-path`) + path quoting en Windows | `tests/test_playit_manager.py` | — | 🟢 |
| 3.7b | *(Refactor a EventBus skipeado — ratio esfuerzo/beneficio marginal)* | — | — | — |
| 3.9 | `Scheduler` + `SchedulerService` — fusionar en `logic.Scheduler` ✅ | `logic.py`, ~~`scheduler_service.py`~~ | ~90 | 🟡 |

### 3B. Thread Safety + Bug Risks (hallazgos de revisión)

| # | Tarea | Archivos | Riesgo |
|---|-------|----------|--------|
| 3.15 | `statemanager.py` — `threading.Lock` + asignación directa (eliminado `globals()`) ✅ | `statemanager.py`, `main.py` | 🟠 |
| 3.16 | `settings_manager.py` — `_settings[key]=value` dentro del lock + double-checked locking ✅ | `settings_manager.py` | 🟠 |
| 3.17 | Tests Windows compat — `/tmp/` → `tempfile.gettempdir()` ✅ | `test_logic.py` | 🟡 |
| 3.18 | Type hints — añadidas a Watchdog, BackupManager, Toast, Heartbeat, ServerProperties, SingleInstance ✅ | `app/services/*.py`, `app/core/single_instance.py` | 🟢 |
| 3.23 | Safe Init audit — verificar que todos los `__init__` en `app/services/` inicialicen atributos antes de suscripciones/hilos de fondo | `app/services/*.py` | 🟢 |
| 3.24 | `.on()` deprecation check — escanear que no existan remanentes del patrón `.on()` en EventBus ni en ningún subscriptor | `app/core/server_events.py`, `app/**/*.py` | 🟢 |

### 3C. Tests para módulos críticos sin cobertura

| # | Módulo | LOC | Prioridad |
|---|--------|-----|-----------|
| 3.19 | `playit_manager.py` | 443 | 🔴 |
| 3.20 | `heartbeat.py` | 61 | 🟡 |
| 3.21 | ~~`scheduler_service.py`~~ *(eliminado en F3.9)* | — | — |
| 3.22 | `single_instance.py` | 71 | 🟢 |
| 3.25 | Cross-platform test isolation — mockear `sys.platform`, `platform.system()`, `platform.machine()` en tests existentes | `test_java_installer.py`, `test_provisioning.py` | 🟢 |

---

## Fase 4: Auto-Backup Scheduler

**Objetivo:** Implementar backups automáticos programables por servidor, con gestión de retención. El usuario dice "esto ya debería estar" — es una prioridad alta.

### Justificación
Ya existe `BackupManager.create_backup()` y un scheduler loop en `ZBBManager._start_scheduler_loop()` que corre cada 30s. Solo falta:
- Un `BackupScheduler` en `metadata.json` (paralelo al restart scheduler existente)
- Una verificación adicional en el loop
- UI en la pestaña Automation

### Tareas

| # | Tarea | Archivos | Esfuerzo |
|---|-------|----------|----------|
| 4.1 | `BackupScheduler` — modelo de datos en metadata.json (`auto_backup.enabled`, `interval_hours`, `retention_count`, `mode`, `last_run`) | `logic.py` (nueva clase o extender `Scheduler`) | Bajo |
| 4.2 | Extender `_start_scheduler_loop` en ZBBManager para check backup due | `core.py` | Bajo |
| 4.3 | Retención automática — al crear backup, eliminar los más viejos si excede `retention_count` | `backup_manager.py` | Bajo |
| 4.4 | Mutex backup-in-progress para evitar colisión con restart backup | `core.py`, `backup_manager.py` | Bajo |
| 4.5 | UI — sección "Auto-Backups" en pestaña Automation (switch, intervalo, retención) | `server_properties_editor.py` | Medio |
| 4.6 | UI — mostrar próximo backup programado en pestaña Backups | `server_properties_editor.py` | Bajo |
| 4.7 | Eventos `BACKUP_COMPLETED` / `BACKUP_FAILED` para notificaciones | `server_events.py`, `core.py` | Bajo |
| 4.8 | Tests | `tests/` | Medio |

**Complejidad total:** Media (~4-6 hrs)  
**Dependencias:** Fase 3 completa (thread safety para metadata writes)

---

## Fase 5: Crash Report Collector

**Objetivo:** Ante cada crash detectado por Watchdog, escribir un archivo JSON diagnóstico con toda la información disponible del servidor, sistema, y cola de consola.

### Justificación
- **0 nuevas dependencias** — `json`, `datetime`, `platform`, `uuid` son stdlib; `psutil` ya existe
- **Toda la data está en memoria en el momento del crash** (exit code, stderr tail, uptime, crash classification, console buffer, server metadata)
- **Fácil integración** — Watchdog ya emite `CRASHED` vía `EventBus`. Basta un subscriptor nuevo

### Formato del reporte (propuesto)
```json
{
  "schema_version": 1,
  "timestamp": "2026-05-16T14:30:22",
  "server": { "name": "...", "version": "1.20.1", "type": "Fabric", "ram": "2G" },
  "crash": { "reason": "out_of_memory", "exit_code": 1, "retry_attempt": 2 },
  "stderr_tail": ["Exception in thread...", "...", "..."],
  "console_tail": ["[14:30:20] [System] Starting server...", "..."],
  "system_info": { "os": "Windows 10", "ram_gb": 15.9, "cpu_count": 8 },
  "watchdog_state": { "max_retries": 3, "current_retries": 2 }
}
```

### Tareas

| # | Tarea | Archivos | Esfuerzo |
|---|-------|----------|----------|
| 5.1 | Crear `CrashReporter` — clase que subscribe a `CRASHED`, snapshotea console buffer y escribe JSON | `app/services/crash_reporter.py` (nuevo) | Medio |
| 5.2 | Integrar en `ZBBManager._setup_monitors()` | `core.py` | Bajo |
| 5.3 | Almacenamiento en `servers/<name>/crash_reports/` (sigue convención Minecraft) | — | Bajo |
| 5.4 | Tests | `tests/` | Medio |

**Complejidad:** Baja (~2 hrs)  
**Dependencias:** Fase 3 completa (thread safety), ninguna otra

---

## Fase 6: Discord Webhook

**Objetivo:** Enviar notificaciones a Discord vía webhook cuando ocurran eventos del servidor (crash, ready, zombie, lag, backup).

### Justificación
- **0 nuevas dependencias** — `requests` ya existe en `requirements.txt` (POST HTTP)
- **API simple** — Discord webhook = POST con `{"content": "mensaje"}` a una URL, sin OAuth
- **50-80 líneas de código** en un solo archivo nuevo
- **Riesgo mínimo** — arquitectura puramente aditiva

### Tareas

| # | Tarea | Archivos | Esfuerzo |
|---|-------|----------|----------|
| 6.1 | Crear `DiscordWebhookService` — subscribe a eventos vía EventBus, formatea mensajes, POST asíncrono | `app/services/discord_webhook.py` (nuevo) | Bajo |
| 6.2 | Añadir `discord_webhook_url` + `discord_notify_on` a defaults de settings | `settings_manager.py` | Bajo |
| 6.3 | Integrar en `ZBBManager.__init__()` | `core.py` | Bajo |
| 6.4 | Diseño thread-safe con `queue.Queue` + worker único secuencial + rate-limit (evitar thread exhaustion en eventos masivos como console line spam) | `discord_webhook.py` | Medio |
| 6.5 | Tests | `tests/` | Bajo |

**Complejidad:** Muy baja (~1-2 hrs)  
**Dependencias:** Fase 3 completa (EventBus thread safety)

---

## Fase 7: Server Templates + Modpacks

**Objetivo:** Permitir guardar y cargar configuraciones completas de servidor como plantillas reutilizables, con soporte para modpacks (lista de mods → auto-instalación desde Modrinth).

### Concepto

**Server Template** = archivo JSON que captura:
- Versión + tipo de servidor (Vanilla/Fabric/Paper/Forge/Purpur)
- RAM allocation + JVM flags
- Server properties (gamemode, difficulty, seed, view-distance, etc.)
- Lista de mods/plugins con slugs de Modrinth + versiones
- Metadatos (nombre, descripción, autor, fecha)

**Modpack** = template + lista de mods → al aplicarse, auto-descarga mods desde Modrinth

### Tareas

| # | Tarea | Archivos | Esfuerzo |
|---|-------|----------|----------|
| 7.1 | Definir formato JSON de template (`server-template.json`) | Documentación | Bajo |
| 7.2 | `TemplateManager` — save/load/list/delete templates | `app/services/template_manager.py` (nuevo) | Medio |
| 7.3 | Template selector en ServerWizard Step 2 (dropdown o galería de templates) | `server_wizard.py` | Medio |
| 7.4 | Save as template — botón en Properties Editor para guardar server actual como template | `server_properties_editor.py` | Medio |
| 7.5 | Soporte de modpacks — al aplicar template, descargar mods listados desde Modrinth | `template_manager.py`, `modrinth.py` | Medio |
| 7.6 | Templates incluidos por defecto: "Lite SMP", "Modded Fabric", "Vanilla+", "Paper Performance" | `assets/templates/` (carpeta nueva) | Bajo |
| 7.7 | Tests | `tests/` | Medio |

**Complejidad:** Media-alta (~6-8 hrs)  
**Dependencias:** Fase 4-6 completas, Modrinth client existente

---

## Fase 8: Bulk Mod Operations

**Objetivo:** Operaciones masivas sobre mods instalados: selección múltiple, instalación batch, actualización masiva, eliminación en lote.

### Justificación
El Modrinth Browser ya tiene:
- Lista de mods instalados con delete individual (`_on_show_installed`)
- Check de updates con lista de desactualizados (`check_updates`)
- Instalación individual

Solo falta extender con multi-select y batch actions.

### Tareas

| # | Tarea | Archivos | Esfuerzo |
|---|-------|----------|----------|
| 8.1 | Multi-select en lista de mods instalados (checkboxes en vez de delete individual) | `modrinth_browser.py` | Medio |
| 8.2 | Botón "Update Selected" — descarga batch de versiones nuevas | `modrinth_browser.py`, `modrinth.py` | Medio |
| 8.3 | Botón "Delete Selected" — batch delete con confirmación | `modrinth_browser.py` | Medio |
| 8.4 | Botón "Install Multiple" — seleccionar varios resultados de búsqueda e instalar de una | `modrinth_browser.py` | Medio |
| 8.5 | Progress bar batch — barra única que muestra "Installing 3/5 mods..." | `modrinth_browser.py` | Medio |
| 8.6 | Tests | `tests/` | Medio |

**Complejidad:** Media (~4-6 hrs)  
**Dependencias:** Fase 7 (template/modpack infraestructura opcional pero recomendada para consistencia)

---

## Fase 9: Server Migration (.zbbpack)

**Objetivo:** Exportar un servidor completo (sin JAR) a un archivo portátil `.zbbpack` que pueda importarse en otra máquina u otra plataforma.

### Justificación
- **Sin JAR** — el JAR se re-descarga al importar según versión + tipo, lo que hace el pack más liviano y universal
- **Cross-platform** — el ZIP contiene world, configs, lista de mods (no los jars), metadata

### Formato .zbbpack (propuesto)
```text
server.zbbpack/
├── manifest.json          # metadata, version, type, template info
├── world/                 # world data
├── server.properties      # config
├── mods/                  # (opcional) mod jars OR lista en manifest
├── plugins/               # (opcional)
└── crash_reports/         # (opcional) historial
```

### Tareas

| # | Tarea | Archivos | Esfuerzo |
|---|-------|----------|----------|
| 9.1 | Export — crear ZIP con world + config + metadata (sin JAR, sin JDK) | `app/services/migration.py` (nuevo) | Medio |
| 9.2 | Import — descomprimir, re-descargar JAR según versión, re-scaffold | `migration.py` | Medio |
| 9.3 | Mod list en manifest — guardar slugs de mods, re-descargar desde Modrinth al importar | `migration.py`, `modrinth.py` | Medio |
| 9.4 | UI — botón Export en Dashboard/Properties | `main.py`, `server_properties_editor.py` | Bajo |
| 9.5 | UI — Import wizard (seleccionar .zbbpack, confirmar, ver progreso) | `server_wizard.py` o `main.py` | Medio |
| 9.6 | Tests | `tests/` | Medio |

**Complejidad:** Media (~5-7 hrs)  
**Dependencias:** Fase 7 (template format, modpack infra), Modrinth client existente

---

## Fase 10: Cross-Platform (Linux)

**Objetivo:** Garantizar funcionamiento correcto en Linux.

| # | Tarea | Archivos | Riesgo |
|---|-------|----------|--------|
| 10.1 | `platform_utils.py` — `open_directory(path)` unificado | Nuevo + `main.py`, `server_properties_editor.py` | 🟢 |
| 10.2 | `platform_utils.py` — `create_link(src, dst)` unificado | Nuevo + `main.py`, `core.py` | 🟢 |
| 10.3 | SIGTERM handler en PlayitManager | `playit_manager.py` | 🟡 |
| 10.4 | `stop()` con `wait(timeout=5)` + `kill()` en Linux | `playit_manager.py` | 🟡 |
| 10.5 | `single_instance.py` verificar captura de SIGTERM | `single_instance.py` | 🟢 |

---

## Fase 11: UI/UX — ZBB 2.0

**Objetivo:** Transformar la experiencia de usuario con interfaces modernas, informativas, y eficientes.

### 11A. ServerWizard Rediseñado

| # | Tarea | Riesgo |
|---|-------|--------|
| 11.1 | Pre-flight checks integrados (Java, disco, puerto) | 🟡 |
| 11.2 | Barra de progreso con tiempo estimado | 🟢 |
| 11.3 | Resumen final antes de crear | 🟢 |
| 11.4 | Server Templates selector (Lite SMP, Modded Fabric, Vanilla+) | 🟡 |
| 11.5 | Botón "▶ Start Now" post-creación (ya existe, refinar) | 🟢 |

### 11B. ServerPropertiesEditor Rediseñado

| # | Tarea | Riesgo |
|---|-------|--------|
| 11.6 | Reducir de 7 a 4 pestañas (General, World, Management, Advanced) | 🟠 |
| 11.7 | `SettingsField` unificada con validación y tooltip | 🟡 |
| 11.8 | Agrupar Backups + Auto-restart + JDK en "Server Management" | 🟡 |
| 11.9 | Carga eager del diálogo completo | 🟢 |
| 11.10 | Validación visual inline | 🟢 |

### 11C. Layout + Consola

| # | Tarea | Riesgo |
|---|-------|--------|
| 11.11 | Sidebar colapsable/redimensionable | 🟠 |
| 11.12 | Dashboard compacto (~80px) | 🟢 |
| 11.13 | Indicador visual de servidor activo en sidebar | 🟢 |
| 11.14 | Console search/filter | 🟡 |
| 11.15 | Separación visual de console input | 🟢 |
| 11.16 | Reemplazar emojis con iconos reales (CTkImage) | 🟡 |
| 11.17 | Fuentes consistentes desde AppConfig | 🟢 |

### 11D. Mejoras Generales

| # | Tarea | Riesgo |
|---|-------|--------|
| 11.18 | Server performance dashboard (TPS, RAM, players) | 🟠 |
| 11.19 | Modo oscuro/claro completo | 🟢 |
| 11.20 | Tooltips descriptivos en todos los campos | 🟢 |

---

## Resumen de Fases

| Fase | Descripción | LOC cambio | Prioridad | Estado |
|------|-------------|-----------|-----------|--------|
| **F0-F2** | Foundation + Quick Wins + Wizard UX | — | 🥇 | ✅ |
| **FA-FB** | UI + Layout Final v1.4 | ~150 | 🥇 | ✅ |
| **FIX-P1** | 7 Critical Bugs | -50 / +80 | 🥇 | ✅ |
| **FIX-P2** | Thread Safety + Dead Code | -20 / +40 | 🥇 | ✅ |
| **F3** | Foundation — Refactors + Thread Safety + Tests | -200 / +100 | 🥇 | ✅ |
| **F4** | Auto-Backup Scheduler | +150 | 🥇 | ✅ |
| **F5** | Crash Report Collector | +80 | 🥇 | F3 |
| **F6** | Discord Webhook | +60 | 🥈 | F3 |
| **F7** | Server Templates + Modpacks | +350 | 🥈 | F4-F6 |
| **F8** | Bulk Mod Operations | +200 | 🥈 | F7 (recomendado) |
| **F9** | Server Migration (.zbbpack) | +250 | 🥉 | F7 |
| **F10** | Cross-Platform (Linux) | +80 | 🥉 | F3 |
| **F11** | UI/UX — ZBB 2.0 | +300 | 🥉 | F3 |

### Orden de Ejecución Recomendado

```
F0 → F0.5 → F1 → F2 → F3 → F4 → FA → FB → FIX-P1 → FIX-P2 → F5 → F6 → F7 → F8 → F9 → F10 → F11
(hecho) (hecho) (hecho) (hecho) (hecho) (hecho) (hecho) (hecho) (hecho) (hecho) ⬆️    ↑    ↑    ↑    ↑     ↑     ↑
                                                                                  Crash Discord  ...  Linux  ZBB
                                                                                  Report        2.0
```

### Branch Strategy
- Rama principal: `main` (producción, estable)
- Rama de integración: `dev` (fast-forward desde main)
- Feature branches: `feature/<nombre>` (eliminar tras merge)
- Sin merge commits — solo fast-forward o squash
- Commits atómicos (un commit = un cambio)

### Testing
```powershell
python -m pytest tests/ -v           # Regresión (375 tests)
python -m pytest tests/ -x -q        # Rápido (fail-fast)
python -m py_compile app/ruta.py     # Sintaxis
```

---

## Feature Matrix

| Feature | Complejidad | Nuevas deps | Archivos nuevos | LOC estimado |
|---------|-------------|-------------|-----------------|-------------|
| Auto-Backup Scheduler | Media | 0 | 0 | +150 |
| Crash Report Collector | Baja | 0 | 1 | +80 |
| Discord Webhook | Muy baja | 0 | 1 | +60 |
| Server Templates | Media-alta | 0 | 1 | +350 |
| Bulk Mod Operations | Media | 0 | 0 | +200 |
| Server Migration | Media | 0 | 1 | +250 |

Todas las features propuestas requieren **0 nuevas dependencias externas**. Todo se construye con `requests`, `psutil`, `json`, `threading`, `datetime`, `pathlib` — todos ya presentes en el proyecto.
