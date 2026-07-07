# ZeroBlockBridge — Roadmap de Desarrollo

**Última actualización:** 2026-07-07 (rev 10 — F13/F14/F15 planificadas: higiene de disco, Settings 2.0, light theme)
**Versión proyecto:** Pre-alpha (desarrollo activo)
> **Test count:** 544 tests, 100% pass, 0 flaky

**Historial completo de fases/auditorías resueltas:** ver `docs/roadmap-history.md` (F0-F3, FA-FB, FIX-P1/P2/P3, F4, P0, EXE-PERF, F5, F6, MODS-B, F8, BUG-AUDIT, NR, AUDIT-2, AUDIT-3, Handover 2026-06-23). Este archivo solo trackea lo pendiente o en curso.

### Log de sesiones recientes (fuera de roadmap formal)
- **2026-07-05 (9):** fix(core) job-object reaping proceso servidor + port preflight + mods tab gating; feat(ui) server delete via right-click + first-run EULA consent; fix(versions) migración Paper Fill API v3; fix(tunnel) reap agentes playitd huérfanos + silenciar ruido duel-session; fix(threading) I/O lento y callbacks fuera de locks; fix(heartbeat) eventos fuera del lock — 463 tests pass
- **2026-07-05 (10):** fix(ui) icono mod card centrado verticalmente; fix(ui) contraste texto/fondo Modrinth Browser (`_MODRINTH_GREEN` con texto blanco ilegible → `#0f172a`; `COLOR_TEXT_PRIMARY` sin tupla light/dark en 3 sitios corregido) — 463 tests pass
- **2026-07-06 (11):** feat(players) CA-H02 — player_files.py (ops/bans/whitelist persistence) + PlayersDashboard como CTkTabview (Online/Whitelist/Operators/Bans), ban/kick funcionan offline, confirmaciones ZBBDialog; feat(console) CA-H03 — ConsoleWidget.highlight()/jump_to_next_match() con tags search_hit/search_hit_current, search bar en Console + Tunnel Log tabs; feat(world) CA-H04 — list_worlds/get_active_world/set_active_world en server_properties.py + dropdown en World tab; feat(templates) F7 resto — template_manager.py (save/load/list/delete) + selector en wizard Step 2 + save-as-template + 4 templates por defecto; feat(migration) F9 — migration.py export_server/import_server (.zbbpack, excluye jar/logs, zip-slip guard) + botón export en Backups tab + menú "Add Server" (Folder/.zbbpack) en main.py — 483 tests pass
- **2026-07-07 (13):** feat(settings) F14 completo — AppSettingsDialog reescrito como CTkTabview 5 tabs (General/Notifications/Java/Storage/About); selector de tema (Light/System gated hasta F15 con toast); checkboxes por evento webhook (`webhook_events` setting + `enabled_events` en DiscordWebhookService); Tab Java: JDKs gestionados con tamaño + delete + purge unused (nuevos `ZBBManager.list_managed_jdks/purge_jdk/purge_unused_jdks` con guard is_running) + tabla de Javas detectados (`detect_all()`); Tab Storage: disk usage por categoría (nuevo `services/disk_usage.py`) + clear crash reports (`ZBBManager.purge_crash_reports`); Tab About con nueva `AppConfig.APP_VERSION` (también en título de ventana); keys muertas `servers_dir`/`java_preferences` eliminadas de SettingsManager; `JdkManager.list_installed()` nuevo — smoke test Tk real; feat(java) F13 — descarga JRE preferida con fallback a JDK (`_query_assets`, ~45 MB vs ~300 MB por versión), limpieza ~1.3 GB (app/.zbb_cache stale + dist runtime dirs), `.venv` de proyecto — 544 tests pass
- **2026-07-06 (12):** fix(ui) wizard reorganizado 4→5 steps (Identity, Engine+Version, Resources, Rules&Security, World&Network) para eliminar truncamiento de RAM y saturación de step3; feat(ui) selección de Java interactiva en wizard Step 3 (radio: usar Java detectado del sistema vs auto-descargar recomendado, con dropdown de instalaciones) — antes solo mostraba label estático; fix(ui) botón Next de búsqueda en consola ahora re-busca si el texto cambió desde el último Enter (antes solo ciclaba matches viejos); fix(ui) `VersionManager._refresh_versions` → `refresh_versions()` (AttributeError en wizard); feat(ui) merge de botones "Load Existing Folder"/"Import .zbbpack" en un único "Add Server" con menú de 2 opciones; feat(settings) export a .zbbpack ahora también disponible desde Server Settings (Backups tab), no solo click-derecho — 483 tests pass

