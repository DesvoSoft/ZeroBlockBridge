# ZeroBlockBridge (ZBB) - Developer Onboarding Protocol

Welcome to the ZeroBlockBridge development team. This protocol is designed to calibrate new developers (Human or AI) for rapid integration into the project.

---

## 1. Treasure Map: Project Structure
Understand where the vital organs of ZBB reside:

*   `app/`: The primary application package.
    *   `app/core.py`: The orchestrator logic (Headless-ready).
    *   `app/logic.py`: Core utilities, downloaders, and helper functions.
    *   `app/services/`: Specific API clients (Modrinth, Playit, etc.) and background services.
    *   `app/main.py`: The CustomTkinter GUI entry point.
*   `.planning/`: Internal technical analysis, research reports, and architectural decisions.
*   `tests/`: Comprehensive `pytest` suite for regression testing.
*   `assets/`: Visual resources (Icons, Logos).

---

## 2. Vital Components
The application functions through two primary systems:

### The Brain: `ZBBManager`
Located in `app/core.py`, this class manages the lifecycle of all servers, tunnels, and background monitors. It is the central authority for state management.

### The Nervous System: `EventBus`
Located in `app/server_events.py`, this is a robust pub/sub system. Every significant event (Server start, console line, error) flows through here. **Never use direct method calls for UI updates; subscribe to the EventBus instead. Queda explícitamente prohibido el uso de `.on()` en favor de `.subscribe()`.**

---

## 3. Mission Workflow
Adhere to this cycle for every task:

1.  **Check Status**: Read `.planning/CHECKLIST.md` to identify the current objective and task status.
2.  **Audit History**: You **must** read the latest `tests/AUDIT_REPORT.md` before proposing structural changes to understand the current technical health.
3.  **Implementation**: Follow the protocols defined in `docs/STANDARDS.md`.
4.  **Verification**: Run `python -m pytest tests/` to ensure no regressions.
5.  **Commitment**: Use the following Git configuration for all contributions:
    *   **User**: `DesvoSoft`
    *   **Email**: `desvox23@gmail.com`
    *   **Branch**: Always target `dev` unless specified.

---

## 4. Key Commandments
1.  **Read Before Writing**: Inspect the existing codebase to maintain pattern consistency.
2.  **Respect the Decoupling**: If you add a new feature, ask yourself: "Can this work without a window?"
3.  **No Prints**: Use the logger.
4.  **Update the Checklist**: Mark tasks as completed (✅) or in progress (🚧) as you work.

---

**Protocol initiated. Welcome to ZBB.**
