@echo off
title ZeroBlockBridge — Linux (Docker)
color 0A

echo ============================================
echo   ZeroBlockBridge — Linux Launcher
echo ============================================
echo.
echo   [1] GUI mode   — Full Python+Tk via X11
echo   [2] Binary mode — Native Linux binary
echo.
set /p MODE="Select mode (1 or 2): "

if "%MODE%"=="2" goto :binary
if "%MODE%"=="1" goto :gui
echo Invalid selection.
pause
exit /b 1

:gui
echo.
echo --- GUI Mode (X11 forwarding) ---
set SERVICE=zbb-gui
goto :check

:binary
echo.
echo --- Binary Mode (native Linux binary) ---
set SERVICE=zbb-linux
goto :check

:check
REM --- Check Docker ---
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker not found. Install Docker Desktop first.
    pause
    exit /b 1
)
echo [OK] Docker found

REM --- Check VcXsrv ---
tasklist /FI "IMAGENAME eq vcxsrv.exe" 2>NUL | find /I "vcxsrv.exe" >NUL
if %errorlevel% neq 0 (
    echo [WARN] VcXsrv not running. Starting it now...
    start "" "C:\Program Files\VcXsrv\vcxsrv.exe" :0 -multiwindow -ac -lesslog -nocursor
    timeout /t 3 /nobreak >nul
    echo [OK] VcXsrv started
) else (
    echo [OK] VcXsrv running
)

REM --- Detect host IP ---
for /f "delims=" %%a in ('powershell -NoProfile -Command "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1 | ForEach-Object { (Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4).IPAddress })"') do set HOST_IP=%%a
if "%HOST_IP%"=="" set HOST_IP=host.docker.internal

echo.
echo Host IP: %HOST_IP%
echo Service: %SERVICE%
echo.

REM --- Build and run ---
echo Building Docker image...
if "%SERVICE%"=="zbb-gui" (
    docker build -f Dockerfile.gui -t zbb-gui . -q
) else (
    docker build -f Dockerfile.linux -t zbb-linux . -q
)

echo.
echo Starting %SERVICE%...
echo (Close this window or press Ctrl+C to stop)
echo.

docker run --rm -it ^
    --name %SERVICE% ^
    -e DISPLAY="%HOST_IP%:0" ^
    --add-host=host.docker.internal:host-gateway ^
    -v "%cd%\servers:/opt/zeroblockbridge/servers" ^
    %SERVICE%

echo.
echo Container stopped.
pause