**Siguiente prioridad:** F15 (light theme). F13 y F14 ✅ 2026-07-07. Después: F10 (Linux) o F11 Bloques B/C.

---

## Estado Actual

### Foundation Score: 6.6/10 — Sólida con fisuras conocidas
| Área | Score | Nota |
|------|-------|------|
| Type hints | 3/10 | ~28.5% tipado, sin mypy en CI |
| Dependencias | 7/10 | Pin en requirements.txt ✅, pyproject.toml ✅ |

### Todas las fases fundacionales completas ✅
F0-F3, FA-FB, FIX-P1/P2/P3, F4, P0 (Foundation Hardening), EXE-PERF, F5 (Crash Reports), F6 (Discord Webhook), MODS-B, F8 (Bulk Mods), BUG-AUDIT (18/19), AUDIT-2, AUDIT-3 — todas ✅. Detalle en `docs/roadmap-history.md`.

---

## Tabla de Estado de Fases (índice único)

| Fase | Descripción | Prioridad | Estado |
|------|-------------|-----------|--------|
| F0-F3 → F6, P0, EXE-PERF, MODS-B, F8 | Foundation completa | 🥇 | ✅ (ver history) |
| **F7** | Templates propios (TemplateManager, save-as-template, defaults) | 🥈 | ✅ Implementado 2026-07-06 |
| **CA-H01** | JVM args UI por servidor | 🥈 | ✅ Implementado |
| **CA-H02** | Player management unificado (operators+bans+whitelist) | 🥈 | ✅ Implementado 2026-07-06 |
| **CA-H03** | Console search/filter | 🥈 | ✅ Implementado 2026-07-06 |
| **CA-H04** | World switching UI | 🥈 | ✅ Implementado 2026-07-06 |
| **MODS-SEC** | Mods security hardening | — | ✅ Implementado |
| **F9** | Server Migration (.zbbpack) | 🥉 | ✅ Implementado 2026-07-06 |
| **F10** | Cross-Platform Linux | 🥉 | ⬜ Pendiente — **próxima prioridad** |
| **F11** | UI/UX ZBB 2.0 "Dirt Block" | 🥉 | 🔶 Parcial — Bloque A (palette/botones) ✅, Bloques B/C/D pendientes |
| **F12** | Feature Gaps vs competencia | 🥉 | ⬜ Sin iniciar |
| **F13** | Higiene de disco + JRE on-demand | 🥇 | ✅ Implementado 2026-07-07 |
| **F14** | App Settings 2.0 (tabbed: General/Notifications/Java/Storage/About) | 🥇 | ✅ Implementado 2026-07-07 |
| **F15** | Light theme completo (tokens a tuplas + selector) — consolida F11.D5 | 🥈 | ⬜ Aprobado 2026-07-07 |
| **REFACT-1** | JavaResolver + launch steps | ⏸️ | Pospuesto (YAGNI pre-alpha) |
| **CA-M01-M06** | NeoForge/Quilt, CurseForge, dep graph, perf dashboard, hot-switch | 🥉 | ⬜ Sin iniciar |
| **CA-L01-L04** | Multi-server, profiles, remote mgmt, Hangar plugins | 🔮 | ⬜ Largo plazo |

### Orden de Ejecución Recomendado
```
F13 (disco/JRE) → F14 (Settings 2.0) → F15 (light theme)
    → F10 (Linux) + F11 Bloques B/C/D (UI 2.0)
        → CA-M01..M06 (sprint medio: NeoForge/Quilt, modpack dep graph, perf dashboard)
            → CA-L01..L04 (largo plazo: multi-server, remote mgmt)
```

