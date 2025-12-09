# Zero Block Bridge - Testing Guide

Comprehensive testing procedures for validating all features of Zero Block Bridge.

---

## 📋 Manual Testing Checklist

### Sprint 1 & 2: Core Functionality

#### Test 1: Application Launch ✅

**Steps:**

1. Run `python app/main.py`

**Expected Results:**

- [ ] Window opens with title "Zero Block Bridge (MVP)"
- [ ] Java version appears in top-right corner
  - Green text "Java: version-info" (if installed)
  - Red text "Java NOT FOUND" (if not installed)
- [ ] Server Log tab shows "[System] Loaded X servers."
- [ ] Tunnel Log tab is visible and empty

---

#### Test 2: Java Detection ✅

**Steps:**

1. Check Java status indicator

**Expected Results:**

- [ ] **If Java installed**: Green "Java: java version..." in top-right
- [ ] **If Java NOT installed**: Red "Java NOT FOUND" in top-right
- [ ] Server Log shows appropriate message

---

#### Test 3: Create Vanilla Server ✅

**Steps:**

1. Click "Create Server"
2. Enter name: `test-vanilla`
3. Choose type: `1` (Vanilla 1.21.1)
4. Wait for installation

**Expected Results:**

- [ ] Progress dialog appears with percentage
- [ ] Download completes (~50MB)
- [ ] Server appears in sidebar list
- [ ] Files created:
  - `servers/test-vanilla/server.jar` exists
  - `servers/test-vanilla/eula.txt` contains `eula=true`
- [ ] Console shows "[System] Server created successfully."

---

#### Test 4: Create Fabric Server ✅

**Steps:**

1. Click "Create Server"
2. Enter name: `test-fabric`
3. Choose type: `2` (Fabric 1.20.1)
4. Wait for installation

**Expected Results:**

- [ ] Progress dialog appears
- [ ] Download completes (~200MB + installer runs)
- [ ] Server appears in sidebar list
- [ ] Files created:
  - `servers/test-fabric/fabric-server-launch.jar` exists
  - `servers/test-fabric/server.jar` exists
  - `servers/test-fabric/libraries/` folder exists
  - `servers/test-fabric/eula.txt` contains `eula=true`

---

#### Test 5: Duplicate Server Name ❌

**Steps:**

1. Try to create a server with an existing name

**Expected Results:**

- [ ] Console shows error: "[Error] Server 'name' already exists."
- [ ] No new server created

---

#### Test 6: UI Responsiveness ✅

**Steps:**

1. Create a server and observe UI during download

**Expected Results:**

- [ ] Window can be moved during download
- [ ] Window doesn't freeze
- [ ] Progress dialog updates smoothly
- [ ] Other UI elements remain interactive

---

### Sprint 3: Server Management

#### Test 7: Start Vanilla Server ✅

**Steps:**

1. Select a Vanilla server
2. Click "Start Server"

**Expected Results:**

- [ ] Status changes to "Running <server-name>" (green)
- [ ] Start button becomes disabled
- [ ] Stop button becomes enabled
- [ ] Server Log shows:
  - "[System] Starting server with: java -Xmx2G -jar server.jar nogui"
  - "Preparing spawn area..." (first run)
  - "Done! For help, type 'help'"

---

#### Test 8: Connect to Server Locally ✅

**Steps:**

1. Start a server
2. Wait for "Done!" message
3. Open Minecraft (matching version)
4. Connect to `localhost`

**Expected Results:**

- [ ] Successfully join the server
- [ ] Server Log shows: "Player joined the game"
- [ ] Can move around and interact with world

---

#### Test 9: Stop Server ✅

**Steps:**

1. Click "Stop Server" on a running server

**Expected Results:**

- [ ] Server Log shows:
  - "Stopping server"
  - "Saving chunks"
  - "[System] Server process exited."
- [ ] Status changes to "Idle"
- [ ] Start button becomes enabled
- [ ] Stop button becomes disabled

---

#### Test 10: Start Fabric Server ✅

**Steps:**

1. Select a Fabric server
2. Click "Start Server"

**Expected Results:**

- [ ] Server Log shows Fabric loader logs
- [ ] Server starts successfully
- [ ] "Done!" message appears
- [ ] Can connect with Fabric-compatible client

---

### Sprint 4: Playit Integration

#### Test 11: First-Time Tunnel Setup ✅

**Steps:**

1. Click "Start Tunnel"
2. Observe Tunnel Log and browser

**Expected Results:**

- [ ] Tunnel status shows "Tunnel: ⏳ Starting..." (orange)
- [ ] Tunnel Log shows:
  - "[Playit] Downloading agent v0.16.5..." (if first run)
  - "[Debug] Starting agent..."
  - "[Playit] Visit link to setup https://playit.gg/claim/..."
- [ ] Browser opens automatically with claim URL
- [ ] "Link Account" button appears in UI (orange)

---

#### Test 12: Account Linking ✅

**Steps:**

1. Click "Approve" on the Playit.gg claim page
2. Return to application

**Expected Results:**

- [ ] Tunnel Log shows:
  - "[Playit] Program approved :)"
  - "[Playit] tunnel running, 1 tunnels registered"
- [ ] Tunnel status changes to "Tunnel: ● Online" (green)
- [ ] Public IP shows: "Public IP: xxxxx.ply.gg"
- [ ] "Link Account" button disappears

---

#### Test 13: Connect via Tunnel ✅

**Steps:**

1. Ensure server is running AND tunnel is online
2. Copy the .ply.gg address from "Public IP"
3. Connect from Minecraft using this address

