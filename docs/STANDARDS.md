# ZeroBlockBridge (ZBB) - Master Technical Standards

This document defines the technical identity, architectural philosophy, and coding standards for the ZeroBlockBridge project. All contributors (Human or AI) must adhere to these rules to ensure the maintainability and scalability of the platform.

---

## 1. Architectural Philosophy: Event-Driven & Decoupled
ZBB is built on a strict **decoupled architecture** to ensure the core logic can run independently of any specific interface.

*   **Model-View-Controller (MVC) Hybrid**: The UI (`app/ui/main.py`) must never contain business logic. It serves only as a visual shell.
*   **Event-Driven Communication**: All communication between the UI and the Core (`app/core/core.py`) must occur through the `EventBus`. Prohibir explícitamente el uso de `.on()` en favor de `.subscribe()`.
*   **Headless-Ready**: Every feature must be implemented such that it could function via a CLI or REST API without a GUI. 
*   **Single Source of Truth**: `ZBBManager` is the orchestrator. No other component should directly manage server lifecycles or global configurations.

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

---

## 4. Aesthetics & UI: Neo-Modern Brand Book
The ZBB interface follows a **Neo-Modern** aesthetic designed to feel premium and state-of-the-art.

*   **Corner Radius**: A uniform `corner_radius=12` is mandatory for all frames, buttons, and input fields.
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

**Failure to adhere to these standards is considered a regression in project quality.**