---

## F7: Server Templates + Modpacks — ✅ Completo

**Dependencia:** F8 (bulk mod ops) ✅ completo — reutiliza batch download infra.

| # | Tarea | LOC | Esfuerzo | Estado |
|---|-------|-----|----------|--------|
| 7.1 | Definir formato JSON template | doc | 30 min | ✅ |
| 7.2 | TemplateManager — save/load/list/delete | ~100 | 2 hrs | ✅ `app/services/template_manager.py` |
| 7.3 | Template selector en ServerWizard Step 2 | ~50 | 1 hr | ✅ |
| 7.4 | Save template desde Properties Editor / wizard footer | ~30 | 45 min | ✅ |
| 7.5 | Modpack support — auto-descargar mods de Modrinth | ~60 | 1.5 hrs | ✅ Implementado 2026-07-01 — `download_version_to()` + `install_mrpack()` reutilizado de CA-M04 |
| 7.6 | Templates por defecto (Lite SMP, Modded Fabric, Vanilla+, Paper Performance) | ~20 | 30 min | ✅ |
| 7.7 | Tests | ~80 | 1 hr | ✅ `tests/test_template_manager.py` |

---

## CA-HIGH: Competitive Analysis — ✅ Completo

**Origen:** Investigación comparativa vs auto-mcs (Python server manager) y Prism Launcher (Qt client launcher), 2026-06-23. ZBB lidera en auto-healing (zombie detection, exponential backoff, TPS lag monitor — nadie más lo tiene documentado).

| ID | Feature | Referencia | LOC est. | Esfuerzo | Estado |
|----|---------|-----------|----------|---------|--------|
| CA-H01 | JVM args expuestos por servidor (`-Xmx`/`-Xms` + flags custom) | Prism da este control por instancia | ~60 | 1.5 hrs | ✅ Implementado |
| CA-H02 | Player management unificado — operators+bans+whitelist en una página | auto-mcs patrón | ~80 | 2 hrs | ✅ Implementado 2026-07-06 — `player_files.py` + `PlayersDashboard` (CTkTabview) |
| CA-H03 | Console search/filter — keyword/level/player en raw output | ninguno lo tiene — oportunidad | ~40 | 1 hr | ✅ Implementado 2026-07-06 — `ConsoleWidget.highlight()` + search bar |
| CA-H04 | World switching UI — listar mundos, cambiar `level-name` sin editar server.properties a mano | auto-mcs lo tiene | ~60 | 1.5 hrs | ✅ Implementado 2026-07-06 — dropdown en Properties Editor World tab |

---

## CA-MED / CA-LONG (scope medio y largo plazo — sin iniciar)

| ID | Feature | Referencia | LOC est. |
|----|---------|-----------|----------|
| CA-M01 | NeoForge/Quilt support | auto-mcs | ~80 |
| CA-M02 | CurseForge integration (Modrinth solo hoy) | Prism | ~120 |
| CA-M03 | Mod dep graph + conflict detection | Prism | ~150 |
| CA-M04 | Modpack import `.mrpack` | ✅ Implementado (ver F7.5, MODS-B) | — |
| CA-M05 | Performance metrics dashboard (TPS+RAM histórico) — overlap con F11.D4, consolidar ahí | — | ~150 |
| CA-M06 | Version/modloader hot-switch sin crear server nuevo | auto-mcs | ~120 |
| CA-L01 | Multi-server management — mayor brecha vs auto-mcs, requiere refactor ZBBManager | auto-mcs | grande |
| CA-L02 | Server profiles/instances (prerrequisito de CA-L01) | Prism | — |
| CA-L03 | Remote management — REST API + cliente pareado (patrón Telepath), requiere F10 + headless mode | auto-mcs Telepath | — |
| CA-L04 | Spigot/CraftBukkit/Paper plugins (Hangar API client) | auto-mcs | — |

**Feature Matrix competitiva completa (ZBB vs auto-mcs vs Prism):** ver `docs/roadmap-history.md` si se necesita el detalle fila-por-fila; resumen: ZBB único en zombie detection, TPS lag monitor, crash backoff, bytecode analyzer. Brechas: multi-server, CurseForge, dep graph, world switching, console filter, headless/CLI.

