# Zero Block Bridge - User Guide

Complete guide to using Zero Block Bridge for creating and managing Minecraft servers with built-in tunneling.

---

## 📋 Table of Contents

- [Installation](#installation)
- [Getting Started](#getting-started)
- [Creating Servers](#creating-servers)
- [Managing Servers](#managing-servers)
- [Setting Up Tunneling](#setting-up-tunneling)
- [Console Logs](#console-logs)
- [Troubleshooting](#troubleshooting)

---

## 📦 Installation

### Prerequisites

Before running Zero Block Bridge, ensure you have:

1. **Python 3.10 or higher**

   - Download from [python.org](https://www.python.org/downloads/)
   - During installation, check "Add Python to PATH"

2. **Java 17 or higher**
   - Required for running Minecraft servers
   - Download from [Adoptium](https://adoptium.net/) (recommended) or [Oracle](https://www.oracle.com/java/technologies/downloads/)

### Setup Steps

1. **Clone or download** the project to your computer

2. **Install Python dependencies:**

   ```bash
   pip install customtkinter requests
   ```

3. **Run the application:**
   ```bash
   python app/main.py
   ```

---

## 🚀 Getting Started

### First Launch

When you first launch Zero Block Bridge:

1. The application window opens with the title **"Zero Block Bridge (MVP)"**
2. **Java version** is displayed in the top-right corner:
   - ✅ Green text shows "Java: version-info" if Java is detected
   - ❌ Red text shows "Java NOT FOUND" if Java is missing
3. The **Server Log** tab displays system messages
4. Empty server list appears in the sidebar (if no servers exist yet)

---

## 🎮 Creating Servers

### Step-by-Step Instructions

1. **Click** the **"Create Server"** button in the sidebar

2. **Enter a server name** when prompted

   - Use alphanumeric characters (e.g., "survival-world", "creative-server")
   - Avoid special characters or spaces

3. **Choose server type** by entering:

   - `1` for **Vanilla 1.21.1** (Official Minecraft server)
   - `2` for **Fabric 1.20.1** (Modded server platform)

4. **Wait for installation**

   - Progress dialog shows download and installation status
   - **Vanilla**: ~50MB download (~1-2 minutes)
   - **Fabric**: ~200MB download + installation (~3-5 minutes)

5. **Server appears** in the sidebar when complete

### What Gets Created

After successful installation, you'll find:

**For Vanilla 1.21.1:**

```
servers/<server-name>/
├── server.jar          # Server executable
├── eula.txt            # EULA acceptance (auto-accepted)
└── world/              # Created after first run
```

**For Fabric 1.20.1:**

```
servers/<server-name>/
├── fabric-server-launch.jar    # Fabric launcher
├── server.jar                   # Minecraft server
├── libraries/                   # Fabric dependencies
├── eula.txt                     # EULA acceptance (auto-accepted)
└── mods/                        # Mod folder (created on first run)
```

---

## 🎛️ Managing Servers

### Starting a Server

1. **Select** a server from the sidebar list
2. The dashboard updates to show the selected server name
3. **Click** the green **"Start Server"** button
4. **Monitor** the Server Log tab for startup progress:
   - "Starting minecraft server..."
   - World generation (first run only)
   - "Done!" when ready

**Status Indicators:**

- Status bar shows **"Running <server-name>"** in green
- Start button becomes disabled
- Stop button becomes enabled

### Stopping a Server

1. **Click** the red **"Stop Server"** button
2. Watch the console for shutdown sequence:
   - "Stopping server"
   - "Saving chunks"
   - "Server process exited"
3. Status returns to **"Idle"**

### Connecting to Your Server

**Local Play (Same Computer):**

1. Open Minecraft (matching version)
2. Multiplayer → Direct Connect
3. Server Address: `localhost`

**LAN Play (Same Network):**

1. Find your local IP address
2. Share `<your-ip>:25565` with friends on your network

**Internet Play:**
See [Setting Up Tunneling](#setting-up-tunneling) below.

---

## 🌐 Setting Up Tunneling

Tunneling allows friends from anywhere to connect to your server without port forwarding.

### Starting the Tunnel

1. **Click** the **"Start Tunnel"** button in the tunnel controls section

2. **Watch the Tunnel Log** tab for:

   ```
   [Playit] Downloading agent v0.16.5...
   [Playit] Starting agent...
   [Playit] Visit link to setup https://playit.gg/claim/...
   ```

3. **Browser opens automatically** with the claim URL
   - If it doesn't open, click the **"Link Account"** button that appears

### Linking Your Account

1. **Sign in** to Playit.gg (or create a free account)
2. **Click "Approve"** to link this agent to your account
3. **Return to the application**

The tunnel will automatically complete setup:

```
[Playit] Program approved :)
[Playit] tunnel running, 1 tunnels registered
```

### Getting Your Public IP

Once the tunnel is online:

- **Status indicator**: Changes to **"Tunnel: ● Online"** (green)
- **Public IP**: Displayed as **"Public IP: your-address.ply.gg"**
- **Share this address** with friends to join your server

### Troubleshooting Tunnel Issues

**AgentDisabledOverLimit Error:**

- You have too many agents registered on your Playit account
- Delete unused agents at [Playit.gg Dashboard](https://playit.gg/account/agents)

**Connection Errors / Stuck Tunnel:**

1. Click **"Stop Tunnel"**
2. Click **"Reset Agent"**
3. Type `yes` to confirm
4. Click **"Start Tunnel"** again

**Claim URL Not Appearing:**

- Check the **Tunnel Log** tab for error messages
- Ensure your internet connection is stable
- Try restarting the application

---

## 📊 Console Logs

Zero Block Bridge features **separate log tabs** for better organization:

### Server Log Tab

Displays output from your Minecraft server:

- Server startup messages
- Player join/leave events
- World saving events
- Error messages and warnings
- Plugin/mod loading (Fabric servers)

**Example messages:**

```
[System] Starting server with: java -Xmx2G -jar server.jar nogui
[Server] Preparing spawn area: 97%
[Server] Done! For help, type "help"
[Server] Player123 joined the game
```

### Tunnel Log Tab

Displays output from the Playit agent:

- Agent download and update status
- Tunnel connection status
- Public IP assignment
- Authentication messages
- Error diagnostics

**Example messages:**

```
[Playit] Downloading agent v0.16.5...
[Playit] tunnel running, 1 tunnels registered
[UI] Opened claim URL in browser: https://playit.gg/claim/...
```

**Switching Tabs:**
Click on the tab name to switch between Server Log and Tunnel Log views.

---

## 🔧 Troubleshooting

### Java Issues

**"Java NOT FOUND" in red:**

1. Install Java 17+ from [Adoptium](https://adoptium.net/)
2. Restart the application
3. Verify green "Java: ..." indicator appears

**Server crashes immediately:**

- Check Server Log for specific errors
- Verify you have enough RAM (at least 2GB free)
- Update Java to the latest version

### Server Creation Issues

**"Server 'name' already exists" error:**

- Choose a different name, or
- Delete the existing server folder in `servers/`

**Download fails:**

- Check internet connection
- Verify firewall isn't blocking Python
- Try again (network might be temporarily down)

### Playit Tunnel Issues

**"TooManyRequests" errors:**

- Playit API is rate-limiting your requests
- Wait 1-2 minutes and try again
- If persistent, try "Reset Agent"

**Tunnel shows "Online" but friends can't connect:**

1. Verify your **Minecraft server is running** (separate from tunnel)
2. Give friends the **exact .ply.gg address** (not localhost)
3. Ensure server version matches client version
4. Check server is listening on default port (25565)

### General Issues

**Application won't start:**

- Verify Python dependencies: `pip install customtkinter requests`
- Run from terminal to see error messages
- Check Python version: `python --version` (should be 3.10+)

**UI freezes or crashes:**

- Close and restart the application
- Check console for error messages
- Ensure no other instance is running

---

## 📁 File Structure Reference

Understanding where things are stored:

```
MCTunnel/
├── app/                    # Application code
│   ├── main.py
│   ├── logic.py
│   ├── playit_manager.py
│   └── ui_components.py
│
├── servers/                # Your server instances
│   ├── survival-world/     # Example server
│   │   ├── server.jar
│   │   ├── world/
│   │   └── server.properties
│   └── creative-server/    # Another server
│
├── bin/                    # Playit agent (auto-managed)
│   └── playit.exe
│
├── config/                 # Playit configuration
│   └── (auto-generated)
│
├── config.json             # App settings (RAM, etc.)
└── README.md
```

---

## 🎯 Quick Tips

- **RAM Allocation**: Default is 2GB. Edit `config.json` to change: `"ram_allocation": "4G"`
- **Multiple Servers**: Create as many as you want! Each is independent.
- **Switching Servers**: Stop one before starting another (or run on different ports)
- **Server Files**: Found in `servers/<name>/` - add mods here for Fabric
- **Config Editing**: Edit `server.properties` in server folder for advanced settings
- **Backups**: Copy entire `servers/<name>/` folder to back up a world

---

## 📚 Additional Resources

- **Main README**: [README.md](README.md) - Project overview
- **Testing Guide**: [TESTING.md](TESTING.md) - Test cases and verification
- **Playit.gg Docs**: [docs.playit.gg](https://docs.playit.gg/) - Advanced tunneling
- **Minecraft Wiki**: [minecraft.wiki](https://minecraft.wiki/) - Server configuration

---

**Need help?** Open an issue on GitHub or check the [TESTING.md](TESTING.md) guide for validation steps.
