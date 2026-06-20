# ZeroBlockBridge — Handover Note

**Fecha:** 2026-06-20  
**Branch activo:** `dev` (sin push a origin todavía)  
**Tests:** 364/364 pasando, 0 flaky  

---

## Qué se hizo esta sesión

### EXE-PERF — Todos resueltos (4 commits)

| Commit | Fix |
|--------|-----|
| `026d13e` | `on_close` no bloquea mainloop; shutdown en thread; executor UI cancelado; huérfanos killed; eliminado `sys.exit(0)` (EXE-02/03/05/06) |
| `4bfefe8` | `executor.shutdown(cancel_futures=True)` — sin loop sobre `_threads` privado (EXE-01) |
| `2fee336` | Watchdog silenciado ANTES de `runner.stop()` — fix HA-03 |
| `61a103a` | `VersionManager.__init__` lazy — sin disco/red en init (EXE-04) |
| `e683436` | roadmap actualizado |

**Comportamiento nuevo de `on_close`:**
1. `withdraw()` — ventana desaparece al instante
2. `executor.shutdown(cancel_futures=True)` — cancela tasks UI pendientes
3. `_do_shutdown()` en thread separado — llama `zbb_manager.shutdown()`, luego `_kill_orphan_processes()`
4. `_poll_shutdown()` via `after(100)` — mainloop sigue vivo, `destroy()` cuando shutdown termina (timeout 8s)

---

## Próximos fixes — orden recomendado

### 1. CA-02 🔴 — Fabric/Forge installer usa `"java"` hardcoded

**Archivo:** `app/core/logic.py` → `_run_installer()`  
**Problema:** Usa `"java"` literal, no el JDK resuelto por ZBB. Si el usuario no tiene Java en PATH (caso común con auto-JDK), el installer falla.  
**Fix:** Pasar `java_bin` como parámetro desde `ServerOrchestrator.start_server()` donde ya está resuelto.

### 2. MA-02 🟡 — `open()` sin `encoding="utf-8"` en logic.py

**Archivo:** `app/core/logic.py` — múltiples `open()` sin encoding  
**Problema:** En Windows con locale non-UTF8, corrompe MOTDs con `§` (colores Minecraft).  
**Fix:** Agregar `encoding="utf-8"` a todos los `open()` en `logic.py` (y verificar `settings_manager.py`).

### 3. HA-05 🟡 — Race condition en `_do_restart` del Watchdog

**Archivo:** `app/services/watchdog.py:134-135`  
**Problema:** Chequea `self._runner.running` sin lock entre el check y el `start()`. Puede causar doble-start.  
**Fix:** Usar `threading.Lock` o `threading.Event` para serializar el restart.

### 4. HA-06 🟡 — `connected_players` stale después de restart

**Problema:** Dict de jugadores no se limpia en restart — dashboard muestra jugadores fantasma.  
**Fix:** Emitir `PLAYER_COUNT` con lista vacía al emitir `STOPPED`.

### 5. MA-05 🟡 — Restart scheduler silenciosamente skippeado si >120s tarde

**Problema:** Si el sistema estuvo suspendido o tick loop se atrasó, restart programado se pierde sin log ni notificación.  
**Fix:** En `SchedulerOrchestrator`, si `is_due` y `remaining < -120`, emitir NOTIFICATION de warning antes de ejecutar.

### 6. MA-03 🟡 — `save_automation()` al abrir pestaña Automation

**Problema:** Escribe a disco en cada `tab_changed` aunque el usuario no tocó nada.  
**Fix:** Solo guardar si hubo cambio real (dirty flag o comparar valores antes de save).

### 7. LA-02 🔵 — `_jar_ready_events` dict nunca se limpia (logic.py)

**Problema:** Leak menor — crece unbounded si el usuario crea muchos servidores en sesión larga.  
**Fix:** Limpiar la key después de `wait_for_jar_ready()`.

---

## Estado BUG-AUDIT (2026-06-19)

| Severidad | Total | Resueltos | Pendientes |
|-----------|-------|-----------|-----------|
| 🔴 CRITICAL | 2 | 1 | 1 (CA-02) |
| 🟡 HIGH | 6 | 3 | 3 (HA-05, HA-06 + 1 prev) |
| 🟡 MEDIUM | 5 | 2 | 3 (MA-02, MA-03, MA-05) |
| 🔵 LOW | 6 | 0 | 6 (LA-01 a LA-06) |
| **TOTAL** | **19** | **6** | **13** |

---

## Estado general del proyecto

- `dev` branch está limpio, no hay uncommitted changes
- `dev` NO está pusheado a origin (decisión del usuario)
- `site` branch pusheado a GitHub (GitHub Pages)
- `main` = release 1.4 — próximo merge cuando dev esté listo
- Pendiente de P0 Foundation Hardening (ver roadmap) antes de merge a main
- CA-02 es bloqueante para release si el target audience usa Fabric/Forge