---

## F9-F11: Migration, Linux, UI 2.0

### F9: Server Migration (.zbbpack) — ✅ Completo
| # | Tarea | Esfuerzo | Estado |
|---|-------|----------|--------|
| 9.1 | Export — ZIP con world + config + metadata (sin JAR, sin logs) | 2 hrs | ✅ `app/services/migration.py::export_server` (zip-slip guard) |
| 9.2 | Import — descomprimir, validar, recrear server | — | ✅ `migration.py::import_server` |
| 9.3 | UI — menú "Add Server" (Folder/.zbbpack) en main.py + export en Backups tab | — | ✅ |

### F10: Cross-Platform Linux
| # | Tarea | Riesgo |
|---|-------|--------|
| 10.2 | platform_utils.py — create_link(src, dst) unificado | 🟢 |
| 10.3 | SIGTERM handler en PlayitManager | 🟡 |
| 10.4 | stop() con wait(timeout=5) + kill() en Linux | 🟡 |
| 10.5 | single_instance.py verificar captura de SIGTERM | 🟢 |

### F11: UI/UX — ZBB 2.0 — "Dirt Block" Design Language

**Objetivo:** Modernizar UI con identidad visual Minecraft (tierra pixelada, verdes apagados, marrones slate).

**Bloque A (palette, botones, labels) — ✅ Implementado**, aplicado en todos los paneles (commit b5ca173). NR-DASH/01/02/09 resueltos (commit e37cc0a).

**Bloque B — Cambios visuales main.py, sin tocar lógica. Riesgo 🟢.**
| # | Tarea | Archivo | LOC | Esfuerzo |
|---|-------|---------|-----|---------|
| 11.B1 | Sidebar accent line — borde izquierdo 3px `COLOR_ACCENT_GREEN` en item seleccionado | ui_components.py | ~15 | 30 min |
| 11.B2 | Server list items como cards — fondo `COLOR_BG_CARD_DARK`, dot de estado, nombre bold, versión/tipo abajo, hover sutil | ui_components.py | ~40 | 1 hr |
| 11.B3 | Dashboard tunnel colapsado por defecto cuando offline | main.py | ~20 | 45 min |
| 11.B4 | Status bar topbar — fondo `COLOR_BG_CARD_DARK` diferenciado | main.py | ~10 | 20 min |

**Bloque C — Console coloring. Riesgo 🟡 (tocar ConsoleWidget).**
| # | Tarea | Archivo | LOC | Esfuerzo |
|---|-------|---------|-----|---------|
| 11.C1 | Syntax coloring básico — ERROR/WARN rojo/amarillo, joined/left verde/slate, [Server] azul | ui_components.py (ConsoleWidget) | ~40 | 1 hr |

**Bloque D — Rediseño mayor. Riesgo 🟠. Depende de A+B estables.**
| # | Tarea | Archivo | LOC | Esfuerzo |
|---|-------|---------|-----|---------|
| 11.D1 | ServerWizard rediseñado (pre-flight, progreso, resumen, templates, start now) | server_wizard.py | +150 | 3 hrs |
| 11.D2 | ServerPropertiesEditor rediseñado (4 tabs, SettingsField, inline validation) | server_properties_editor.py | +200 | 4 hrs |
| 11.D3 | Sidebar colapsable (toggle con animación simple) | main.py | ~60 | 1.5 hrs |
| 11.D4 | Performance dashboard visual (TPS graph, RAM usage) — consolida con CA-M05/F12.4 | main.py + nuevo archivo | +150 | 3 hrs |
| 11.D5 | Dark/light mode toggle persistido en settings — **consolidado en F15** (no duplicar trabajo aquí) | main.py + app_config.py | ~40 | 1 hr |
| 11.D6 | Tooltips en botones de acción | main.py | ~30 | 45 min |

**Orden recomendado:** 11.B4 → 11.B3 → 11.B1+B2 → 11.C1 → 11.D* (próxima iteración mayor)

