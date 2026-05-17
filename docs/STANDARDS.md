# ZeroBlockBridge (ZBB) - Master Technical Standards

This document defines the technical identity, architectural philosophy, and coding standards for the ZeroBlockBridge project. All contributors (Human or AI) must adhere to these rules to ensure the maintainability and scalability of the platform.

---

## 1. Architectural Philosophy: Event-Driven & Decoupled
ZBB is built on a strict **decoupled architecture** to ensure the core logic can run independently of any specific interface.

*   **Model-View-Controller (MVC) Hybrid**: The UI (`app/ui/main.py`) must never contain business logic. It serves only as a visual shell.
*   **Event-Driven Communication**: All communication between the UI and the Core (`app/core/core.py`) must occur through the `EventBus`. Prohibir explícitamente el uso de `.on()` en favor de `.subscribe()`.
*   **Headless-Ready**: Every feature must be implemented such that it could function via a CLI or REST API without a GUI. 
*   **Single Source of Truth**: `ZBBManager` is the orchestrator. No other component should directly manage server lifecycles or global configurations.
*   **Platform Neutrality**: Queda prohibido el uso de `os.startfile` y `_winapi` en el núcleo. Toda interacción con el sistema operativo debe usar abstracciones que detecten `sys.platform`. Las rutas se construyen exclusivamente con `pathlib.Path` para garantizar compatibilidad entre Windows y Linux.

### Code Example: Emitting Events
```python
# In Core/Service
self.events.emit(ServerEvent.STATUS_CHANGED, {"server": name, "status": "running"})

# In UI (Subscription)
self.events.subscribe(ServerEvent.STATUS_CHANGED, self._update_ui_status)
```

---

## 2. Concurrency Standards
ZBB is a multi-threaded application handling multiple server processes and network monitors.

*   **Thread Safety**: Use `threading.RLock` for all shared state access (e.g., in `EventBus` or `CircularBuffer`).
*   **Daemon Threads**: All background threads (monitors, listeners, API pollers) **must** be initialized with `daemon=True` to ensure the application exits cleanly.
*   **Non-Blocking UI**: Never perform I/O, heavy computation, or network requests on the main thread. Use `threading.Thread` for these tasks.
*   **Race Condition Prevention**: Always use context managers (`with self._lock:`) when accessing shared resources.
*   **Protocolo de Sincronía "Atomic-First" (Bytecode & IO)**:
    *   **Integridad de Archivos**: Antes de invocar cualquier analizador de archivos (Bytecode, Logs, Configs), es OBLIGATORIO realizar un bucle de verificación de existencia en disco (`os.path.exists`) y tamaño (`os.path.getsize > 0`) con un timeout de 5s. Los eventos de hilos no son suficientes para garantizar que el SO ha liberado el archivo.

---

## 3. Logging Protocol (CONV-01)
The use of `print()` is strictly prohibited in the production codebase.

*   **Logger Initialization**: Every module must initialize its own logger: `logger = logging.getLogger(__name__)`.
*   **Standard Prefixes**: Logs should follow the format: `[LEVEL] [Module] Message`.
*   **Prohibition of Emojis**: Do not use emojis in logging strings. Keep it technical and clean.
*   **Log Levels**:
    *   `DEBUG`: Detailed diagnostic information.
    *   `INFO`: General confirmation of application milestones.
    *   `WARNING`: Recoverable issues or unexpected behavior.
    *   `ERROR`: Non-recoverable failures that require attention.

### 3a. Silent Failure Prevention (No-Silent Failures)
Queda **estrictamente prohibido** el uso de `except: pass`.

**Requisitos obligatorios para todo bloque `except`:**
1. La excepción capturada debe ser lo más específica posible (`ValueError`, `OSError`, `requests.ConnectionError`, etc.).
2. Antes de cualquier retorno por defecto, se debe llamar a `logger.exception()` o `logger.warning()` con un mensaje que describa el contexto del fallo.
3. Excepciones admitidas (con justificación documentada): operaciones de limpieza en destructores o cierres donde el error no afecta al estado del programa.

```python
# Correcto
try:
    data = json.loads(raw)
except json.JSONDecodeError as e:
    logger.exception("Failed to parse server metadata: %s", e)
    data = {}

# Incorrecto
try:
    data = json.loads(raw)
except:
    pass
```

---

