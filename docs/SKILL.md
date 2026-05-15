---
name: zeroblockbridge-development
description: Project-specific guidelines for ZeroBlockBridge (ZBB). Use for all feature implementations, bug fixes, and architectural changes in this project.
---

# ZeroBlockBridge Development Skill

## Overview

ZeroBlockBridge (ZBB) is a Python-based Minecraft Server Management application. It prioritizes simplicity, automation, and stability.

## Architectural Principles

### 1. Auto-Healing First
- All server processes must be monitored by the `Watchdog Service`.
- Handle specific crash types: `jvm_config_error`, `out_of_memory`, `oom_kill`, `boot_crash`, `runtime_crash`.
- Implement exponential backoff for restarts.

### 2. Services over Monoliths
- Decouple logic from `main.py`.
- Move server lifecycle management, version fetching, and utilities into the `app/services/` directory.
- Use the `ServerEvents` system to communicate between logic and UI.
- **EventBus**: Prohibir explícitamente el uso de `.on()` en favor de `.subscribe()`.

### 3. Command Security
- All console commands MUST pass through `CommandSanitizer`.
- Use a character-based filter (`|`, `;`, `&`, etc.) rather than a command blacklist.

### 4. Java Version Management
- Always match the Java runtime to the Minecraft version requirements:
  - MC ≥ 1.20.6: Java 21
  - MC 1.17 - 1.20.4: Java 17
  - MC < 1.17: Java 8 or 16
- Validate Java version before starting the server.
- **Rango de Estabilidad**:
  - Permitir ejecución si Requerido <= Detectado <= 21.
  - Lanzar advertencia naranja si Detectado > Requerido.
  - Bloqueo rojo solo si Detectado > 21 o Detectado < Requerido.

### 5. Playit.gg Integration
- Estandarizar el uso del agente de Playit.gg en la versión v0.16.5.
- **Regla de Oro**: El argumento para el secreto es `--secret_path` (con guion bajo). Queda estrictamente prohibido el uso de `--secret-path`.
- Los ejemplos de comandos deben incluir siempre `--stdout` y usar rutas entrecomilladas para Windows. Ejemplo: `playit --secret_path "C:\ruta\al\secreto.txt" --stdout`.

### 6. Protocolo de Inicialización de Clases (Safe Init)
- **Regla**: Todos los atributos de datos (como `self.cache`, `self.settings`) DEBEN inicializarse en la primera línea del `__init__`, antes de disparar cualquier hilo de fondo (`_warm`, `_monitor`) o suscripción al EventBus. Esto evita errores de `AttributeError`.

## UI Guidelines (CustomTkinter)
- Use the established dark theme tokens in `app/app_config.py`.
- Maintain the 6-step Wizard pattern for server creation.
- Ensure all GUI operations are non-blocking (use threading/asynchronous tasks for I/O).

## Conventions
- **Language**: Documentation and comments in Spanish (español neutro).
- **Logging**: NO `print()`. Use `logging.getLogger(__name__)`.
- **Code Style**: No emojis in code or comments.
- **Backups**: Use ZIP format with `backup_YYYYMMDD_HHMMSS.zip` naming convention.

### 7. JDK Auto-Installation (JdkManager)
- `JdkManager` en `app/services/java_installer.py` descarga JDKs portables desde la API de Adoptium/Temurin.
- La caché portable se almacena en `.zbb_cache/jdks/{version}/` — nunca modifica PATH del sistema.
- **Atomic-First**: SHA256 verification del binario descargado antes de extraer.
- **Adoptium folder structure**: Maneja el prefijo intermedio (`jdk-21.0.1+12/`) dentro del zip automáticamente.
- **Multi-plataforma**: Soporta Windows, Linux, macOS; detecta arquitecturas x64 y ARM64.
- **Permisos**: Aplica `chmod +x` al binario en sistemas Unix post-extracción.
- **Network resilience**: Excepciones específicas `JdkDownloadError` / `JdkIntegrityError` con retry (2 intentos).
- **Fallback chain**: System Java → JDK Cache → Download → Error.

## Key Files
- `app/main.py`: Main entry point and UI coordination.
- `app/logic.py`: Core business logic.
- `app/constants.py`: Global constants and paths.
- `app/services/watchdog.py`: Crash detection logic.
- `app/services/sanitizer.py`: Command security.
