# Zero Block Bridge - User Guide

Complete guide to using Zero Block Bridge for creating and managing Minecraft servers with built-in tunneling, backups, and automated restarts.

---

## 📋 Table of Contents

- [Installation](#installation)
- [Getting Started](#getting-started)
- [Creating Servers](#creating-servers)
- [Managing Servers](#managing-servers)
- [Server Console Commands](#server-console-commands)
- [Automated Backups](#automated-backups)
- [Scheduled Restarts](#scheduled-restarts)
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

2. **Java 17 or higher** (Java 24 fully supported)
   - Required for running Minecraft servers
   - Download from [Adoptium](https://adoptium.net/) (recommended) or[ Oracle](https://www.oracle.com/java/technologies/downloads/)

### Setup Steps

1. **Clone or download** the project to your computer

2. **Install Python dependencies:**

   ```bash
   pip install customtkinter requests psutil playsound
   ```

   **Note for Linux users regarding sound notifications:**
   The application uses the `playsound` library for audio notifications. On some Linux distributions, `playsound` relies on external audio playback tools like `GStreamer` or `mpg123`. If you encounter issues with sound notifications, ensure one of these is installed. For Debian/Ubuntu-based systems, you can install `GStreamer` with:
   ```bash
   sudo apt-get update
   sudo apt-get install libgstreamer1.0-0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
   ```
   Alternatively, `mpg123` can often work as well:
   ```bash
   sudo apt-get update
   sudo apt-get install mpg123
   ```

3. **Run the application:**
   ```bash
   python app/main.py
   ```

---

## 🚀 Getting Started

### First Launch

When you first launch Zero Block Bridge:

1. The application window opens with the title **"Zero Block Bridge"**
2. **Java version** is displayed in the top-right corner:
   - ✅ Green text shows "Java: version-info" if Java is detected
   - ❌ Red text shows "Java NOT FOUND" if Java is missing
3. The **Server Log** tab displays system messages
4. Empty server list appears in the sidebar (if no servers exist yet)

---

## 🎮 Creating Servers

### Server Creation Wizard

Zero Block Bridge features a comprehensive 5-step wizard:

1. **Click** the **"Create Server"** button in the sidebar

2. **Step 1: Server Type & Name**

   - Enter a unique server name (alphanumeric, no spaces)
   - Choose between:
     - **Vanilla 1.21.1** (Official Minecraft server)
     - **Fabric 1.20.1** (Modded server platform)

3. **Step 2: Performance (RAM)**

   - **Slider**: Drag to allocate RAM (512MB - system max)
   - **Manual Entry**: Type exact MB value
   - Recommendations:
     - Vanilla: 2048 - 4096 MB
     - Fabric/Modded: 6144 - 8192 MB

4. **Step 3: World Settings**

   - **World Seed**: Optional seed for world generation
   - **Game Mode**: survival, creative, adventure, or spectator
   - **Difficulty**: peaceful, easy, normal, or hard

5. **Step 4: Storage Location**

   - Shows where server will be saved (`servers/<name>/`)
   - Custom locations coming soon

6. **Step 5: Review & Create**
   - Review all settings
   - Click "Create Server" to begin installation

### Installation Process

- **Vanilla**: ~50MB download (~1-2 minutes)
- **Fabric**: ~200MB download + installation (~3-5 minutes)
- Progress dialog shows real-time status
- EULA is automatically accepted
- Server properties are configured with wizard settings

---

## 🎛️ Managing Servers

### Dashboard Controls

When you select a server, the dashboard shows:

**Server Controls:**

- ▶ **Start** - Launch the server
- ■ **Stop** - Gracefully shut down
- ⚙ **Properties** - Edit server.properties

**Auto-Restart:**

- Checkbox to enable/disable
- Mode selector: "Interval" or "Daily Time"
- **Interval Mode**: Restart every X hours (enter number + "Apply")
- **Daily Time Mode**: Restart at specific time (enter HH:MM + "Apply")
- **Apply** button - Save changes without toggling

**Backups:**

- Shows last backup date/time
- **✚ Backup Now** - Create instant backup

### Starting a Server

1. **Select** a server from the sidebar list
2. **Click** the green **"Start Server"** button
3. **Monitor** the Server Log tab for startup progress
4. Status bar shows **"Running <server-name>"** in green

### Stopping a Server

1. **Click** the red **"Stop Server"** button
2. Watch console for shutdown sequence
3. Status returns to **"Idle"**

### Editing Properties

1. **Click** the **"⚙ Properties"** button (server must be stopped)
2. Navigate through tabs:
   - **General**: MOTD, max players, game mode, difficulty
   - **World**: Seed, level type, spawn settings, view distance
   - **Network**: Port, whitelist, RCON, online mode
   - **Advanced**: All other properties
   - **Backups**: Manage backups (see below)
   - **Automation**: Configure scheduled restarts (see below)
3. **Click "Save"** to apply changes

---

## 💻 Server Console Commands

### Sending Commands

At the bottom of the **Server Log** tab:

1. Type any Minecraft server command in the input field
2. Press **Enter** or click **"Send"**
3. Command is executed on the server

**Example Commands:**

```
say Hello everyone!
op PlayerName
gamemode creative PlayerName
weather clear
time set day
list
whitelist add PlayerName
```

**Note**: Server must be running to send commands.

---

## 💾 Automated Backups

### Creating Backups

**From Dashboard:**

- Click **"✚ Backup Now"** for instant backup

**From Properties Editor:**

1. Open server properties (server must be stopped)
2. Go to **"Backups"** tab
3. Click **"Create Backup"**

### Restoring Backups

1. Open **Properties → Backups** tab
2. Select a backup from the list (shows date and size)
3. Click **"Restore Selected"**
4. **WARNING**: This wipes the current server folder!

### Backup Storage

- Stored in `servers/<server-name>/backups/`
- Format: `backup_YYYYMMDD_HHMMSS.zip`
- Contains entire server directory

---

## ⏰ Scheduled Restarts

### Configuring Auto-Restart

**From Dashboard:**

1. Check the **Auto-Restart** checkbox
2. Select mode:
   - **Interval**: Restart every X hours
   - **Daily Time**: Restart at specific time (24-hour format)
3. Enter value:

- Interval: Number of hours (e.g., "6")
- Daily Time: HH:MM format (e.g., "03:00" for 3:00 AM)

4. Click **"Apply"** to save

**From Properties Editor:**

1. Open **Properties → Automation** tab
2. Enable "Automated Restarts"
3. Configure interval or time
4. Save properties

### Restart Warnings

Players receive in-game warnings at:

- **1 hour** before restart
- **30 minutes** before restart
- **15 minutes** before restart
- **1 minute** before restart
- **Final countdown**: 5, 4, 3, 2 seconds
- "Restarting NOW!"

### Restart Process

1. Warnings sent to players via `/say` command
2. Final countdown (5-4-3-2)
3. Server stops gracefully
4. 5-second cooldown
5. Server automatically restarts
6. Console shows success/error message

---

## 🌐 Setting Up Tunneling

### Starting the Tunnel

1. **Click** the **"▶ Start Tunnel"** button
2. **Watch the Tunnel Log** tab for:
   ```
   [Playit] Downloading agent v0.16.5...
   [Playit] Starting agent...
   [Playit] Visit link to setup https://playit.gg/claim/...
   ```
3. **Browser opens automatically** with the claim URL
   - If it doesn't, click the **"🔗 Link"** button

### Linking Your Account

1. **Sign in** to Playit.gg (or create a free account)
2. **Click "Approve"** to link this agent
3. **Return to the application**

The tunnel completes setup automatically:

```
[Playit] Program approved :)
[Playit] tunnel running, 1 tunnels registered
```

### Getting Your Public IP

- **Status indicator**: "Tunnel: ● Online" (green)
- **Public IP**: "Public IP: your-address.ply.gg"
- **Share this address** with friends to join your server

### Tunnel Controls

- **■ Stop Tunnel** - Disconnect tunnel
- **↻ Reset** - Clear agent data (requires confirmation)
- **🔗 Link** - Reopen claim URL in browser

---

## 📊 Console Logs

### Server Log Tab

Displays your Minecraft server output:

- Server startup messages
- Player join/leave events
- Commands you send
- World saving events
- Error messages
- Automated restart warnings

**Example:**

```
[System] Starting server with: java -Xmx6543M...
[Server] Done! For help, type "help"
> say Hello from the console!
[System] Server will restart in 1 minute!
```

### Tunnel Log Tab

Displays Playit agent output:

- Agent download status
- Tunnel connection status
- Public IP assignment
- Authentication messages
- Error diagnostics

---

## 🔧 Troubleshooting

### Java Warnings (Java 24)

Modern Java versions show deprecation warnings. These are suppressed automatically with compatibility flags:

- `--enable-native-access=ALL-UNNAMED`
- `-Dorg.lwjgl.util.NoChecks=true`

### Server Won't Start

- Check **Server Log** for specific errors
- Verify sufficient RAM is available
- Ensure Java 17+ is installed
- Check server.properties for invalid values

### Backup/Restore Errors

- Server must be stopped before restoring
- Ensure sufficient disk space
- Check file permissions in servers/ directory

### Scheduled Restart Issues

- Server must be running for restart to trigger
- Check **metadata.json** in server folder for schedule settings
- Warnings appear in console before restart
- Success/error message shown after restart completes

### Tunnel Issues

**AgentDisabledOverLimit:**

- Delete unused agents at [Playit.gg Dashboard](https://playit.gg/account/agents)

**Connection Errors:**

1. Click "Stop Tunnel"
2. Click "Reset Agent" (confirm with "yes")
3. Click "Start Tunnel" again

---

## 📁 File Structure

```
MCTunnel/
├── app/
│   ├── main.py
│   ├── logic.py
│   ├── playit_manager.py
│   ├── server_wizard.py
│   ├── server_properties_editor.py
│   └── ui_components.py
│
├── servers/
│   └── <server-name>/
│       ├── server.jar / fabric-server-launch.jar
│       ├── server.properties
│       ├── world/
│       ├── backups/
│       │   └── backup_YYYYMMDD_HHMMSS.zip
│       └── metadata.json    # Scheduler settings
│
├── bin/
│   └── playit.exe           # Auto-downloaded
│
├── config/
│   └── (playit config)
│
└── README.md
```

---

## 🎯 Quick Tips

- **Multiple Servers**: Create unlimited servers, each fully independent
- **Server Files**: Access in `servers/<name>/` - add mods to `mods/` for Fabric
- **Automated Management**: Set up backups + scheduled restarts for hands-free operation
- **Console Commands**: Send any server command directly from the app
- **RAM Tuning**: Adjust per-server in wizard or via editing server folder

---

## 📚 Additional Resources

- **Main README**: [README.md](README.md) - Project overview
- **Playit.gg Docs**: [docs.playit.gg](https://docs.playit.gg/) -Advanced tunneling
- **Minecraft Wiki**: [minecraft.wiki](https://minecraft.wiki/) - Server configuration

---

**Need help?** Check the console logs for detailed error messages, or refer to the troubleshooting sections above.
