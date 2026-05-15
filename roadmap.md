# ZeroBlockBridge — Roadmap de Desarrollo

## Contenido
- [Fase 1: Playit.gg — Estabilización y Fiabilidad](#-fase-1-playitgg--estabilización-y-fiabilidad)
- [Fase 2: JDK Auto-Installer](#-fase-2-jdk-auto-installer)
- [Fase 3: Mod Ecosystem — Event-Driven](#-fase-3-mod-ecosystem--event-driven)
- [Auditoría Técnica (Completada)](#-auditoría-técnica-completada)

---

## 🔴 Fase 1: Playit.gg — Estabilización y Fiabilidad

### 1A. Versión del Protocolo (Obsolescencia)
**Contexto**: `playit_api.py:link_account()` usa version_hardcodeada `0.17.1`. La versión actual del protocolo es `0.20.1`. La 0.17.x puede causar errores de autenticación o inestabilidad en el túnel.

- [x] **`playit_api.py:link_account()`** — Actualizar `version_major=0`, `version_minor=20`, `version_patch=1` ✅
- [x] **`constants.py:PLAYIT_VERSION`** — Actualizar de `"0.16.5"` a `"0.20.1"` (versión del binario) ✅
- [x] **`playit_api.py:delete_agent()`** — Limpiar bucle `for key in ["id", "agent_id", "agent-id"]` y usar solo el campo estándar de la v2 ✅
- [x] **`playit_manager.py`** — Verificar compatibilidad del flag `--secret_path` con binario 0.20.1 ✅

### 1B. Monitoreo Frágil (Reemplazar stdout por API Local)
**Contexto**: `PlayitManager._parse_line()` depende de 4 patrones Regex sobre la salida stdout del binario. Si el binario cambia un espacio o palabra, el túnel aparece como "Desconectado" aunque funcione.

- [x] **`playit_manager.py`** — Crear `get_local_status()` que consulte `http://127.0.0.1:25374/status` (JSON-RPC local) ✅
- [x] **`playit_manager.py`** — Implementar polling loop (ej. cada 5s) que consulte el puerto local en vez de depender del stdout ✅
- [x] **`playit_manager.py:_parse_line()`** — Reducir/eliminar dependencia de Regex; usar `get_local_status()` como source of truth ✅
- [x] **`playit_manager.py`** — Emitir `TUNNEL_STATUS` basado en respuesta JSON-RPC (estado, IP, DNS) en lugar de stdout ✅
- [x] **`playit_manager.py`** — Agregar fallback: si JSON-RPC no responde, usar stdout como respaldo ✅

### 1C. Reset No Destructivo (Evitar AgentDisabledOverLimit)
**Contexto**: `reset()` borra `playit.toml` e intenta borrar el agente remoto. Si el usuario resetea muchas veces, llega al límite de agentes de la cuenta gratuita.

- [x] **`playit_manager.py:reset()`** — Cambiar lógica: primero intentar "reclamar" el agente existente verificando la validez de `secret_key` ✅
- [x] **`playit_manager.py:reset()`** — Solo borrar `playit.toml` si la `secret_key` es inválida/vencida ✅
- [x] **`playit_manager.py`** — Agregar opción `reuse_agent` al flujo de reset: mantener mismo agent_id y solo regenerar tunnels ✅
- [x] **`playit_api.py`** — Agregar `verify_secret_key()` que haga un ping a la API para validar la llave sin crear agentes duplicados ✅

### 1D. Seguridad de Archivos (Permisos)
**Contexto**: `playit.toml` se crea con permisos por defecto (legible por otros usuarios del sistema en Linux/Mac).

- [x] **`playit_api.py:link_account()`** — Después de escribir `playit.toml`, ejecutar `os.chmod(toml_path, 0o600)` en Unix ✅
- [x] **`playit_manager.py`** — Al detectar `playit.toml` existente, verificar permisos y corregirlos si es necesario ✅

### 1E. Flag `--secret` en subprocess
**Contexto**: Al lanzar el binario con `subprocess.Popen`, no se usa `--secret` para pasar la llave directa, solo `--secret_path`.

- [x] **`playit_manager.py:_start_internal()`** — Agregar flag `--secret <secret_key>` al comando para evitar que el binario cree agentes "invitados" (Guest Mode) si el toml no se lee correctamente ✅

### 1F. Nuevas Funcionalidades (Proxy Protocol, IPv4, Heartbeat)
- [x] **`playit_api.py:create_tunnel()`** — Agregar parámetro opcional `proxy_protocol: bool = False` para activar Proxy Protocol V2 ✅
- [x] **`playit_manager.py:_start_internal()`** — Agregar flag `--network ipv4` para forzar IPv4 en conexiones problemáticas ✅
- [x] **`playit_manager.py`** — Implementar `_heartbeat_loop()` que haga ping periódico al proceso playit (verificar que no sea zombie) ✅
- [x] **`playit_manager.py`** — Si el heartbeat falla N veces seguidas, reiniciar el agente ✅

---

## 🟡 Fase 2: JDK Auto-Installer

**Archivo**: `app/services/java_installer.py` — ✅ Implementado (Fase 1)

### Integración en Core
- [x] **`core.py:start_server()`** — Fallback chain en 3 escenarios: sin Java, >21 experimental, < required ✅
- [x] **`core.py:start_server()`** — Manejar `JdkDownloadError` → `ServerEvent.NOTIFICATION` tipo "error" ✅
- [x] **`core.py`** — Cachear `required_java` en `metadata.json` con `jdk_source: "portable"` post-descarga ✅
- [x] **`main.py`** — Indicador visual en status bar si se está usando JDK portable vs system Java ✅
- [x] **`ServerWizard`** — Agregar flag opcional "Auto-install JDK if missing" (default: true) ✅

### Post-Instalación
- [x] **`java_installer.py`** — Agregar `purge_unused_jdks()` para limpiar JDKs no referenciados por ningún servidor ✅
- [x] **`constants.py`** — Agregar `JDK_CACHE_DIR = BASE_DIR / ".zbb_cache" / "jdks"` ✅

---

## 🟢 Fase 2b: Compatibilidad Linux (Debian-Ready)

### 2b.1 Abstracción de "Open Folder"
**Contexto**: `main.py` y `server_properties_editor.py` tienen lógica duplicada de `os.startfile`/`xdg-open` esparcida en 4 lugares.

- [ ] **`services/platform_utils.py` (nuevo)** — Crear `open_directory(path)` que unifique:
      - `sys.platform == "win32"` → `os.startfile(path)`
      - `sys.platform == "darwin"` → `subprocess.run(["open", path])`
      - default → `subprocess.run(["xdg-open", path])`
- [ ] **`main.py`** — Reemplazar 3 ocurrencias de `os.startfile`/`xdg-open` por `platform_utils.open_directory()`
- [ ] **`server_properties_editor.py:657`** — Reemplazar `os.startfile` por `platform_utils.open_directory()`

### 2b.2 Universal Symlinks (Reemplazar `_winapi`)
**Contexto**: `main.py:517` y `core.py:369` usan `_winapi.CreateJunction`, que solo existe en Windows. En Linux/Mac se necesita `os.symlink`.

- [ ] **`services/platform_utils.py`** — Crear `create_link(src, dst, is_directory=False)`:
      - Windows → `_winapi.CreateJunction(src, dst)` (si es directorio) o `os.symlink`
      - Linux/Mac → `os.symlink(src, dst)`
- [ ] **`main.py:517`** — Reemplazar `import _winapi; _winapi.CreateJunction(...)` por `platform_utils.create_link()`
- [ ] **`core.py:369`** — Reemplazar `import _winapi; _winapi.CreateJunction(...)` por `platform_utils.create_link()`

### 2b.3 Manejo de Señales (SIGTERM en Linux)
**Contexto**: En Linux, `subprocess.Popen` no recibe SIGTERM automáticamente. Si el proceso padre muere, el agente Playit puede quedar zombie.

- [ ] **`playit_manager.py`** — Registrar `signal.signal(signal.SIGTERM, handler)` que ejecute `self.stop()` limpiamente
- [ ] **`playit_manager.py:stop()`** — Asegurar que `process.terminate()` → `process.wait(timeout=5)` → `process.kill()` funcione en Linux (SIGTERM → SIGKILL)
- [ ] **`core.py`** — Propagar `SIGTERM` a procesos hijo vía `preexec_fn=os.setpgrp` en Linux para kills en grupo
- [ ] **`single_instance.py`** — Verificar que `atexit.register` capture `SIGTERM` además de `sys.exit()` normal

---

## 🟠 Fase 3: Mod Ecosystem — Event-Driven

### Evento INSTALL_REQUEST
- [ ] `server_events.py` — Agregar `INSTALL_REQUEST = "install_request"`
- [ ] Payload: `{"server_name", "mod_slug", "mc_version", "loader", "project_type"}`

### Scaffolder como gestor de descargas
- [ ] `scaffolder.py` — Nueva función `handle_install_request(data)`:
      - Escuchar `ServerEvent.INSTALL_REQUEST`
      - Ejecutar descarga en hilo separado (daemon)
      - Reportar progreso vía `ServerEvent.CONSOLE_LINE` + `ServerEvent.NOTIFICATION`
      - Delegar a `ModrinthClient.download_mod()` internamente
- [ ] `scaffolder.py` — Suscribirse al EventBus en `core.py`

### UI desacoplada
- [ ] `modrinth_browser.py:_on_install()` — Reemplazar llamada directa a `provider.download_mod()` por `events.emit(ServerEvent.INSTALL_REQUEST, {...})`
- [ ] `modrinth_browser.py` — Remover import de `ModProvider` (ya no necesario en UI)
- [ ] `modrinth_browser.py` — Escuchar `ServerEvent.CONSOLE_LINE` para feedback de instalación en status bar

### Resolución de Dependencias
- [ ] `scaffolder.py` — `_resolve_dependencies(slug, mc_version, loader)` con API Modrinth
- [ ] `scaffolder.py` — `_install_with_deps()` con orden topológico (máx profundidad 3)

### Optimizer Bundle Event-Driven
- [ ] `server_events.py` — Agregar `INSTALL_OPTIMIZERS = "install_optimizers"`
- [ ] `scaffolder.py` — Mover lógica de `ModProvider.install_optimizer_bundle()` a scaffolder
- [ ] `modrinth_browser.py:_on_install_optimizers()` — Emitir `INSTALL_OPTIMIZERS` en vez de llamar a `provider` directamente

---

## ✅ Auditoría Técnica (Completada)

### Código Muerto Residual
- [x] `main.py:247-345` — Eliminar `_build_management_controls` (~100 líneas) ✅
- [x] `main.py:599` — Eliminar stub `save_scheduler_dashboard` ✅
- [x] `main.py:602` — Eliminar stub `quick_backup_action` ✅
- [x] Adicional: `main.py:426-436` — `toggle_schedule_mode` ✅
- [x] Adicional: `main.py:437-470` — `_format_time_input` ✅

### UI: corner_radius Neo-Modern (estándar = 12)
- [x] `main.py` — Corregido ✅
- [x] `ui_components.py` — Corregido ✅
- [x] `server_properties_editor.py` — Corregido ✅
- [x] `modrinth_browser.py` — Corregido ✅

### Limpieza de Sonidos
- [x] `app/services/audio.py` — Eliminado (31 líneas) ✅
- [x] `main.py` — Eliminado `play_notification_sound` + caller ✅
- [x] `assets/notification.wav` — Eliminado ✅

### Estándares
- [x] `core.py` — Emojis `✓` `✗` reemplazados por `OK` `ERROR` ✅
- [x] `tests/test_java_installer.py` — 28 tests creados ✅

---

## 📦 Resumen de Fases

| Fase | Archivos | Tests | Estado |
|---|---|---|---|
| **F1: Playit.gg** | `playit_api.py`, `playit_manager.py`, `constants.py` | Actualizar tests existentes | ✅ Completa |
| **F2: JDK Core** | `core.py`, `java_installer.py`, `main.py`, `server_wizard.py`, `constants.py` | 28 tests existentes | ✅ Completa |
| **F2b: Linux Compat** | `platform_utils.py`, `main.py`, `core.py`, `playit_manager.py`, `single_instance.py` | — | ❌ |
| **F3a: Evento Mod** | `server_events.py`, `scaffolder.py`, `modrinth_browser.py` | `test_install_request_event` | ❌ |
| **F3b: Dependencias** | `scaffolder.py`, `modrinth.py` | `test_dependency_resolution` | ❌ |
| **Auditoría** | múltiples | regression 188 tests | ✅ Completa |

## 🧹 Fase 1G: Simplificación de PlayitManager

**Contexto**: Tras restaurar `create_tunnel()` vía REST API, gran parte del código de `playit_manager.py` quedó muerto o redundante (<code>_inject_toml_mapping</code>, <code>get_local_status</code>, <code>_status_polling_loop</code>, <code>_dns_polling_loop</code>, <code>_restart_with_mapping</code>). También hay polling loops obsoletos y lógica de stdout que ya no se necesita.

**Branch**: `simplify-playit-manager` (desde `dev`)

- [x] Eliminar código muerto: `_inject_toml_mapping`, `get_local_status`, `_handle_local_status`, `_status_polling_loop`, `_dns_polling_loop`, `_restart_with_mapping` ✅
- [x] Simplificar `_parse_line`: inline solo `AgentDisabledOverLimit` en `_read_output` ✅
- [x] Simplificar `_read_output`: quitar `_parse_line()`, mantener solo filtro spam + log ✅
- [x] Reducir threads en `_start_internal`: solo `_read_output` + `_heartbeat_loop` ✅
- [x] Simplificar `_heartbeat_loop`: restart directo vía `self.start()` en vez de `_restart_with_mapping` ✅
- [x] Correr tests (200/200 pasan) ✅
- [ ] Merge a `dev`

---

**Prioridad**: F1 (Playit.gg — estabilidad) → F1G (Simplificación) → F2 (JDK) → F3a (Evento Mod) → F3b (Dependencias)
