# Zero Block Bridge - Testing Guide

Comprehensive testing procedures for validating all features of Zero Block Bridge.

---

## 📋 Manual Testing Checklist

### Sprint 1 & 2: Core Functionality

#### Test 1: Application Launch ✅

**Steps:**

1. Run `python app/main.py`

**Expected Results:**

- [ ] Window opens with title "Zero Block Bridge"
- [ ] Java version appears in top-right corner
- [ ] Server Log tab shows "[System] Loaded X servers."

---

#### Test 2: Java Detection ✅

**Steps:**

1. Check Java status indicator

**Expected Results:**

- [ ] **If Java installed**: Green "Java: java version..." in top-right
- [ ] **If Java NOT installed**: Red "Java NOT FOUND" in top-right

---

#### Test 3: Create Vanilla Server ✅

**Steps:**

1. Click "Create Server"
2. Enter name: `test-vanilla`
3. Follow wizard steps.

**Expected Results:**

- [ ] Progress dialog appears.
- [ ] Server appears in sidebar list.
- [ ] `servers/test-vanilla/server.jar` exists.
- [ ] `servers/test-vanilla/eula.txt` contains `eula=true`.

---

#### Test 4: Create Fabric Server ✅

**Steps:**

1. Click "Create Server"
2. Enter name: `test-fabric`
3. Choose "Fabric" in the wizard.

**Expected Results:**

- [ ] Progress dialog appears.
- [ ] Server appears in sidebar list.
- [ ] `servers/test-fabric/fabric-server-launch.jar` exists.

---

### Sprint 3: Server Management

#### Test 5: Start & Stop Server ✅

**Steps:**

1. Select a server.
2. Click "▶" (Start).
3. Wait for "Done!" message in console.
4. Click "■" (Stop).

**Expected Results:**

- [ ] Status changes: "⚪ Offline" -> "⏳ Starting..." -> "🟢 Running".
- [ ] Server Log shows startup messages.
- [ ] After stop, Status changes back to "⚪ Offline".

---

#### Test 6: Connect to Server Locally ✅

**Steps:**

1. Start a server.
2. Wait for "Done!" message.
3. Open Minecraft (matching version) and connect to `localhost`.

**Expected Results:**

- [ ] Successfully join the server.
- [ ] Server Log shows player join message.

---

### Sprint 4: Playit Integration

#### Test 7: Tunnel Lifecycle ✅

**Steps:**

1. Click "▶" on the tunnel controls.
2. Wait for tunnel to come online.
3. Click "■" on the tunnel controls.

**Expected Results:**

- [ ] Tunnel status changes: "Offline" -> "Starting..." -> "Online".
- [ ] Public IP is displayed.
- [ ] Tunnel status returns to "Offline" after stopping.

---

### Sprint 5: Refactoring and UI/UX Enhancements

#### Test 8: Initial Server Properties ✅

**Steps:**

1. Create a **new** server. Use custom values in the wizard for:
   - `Game Mode`: creative
   - `View Distance`: 12
   - `Simulation Distance`: 12
2. Start the server once, then stop it.
3. Click the "⚙️" (Edit Properties) button.

**Expected Results:**

- [ ] The properties editor opens.
- [ ] `gamemode` is set to `creative`.
- [ ] `view-distance` is `12`.
- [ ] `simulation-distance` is `12`.
- [ ] `network-compression-threshold` is `256`.
- [ ] `allow-flight` is `true`.
- [ ] `sync-chunk-writes` is `false`.

---

#### Test 9: Properties Button State ✅

**Steps:**

1. Create a **new** server.
2. Select it in the list immediately after creation.
3. Start the server, then stop it.
4. Select the server again.

**Expected Results:**

- [ ] After step 2, the "⚙️" button is **disabled**.
- [ ] After step 4, the "⚙️" button is **enabled**.

---

#### Test 10: Scheduler Warnings ✅

**Steps:**

1. Start a server.
2. Enable "Auto-Restart" and set mode to "Daily Time".
3. Enter a time that is 2-3 minutes in the future. Click "Apply".
4. Monitor the Server Log.

**Expected Results:**

- [ ] When ~1 minute remains, a `[System] Server will restart in 1 minute!` message appears.
- [ ] After the target time passes, the final 5-second countdown begins.

---

#### Test 11: Server List UI Layout ✅

**Steps:**

1. Create a server with a very long name, e.g., `this-is-a-very-long-name-to-test-ui-layout-and-text-truncation`.
2. Observe the server list in the sidebar.

**Expected Results:**

- [ ] The server name is visible but truncated.
- [ ] The select button ("→") is fully visible and not pushed out of view.
- [ ] The button remains functional.

---

## 🧹 Cleanup After Testing

Remove test servers to free up space:

**Windows (PowerShell):**
```powershell
Remove-Item -Recurse -Force servers/test-vanilla
Remove-Item -Recurse -Force servers/test-fabric
```

**Linux/Mac:**
```bash
rm -rf servers/test-vanilla
rm -rf servers/test-fabric
```

---

## ⚠️ Known Issues / Expected Behavior

- **First server run**: The first time a new server starts, it generates its files. Settings from the wizard are applied on the first start.
- **Progress may jump**: Download speed varies, so the progress bar may not be perfectly smooth.
- **IPv6 connection errors**: Playit may show IPv6 network errors in its log; this is normal as it falls back to IPv4.

---

**Testing completed?** Return to [README.md](README.md) or [USAGE.md](USAGE.md) for normal usage.