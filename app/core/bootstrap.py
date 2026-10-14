"""Resolves where ZBB stores its data (servers/config/backups/bin/.zbb_cache)
and handles the Windows install flow around it.

Must run -- and must finish running -- before `app.core.constants` is
imported anywhere in the process. That module fixes `BASE_DIR` (and every
path derived from it) at import time, and 25+ other modules bind those
constants at module load, so there is no later point at which the choice
can still be applied. Every dialog shown from here must therefore stay
free of any `app.core.constants` dependency, directly or transitively.

Where the data lives:
  * Portable copy  -- a PORTABLE_FLAG file next to the exe: data next to it.
  * Everything else -- the folder recorded in the per-user marker
    (%LOCALAPPDATA%\\ZeroBlockBridge\\install.json), which also remembers
    whether and where the app is installed.
"""

import json
import logging
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from app.core.app_config import AppConfig
from app.core.fs_links import create_junction, is_link, link_target, remove_link

logger = logging.getLogger(__name__)

MARKER_FILENAME = "install.json"
PORTABLE_FLAG = "ZeroBlockBridge-portable.txt"
_PORTABLE_FLAG_TEXT = (
    "ZeroBlockBridge portable mode: servers, backups and settings are stored\n"
    "in this folder, next to ZeroBlockBridge.exe. Keep this file here.\n"
)

# Marker "mode" values
MODE_INSTALLED = "installed"  # exe copied to Programs, shortcuts + Apps entry
MODE_MANUAL = "manual"        # user chose to keep running a loose exe

# Files left behind in config/ that must never be carried over.
_CONFIG_SKIP = {".zbb.lock", "versions_cache.json"}


@dataclass
class SetupResult:
    """What the setup dialog decided. `mode` is MODE_INSTALLED, MODE_MANUAL
    or "portable"; `exe_path` is the installed exe for MODE_INSTALLED."""
    mode: str
    data_dir: Path
    exe_path: Path | None = None


def _marker_path() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        base = Path(local_appdata) / "ZeroBlockBridge"
    else:
        base = Path.home() / ".zeroblockbridge"
    return base / MARKER_FILENAME


