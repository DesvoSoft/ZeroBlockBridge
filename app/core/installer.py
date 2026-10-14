"""Per-user Windows install of the single-file ZeroBlockBridge.exe.

"Installing" means: copy the exe to %LOCALAPPDATA%\\Programs\\ZeroBlockBridge
(no admin rights needed), add Start menu / Desktop shortcuts, and register
an entry under Settings -> Apps so it can be uninstalled like any other app.

Runs from `app.core.bootstrap` before the data directory is decided, so it
must stay free of any `app.core.constants` dependency (directly or
transitively).
"""

import datetime
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.core.fs_links import is_link, remove_link

logger = logging.getLogger(__name__)

APP_NAME = "ZeroBlockBridge"
EXE_NAME = "ZeroBlockBridge.exe"
SHORTCUT_NAME = "ZeroBlockBridge.lnk"
PUBLISHER = "DesvoSoft"
HOMEPAGE = "https://github.com/DesvoSoft/ZeroBlockBridge"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ZeroBlockBridge"
UNINSTALL_ARG = "--uninstall"

_CREATE_NO_WINDOW = 0x08000000
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200

# SHGetFolderPathW CSIDLs -- resolve OneDrive-redirected folders correctly.
_CSIDL_PROGRAMS = 0x0002
_CSIDL_DESKTOPDIRECTORY = 0x0010


def _local_appdata() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) if local else Path.home() / "AppData" / "Local"


def default_install_dir() -> Path:
    return _local_appdata() / "Programs" / APP_NAME


def standard_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / APP_NAME if local else Path.home() / APP_NAME


def same_path(a, b) -> bool:
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


# ----------------------------------------------------------------------
# Shell folders and shortcuts
# ----------------------------------------------------------------------
def _shell_folder(csidl: int) -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0 and buf.value:
            return Path(buf.value)
    except Exception as e:
        logger.debug("SHGetFolderPathW(%#x) failed: %s", csidl, e)
    return None


def start_menu_shortcut_path() -> Path | None:
    programs = _shell_folder(_CSIDL_PROGRAMS)
    if programs is None:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None
        programs = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return programs / SHORTCUT_NAME


def desktop_shortcut_path() -> Path | None:
    desktop = _shell_folder(_CSIDL_DESKTOPDIRECTORY)
    return desktop / SHORTCUT_NAME if desktop else None


def create_shortcut(target: Path, lnk_path: Path) -> None:
    """Write a .lnk via the WScript.Shell COM object. Paths travel as env
    vars so no quoting/escaping of user paths is ever needed."""
    lnk_path.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:ZBB_LNK);"
        "$s.TargetPath = $env:ZBB_TARGET;"
        "$s.WorkingDirectory = $env:ZBB_WORKDIR;"
        "$s.IconLocation = $env:ZBB_TARGET + ',0';"
        "$s.Description = 'Minecraft server manager';"
        "$s.Save()"
    )
    env = dict(os.environ, ZBB_LNK=str(lnk_path), ZBB_TARGET=str(target),
               ZBB_WORKDIR=str(target.parent))
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", script],
        env=env, capture_output=True, text=True, timeout=30, creationflags=_CREATE_NO_WINDOW,
    )
    if result.returncode != 0 or not lnk_path.exists():
        raise OSError(f"Could not create shortcut {lnk_path}: {(result.stderr or result.stdout).strip()}")


def add_shortcuts(target: Path, start_menu: bool = True, desktop: bool = True) -> list[str]:
    """Create the requested shortcuts; returns human-readable failures
    (a missing shortcut never fails an install)."""
    failures = []
    wanted = []
    if start_menu:
        wanted.append(("Start menu", start_menu_shortcut_path()))
    if desktop:
        wanted.append(("Desktop", desktop_shortcut_path()))
    for label, path in wanted:
        if path is None:
            failures.append(f"{label}: folder not found")
            continue
        try:
            create_shortcut(target, path)
        except (OSError, subprocess.SubprocessError) as e:
            logger.warning("%s shortcut failed: %s", label, e)
            failures.append(f"{label}: {e}")
    return failures


def remove_shortcuts() -> None:
    for path in (start_menu_shortcut_path(), desktop_shortcut_path()):
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Could not remove shortcut %s: %s", path, e)


