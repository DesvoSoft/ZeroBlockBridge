# 🚀 Zero Block Bridge

**Minecraft Server Management with Built-in Tunneling, Backups & Automation**

Zero Block Bridge is a feature-rich desktop application that simplifies Minecraft server creation and management. Create servers with a wizard, automate restarts, manage backups, and share with friends—no terminal commands or port forwarding required.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Java 17+](https://img.shields.io/badge/java-17+-orange.svg)](https://adoptium.net/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ Features

### Server Management

- **📝 5-Step Creation Wizard**: Name, type, RAM, world settings, and review
- **🎮 Multi-Version Support**: Vanilla 1.21.1 and Fabric 1.20.1
- **⚡ Custom RAM Allocation**: Slider + manual entry with validation (512MB - system max)
- **🎛️ Server Properties Editor**: Tabbed interface for all settings
- **💻 Integrated Console**: Send commands directly from the app
- **📊 Live Monitoring**: Real-time server and tunnel logs in separate tabs

### Automation & Backups

- **💾 One-Click Backups**: Create and restore ZIP backups instantly
- **⏰ Scheduled Restarts**:
  - Interval mode (every X hours)
  - Daily time mode (specific time like 03:00)
  - Multi-stage warnings (1h, 30m, 15m, 1m, countdown)
  - Automatic success/error notifications
- **🔄 Auto-Management**: Set it and forget it with automated restarts + backups

### Tunneling & Sharing

- **🌐 Built-in Playit.gg Integration**: No port forwarding needed
- **🔗 One-Click Tunnel Setup**: Auto-opens claim link in browser
- **📍 Public IP Display**: Share `.ply.gg` address with friends
- **🔄 Auto-Update**: Agent stays up to date automatically

### Developer Experience

- **🎨 Modern GUI**: Clean dark theme built with CustomTkinter
- **Java 24 Support**: Fully compatible with latest Java versions
- **🛡️ Error Handling**: Comprehensive validation and user feedback
- **📁 Organized Structure**: Dedicated folders for each server

---

## 🖼️ Interface Overview

The application features:

- **Sidebar**: Server list with selection
- **Dashboard**: Server/tunnel controls, auto-restart settings, quick backup
- **Tabbed Console**: Separate logs for Server and Tunnel output
- **Console Input**: Send server commands directly from the UI
- **Properties Editor**: 6 tabs (General, World, Network, Advanced, Backups, Automation)

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+** ([Download](https://www.python.org/downloads/))
- **Java 17+** (Java 24 fully supported) ([Download](https://adoptium.net/))

### Installation

1.  **Clone the repository**

    ```bash
    git clone https://github.com/yourusername/MCTunnel.git
    cd MCTunnel
    ```

2.  **Install dependencies**

    Create a virtual environment (recommended):
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```

    Install dependencies from the `requirements.txt` file:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the application**
    ```bash
    python app/main.py
    ```

### First Server

1.  Click **"Create Server"** in the sidebar.
2.  Follow the 5-step wizard to configure your server.
3.  Select the server from the list.
4.  Click **"▶ Start"**. On the very first run, the server will start, create necessary files, and then you can stop it. On the second start, your settings from the wizard will be applied.
5.  **Optional**: Enable tunneling to play with friends online.

---

## 📖 Documentation

- **[USAGE.md](docs/USAGE.md)** - Complete user guide with all features
- **[TESTING.md](docs/TESTING.md)** - Test cases and verification steps

---

## 🎯 Key Features Explained

### Server Creation Wizard

The wizard guides you through:

1.  **Type & Name**: Choose Vanilla/Fabric and name your server
2.  **RAM**: Use slider or type exact MB value (with validation)
3.  **World Settings**: Seed, game mode, difficulty
4.  **Location**: View save location (custom paths coming soon)
5.  **Review**: Confirm all settings before creation

### Automated Restarts

Configure from the dashboard or properties editor:

- **Interval Mode**: Restart every X hours.
- **Daily Time Mode**: Restart at a specific time (e.g., 03:00 for 3AM).
- **Warnings**: Players get in-game notifications starting 1 hour before restart.
- **Final Countdown**: A 5-second countdown is announced in-game before shutdown.

### Backups

- **Create**: Dashboard button or Properties → Backups tab
- **Format**: ZIP archives with timestamp (`backup_YYYYMMDD_HHMMSS.zip`)
- **Restore**: Select backup in properties editor (wipes current server!)
- **Storage**: `servers/<server-name>/backups/`

### Console Commands

Send any Minecraft command:

```
say Hello everyone!
op PlayerName
gamemode creative PlayerName
```

Commands appear in the log with `>` prefix and execute immediately.

---

## 🏗️ Project Structure

The project follows a clean architecture, separating UI, business logic, and services.

```
MCTunnel/
├── app/
│   ├── main.py                    # Main application, UI layout, and event handling
│   ├── logic.py                   # Core server logic (start, stop, backup, properties)
│   ├── constants.py               # Centralized constants (URLs, paths, versions)
│   ├── scheduler_service.py       # Handles the logic for automated restarts
│   ├── playit_manager.py          # Manages the playit.gg tunneling agent
│   ├── server_wizard.py           # UI and logic for the 5-step creation wizard
│   ├── server_properties_editor.py # UI for the server properties editor
│   └── ui_components.py           # Reusable UI widgets (console, list items)
│
├── servers/                       # (Generated) Created servers are stored here
│   └── <server-name>/
│       ├── server.jar
│       ├── server.properties
│       └── metadata.json          # Stores RAM allocation, scheduler config, etc.
│
├── bin/                           # (Generated) Binaries like the playit agent
│
├── config/                        # (Generated) Playit.gg agent configuration
│
├── config.json                    # (Generated) App-level configuration
├── requirements.txt               # Project dependencies for pip
│
├── USAGE.md                       # User guide
├── TESTING.md                     # Test documentation
└── README.md                      # This file
```

---

## 🛠️ Technical Details

### Supported Versions

- **Vanilla**: 1.21.1 (latest official release)
- **Fabric**: 1.20.1 (with Fabric Loader 0.18.1)

### System Requirements

- **OS**: Windows, macOS, Linux
- **Python**: 3.10 or higher
- **Java**: 17 minimum, 24 fully supported
- **RAM**: 2GB minimum (4GB+ recommended for modded)
- **Disk**: ~500MB per server + world size

### Dependencies

All required Python packages are listed in the `requirements.txt` file. The main dependencies are:
- **customtkinter**: For the modern graphical user interface.
- **requests**: For downloading server files.
- **psutil**: For detecting system information like available RAM.

---

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

- Additional server versions (Paper, Purpur, etc.)
  -More automation options (scheduled backups, auto-updates)
- Custom storage locations
- Multi-server simultaneous operation
- Plugin/mod management UI

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **CustomTkinter**: Modern UI framework by Tom Schimansky
- **Playit.gg**: Free tunneling service for easy multiplayer
- **Minecraft/Mojang**: For creating an amazing game
- **Fabric**: Lightweight modding platform

---

## 📞 Support

- **Documentation**: See [docs/USAGE.md](docs/USAGE.md) for detailed instructions
- **Issues**: Report bugs or request features via GitHub Issues
- **Discussions**: Share your server setups and get help from the community

---

**Made with ❤️ for the Minecraft community**
