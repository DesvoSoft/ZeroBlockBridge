# ZeroBlockBridge — Roadmap de Desarrollo

> **Documento maestro de contexto:** `.planning/PROJECT_CONTEXT.md`
> **Auditoría detallada:** `.planning/AUDITORIA_R1.md`
> **Última actualización:** 2026-05-16

---

## Estructura del Plan

- [Fase 0: Auditoría Táctica ✅](#fase-0-auditoría-táctica-completada)
- [Fase 0.5: Corrección de Críticos ✅](#fase-05-corrección-de-críticos-seguridad--data-loss)
- [Fase 1: Quick Wins ✅](#fase-1-quick-winds-bajo-riesgo)
- [Fase 2: Bugfixes + Wizard UX ✅](#fase-2-bugfixes--wizard-ux)
- [Fase 3: Refactors Estructurales](#fase-3-refactors-estructurales)
- [Fase 4: Cross-Platform (Linux)](#fase-4-cross-platform-linux-compat)
- [Fase 5: UI/UX — ZBB 2.0](#fase-5-uiux--zeroblock-bridge-20)
- [Fase 6: Features Innovadoras](#fase-6-features-innovadoras)
- [Resumen de Fases](#resumen-de-fases)

---

## Fase 0: Auditoría Táctica (COMPLETADA)

**Objetivo:** Entender el código base a fondo antes de modificar nada.

| Tarea | Archivos | Estado |
|-------|----------|--------|
| Análisis de import graph (38 archivos, ~6,200 LOC) | Todos | ✅ |
| Thread audit (24 spawns, 6 innecesarios) | main.py, logic.py, core.py | ✅ |
| I/O map (metadata.json leído en 8+ lugares) | Todos | ✅ |
| Security scan (sanitizer OK, sin SQL) | sanitizer.py | ✅ |
| Memory baseline estimado (~35-45 MB idle) | — | ✅ |
| Identificación sobreingeniería (46 hallazgos, 14 alto impacto) | Todos | ✅ |
| Script de profiling generado | `scripts/profile_app.py` | ✅ |
| Documento maestro de contexto | `.planning/PROJECT_CONTEXT.md` | ✅ |
| ~2,800 LOC potencialmente eliminables de ~6,200 | — | 📊 |

---

## Fase 0.5: Corrección de Críticos (Seguridad + Data Loss)

**Objetivo:** Corregir bugs que pueden causar pérdida de datos, seguridad comprometida, o UI bloqueada. ~42 min de trabajo.

| # | Prioridad | Tarea | Archivo | Líneas | Riesgo | Tiempo |
|---|-----------|-------|---------|--------|--------|--------|
| 0.5.1 | 🔴 | Backup: hacer ZIP de respaldo ANTES de restaurar | `backup_manager.py:87-102` | ~15 | 🔴 (data loss) | 15 min |
| 0.5.2 | 🔴 | Sanitizer: `%` no debe estar bloqueado (válido en MC) | `sanitizer.py:6` | 1 | 🔴 (UX) | 2 min |
| 0.5.3 | 🔴 | JDK: no reintentar si SHA256 falló + detectar SHA-256 vs SHA-512 | `java_installer.py:73-78,189-202` | ~10 | 🔴 (wasted bandwidth) | 10 min |
| 0.5.4 | 🟠 | Port validation: negativos fuera | `scaffolder.py:22` | ~5 | 🟠 (túnel roto) | 5 min |
| 0.5.5 | 🟠 | DownloadProgressDialog: `protocol("WM_DELETE_WINDOW")` para grab_release | `ui_components.py:220-272` | 1 | 🟠 (UI lockeada) | 5 min |
| 0.5.6 | 🟠 | Watchdog backoff con límite superior (1 hora max) | `watchdog.py:178-179` | ~3 | 🟠 (server nunca revive) | 5 min |

**Detalle técnico de cada fix:**

### 0.5.1 — Backup restore safety (backup_manager.py)
```python
# ANTES: wipe → extract (si ZIP corrupto, data loss)
shutil.rmtree(server_path)  # wipe primero
zipf.extractall(server_path)  # si falla, datos perdidos

# DESPUÉS: backup previo → wipe → extract → restore si falla
_temp_backup = shutil.make_archive(...)  # respaldo antes de tocar
try:
    wipe_server_dir()
    extract_zip()
except:
    restore_from_temp_backup()
    raise
finally:
    cleanup_temp_backup()
```

### 0.5.2 — Sanitizer % fix (sanitizer.py:6)
```python
# ANTES: INJECTION_CHARS incluye %
INJECTION_CHARS = set(';|&`$%')

# DESPUÉS: % eliminado de INJECTION_CHARS (válido en comandos MC)
INJECTION_CHARS = set(';|&`$')
```

### 0.5.3 — JDK checksum retry + SHA detection (java_installer.py)
```python
# ANTES: reintenta descarga contra misma URL (siempre falla)
if not _verify_checksum(zip_path, expected_checksum):
    zip_path.unlink()  # misma URL → mismo checksum → siempre falla

# DESPUÉS: detectar SHA-256 vs SHA-512 + abortar inmediatamente
if len(expected_checksum) == 128:
    actual = _compute_sha512(zip_path)  # nueva función
else:
    actual = _compute_sha256(zip_path)
if actual != expected_checksum:
    raise JdkIntegrityError(...)  # no retry
```

### 0.5.4 — Port validation (scaffolder.py)
```python
# AÑADIR al inicio de pre_boot_scaffold():
if not (1 <= port <= 65535):
    raise ValueError(f"Invalid port: {port}. Must be 1-65535.")
```

### 0.5.5 — Dialog grab release (ui_components.py)
```python
# AÑADIR en __init__ de DownloadProgressDialog:
self.protocol("WM_DELETE_WINDOW", self.close)
```

### 0.5.6 — Watchdog backoff cap (watchdog.py)
```python
# ANTES: backoff exponencial sin límite
def _compute_backoff(self):
    return self._backoff_base * (2 ** (self.retry_count - 1))

# DESPUÉS: cap a 3600s (1 hora)
def _compute_backoff(self):
    delay = self._backoff_base * (2 ** (self.retry_count - 1))
    return min(delay, 3600)  # cap at 1 hour
```

---

## Fase 1: Quick Wins (COMPLETADA)

**Objetivo:** Eliminar código muerto y sobreingeniería obvia. ~30 min de trabajo, ~194 LOC eliminadas.

| # | Tarea | Archivos | LOC | Riesgo | Estado |
|---|-------|----------|-----|--------|--------|
| 1.1 | `statemanager.py` — singleton+facade → 3 vars + 2 funciones | `statemanager.py`, `main.py` | ~50 | 🟢 | ✅ |
| 1.2 | Fix `select_server()` duplicado (línea 346) | `main.py:345-346` | 1 (bug) | 🟢 | ✅ |
| 1.3 | Eliminar `mod_provider.py` — usar `ModrinthClient` directo | `mod_provider.py`, `modrinth_browser.py` | 67 | 🟢 | ✅ |
| 1.4 | `console_buffer.py` — `CircularBuffer` → `collections.deque` | `console_buffer.py` | 32 | 🟢 | ✅ |
| 1.5 | `server_events.py` — eliminar `RLock` + `EventPayload` muerto | `server_events.py` | ~15 | 🟢 | ✅ |
| 1.6 | Eliminar `read_properties()` alias en `server_properties.py` | `server_properties.py` | 2 | 🟢 | ✅ |
| 1.7 | `settings_manager.py` — singleton → funciones módulo | `settings_manager.py` | ~35 | 🟡 | ✅ |

---

## Fase 2: Bugfixes + Playit UX + Wizard UX (COMPLETADA)

**Objetivo:** Corregir bugs activos, arreglar el filtro de Modrinth, rediseñar la UI de linking de Playit, mejorar la experiencia de creación de servidores, y agregar soft reset tunnel.

### 2A. Bugfixes

| # | Tarea | Archivos | Riesgo | Estado |
|---|-------|----------|--------|--------|
| 2.1 | Fix `check_java_startup()` — usar `JavaDetector` en vez de parsear ruta | `main.py:298-313` | 🟡 | ✅ |
| 2.2 | DNS recovery chain (3 mecanismos) | `playit_manager.py` | 🔴 | ✅ |
| 2.3 | Verificar que `TunnelStatusProvider.schedule_update()` elimina el "Starting..." duplicado | `main.py`, `statemanager.py` | 🟢 | ✅ |

### 2B. Modrinth Critical Fix

| # | Tarea | Archivos | Riesgo | Estado |
|---|-------|----------|--------|--------|
| 2.4 | Fix `project_type` filter — pasar valor del dropdown + arreglar `get_popular_mods()` | `modrinth_browser.py` | 🟡 | ✅ |

### 2C. Playit Link UX Redesign

| # | Tarea | Archivos | Riesgo | Estado |
|---|-------|----------|--------|--------|
| 2.5 | Rediseñar UI de linking: collapsible con botón "⚡ Link", auto-open web, hide reset si unlinked | `main.py` | 🟡 | ✅ |
| 2.14 | Soft reset tunnel — solo borra túneles, reusa agente. Click "▶" para nuevo túnel | `playit_manager.py`, `core.py`, `main.py` | 🟢 | ✅ |

### 2D. Wizard + Barra de Progreso + Status

| # | Tarea | Archivos | Riesgo | Estado |
|---|-------|----------|--------|--------|
| 2.6 | `progress_callback(float)` → `progress_callback(float, str)` con estados | `ui_components.py`, `sha1_validator.py` | 🟢 | ✅ |
| 2.7 | Mensajes de progreso detallados (descarga, SHA1, normalize, scaffold, bytecode, tunnel) | `main.py`, `server_wizard.py` | 🟢 | ✅ |
| 2.8 | Pre-flight Java check en ServerWizard Step 2 | `server_wizard.py` | 🟡 | ✅ |
| 2.9 | Botón "▶ Start Now" al finalizar creación | `main.py` | 🟢 | ✅ |
| 2.10 | Status badge por tipo de Java (System/Portable) en barra de estado | `java_detector.py`, `main.py` | 🟢 | ✅ |

### 2E. Remote Agent + JDK Pre-download

| # | Tarea | Archivos | Riesgo | Estado |
|---|-------|----------|--------|--------|
| 2.11 | Remote agent cleanup — gate `key_valid` eliminado | `playit_manager.py` | 🟡 | ✅ |
| 2.12 | Pre-download JDK durante wizard tras bytecode analysis | `main.py`, `java_installer.py` | 🟡 | ✅ |
| 2.13 | Reset UI fijo — `skip_debounce` post-reset | `main.py` | 🟢 | ✅ |

### Estados de Progreso Definidos (implementados)

```
0%  → Downloading {type} {version} server jar...
20% → Verifying file integrity (SHA1)...
25% → Preparing server jar...
30% → Applying server icon...
35% → Configuring server environment...
50% → Analyzing Java requirements...
60% → Setting up Playit tunnel...
80% → Finalizing setup...
100% → ✓ Server ready!
```

---

## Fase 3: Refactors + Modrinth Management

**Objetivo:** Reducir duplicación y complejidad en la lógica central (~248 LOC saved) y mejorar la gestión de mods con nuevas funcionalidades en el browser.

### 3A. Refactors Estructurales

| # | Tarea | Archivos | LOC saved | Riesgo | Estado |
|---|-------|----------|-----------|--------|--------|
| 3.1 | `normalize_server_jar()` extraer helper symlink/copy (122→~60 LOC) | `logic.py:209-331` | ~60 | 🟡 | ❌ Pendiente |
| 3.2 | `install_fabric` + `install_forge` → `_run_installer()` helper | `logic.py:178-374` | ~50 | 🟡 | ✅ Completado |
| 3.3 | `start_server()` extraer auto-install helper (222→~140 LOC) | `core.py:129-351` | ~80 | 🟠 | ❌ Pendiente |
| 3.4 | `on_tunnel_status()` refactor a state machine — eliminar patrón `pack_forget`/`pack` | `main.py:658-735` | ~20 | 🟡 | ❌ Pendiente |
| 3.5 | Centralizar acceso a `metadata.json` en `get_server_meta()`/`update_server_meta()` | `logic.py` + callers | ~30 | 🟡 | ✅ Completado |
| 3.6 | Eliminar `_pre_warm_version_cache()` de bootstrap | `core.py:119-124` | ~8 | 🟢 | ✅ Completado |
| 3.7 | `PlayitManager` aceptar EventBus en vez de 4 callbacks | `playit_manager.py`, `core.py` | ~15 | 🟠 | ❌ Pendiente |
| 3.8 | Eliminar `_apply_pending_settings()` (duplica scaffolder) | `logic.py:402-428` | ~28 | 🟡 | ✅ Completado |
| 3.9 | `Scheduler` + `SchedulerService` fusionar en funciones | `logic.py`, `scheduler_service.py` | ~90 | 🟡 | ❌ Pendiente |

### 3B. Modrinth Management (UI + Funcionalidad)

| # | Tarea | Archivos | Riesgo | Estado |
|---|-------|----------|--------|--------|
| 3.10 | Añadir gestión de mods instalados (lista con checkboxes, desinstalar con confirmación) | `modrinth_browser.py` | 🟡 | ✅ Completado |
| 3.11 | Añadir paginación en búsqueda ("Load More" que incrementa offset) | `modrinth_browser.py`, `modrinth.py` | 🟢 | ✅ Completado |
| 3.12 | Mostrar íconos reales de mods vía `icon_url` en vez de placeholders de letras | `modrinth_browser.py` | 🟢 | ✅ Completado |
| 3.13 | Exponer "Check for Updates" en UI llamando `ModrinthClient.check_updates()` | `modrinth_browser.py` | 🟡 | ✅ Completado |
| 3.14 | Añadir selector de versión al instalar (dropdown de versiones compatibles antes de descargar) | `modrinth_browser.py`, `modrinth.py` | 🟡 | ✅ Completado |

### Pendientes del roadmap anterior (integrados aquí)

| Tarea original | Ahora en |
|---------------|----------|
| `platform_utils.py` — `open_directory()` | Fase 4.1 |
| `platform_utils.py` — `create_link()` | Fase 4.2 |
| SIGTERM handler Linux | Fase 4.3 |
| `stop()` con wait+kill en Linux | Fase 4.4 |
| `single_instance.py` + SIGTERM | Fase 4.5 |
| Mod Ecosystem Event-Driven | Reevaluado — baja prioridad |

---

## Fase 4: Cross-Platform (Linux Compat)

**Objetivo:** Garantizar funcionamiento correcto en Linux (hereda de Fase 2b del roadmap anterior).

| # | Tarea | Archivos | Riesgo |
|---|-------|----------|--------|
| 4.1 | `platform_utils.py` — `open_directory(path)` unificado | Nuevo + `main.py`, `server_properties_editor.py` | 🟢 |
| 4.2 | `platform_utils.py` — `create_link(src, dst)` unificado | Nuevo + `main.py`, `core.py` | 🟢 |
| 4.3 | SIGTERM handler en `playit_manager.py` | `playit_manager.py` | 🟡 |
| 4.4 | `stop()` con `wait(timeout=5)` + `kill()` en Linux | `playit_manager.py` | 🟡 |
| 4.5 | `single_instance.py` verificar captura de SIGTERM | `single_instance.py` | 🟢 |

---

## Fase 5: UI/UX — ZeroBlock Bridge 2.0

**Objetivo:** Transformar la experiencia de usuario con interfaces modernas, informativas, y eficientes.

### 5A. ServerWizard Rediseñado

| # | Tarea | Riesgo |
|---|-------|--------|
| 5.1 | Pre-flight checks integrados (Java, espacio en disco, puerto disponible) | 🟡 |
| 5.2 | Barra de progreso con texto descriptivo y estimación de tiempo | 🟢 |
| 5.3 | Resumen final antes de crear ("Server X con Paper 1.20.1, 2GB RAM, Java 17") | 🟢 |
| 5.4 | Botón "▶ Start Now" post-creación | 🟢 |
| 5.5 | Server Templates selector (Lite SMP, Modded Fabric, Vanilla+) | 🟡 |

### 5B. ServerPropertiesEditor Rediseñado

| # | Tarea | Riesgo |
|---|-------|--------|
| 5.6 | Reducir de 7 a 4 pestañas (General, World, Management, Advanced) | 🟠 |
| 5.7 | Crear clase `SettingsField` unificada con validación y tooltip | 🟡 |
| 5.8 | Agrupar Backups + Auto-restart + JDK en "Server Management" | 🟡 |
| 5.9 | Carga eager (no lazy) del diálogo completo | 🟢 |
| 5.10 | Validación visual inline (borde rojo + mensaje) para campos inválidos | 🟢 |
| 5.11 | Backup scheduler visual con selector de hora | 🟡 |

### 5C. Layout + Consola

| # | Tarea | Riesgo |
|---|-------|--------|
| 5.12 | Sidebar colapsable/redimensionable (toggle hamburguesa) | 🟠 |
| 5.13 | Dashboard compacto (~80px en vez de ~130px, reducir pady y botones) | 🟢 |
| 5.14 | Indicador visual de servidor activo en sidebar (border/accent color) | 🟢 |
| 5.15 | Console search/filter (buscar texto en logs, filtrar por nivel) | 🟡 |
| 5.16 | Separación visual de console input (fg_color distinto del fondo) | 🟢 |
| 5.17 | Reemplazar emojis en botones con iconos reales (CTkImage) | 🟡 |
| 5.18 | Fuentes consistentes — migrar hardcodeos a `AppConfig.FONT_*` | 🟢 |
| 5.19 | Gear de settings mover a toolbar dedicada | 🟢 |

### 5D. Mejoras Generales UI

| # | Tarea | Riesgo |
|---|-------|--------|
| 5.20 | Server performance dashboard (TPS, RAM, players en tiempo real) | 🟠 |
| 5.21 | Modo oscuro/claro completo — pulir colores del tema | 🟢 |
| 5.22 | Tooltips descriptivos en todos los campos de config | 🟢 |

---

## Fase 6: Features Innovadoras

**Objetivo:** Agregar funcionalidades que diferencien a ZeroBlockBridge de otros launchers.

### ⭐ Alta Prioridad

| # | Feature | Descripción | Esfuerzo |
|---|---------|-------------|----------|
| 6.1 | **Server Templates** | Perfiles predefinidos reutilizables (guardar/cargar config completa) | 2-3 días |
| 6.2 | **Server Import/Export (.zbbpack)** | Backup portátil en ZIP con config + mundo + mods | 2-3 días |
| 6.3 | **Auto-backup scheduler visual** | UI para programar backups automáticos con retención | 1 día |

### 🟡 Media Prioridad

| # | Feature | Descripción | Esfuerzo |
|---|---------|-------------|----------|
| 6.4 | **Plugin/Mod auto-installer** | Seleccionar mods populares durante creación del servidor | 2 días |
| 6.5 | **One-click deploy** | "Lite SMP", "Modded Fabric", "Vanilla+" con 1 clic | 3 días |
| 6.6 | **Launch presets** | Perfiles Survival / Creative / Minigame que ajustan server.properties | 1 día |
| 6.7 | **Server health dashboard** | Gráficos de TPS, RAM, jugadores, chunks | 2 días |

### 🟢 Baja Prioridad

| # | Feature | Descripción | Esfuerzo |
|---|---------|-------------|----------|
| 6.8 | **Modo headless** | `launcher.py --headless` para VPS sin GUI | 2 días |
| 6.9 | **Web dashboard** | Monitoreo vía navegador (FastAPI + websocket) | 5 días |
| 6.10 | **Auto-update** | Verificar y descargar nuevas versiones de ZBB | 1 día |

---

## Resumen de Fases

| Fase | Descripción | LOC cambio | Tiempo estimado | Prioridad |
|------|-------------|-----------|-----------------|-----------|
| **F0** | Auditoría Táctica | ~0 | ✅ Completa | — |
| **F0.5** | Corrección de Críticos | ~+35 | ✅ Completa | — |
| **F1** | Quick Wins | -194 | ✅ Completa (~30 min) | — |
| **F2** | Bugfixes + Playit UX + Wizard UX | +150 | ✅ Completa | — |
| **F3** | Refactors + Modrinth Management | -180 | ~4 hrs | 🥇 Siguiente |
| **F4** | Cross-Platform (Linux) | +80 | ~2 hrs | 🥈 |
| **F5** | UI/UX — ZBB 2.0 | +350 | ~6 hrs | 🥉 |
| **F6** | Features Innovadoras | +500 | ~2-3 semanas | 🥉 |

### Orden de Ejecución Recomendado
```
F0 → F0.5 → F1 → F2 → F3 → F4 → F5 → F6
(hecho) (hecho) (hecho) (hecho) ⬆️
                          empezar aquí
```

### Branch Strategy
- Rama principal de desarrollo: `dev`
- Feature branches desde `dev`: `feature/<nombre>`
- Commits atómicos (un commit = un cambio)
- Merge a `dev` después de cada fase o feature completa
- NO mergear a `main` hasta tener versión estable

### Testing
```powershell
python -m pytest tests/ -v           # Regresión
python -m py_compile app/ruta.py     # Sintaxis
python scripts/profile_app.py        # Baseline rendimiento
```

---

## Pendientes del Roadmap Anterior (Migrados)

Los siguientes items del roadmap original han sido reevaluados e integrados:

| Item original | Estado | Nueva ubicación |
|--------------|--------|-----------------|
| Fase 1G: Merge simplificación Playit a `dev` | ✅ Completado | Fase 2 + merge a dev |
| Fase 2b: Linux compat (platform_utils) | Pendiente | Fase 4.1-4.2 |
| Fase 2b: SIGTERM + stop Linux | Pendiente | Fase 4.3-4.5 |
| Fase 3a: Mod Ecosystem Event-Driven | Reevaluado | ⏸ Pospuesto (baja prioridad) |
| Fase 3b: Dependency Resolution | Reevaluado | ⏸ Pospuesto |

**Razón del pospuesto de Fase 3 (Mod Ecosystem):** El Event-Driven para mods es un refactor grande
que no aporta valor visible al usuario. Priorizamos mejoras de UX y estabilidad primero.