**Criterio de aceptación global:**
- [ ] Server list items son cards con dot de estado
- [ ] Console colorea ERROR rojo, WARN amarillo, joins verde
- [ ] Dashboard tunnel colapsado cuando offline
- [ ] .exe compilado sin regresión visual en Windows

---

## F13-F15: Higiene de Disco, Settings 2.0, Light Theme

**Origen:** Auditoría de peso del proyecto 2026-07-07. `dist/` pesaba 750 MB; diagnóstico verificado: PyInstaller NO empaqueta los JDKs (spec solo incluye `assets/`; EXE real = 21 MB). El bloat era: (a) `dist/.zbb_cache/` 595 MB + `dist/servers/` 130 MB generados en **runtime** al correr el exe desde `dist/` (diseño portable: `BASE_DIR` frozen = carpeta del exe, `constants.py:46`); (b) `app/.zbb_cache/` 595 MB stale de código viejo — nada lo referencia (`JDK_CACHE_DIR` apunta a raíz); (c) `backups/` 282 MB sin visibilidad. Total ~1.8 GB de JDKs triplicados en disco. Git no afectado (`.zbb_cache/` y `dist/` ya en `.gitignore`).

### F13: Higiene de disco + JRE on-demand — 🥇 próxima prioridad

| # | Tarea | Archivo | Esfuerzo | Estado |
|---|-------|---------|----------|--------|
| 13.1 | Limpieza one-time: borrar `app/.zbb_cache/` (595 MB stale) + runtime dirs de `dist/` (~730 MB, se regeneran). `backups/` NO se toca (F14.4 dará control) | — | 10 min | ✅ 2026-07-07 — ~1.3 GB liberados |
| 13.2 | Descargar `image_type: "jre"` en vez de `"jdk"` (Adoptium), con fallback a `"jdk"` si no hay JRE para esa versión (ej. Java 16) — ~300 MB → ~45 MB por versión. Verificado: nada usa `javac`; `_find_java_binary` compatible con layout JRE; caches existentes siguen válidos | `services/java_installer.py:110` | 1.5 hrs | ✅ 2026-07-07 — `_query_assets` jre→jdk fallback (404/vacío) |
| 13.3 | Dev env: crear `.venv` del proyecto con las 5 deps + pytest/flake8/pyinstaller (hoy se usa Python global `C:\Python314` con ~180 paquetes de otros proyectos — NO podar el global) | — | 20 min | ✅ 2026-07-07 — `.venv` con 26 paquetes (vs ~180 global) |
| 13.4 | Tests: fallback jre→jdk, marker/checksum intactos | `tests/` | 45 min | ✅ 2026-07-07 — `TestJreFallback` 5 tests |

### F14: App Settings 2.0 — 🥇

**Base:** `app/ui/app_settings.py` (hoy: 1 sección webhook, 560x340). Rediseño con `CTkTabview` + `CTkScrollableFrame` (patrón ya probado en `server_properties_editor.py:126`), ventana ~720x520. Hallazgos que habilitan esto: `purge_cache(version)`/`purge_unused_jdks()` en `java_installer.py:266,298` son código muerto útil (nadie los llama); `java_detector.detect_all()` (PATH+JAVA_HOME+registro+well-known) sin UI; webhook con 4 eventos hardcoded (`discord_webhook.py:17-20`); keys huérfanas en `SettingsManager` (`servers_dir`, `java_preferences` — declaradas, nunca leídas); no existe `APP_VERSION` en ninguna parte.

