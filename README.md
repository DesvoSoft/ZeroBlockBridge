# MC-Tunnel Manager (MVP)

**Role:** Tech Lead / Product Owner
**Target:** MVP (Fase 1)

## 1. Visión del Producto

Crear una aplicación de escritorio ligera en **Python** que democratice la creación de servidores de Minecraft. El objetivo es abstraer la complejidad de la terminal (`java -jar...`) y la red (Port Forwarding) en una interfaz gráfica moderna "One-Click", utilizando **Playit.gg** como backbone de conectividad.

## 2. Stack Tecnológico

- **Lenguaje Core:** Python 3.10+
- **GUI Framework:** `CustomTkinter`
- **Networking:** `requests` (Descargas), `playit.gg` (Túnel)
- **Concurrencia:** `threading`, `subprocess`

## 3. Arquitectura

### Estructura de Directorios

```text
/MC-Manager-App
│
├── /app                 # Source Code
│   ├── main.py          # Entry Point
│   ├── ui_components.py # Custom Widgets
│   └── logic.py         # Backend Logic
│
├── /bin                 # External Binaries
│   ├── /playit          # Playit Agent
│   └── /java            # (Optional) Portable JDK
│
├── /servers             # Server Instances
│   └── /server_01       # Instance Data
│
└── config.json          # Global Config
```

## 4. Desarrollo (Sprints)

- [x] **Sprint 1:** Esqueleto (UI & Config)
- [ ] **Sprint 2:** Gestión de Archivos y Descargas
- [ ] **Sprint 3:** El Motor (Minecraft Process)
- [ ] **Sprint 4:** El Túnel (Integración Playit.gg)

## 5. Ejecución

```bash
# Instalar dependencias
pip install customtkinter requests

# Ejecutar
python app/main.py
```