# ----------------------------------------------------------------------
# Settings -> Apps registration (HKCU, no admin)
# ----------------------------------------------------------------------
def register_uninstall(exe: Path, version: str) -> None:
    if sys.platform != "win32":
        return
    import winreg
    try:
        size_kb = exe.stat().st_size // 1024
    except OSError:
        size_kb = 0
    values = {
        "DisplayName": (winreg.REG_SZ, "ZeroBlockBridge"),
        "DisplayVersion": (winreg.REG_SZ, version),
        "Publisher": (winreg.REG_SZ, PUBLISHER),
        "DisplayIcon": (winreg.REG_SZ, f"{exe},0"),
        "InstallLocation": (winreg.REG_SZ, str(exe.parent)),
        "UninstallString": (winreg.REG_SZ, f'"{exe}" {UNINSTALL_ARG}'),
        "URLInfoAbout": (winreg.REG_SZ, HOMEPAGE),
        "InstallDate": (winreg.REG_SZ, datetime.date.today().strftime("%Y%m%d")),
        "EstimatedSize": (winreg.REG_DWORD, size_kb),
        "NoModify": (winreg.REG_DWORD, 1),
        "NoRepair": (winreg.REG_DWORD, 1),
    }
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        for name, (kind, value) in values.items():
            winreg.SetValueEx(key, name, 0, kind, value)


def unregister_uninstall() -> None:
    if sys.platform != "win32":
        return
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning("Could not remove uninstall entry: %s", e)


# ----------------------------------------------------------------------
# Install / update / uninstall
# ----------------------------------------------------------------------
def copy_exe(src: Path, dest: Path) -> None:
    """Copy via a temp file + os.replace so a failed copy never leaves a
    truncated exe. Raises PermissionError while `dest` is running."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".new")
    shutil.copy2(src, tmp)
    try:
        os.replace(tmp, dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def install(src_exe: Path, version: str, install_dir: Path | None = None,
            start_menu: bool = True, desktop: bool = True) -> tuple[Path, list[str]]:
    """Install (or reinstall) `src_exe`. Returns (installed exe, shortcut
    failures). Raises OSError if the exe itself can't be copied."""
    dest = (install_dir or default_install_dir()) / EXE_NAME
    if not same_path(src_exe, dest):
        copy_exe(src_exe, dest)
    failures = add_shortcuts(dest, start_menu=start_menu, desktop=desktop)
    try:
        register_uninstall(dest, version)
    except OSError as e:
        logger.warning("Could not register uninstall entry: %s", e)
        failures.append(f"Apps list entry: {e}")
    logger.info("Installed %s %s to %s", APP_NAME, version, dest)
    return dest, failures


def update(src_exe: Path, installed_exe: Path, version: str) -> None:
    """Replace the installed exe with `src_exe` (shortcuts keep pointing at
    the same path). Raises PermissionError if the installed app is open."""
    copy_exe(src_exe, installed_exe)
    try:
        register_uninstall(installed_exe, version)
    except OSError as e:
        logger.warning("Could not update uninstall entry: %s", e)


def remove_data_dir(data_dir: Path) -> None:
    """Delete ZBB's data folder. Servers created in a custom location are
    linked into servers/ with junctions: unlink those first so deleting the
    data folder can never reach into the user's own folders."""
    servers = data_dir / "servers"
    if servers.is_dir():
        for entry in servers.iterdir():
            if is_link(entry):
                remove_link(entry)
    shutil.rmtree(data_dir, ignore_errors=True)


def schedule_removal(exe: Path) -> None:
    """Delete the installed exe (its whole folder when it's the standard
    install folder) a few seconds after this process exits -- a running exe
    can't delete its own file."""
    if same_path(exe.parent, default_install_dir()):
        remove = f'rmdir /s /q "{exe.parent}"'
    else:
        remove = f'del /f /q "{exe}"'
    subprocess.Popen(
        f"cmd /c ping 127.0.0.1 -n 4 >nul & {remove}",
        cwd=str(exe.parent.parent), close_fds=True,
        creationflags=_CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP,
    )


def launch(exe: Path) -> None:
    """Start another copy of the app, detached. The PyInstaller env reset
    keeps the child from reusing this process's onefile temp dir."""
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("_PYI_") or k == "_MEIPASS2")}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen(
        [str(exe)], cwd=str(exe.parent), env=env, close_fds=True,
        creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP,
    )
