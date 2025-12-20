<h1 align="center">ZeroBlockBridge</h1>

<p align="center">Minecraft Server Management with Built-in Tunneling, Backups & Automation</p>

<p align="center">
  <img src="assets/logo.png" alt="ZeroBlockBridge Logo" width="350"/>
</p>

ZeroBlockBridge is a desktop application that simplifies Minecraft server creation and management, designed with the intent to provide a user‑friendly interface that can safely turn any computer into a Minecraft server. With Zero Block Bridge, you can easily host a server to play with your friends and community — without the hassle of complex setup, port forwarding or unsafe configurations.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: PolyForm Noncommercial](https://img.shields.io/badge/License-PolyForm_Noncommercial-red.svg)](https://polyformproject.org/licenses/noncommercial/1.0.0/)
---

## Features

### Server Management

- **Creation Wizard**: Name, type, RAM, world settings, and review.
- **Multi-Version Support**: Vanilla and Fabric 1.20.1.
- **Custom RAM Allocation**: Slider + manual entry with validation (512MB - system max).
- **Server Properties Editor**: Tabbed interface for all settings.
- **Integrated Console**: Send commands directly from the app.
- **Live Monitoring**: Real-time server and tunnel logs in separate tabs.

### Automation & Backups

- **One-Click Backups**: Create and restore ZIP backups instantly.
- **Scheduled Restarts**:
  - Interval mode (every X hours).
  - Daily time mode (specific time like 03:00).
  - Multi-stage warnings (1h, 30m, 15m, 1m, countdown).
  - Automatic success/error notifications.
- **Auto-Management**: Set it and forget it with automated restarts + backups.

### Tunneling & Sharing

- **Built-in [Playit.gg](https://playit.gg/) Integration**: No port forwarding needed.
- **One-Click Tunnel Setup**: Auto-opens claim link in browser.
- **Public IP Display**: Share the provided public address.
- **Auto-Update**: Agent stays up to date automatically.

Note: playit.gg is a global proxy that allows anyone to host a server without port forwarding by using tunneling.

### Developer Experience

- **Modern GUI**: Clean dark theme built with CustomTkinter.
- **Cross-Platform Sound**: Reliable notifications on Windows and Linux.
- **Java 24 Support**: Fully compatible with latest Java versions.
- **Error Handling**: Comprehensive validation and user feedback.
- **Organized Structure**: Dedicated folders for each server.

---

## Interface Overview

The application features:

- **Sidebar**: Server list with selection.
- **Dashboard**: Server/tunnel controls, auto-restart settings, quick backup.
- **Tabbed Console**: Separate logs for Server and Tunnel output.
- **Console Input**: Send server commands directly from the UI.
- **Properties Editor**: 6 tabs (General, World, Network, Advanced, Backups, Automation).

---

## Quick Start

### Prerequisites

- **Python 3.10+** ([Download](https://www.python.org/downloads/))
- **Java 17+** ([Download](https://www.java.com/en/download/))

### Installation

1.  **Clone the repository**

    ```bash
    git clone https://github.com/DesvoSoft/ZeroBlockBridge.git
    ```

2. **Navigate to the core app folder**
   ```bash
    cd ZeroBlockBridge
    cd app
    ```

3.  **Install dependencies**

    Create a virtual environment (recommended):

    ```bash
    py -m venv venv
    .\venv\Scripts\activate
    ```

    Install dependencies from the `requirements.txt` file:

    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application**
    ```bash
    py main.py
    ```

> **Note:** Depending on your operating system and environment configuration, you might need to adjust the command used to run Python. For example, use `py`, `python`, or `python3` as appropriate.

### First Server

1.  Click **"Create Server"** in the sidebar.
2.  Follow the 5-step wizard to configure your server.
3.  Select the server from the list.
4.  Click **"Start"**. On the very first run, the server will start, create necessary files, and then you can stop it. On the second start, your settings from the wizard will be applied.
5.  **Optional**: Enable tunneling to play with friends online.

Note: The tunneling feature uses the free third party services from [Playit.GG](http://playit.gg/). The app will lead to their website and the respecitve dashboard to connect the agent, the tunnel, and to confirm your shearable IP (One time process).

---

## Documentation

- **[USAGE.md](docs/USAGE.md)** - Complete user guide with all features.
- **[TESTING.md](docs/TESTING.md)** - Test cases and verification steps.

---

## Key Features

### Server Creation Wizard

The wizard guides you through:

1.  **Type & Name**: Choose Vanilla/Fabric and name your server.
2.  **RAM**: Use slider or type exact MB value (with validation).
3.  **World Settings**: Seed, game mode, difficulty.
4.  **Location**: View save location (custom paths coming soon).
5.  **Review**: Confirm all settings before creation.

### Automated Restarts

Configure from the dashboard or properties editor:

- **Interval Mode**: Restart every X hours.
- **Daily Time Mode**: Restart at a specific time (e.g., 03:00 for 3AM).
- **Warnings**: Players get in-game notifications starting 1 hour before restart.
- **Final Countdown**: A 5-second countdown is announced in-game before shutdown.

### Backups

- **Create**: Dashboard button or Properties → Backups tab.
- **Format**: ZIP archives with timestamp (`backup_YYYYMMDD_HHMMSS.zip`).
- **Restore**: Select backup in properties editor (wipes current server!).
- **Storage**: `servers/<server-name>/backups/`.

### Console Commands

Send any Minecraft command:

```
say Hello everyone!
op PlayerName
gamemode creative PlayerName
```

Commands appear in the log with `>` prefix and execute immediately.

---

## Privacy & Service Disclaimer

ZeroBlockBridge is designed with simplicity and transparency in mind:

- **No External Connections**: The software does not connect to any external services other than the free tunneling services provided by [Playit.gg](https://playit.gg).  
- **No Data Collection**: ZeroBlockBridge is not intended to collect, store, or transmit any personal information or usage data.  
- **User Control**: All server management, backups, and tunneling operations remain fully under the user’s control.  

This ensures that your Minecraft server management experience is secure, private, and limited strictly to the features described.

---

## Project Structure

The project follows a clean architecture, separating UI, business logic, and services.

```
ZeroBlockBridge/
├── app/
│   ├── main.py                    # Main application, UI layout, and coordination
│   ├── logic.py                   # Core business logic & Sound Utility
│   ├── app_config.py              # Centralized configuration and constants
│   ├── server_events.py           # Event system for server state
│   ├── scheduler_service.py       # Handles the logic for automated restarts
│   ├── playit_manager.py          # Manages the playit.gg tunneling agent
│   ├── server_wizard.py           # UI and logic for the 5-step creation wizard
│   ├── server_properties_editor.py # UI for the server properties editor
│   ├── ui_components.py           # Reusable UI widgets (console, list items)
|   └── requirements.txt           # Project dependencies for pip
│
├── assets/                        # Other misc files
│   ├── notification.wav           # Notification sound effect
|   ├── server-icon.png            # Image used during devolpment as server icon
|   └── logo.png                   # Project logo
|
├── docs/                          
│   ├── USAGE.md                   # User guide
|   └── TESTING.md                 # Test documentation<server-name>/
|
├── servers/                       # (Generated) Created servers are stored here
│   └── <server-name>/
│       ├── server.jar
│       ├── server.properties
│       └── metadata.json          # Stores RAM allocation, scheduler config, etc.
│
├── bin/                           # (Generated) Binaries like the playit agent
│
├── config/                        # (Generated) Playit.gg agent configuration
│   └── config.json                # (Generated) App-level configuration
│
└── README.md                      # This file c:
```

---

## Technical Details

### Supported Versions

- **Vanilla**: All existing and officially available verions, including 1.21.1 (latest official release)
- **Fabric**: 1.20.1 (with Fabric Loader 0.18.1) (Currently the only mod loader version I have implemented)

### System Requirements

- **OS**: Windows/Linux
- **Python**: 3.10 or higher
- **Java**: 17 minimum, 24 supported (This might also depend on your desired Minecraft server version)
- **RAM**: 2GB minimum (4GB+ recommended for modded servers)
- **Disk**: ~500MB per server + world size

### Dependencies

All required Python packages are listed in `requirements.txt`. The dependencies are:

- **customtkinter** – Modern graphical user interface framework for Python.  
- **darkdetect** – Detects system dark/light mode for adaptive UI themes.  
- **requests** – Handles HTTP requests for downloading server files and updates.  
- **psutil** – Provides system information (CPU, RAM, processes) for resource management.  
- **packaging** – Utilities for version parsing and dependency handling.  
- **playsound==1.2.2** – Lightweight library for playing notification sounds.  
- **Pillow** – Image processing library, used for server icon feature.  

---

## Contributing

Contributing, issues and pull requests are welcome!
Feedback is always appreciated ❤️

---

## License

**ZeroBlockBridge** © 2025 by **DesvoSoft**.

This project is licensed under the **PolyForm Noncommercial License 1.0.0**.

### Restriction

* **No Commercial Use** — You may **not** use this software for any commercial purpose. This includes:
* Selling the software or any modified version of it.
* Using the software as part of a paid hosting service.
* Using the software to support the operations of a for-profit business.

[View Full License Text](https://polyformproject.org/licenses/noncommercial/1.0.0/)

---

## Acknowledgments

- **CustomTkinter**: Modern UI Python framework by Tom Schimansky.
- **Playit.gg**: Free tunneling service for easy multiplayer.
- **Minecraft/Mojang**: For creating an amazing game.

---

## Support

- **Documentation**: See [docs/USAGE.md](docs/USAGE.md) for detailed instructions.
- **Issues**: Report bugs or request features via GitHub Issues.
- **Discussions**: Share your server setups and get help from the community.

---

**Built by a player, for players — Empowering Minecraft creators & friends**

![Privacy Friendly](https://img.shields.io/badge/Privacy-Friendly-green?style=for-the-badge&logo=shield)
![Community](https://img.shields.io/badge/Made_for-Minecraft_Community-blue?style=for-the-badge&logo=minecraft)