def read_marker(marker_path: Path | None = None) -> dict:
    marker_path = marker_path or _marker_path()
    try:
        with open(marker_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        logger.debug("No usable data dir marker at %s: %s", marker_path, e)
        return {}
    return data if isinstance(data, dict) else {}


def write_marker(data: dict, marker_path: Path | None = None) -> None:
    marker_path = marker_path or _marker_path()
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    with open(marker_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def is_writable_dir(path: Path) -> bool:
    """Best-effort check that `path` exists (creating it if needed) and
    can actually be written to -- catches Program Files-style installs
    without admin rights."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".zbb_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError as e:
        logger.debug("Data dir %s not writable: %s", path, e)
        return False


def _same_path(a, b) -> bool:
    from app.core.installer import same_path
    return same_path(a, b)


# ----------------------------------------------------------------------
# Is a folder ZBB's?
# ----------------------------------------------------------------------
def looks_like_zbb_data(folder: Path) -> bool:
    """True when `folder` holds ZBB data (not just any config/ or servers/
    that happens to sit next to the exe, e.g. in Downloads)."""
    config = folder / "config"
    if (config / "zbb_settings.json").is_file():
        return True
    try:
        with open(config / "config.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and "java_path" in data and "accepted_eula" in data


def _in_use(folder: Path) -> bool:
    """Another ZBB instance is running from this data folder."""
    try:
        pid = int((folder / "config" / ".zbb.lock").read_text().strip())
    except (OSError, ValueError):
        return False
    if pid == os.getpid():
        return False
    try:
        import psutil
        name = psutil.Process(pid).name().lower()
    except Exception:  # gone, or not ours to inspect: not in use
        return False
    # A stale lock whose PID was reused by an unrelated program doesn't count.
    return "zeroblockbridge" in name or name.startswith("python")


def _is_app_folder(folder: Path) -> bool:
    """A folder an older build adopted as data dir because it was a portable
    copy: the exe itself lives there."""
    try:
        return any(folder.glob("ZeroBlockBridge*.exe"))
    except OSError:
        return False


def _looks_like_server(entry: Path) -> bool:
    return is_link(entry) or (entry / "metadata.json").is_file() or (entry / "server.properties").is_file()


def _use(data_dir: Path) -> Path:
    os.environ["ZBB_DATA_DIR"] = str(data_dir)
    if "app.core.constants" in sys.modules:
        # Too late: paths were already fixed to another folder. This is the
        # bug that silently split data between two folders -- make it loud.
        logger.error("app.core.constants was imported before the data dir was resolved; "
                     "data may be written to the wrong folder")
    return data_dir


def write_portable_flag(exe_dir: Path) -> None:
    (exe_dir / PORTABLE_FLAG).write_text(_PORTABLE_FLAG_TEXT, encoding="utf-8")


# ----------------------------------------------------------------------
# Stray data rescue
# ----------------------------------------------------------------------
def _move_entry(src: Path, dest: Path) -> None:
    if is_link(src):
        # A server created in a custom folder: recreate the link, never
        # move (or copy) the user's folder itself.
        target = link_target(src)
        if not os.path.isabs(target):
            target = os.path.join(str(src.parent), target)
        create_junction(target, str(dest))
        remove_link(src)
        return
    try:
        os.rename(src, dest)  # same volume: atomic, nothing copied
    except OSError:
        shutil.move(str(src), str(dest))  # other volume; caller checked nothing uses it


def _remove_if_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass


def _rescue_config(src_cfg: Path, dest_cfg: Path) -> list[str]:
    """Carry over config files the data dir doesn't have yet (playit.toml
    holds the tunnel agent's secret); never overwrite newer ones."""
    moved = []
    if not src_cfg.is_dir() or is_link(src_cfg):
        return moved
    for entry in list(src_cfg.iterdir()):
        dest = dest_cfg / entry.name
        if entry.name in _CONFIG_SKIP or os.path.lexists(dest):
            continue
        try:
            dest_cfg.mkdir(parents=True, exist_ok=True)
            shutil.move(str(entry), str(dest))
            moved.append(f"config/{entry.name}")
        except OSError as e:
            logger.warning("Could not move %s to %s: %s", entry, dest, e)
    return moved


def _rescue_entries(src_root: Path, dest_root: Path, servers: bool) -> list[str]:
    """Move each entry of servers/ or backups/ that isn't in the data dir yet."""
    moved = []
    if not src_root.is_dir() or is_link(src_root):
        return moved
    for entry in list(src_root.iterdir()):
        if servers and not _looks_like_server(entry):
            continue
        dest = dest_root / entry.name
        if os.path.lexists(dest):
            logger.warning("Not moving %s: %s already exists", entry, dest)
            continue
        try:
            dest_root.mkdir(parents=True, exist_ok=True)
            _move_entry(entry, dest)
            moved.append(f"{src_root.name}/{entry.name}")
        except OSError as e:
            logger.warning("Could not move %s to %s: %s", entry, dest, e)
    _remove_if_empty(src_root)
    return moved


def rescue_stray_data(exe_dir: Path, data_dir: Path) -> list[str]:
    """Move servers/backups/config written next to the exe into `data_dir`.

    Older builds imported `app.core.constants` while the first-run dialog
    was still open, so the whole first session wrote next to the exe while
    every later session read the chosen folder -- servers created that first
    time vanished from the list. Only runs when the exe folder really holds
    ZBB data and no other instance uses it; only server-looking entries
    move, and entries already present in `data_dir` are left alone.
    Returns the names of what was moved.
    """
    if _same_path(exe_dir, data_dir) or not looks_like_zbb_data(exe_dir):
        return []
    if _in_use(exe_dir):
        logger.warning("Not moving data from %s: another ZBB instance is using it", exe_dir)
        return []
    moved = []
    for sub in ("servers", "backups"):
        moved += _rescue_entries(exe_dir / sub, data_dir / sub, servers=(sub == "servers"))
    moved += _rescue_config(exe_dir / "config", data_dir / "config")

    if moved:
        logger.info("Moved data left next to the exe into %s: %s", data_dir, ", ".join(moved))
    return moved


# ----------------------------------------------------------------------
# Install state
# ----------------------------------------------------------------------
def _launch_and_exit(exe: Path) -> None:
    from app.core import installer
    installer.launch(exe)
    sys.exit(0)


def _apply_setup(result: SetupResult | None, exe: Path, marker: dict, marker_path: Path,
                 data_dir: Path | None = None) -> Path:
    if result is None:
        # Window closed without choosing. First run: nothing is set up yet,
        # so quit. Install offer: run as before and ask again next time.
        if data_dir is None:
            sys.exit(0)
        return _use(data_dir)
    if result.mode == "portable":
        write_portable_flag(exe.parent)
        return _use(exe.parent)
    marker = dict(marker, data_dir=str(result.data_dir), mode=result.mode)
    if result.mode == MODE_INSTALLED and result.exe_path is not None:
        marker.update(exe_path=str(result.exe_path), version=AppConfig.APP_VERSION)
    write_marker(marker, marker_path)
    if result.mode == MODE_INSTALLED and result.exe_path is not None \
            and not _same_path(result.exe_path, exe):
        _launch_and_exit(result.exe_path)
    return _use(result.data_dir)


def _reconcile_install(marker: dict, marker_path: Path, exe: Path, data_dir: Path) -> Path:
    """Data dir is known; deal with how this exe relates to the install."""
    from app.ui import first_run_dialog as ui

    mode = marker.get("mode")
    if mode == MODE_MANUAL:
        return _use(data_dir)

    installed = Path(marker["exe_path"]) if mode == MODE_INSTALLED and marker.get("exe_path") else None
    if installed is not None and installed.exists():
        if _same_path(installed, exe):
            if marker.get("version") != AppConfig.APP_VERSION:
                # Updated in place (by us or by hand): keep marker + Apps entry current.
                from app.core import installer
                write_marker(dict(marker, version=AppConfig.APP_VERSION), marker_path)
                try:
                    installer.register_uninstall(installed, AppConfig.APP_VERSION)
                except OSError as e:
                    logger.warning("Could not refresh uninstall entry: %s", e)
            return _use(data_dir)

        choice = ui.ask_already_installed(exe, installed, marker.get("version"))
        if choice == "updated":
            write_marker(dict(marker, version=AppConfig.APP_VERSION), marker_path)
            _launch_and_exit(installed)
        elif choice == "open":
            _launch_and_exit(installed)
        elif choice == "cancel":
            sys.exit(0)
        return _use(data_dir)

    # Data folder chosen by an older build (no install support) or the
    # installed copy was deleted: offer to install, keeping the data folder.
    result = ui.ask_setup(exe, data_dir=data_dir)
    return _apply_setup(result, exe, marker, marker_path, data_dir=data_dir)


def _adopt_portable(exe_dir: Path) -> Path:
    try:
        write_portable_flag(exe_dir)
    except OSError as e:
        logger.debug("Could not write portable flag: %s", e)
    return _use(exe_dir)


def resolve_data_dir() -> Path:
    """Return the directory ZBB should use for servers/config/etc.,
    setting ZBB_DATA_DIR so `app.core.constants` picks it up. May instead
    hand over to the installed copy and exit the process."""
    if not getattr(sys, "frozen", False):
        # Dev mode: unchanged behavior (repo root), no marker/dialog.
        return Path(__file__).resolve().parent.parent.parent

    exe = Path(sys.executable).resolve()
    exe_dir = exe.parent
    if (exe_dir / PORTABLE_FLAG).exists():
        return _use(exe_dir)

    marker_path = _marker_path()
    marker = read_marker(marker_path)
    data_dir = Path(marker["data_dir"]) if marker.get("data_dir") else None
    if data_dir is not None and is_writable_dir(data_dir):
        if looks_like_zbb_data(exe_dir) and not _same_path(exe_dir, data_dir) and _is_app_folder(data_dir):
            # Two portable copies from before install support: the marker
            # points at the other copy's folder. Keep this one separate.
            return _adopt_portable(exe_dir)
        rescue_stray_data(exe_dir, data_dir)
        if sys.platform != "win32":
            return _use(data_dir)
        return _reconcile_install(marker, marker_path, exe, data_dir)

    if looks_like_zbb_data(exe_dir):
        # Pre-dates the data-dir choice: it already writes next to the exe.
        # Keep it that way -- no dialog, no disruption.
        return _adopt_portable(exe_dir)

    from app.ui import first_run_dialog as ui
    result = ui.ask_setup(exe, data_dir=None)
    return _apply_setup(result, exe, marker, marker_path)
