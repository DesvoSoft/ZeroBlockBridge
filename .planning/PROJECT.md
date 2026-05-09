# ZeroBlockBridge

## What This Is

ZeroBlockBridge (ZBB) es un gestor de servidores Minecraft de escritorio que permite crear, administrar y compartir servidores sin configuración compleja ni port forwarding. Construido con Python y CustomTkinter, está diseñado para jugadores que quieren hostear servidores para su comunidad de forma sencilla.

## Core Value

Los usuarios pueden crear, iniciar y compartir un servidor Minecraft con amigos en menos de 5 minutos, sin conocimientos técnicos ni configuración de red.

## Requirements

### Validated

<!-- Shipped and confirmed valuable in existing codebase. -->

- ✓ Server creation wizard (Vanilla/Fabric/Forge) — existing
- ✓ Server process management (start/stop/restart) — existing
- ✓ Playit.gg tunnel integration — existing
- ✓ Server properties editor (6 tabs) — existing
- ✓ Backup/restore system (ZIP format) — existing
- ✓ Auto-restart scheduler (interval & daily time) — existing
- ✓ Version fetching/caching (Mojang, Fabric, Forge APIs) — existing
- ✓ Console command sending — existing
- ✓ Server icon upload — existing
- ✓ RAM allocation configuration — existing
- ✓ Sound notifications — existing
- ✓ Dark theme UI — existing
- ✓ In-game restart warnings and countdown — existing

### Active

<!-- Current scope. Building toward these. -->

- [ ] **AUTO-01**: Watchdog service detects Java process crashes (OOM, exit_code != 0) and auto-restarts with configurable max retries (default 3)
- [ ] **AUTO-02**: Command validation layer prevents dangerous/malformed commands from reaching server stdin
- [ ] **AUTO-03**: Lag detection monitors console for "Can't keep up!" patterns with configurable restart thresholds
- [ ] **ARCH-01**: Extract server lifecycle management from main.py into dedicated service classes
- [ ] **ARCH-02**: Implement typed event system (ServerCrashed, PlayerJoined, ServerReady, etc.) decoupling UI from logic
- [ ] **ARCH-03**: Circular buffer console (FIFO) prevents memory growth during long sessions
- [ ] **ECO-01**: Add Paper server type support with dynamic version resolution
- [ ] **ECO-02**: Add Purpur server type support
- [ ] **ECO-03**: Modrinth integration for mod search, install, and updates
- [ ] **PROV-01**: Java version detection and automatic suggestion per Minecraft version
- [ ] **PROV-02**: Server directory scaffolding (pre-generate eula.txt, start scripts, metadata)
- [ ] **PROV-03**: Analyze auto-mcs Spigot/Bukkit build-tools approach and decide ZBB strategy

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- **Remote access API (Telepath)** — Alta complejidad, requiere seguridad de red. No necesario para la experiencia local.
- **Headless/CLI mode** — Depende de ARCH-01/ARCH-02. Postergado hasta después de la modularización.
- **macOS support** — Sin entorno de pruebas ni demanda actual.
- **Docker support** — Complejidad adicional sin caso de uso claro para la base de usuarios actual.
- **ACL/player management UI** — El watchdog service incluye validación de comandos, pero la gestión completa de operadores/baneos queda para una fase posterior.
- **Spigot/CraftBukkit build-tools compilation** — Analizar pero probablemente limitarse a binarios precompilados (Paper/Purpur) para ahorrar recursos del host.

## Context

ZBB es un proyecto brownfield (~3,160 líneas Python, 11 archivos en `app/`). El codebase actual es monolítico: `app/main.py` (700 líneas) mezcla controlador y vista. El archivo de referencia es auto-mcs (v2.3.8, ~45K LOC), un proyecto maduro con 6+ años de desarrollo del cual extraer patrones.

El análisis de brechas (`.planning/codebase/CONCERNS.md`) identificó 18 carencias. Este proyecto prioriza:
1. **Auto-Healing** — La carencia crítica #2 (Error Handling)
2. **Arquitectura** — Paso necesario para escalar sin espagueti
3. **Ecosistema** — Competitividad frente a alternativas

## Constraints

- **Tech Stack**: Python 3.10+, CustomTkinter (sin cambiar UI framework)
- **Performance**: El watchdog debe ser "zero-impact" (sin polling constante, basado en eventos)
- **Compatibility**: Debe seguir funcionando en Windows 10/11 y Linux
- **Dependency**: La modularización (ARCH-*) es prerequisito para el headless/CLI futuro
- **Security**: La validación de comandos debe implementarse desde la fase inicial de auto-healing

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Watchdog basado en eventos (no polling) | exit_code del proceso Java + parser de consola | — Pending |
| Auto-restart con máximo 3 intentos | Evita bucles infinitos en crashes persistentes | — Pending |
| Evolución: monolitos → servicios (no reescritura) | Menor riesgo, entrega incremental de valor | — Pending |
| Paper/Purpur como prioridad de ecosistema | Estándar de la comunidad para servidores con plugins | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-08 after initialization*