| # | Tarea | Archivo | Esfuerzo | Estado |
|---|-------|---------|----------|--------|
| 14.1 | Refactor dialog a CTkTabview (General/Notifications/Java/Storage/About) | `ui/app_settings.py` | 2 hrs | ✅ 2026-07-07 |
| 14.2 | Tab General: selector tema Dark/Light/System (Light deshabilitado hasta F15; infra ya existe: `main.py:50-51` lee `theme` al arrancar) + limpiar keys muertas de `SettingsManager` | `ui/app_settings.py`, `services/settings_manager.py` | 1 hr | ✅ 2026-07-07 |
| 14.3 | Tab Notifications: webhook actual + checkboxes por evento (crash/ready/backup ok/backup fail) filtrando `EVENT_STYLES` vía settings | `ui/app_settings.py`, `services/discord_webhook.py` | 1.5 hrs | ✅ 2026-07-07 |
| 14.4 | Tab Java: (a) JDKs gestionados — versión + tamaño en disco + delete por versión + "Purge unused" (conecta `purge_cache`/`purge_unused_jdks` vía método nuevo en ZBBManager, arquitectura EventBus respetada); (b) tabla read-only de Javas detectados en el sistema (`detect_all()`: versión/ruta/origen). Bloqueado con server corriendo (patrón restart-required) | `ui/app_settings.py`, `core/core.py` | 2.5 hrs | ✅ 2026-07-07 |
| 14.5 | Tab Storage: resumen de disco por categoría — servers, backups (total + por server), JDK cache, crash reports, versions cache — con botones de limpieza donde aplica | `ui/app_settings.py` | 2 hrs | ✅ 2026-07-07 |
| 14.6 | Tab About: nueva constante `APP_VERSION` en `app_config.py`, mostrada en dialog + título de ventana. Base futura para update-check | `core/app_config.py`, `ui/app_settings.py`, `ui/main.py` | 45 min | ✅ 2026-07-07 |
| 14.7 | Tests: filtro eventos webhook, purge vía ZBBManager, settings keys | `tests/` | 1.5 hrs | ✅ 2026-07-07 |

### F15: Light theme completo — 🥈 (consolida F11.D5)

**Estado actual medido:** ~63 usos de color en `app/ui/` ya usan tuplas `(light, dark)`, pero ~104 usan tokens single-color dark-only (ej. `COLOR_TEXT_PRIMARY = "#f1f5f9"`). En light mode hoy la app se ve rota a medias. La mayoría referencia tokens de `AppConfig` → convertir tokens a tuplas arregla casi todo centralmente. `icon()` ya acepta tuplas (`main.py:453`).

| # | Tarea | Archivo | Esfuerzo | Estado |
|---|-------|---------|----------|--------|
| 15.1 | Convertir tokens single-color de `AppConfig` a tuplas `(light, dark)` | `core/app_config.py` | 2 hrs | ⬜ |
| 15.2 | Barrido de consumidores no-CTk que no aceptan tuplas: consola (tags), PIL/icons con color string, toasts | `ui/*.py` (~7 archivos) | 2 hrs | ⬜ |
| 15.3 | Sincronizar `assets/zbb_theme.json` con tokens light | `assets/zbb_theme.json` | 1 hr | ⬜ |
| 15.4 | Habilitar Light/System en Tab General (F14.2): `ctk.set_appearance_mode()` en vivo + persistir. Cierra F11.D5 | `ui/app_settings.py` | 30 min | ⬜ |
| 15.5 | QA visual completa en ambos modos (todos los diálogos/tabs) | — | 1.5 hrs | ⬜ |

### Descartados por scope (2026-07-07 — reconsiderar después de F15)

| Idea | Por qué se descartó | Cuándo reconsiderar |
|------|--------------------|--------------------|
| Idioma / i18n | Sin infra de strings; barrido masivo de UI | Post-F11.D, si hay demanda |
| System tray (minimizar a bandeja) | Dependencia nueva (pystray) + edge cases Win | Post-F10 |
| Auto-update real (descargar exe nuevo) | Requiere releases firmados + canal estable; hoy pre-alpha | Cuando haya releases en GitHub; F14.6 (`APP_VERSION`) es el prerrequisito |
| Defaults globales para wizard (RAM, aikars) | El wizard ya resuelve por server; valor marginal | Si usuarios crean muchos servers |
| jlink custom runtime | Complejidad alta sin ganancia extra vs JRE Adoptium (F13.2) | No planeado |
| Excluir `servers/` del spec PyInstaller | Innecesario — nunca se empaquetó (diagnóstico erróneo del análisis original) | N/A |

---

## F12: Feature Gaps (vs. competencia)

**Origen:** Brechas identificadas 2026-07-04, sin trabajo iniciado.

