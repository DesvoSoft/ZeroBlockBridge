# MC-Tunnel Manager - Testing Guide

## Manual Testing Checklist

### Sprint 1 & 2 Testing

#### Test 1: Application Launch

- [ ] Run `python app/main.py`
- [ ] Window opens with title "MC-Tunnel Manager (MVP)"
- [ ] Java version appears in top-right (or "Java NOT FOUND")
- [ ] Console shows "[System] Loaded 0 servers." (if no servers exist)

#### Test 2: Java Detection

- [ ] If Java is installed, status shows "Java: version-info" in green
- [ ] If Java is NOT installed, status shows "Java NOT FOUND" in red
- [ ] Console logs appropriate message

#### Test 3: Create Vanilla Server

1. Click "Create Server"
2. Enter name: `test-vanilla`
3. Choose type: `1` (Vanilla)
4. Progress dialog appears
5. Wait for completion (~50MB download)
6. Verify:
   - [ ] Server appears in sidebar
   - [ ] `servers/test-vanilla/server.jar` exists
   - [ ] `servers/test-vanilla/eula.txt` contains `eula=true`

#### Test 4: Create Fabric Server

1. Click "Create Server"
2. Enter name: `test-fabric`
3. Choose type: `2` (Fabric)
4. Progress dialog appears
5. Wait for completion (~200MB download + installation)
6. Verify:
   - [ ] Server appears in sidebar
   - [ ] `servers/test-fabric/fabric-server-launch.jar` exists
   - [ ] `servers/test-fabric/server.jar` exists
   - [ ] `servers/test-fabric/libraries/` folder exists
   - [ ] `servers/test-fabric/eula.txt` contains `eula=true`

#### Test 5: Duplicate Server Name

1. Try to create a server with an existing name
2. Verify console shows error: "[Error] Server 'name' already exists."

#### Test 6: UI Responsiveness

- [ ] During download, window can be moved
- [ ] During download, window doesn't freeze
- [ ] Progress dialog updates smoothly

#### Test 7: Server List Refresh

- [ ] After creating server, it appears in sidebar automatically
- [ ] Restart app, servers still appear in list

## Automated Testing (CLI)

### Test Vanilla Download

```bash
python -c "import sys; sys.path.append('.'); from app.logic import download_server; print(download_server('cli_test_vanilla', 'Vanilla', '1.21.1'))"
```

Expected: `servers\cli_test_vanilla\server.jar`

### Test Fabric Installation

```bash
python -c "import sys; sys.path.append('.'); from app.logic import install_fabric; print(install_fabric('cli_test_fabric', '1.20.1'))"
```

Expected: `servers\cli_test_fabric\fabric-server-launch.jar`

### Test Java Detection

```bash
python -c "import sys; sys.path.append('.'); from app.logic import check_java; print(check_java())"
```

Expected: Java version string or `None`

## Cleanup After Testing

```bash
# Remove test servers
rmdir /s /q servers\test-vanilla
rmdir /s /q servers\test-fabric
rmdir /s /q servers\cli_test_vanilla
rmdir /s /q servers\cli_test_fabric
```

## Known Issues / Expected Behavior

- First server creation will take longer (downloading files)
- Progress percentage may jump (depends on download speed)
- Fabric installation takes longer than Vanilla (runs installer)

## Next Sprint Testing (Sprint 3)

Once Sprint 3 is complete, test:

- [ ] Start button launches server
- [ ] Server logs appear in console
- [ ] Stop button terminates server
- [ ] Server status updates correctly