**Expected Results:**

- [ ] Successfully connect to server from external network
- [ ] Server Log shows player join
- [ ] Gameplay works normally

---

#### Test 14: Reset Agent ✅

**Steps:**

1. Click "Reset Agent"
2. Type `yes` to confirm

**Expected Results:**

- [ ] Tunnel Log shows:
  - "[Playit] Resetting agent configuration..."
  - "[Playit] Agent reset complete..."
- [ ] Tunnel status shows "Offline"
- [ ] Public IP shows "N/A"

---

#### Test 15: Restart Tunnel After Reset ✅

**Steps:**

1. After reset, click "Start Tunnel" again

**Expected Results:**

- [ ] **NEW** claim URL is generated
- [ ] Must re-link account
- [ ] Tunnel comes online with new address

---

#### Test 16: Tabbed Console ✅

**Steps:**

1. Start both server AND tunnel
2. Switch between "Server Log" and "Tunnel Log" tabs

**Expected Results:**

- [ ] Server Log shows only Minecraft server output
- [ ] Tunnel Log shows only Playit agent output
- [ ] Tabs switch smoothly
- [ ] No mixed messages between tabs

---

#### Test 17: Tunnel Error Handling ❌

**Steps:**

1. Start tunnel with too many agents already registered (if applicable)

**Expected Results:**

- [ ] Tunnel Log shows:
  - "[Playit] ERROR: Account limit reached! You have too many agents."
  - "[Playit] Please delete unused agents in your Playit.gg dashboard."
- [ ] Tunnel status shows "Tunnel: ✖ Error" (red)

---

#### Test 18: Playit Version Update ✅

**Steps:**

1. If old version exists in `bin/`, run application

**Expected Results:**

- [ ] Tunnel Log shows: "[Playit] Found old version. Updating to 0.16.5..."
- [ ] New version downloads automatically
- [ ] Tunnel starts with updated agent

---

## 🤖 Automated Testing (CLI)

### Quick Validation Tests

#### Test: Vanilla Download

```bash
python -c "import sys; sys.path.append('.'); from app.logic import download_server; print(download_server('cli_test_vanilla', 'Vanilla', '1.21.1'))"
```

**Expected Output:** `servers\cli_test_vanilla\server.jar`

---

#### Test: Fabric Installation

```bash
python -c "import sys; sys.path.append('.'); from app.logic import install_fabric; print(install_fabric('cli_test_fabric', '1.20.1'))"
```

**Expected Output:** `servers\cli_test_fabric\fabric-server-launch.jar`

---

#### Test: Java Detection

```bash
python -c "import sys; sys.path.append('.'); from app.logic import check_java; print(check_java())"
```

**Expected Output:** Java version string (e.g., `java version "17.0.1"...`) or `None`

---

## 🧹 Cleanup After Testing

Remove test servers to free up space:

**Windows (PowerShell):**

```powershell
Remove-Item -Recurse -Force servers\test-vanilla
Remove-Item -Recurse -Force servers\test-fabric
Remove-Item -Recurse -Force servers\cli_test_vanilla
Remove-Item -Recurse -Force servers\cli_test_fabric
```

**Linux/Mac:**

```bash
rm -rf servers/test-vanilla
rm -rf servers/test-fabric
rm -rf servers/cli_test_vanilla
rm -rf servers/cli_test_fabric
```

---

## ⚠️ Known Issues / Expected Behavior

### Normal Behavior

- **First download takes time**: Initial server creation requires downloading ~50-200MB
- **Progress may jump**: Download speed varies, percentage may not be perfectly smooth
- **Fabric slower than Vanilla**: Fabric installer takes extra time to process libraries
- **IPv6 connection errors**: Playit may show IPv6 network errors, this is normal (falls back to IPv4)

### Common Issues

**"TooManyRequests" in Tunnel Log:**

- Playit API is rate-limiting
- Wait 1-2 minutes between attempts
- Use "Reset Agent" if persistent

**Server crashes on start:**

- Check Java version (must be 17+)
- Verify RAM allocation in config.json
- Check Server Log for specific error

**Tunnel stays "Starting..." forever:**

- Check internet connection
- Try "Stop Tunnel" → "Reset Agent" → "Start Tunnel"
- Verify no firewall blocking

---

## 📊 Test Coverage Summary

| Component          | Tests  | Status |
| ------------------ | ------ | ------ |
| UI Launch          | 2      | ✅     |
| Server Creation    | 4      | ✅     |
| Server Management  | 4      | ✅     |
| Playit Integration | 8      | ✅     |
| Error Handling     | 2      | ✅     |
| **Total**          | **20** | **✅** |

---

## 🎯 Testing Best Practices

1. **Test in order**: Follow Sprint 1→4 sequence
2. **Clean state**: Start with no servers for first-time tests
3. **Monitor logs**: Always check **both** Server Log and Tunnel Log tabs
4. **Wait for completion**: Don't interrupt downloads or server startup
5. **Note timestamps**: Server startup can take 30-60 seconds (first run)
6. **Verify externally**: Test tunnel connection from different network when possible

---

## 📝 Reporting Issues

If you find a bug:

1. **Check logs**: Copy relevant messages from Server Log / Tunnel Log
2. **Note your environment**:
   - OS version
   - Python version
   - Java version
3. **Steps to reproduce**: Document exact clicks/inputs
4. **Open an issue**: Submit to GitHub Issues with above info

---

**Testing completed?** Return to [README.md](README.md) or [USAGE.md](USAGE.md) for normal usage.
