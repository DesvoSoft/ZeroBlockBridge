# MC-Tunnel Manager - User Guide

## Installation

### Prerequisites

- **Python 3.10+** installed on your system
- **Java 17+** installed (for running Minecraft servers)

### Setup

1. Clone or download the project
2. Install dependencies:

   ```bash
   pip install customtkinter requests
   ```

## Getting Started

### Launch the Application

```bash
python app/main.py
```

The application will:

- Check for Java installation (displayed in top-right)
- Load existing servers from the `servers/` directory

## Creating a Server

1. Click **"Create Server"** button in the sidebar
2. Enter a server name (e.g., "my-server")
3. Choose server type:
   - **1** = Vanilla 1.21.1
   - **2** = Fabric 1.20.1
4. Wait for the installation to complete (progress shown in dialog)
5. Server will appear in the sidebar list

### What Gets Created

- **Vanilla**: `servers/<name>/server.jar` + `eula.txt`
- **Fabric**: `servers/<name>/fabric-server-launch.jar` + `server.jar` + `libraries/` + `eula.txt`

## Next Steps (After Sprint 3)

Once Sprint 3 is complete, you'll be able to:

- Start/Stop servers from the UI
- View server logs in the console
- Configure RAM allocation

## Troubleshooting

### "Java NOT FOUND" Error

Install Java 17 or later from [Adoptium](https://adoptium.net/) or [Oracle](https://www.oracle.com/java/technologies/downloads/).

### Download Fails

- Check internet connection
- Verify firewall is not blocking Python

### Server Won't Create

- Ensure server name doesn't already exist
- Check you have write permissions in the project folder

## File Structure

```text
/MC-Manager-App
├── /app              # Application code
├── /servers          # Your server instances
├── /bin              # External binaries (playit, java)
├── config.json       # App configuration
└── README.md         # Project overview
```

## Important Commands (Manual)

If you want to run a server manually:

**Fabric 1.20.1:**

```bash
cd servers/your-server-name
java -Xmx2G -jar fabric-server-launch.jar nogui
```

**Vanilla 1.21.1:**

```bash
cd servers/your-server-name
java -Xmx2G -jar server.jar nogui
```