| # | Feature | Prioridad | Notas |
|---|---------|-----------|-------|
| 12.1 | Multi-server dashboard | 🔴 Alta | Brecha crítica — mismo scope que CA-L01 |
| 12.2 | World switching | — | ✅ Resuelto vía CA-H04 (2026-07-06) |
| 12.3 | Console filter/search | — | ✅ Resuelto vía CA-H03 (2026-07-06) |
| 12.4 | Performance dashboard visual | 🟡 Media | Overlap con F11.D4 y CA-M05 — consolidar ahí, no duplicar trabajo |

---

## Pendientes on-radar (bajo impacto, oportunísticos)

Solo abordar si se toca el archivo relevante por otra razón — no priorizar activamente:

| ID | Archivo | Problema | Fix |
|----|---------|---------|-----|
| A3-B05 | `core/playit_manager.py:522` | `_parse_line` chequea `self._api_dns or self._stdout_dns` fuera del lock — posible doble-emit TUNNEL_STATUS bajo concurrencia | Mover early-return check dentro del lock |
| A3-A04 | `core/core.py:104-259` | 4 inline imports de `update_server_meta`/`SERVERS_DIR` (workarounds circular dep) en `_save_jdk_metadata`, `select_server`, `_resolve_java_bin`, `load_server_manually` | Mover imports al top cuando se toque core.py por otra razón |
| LA-06 | `core/logic.py:736-740` | `get_server_ram`/`set_server_ram` thin wrappers | Confirmado usado por SPE — no es dead code, no tocar |
| NR-05 | `ui/modrinth_browser.py` (`_load_popular_mods`) | Sin feedback si no hay internet | Label "No internet connection" + botón Retry |
| NR-10 | `ui/modrinth_browser.py` | Constantes locales `_CARD_BG_DARK` etc. duplican AppConfig | Reemplazar con `AppConfig.COLOR_BG_CARD_DARK` etc. — verificar si sigue pendiente |
| A2-A02 | `core/java_detector.py` | `_probe_java` privado importado desde logic.py — acoplamiento frágil | Exponer como función pública (puede ya estar resuelto vía A3-A02, verificar) |
| A2-P03 | `services/java_detector.py` | `_shared_cache` class-level sin TTL — no detecta Java instalado con app abierta | TTL de 60-300s o método invalidate() |

---

## Notas para Devs y Agentes

### Reglas de Oro
1. **Sin sobreingeniería**: Si se puede hacer con 3 funciones, no se necesita una clase
2. **483 tests deben pasar siempre**: `python -m pytest tests/ -q` antes de cada commit
3. **Cross-platform**: `sys.platform == "win32"` y `platform.system()` guards obligatorios
4. **Sin merge commits**: Solo fast-forward o squash merges
5. **Commits atómicos**: Un commit = un cambio lógico completo

### Dependencias Circulares Conocidas
- `core.py` ↔ `orchestrators.py` — resuelto en P0.5, no reintroducir

### Eventos Huérfanos (no suscritos)
- `ServerEvent.RESTARTED` — sin subscriber (emitido, nunca consumido — hook futuro)

### Errores Comunes a Evitar
1. No usar `bare except:` — siempre especificar excepción
2. No hardcodear `C:\` paths — usar `platform.system()` guards
3. No usar `shell=True` en subprocess — siempre pasar lista de args
4. No importar dentro de funciones para evitar circulares — mejor mover el enum a constants.py
5. No crear threads para I/O rápido (<50ms) — el overhead del thread es mayor
6. Todo `open()` lleva `encoding="utf-8"` — Windows con locale no-UTF8 corrompe MOTDs con `§`
7. `strptime` sobre nombres de archivo del usuario: siempre `try/except ValueError`
8. NOTIFICATION payload: siempre `{"msg": ..., "type": "error"|"warning"|"info"}` — nunca `color` key
9. Watchdog NO emite `NOTIFICATION` — solo `_on_server_crashed` en core.py es dueño de notificaciones de crash
10. Installers (Fabric/Forge): pasar el JDK resuelto por ZBB, nunca asumir `"java"` del sistema

### Testing
```powershell
python -m pytest tests/ -v           # Full suite (483 tests)
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
