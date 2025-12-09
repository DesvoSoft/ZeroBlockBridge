# 🚀 MC-Tunnel Manager

**One-click Minecraft Server Management with Built-in Tunneling**

MC-Tunnel Manager is a lightweight desktop application that simplifies Minecraft server creation and management. No terminal commands, no port forwarding hassles—just click and play.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Features

- ** One-Click Server Creation**: Download and configure Vanilla or Fabric servers automatically
- ** Modern GUI**: Clean, intuitive interface built with CustomTkinter
- ** Built-in Tunneling**: Integrated Playit.gg support for easy multiplayer without port forwarding
- ** Separate Log Streams**: Dedicated tabs for Server and Tunnel logs
- ** Live Console Output**: Real-time monitoring of server activity
- ** Auto-Update**: Automatic Playit agent updates to the latest version
- ** Easy Management**: Start, stop, and reset servers with a single click
- ** Multi-Version Support**:
  - Vanilla 1.21.1
  - Fabric 1.20.1

---

## Screenshots

> **Note**: Screenshots coming soon! The application features a dark-themed interface with:
>
> - Server list sidebar
> - Control panel with status indicators
> - Tabbed console (Server Log / Tunnel Log)
> - Tunnel management with one-click setup

---

## Quick Start

### Prerequisites

- **Python 3.10+** ([Download](https://www.python.org/downloads/))
- **Java 17+** for running Minecraft servers ([Download](https://adoptium.net/))

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/yourusername/MCTunnel.git
   cd MCTunnel
   ```

2. **Install dependencies**

   ```bash
   pip install customtkinter requests
   ```

3. **Run the application**
   ```bash
   python app/main.py
   ```

---

## Usage

### Creating Your First Server

1. **Launch** the application
2. Click **"Create Server"**
3. Enter a server name
4. Choose server type:
   - `1` = Vanilla 1.21.1
   - `2` = Fabric 1.20.1
5. Wait for installation to complete
6. Select your server from the sidebar and click **"Start Server"**

### Setting Up Online Play (Tunneling)

1. Click **"Start Tunnel"** in the tunnel controls
2. A browser window will open with your claim URL
3. Link the agent to your Playit.gg account
4. Copy the public IP address shown in the UI
5. Share this IP with friends to join your server

For detailed usage instructions, see **[USAGE.md](USAGE.md)**.

---

## Architecture

### Project Structure

```
MCTunnel/
├── app/
│   ├── main.py              # Application entry point
│   ├── ui_components.py     # Custom UI widgets
│   ├── logic.py             # Server management logic
│   └── playit_manager.py    # Playit.gg integration
├── bin/                     # Playit agent binary (auto-downloaded)
├── config/                  # Playit configuration
├── servers/                 # Server instances
│   └── <server-name>/       # Individual server files
├── config.json              # Application settings
└── README.md
```

### Tech Stack

- **Language**: Python 3.10+
- **GUI Framework**: CustomTkinter (modern themed widgets)
- **Networking**:
  - `requests` for HTTP downloads
  - Playit.gg agent (v0.16.5) for tunneling
- **Concurrency**: `threading` for non-blocking operations
- **Process Management**: `subprocess` for server control

---

## Roadmap

### Completed ✅

- [x] Sprint 1: UI Framework & Configuration
- [x] Sprint 2: File Management & Downloads
- [x] Sprint 3: Server Process Management
- [x] Sprint 4: Playit.gg Integration

### Future Enhancements 🚧

- [ ] Custom server.properties editor
- [ ] Mod manager for Fabric servers
- [ ] Server backup/restore
- [ ] Multiple tunnel profiles
- [ ] Plugin management for Bukkit/Spigot
- [ ] Player whitelist management
- [ ] Resource pack hosting

---

## Troubleshooting

### "Java NOT FOUND" Error

Install Java 17 or later:

- [Adoptium (Recommended)](https://adoptium.net/)
- [Oracle Java](https://www.oracle.com/java/technologies/downloads/)

### Playit Agent Errors

**AgentDisabledOverLimit**: You have too many agents registered. Delete unused agents in your [Playit.gg dashboard](https://playit.gg/account/agents).

**Connection Issues**: Click "Reset Agent" to clear the configuration and start fresh.

### Server Won't Start

- Verify Java is installed and in PATH
- Check console logs for specific errors
- Ensure server port (default 25565) isn't already in use

For more troubleshooting, see **[TESTING.md](TESTING.md)**.

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [Playit.gg](https://playit.gg/) for the tunneling service
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) for the modern UI framework
- The Minecraft community for inspiration

---

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/MCTunnel/issues)
- **Documentation**: See [USAGE.md](USAGE.md) and [TESTING.md](TESTING.md)

---

**Made with ❤️ by DesvoSoft**
