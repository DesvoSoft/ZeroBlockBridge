# Zero Block Bridge - User Guide

Complete guide to using Zero Block Bridge for creating and managing Minecraft servers with built-in tunneling, backups, and automated restarts.

---

## Table of Contents

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

## Installation

### Prerequisites

Before running Zero Block Bridge, ensure you have:

1. **Python 3.10 or higher**

   - Download from [python.org](https://www.python.org/downloads/)
   - During installation, check "Add Python to PATH"

2. **Java 17 or higher** (Java 24 fully supported)
   - Required for running Minecraft servers
   - Download from [Adoptium](https://adoptium.net/) or [Oracle](https://www.oracle.com/java/technologies/downloads/)

### Setup Steps

1. **Clone or download** the project to your computer

2. **Install Python dependencies:**

   ```bash
   pip install customtkinter requests psutil packaging Pillow
   ```

   **Note for Linux users regarding sound notifications:**
   The application uses a lightweight sound utility for audio notifications. On some Linux distributions, it relies on external audio playback tools like `paplay`, `aplay`, `canberra-gtk-play`, or `mpg123`. If you encounter issues with sound notifications, ensure one of these is installed. For Debian/Ubuntu-based systems, you can install `mpg123` with:

   ```bash
   sudo apt-get update
   sudo apt-get install mpg123
   ```

3. **Run the application:**

   ```bash
   python app/main.py
   ```

---

## Getting Started

### First Launch

When you first launch Zero Block Bridge:

1. The application window opens with the title **"Zero Block Bridge"**
2. **Java version** is displayed in the top-right corner:
   - Green text shows "Java: version-info" if Java is detected
   - Red text shows "Java NOT FOUND" if Java is missing
3. The **Server Log** tab displays system messages
4. Empty server list appears in the sidebar (if no servers exist yet)

---

## Creating Servers

### Server Creation Wizard

Zero Block Bridge features a comprehensive 6-step wizard:

1. **Click** the **"Create Server"** button in the sidebar

2. **Step 1: Server Type & Name**

   - Enter a unique server name (alphanumeric, no spaces)
   - Choose between:
     - **Vanilla** (Official Minecraft server)
     - **Fabric** (Modded server platform)
     - **Forge** (Popular modded server platform)
   - Select the desired **Minecraft Version** (dynamically fetched)

3. **Step 2: Performance (RAM)**

   - **Slider**: Drag to allocate RAM (512MB - system max)
   - **Manual Entry**: Type exact MB value
   - Recommendations:
     - Vanilla: 2048 - 4096 MB
     - Modded (Fabric/Forge): 6144 - 8192 MB

4. **Step 3: World Settings**

   - **World Seed**: Optional seed for world generation
   - **Game Mode**: survival, creative, adventure, or spectator
   - **Difficulty**: peaceful, easy, normal, or hard
   - **View Distance**: 2 - 32 chunks
   - **Simulation Distance**: 2 - 32 chunks

5. **Step 4: Server Icon**

   - **Browse Image**: Select a custom PNG or JPG icon
   - Icons are automatically resized to 64x64 for the server list

6. **Step 5: Storage Location**

   - Shows where server will be saved (`servers/<name>/`)
   - Note: Custom locations coming soon

7. **Step 6: Review & Create**
   - Review all settings
   - Click "Create Server" to begin installation

### Installation Process

- **Vanilla**: ~50MB download (~1-2 minutes)
- **Fabric/Forge**: Download + automated installation (~3-5 minutes)
- Progress dialog shows real-time status
- EULA is automatically accepted
- Server properties are configured with wizard settings on the first run

---

## Managing Servers

### Dashboard Controls

When you select a server, the dashboard shows:

**Server Controls:**

- **Start** - Launch the server
- **Stop** - Gracefully shut down
- **Properties** - Edit server.properties

**Auto-Restart:**

- Checkbox to enable/disable
- Mode selector: "Interval" or "Daily Time"
- **Interval Mode**: Restart every X hours (enter number + "Apply")
- **Daily Time Mode**: Restart at specific time (enter HH:MM + "Apply")
- **Apply** button - Save changes without toggling

**Backups:**

- Shows last backup date/time
- **Backup Now** - Create instant backup

### Starting a Server

1. **Select** a server from the sidebar list
2. **Click** the green **"Start Server"** button
3. **Monitor** the Server Log tab for startup progress
4. Status bar shows **"Running (server-name)"** in green

### Stopping a Server

1. **Click** the red **"Stop Server"** button
2. Watch console for shutdown sequence
3. Status returns to **"Idle"**

### Editing Properties

1. **Click** the **"Properties"** button (server must be stopped)
2. Navigate through tabs:
   - **General**: MOTD, max players, game mode, difficulty, RAM allocation, and Server Icon
   - **World**: Seed, level type, spawn settings, view distance, simulation distance
   - **Network**: Port, whitelist, RCON, online mode
   - **Advanced**: Performance settings and other properties
   - **Backups**: Manage and restore backups
   - **Automation**: Configure scheduled restarts
3. **Click "Save"** to apply changes

---

## Server Console Commands

### Sending Commands

At the bottom of the **Server Log** tab:

1. Type any Minecraft server command in the input field
2. Press **Enter** or click **"Send"**
3. Command is executed on the server

**Example Commands:**

```text
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

## Automated Backups

### Creating Backups

**From Dashboard:**

- Click **"Backup Now"** for instant backup

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

- Stored in `backups/<server-name>/` (relative to the application root)
- Format: `YYYY-MM-DD_HH-MM-SS.zip`
- Contains entire server directory (excluding internal backups)

---

## Scheduled Restarts

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

---

## Setting Up Tunneling

### Starting the Tunnel

1. **Click** the **"Start Tunnel"** button
2. **Watch the Tunnel Log** tab for:

   ```text
   [Playit] Downloading agent v0.16.5...
   [Playit] Starting agent...
   [Playit] Visit link to setup https://playit.gg/claim/...
   ```

3. **Browser opens automatically** with the claim URL
   - If it doesn't, click the **"Link"** button

### Linking Your Account

1. **Sign in** to Playit.gg (or create a free account)
2. **Click "Approve"** to link this agent
3. **Return to the application**

The tunnel completes setup automatically:

```text
[Playit] Program approved :)
[Playit] tunnel running, 1 tunnels registered
```

### Getting Your Public IP

- **Status indicator**: "Tunnel: Online" (green)
- **Public IP**: "Public IP: your-address.ply.gg"
- **Share this address** with friends to join your server

---

## Console Logs

### Server Log Tab

Displays your Minecraft server output:

- Server startup messages
- Player join/leave events
- Commands you send
- World saving events
- Error messages
- Automated restart warnings

### Tunnel Log Tab

Displays Playit agent output:

- Agent download status
- Tunnel connection status
- Public IP assignment
- Authentication messages

---

## Troubleshooting

### Java Warnings (Java 24)

Modern Java versions show deprecation warnings. These are suppressed automatically with compatibility flags:

- `--enable-native-access=ALL-UNNAMED`
- `-Dorg.lwjgl.util.NoChecks=true`

### Server Won't Start

- Check **Server Log** for specific errors
- Verify sufficient RAM is available
- Ensure Java 17+ is installed
- Check server.properties for invalid values

### Tunnel Issues

**AgentDisabledOverLimit:**

- Delete unused agents at [Playit.gg Dashboard](https://playit.gg/account/agents)

**Connection Errors:**

1. Click "Stop Tunnel"
2. Click "Reset Agent" (confirm with "yes")
3. Click "Start Tunnel" again

---

## File Structure

```text
ZeroBlockBridge/
├── app/
│   ├── main.py                    # Main entry point
│   ├── logic.py                   # Core business logic
│   ├── constants.py               # Paths and API URLs
│   ├── version_manager.py         # Dynamic version fetching
│   ├── scheduler_service.py       # Automated restarts
│   ├── playit_manager.py          # Tunneling management
│   ├── server_wizard.py           # 6-step creation wizard
│   ├── server_properties_editor.py # Tabbed properties editor
│   └── ui_components.py           # Reusable UI widgets
│
├── servers/                       # Created servers
│   └── <server-name>/
│       ├── server.jar             # Server binary
│       ├── server.properties      # Config
│       ├── world/                 # World data
│       └── metadata.json          # App-specific settings
│
├── backups/                       # Server backups
│   └── <server-name>/
│       └── YYYY-MM-DD_HH-MM-SS.zip
│
├── bin/                           # External binaries (playit)
├── config/                        # Application configuration
└── assets/                        # Sounds and icons
```

---

## Additional Resources

- **Main README**: [README.md](../README.md) - Project overview
- **Playit.gg Docs**: [docs.playit.gg](https://docs.playit.gg/) - Advanced tunneling
- **Minecraft Wiki**: [minecraft.wiki](https://minecraft.wiki/) - Server configuration

---

**Need help?** Check the console logs for detailed error messages, or refer to the troubleshooting sections above.
