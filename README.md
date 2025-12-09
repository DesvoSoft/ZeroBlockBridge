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

1. **Clone the repository**

   ```bash
   git clone https://github.com/yourusername/MCTunnel.git
   cd MCTunnel
   ```

2. **Install dependencies**

   ```bash
   pip install customtkinter requests psutil
   ```

3. **Run the application**
   ```bash
   python app/main.py
   ```

### First Server

1. Click **"Create Server"** in the sidebar
2. Follow the 5-step wizard:
   - Name your server
   - Choose Vanilla or Fabric
   - Set RAM allocation
   - Configure world settings
   - Review and create
3. Select the server from the list
4. Click **"▶ Start"**
5. **Optional**: Enable tunneling to play with friends online

---

## 📖 Documentation

- **[USAGE.md](USAGE.md)** - Complete user guide with all features
- **[TESTING.md](TESTING.md)** - Test cases and verification steps

---

## 🎯 Key Features Explained

### Server Creation Wizard

The wizard guides you through:

1. **Type & Name**: Choose Vanilla/Fabric and name your server
2. **RAM**: Use slider or type exact MB value (with validation)
3. **World Settings**: Seed, game mode, difficulty
4. **Location**: View save location (custom paths coming soon)
5. **Review**: Confirm all settings before creation

### Automated Restarts

Configure from the dashboard or properties editor:

- **Interval Mode**: Restart every 1, 6, 12, or 24 hours
- **Daily Time Mode**: Restart at specific time (e.g., 03:00 for 3AM)
- **Warnings**: Players get in-game notifications starting 1 hour before
- **Final Countdown**: 5-4-3-2-1 second countdown before restart
- **Auto-Recovery**: Success/error messages after restart completes

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
weather clear
whitelist add PlayerName
```

Commands appear in the log with `>` prefix and execute immediately.

---

## 🏗️ Project Structure

```
MCTunnel/
├── app/
│   ├── main.py                    # Main application & UI
│   ├── logic.py                   # Server/backup/scheduler logic
│   ├── server_wizard.py           # 5-step creation wizard
│   ├── server_properties_editor.py # Properties editor UI
│   ├── playit_manager.py          # Tunneling integration
│   └── ui_components.py           # Reusable UI widgets
│
├── servers/                       # Created servers
│   └── <server-name>/
│       ├── server.jar / fabric-server-launch.jar
│       ├── server.properties
│       ├── world/
│       ├── backups/
│       └── metadata.json          # Scheduler config
│
├── bin/                           # Auto-managed
│   └── playit.exe
│
├── config/                        # Playit config
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

```
customtkinter>=5.0.0    # Modern UI framework
requests>=2.31.0        # HTTP operations
psutil>=5.9.0           # System info (RAM detection)
```

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

- **Documentation**: See [USAGE.md](USAGE.md) for detailed instructions
- **Issues**: Report bugs or request features via GitHub Issues
- **Discussions**: Share your server setups and get help from the community

---

**Made with ❤️ for the Minecraft community**