## 4. Aesthetics & UI: Neo-Modern Brand Book
The ZBB interface follows a **Neo-Modern** aesthetic designed to feel premium and state-of-the-art.

*   **Corner Radius (Regla del 12)**: Un `corner_radius=12` uniforme es **obligatorio** para todos los frames, botones y campos de entrada (excepto Toasts y alertas modales que usan `corner_radius=0` por diseño cuadrado). Esta es una métrica de certificación visual: cualquier componente con un valor distinto (sin excepción documentada) se considera una regression.
*   **Color Palette**: Use **Slate**-based palettes for both Dark and Light modes to avoid high-contrast fatigue.
*   **Typography**: Use **Roboto** (Body) and **Roboto Medium** (Headings/Titles).
*   **Component Pattern**: Data-rich results (like the Modrinth Browser) must use **Cards** with subtle hover effects and clean borders.
*   **Visual Feedback**: Buttons must have defined `hover_color` tokens.

---

## 5. Code Quality & Verification
Quality is non-negotiable. ZBB maintains a robust testing culture.

*   **Linting First**: All code **must** pass `flake8 --select=E9,F63,F7,F82` with zero errors before committing.
*   **Linting**: Adhere to PEP 8 standards. Use `flake8` for static analysis to ensure code cleanliness.
*   **Documentation Integrity**: Preserving existing comments and docstrings is mandatory. New features must be documented using Google-style docstrings.

---

## 6. Quality Certification (Health Score)

Cada fase del Roadmap debe finalizar con una auditoría técnica que garantice un **Health Score > 90/100**.

### Criterios de Evaluación

| Categoría | Máx | Penalización |
|---|---|---|
| **Código Muerto** | 25 pts | -5 pts por cada stub, import no usado, o función huérfana |
| **Manejo de Errores** | 25 pts | -10 pts por cada `except: pass` sin registro |
| **Consistencia Visual** | 20 pts | -5 pts por cada widget con `corner_radius` distinto de 12 (excluyendo Toasts y alertas con `corner_radius=0` documentado) |
| **Documentación** | 15 pts | -5 pts por cada ruta obsoleta o enlace roto en docs/ |
| **Neutralidad de Plataforma** | 15 pts | -5 pts por cada uso de `os.startfile` o `_winapi` sin abstracción |

### Proceso de Certificación
1. Ejecutar `flake8 --select=E9,F63,F7,F82 --statistics app/` — tolerancia cero.
2. Escanear el código en busca de `except:`, `os.startfile`, `_winapi`.
3. Verificar que todos los `corner_radius` en la UI sean `12` (excepción documentada: Toasts y alertas modales pueden usar `0`).
4. Validar que no haya enlaces rotos en `docs/`.

Un Health Score por debajo de 90 requiere una fase correctiva antes de continuar con el siguiente hito del Roadmap.

---

---

## 7. Git Workflow & Release Strategy

### Branch Hierarchy
```
main        Production-ready releases (stable)
  └─ dev    Integration branch for features
       └─ feature/<name>   Feature branches from dev
```

### Workflow Rules
1. **Feature branches** branch from `dev` and merge back to `dev` via `--ff-only`.
2. `dev` merges to `main` only at release milestones (see Release Cadence below).
3. Commits must be in **English**, with conventional prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.
4. No emojis in commit messages, PR descriptions, or branch names.
5. Every merge to `dev` must pass the full test suite (`pytest tests/ -q`).
6. Every merge to `main` must additionally pass linting (`flake8 --select=E9,F63,F7,F82`).

### Release Cadence (Recommended)
| Milestone | Tag | Merge to main |
|-----------|-----|---------------|
| Foundation complete (F3) | `v0.9.0-alpha` | Now |
| First user-visible feature (F4 UI) | `v1.0.0-beta` | After F4 UI |
| External integration (F6 Discord) | `v1.0.0-rc` | After F6 |
| Full release (F11 UI) | `v2.0.0` | After F11 |

### Local Merge Protocol (no `gh` CLI)
```bash
git checkout dev
git merge --ff-only feature/<name>
git checkout main
git merge --ff-only dev
git push origin dev main --no-verify
```

### Commit Message Template
```
<type>: <short summary (max 72 chars)>

<optional body with bullet points explaining what and why,
not how. each bullet <= 72 chars.>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `style`.

---

**Failure to adhere to these standards is considered a regression in project quality.****
