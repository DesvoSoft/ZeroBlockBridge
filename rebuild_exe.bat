@echo off
chcp 65001 >nul
echo Building ZeroBlockBridge.exe...
"C:\Users\johan\AppData\Local\Programs\Python\Python312\python.exe" -m PyInstaller ZeroBlockBridge.spec --clean
if %errorlevel% equ 0 (
    echo Done! dist\ZeroBlockBridge.exe
) else (
    echo Build failed.
)
pause
