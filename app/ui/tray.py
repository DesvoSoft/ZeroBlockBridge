"""System tray icon: keeps ZBB (and its servers/tunnel) running with the
window hidden. Built on pystray; every menu callback runs on pystray's own
thread, so actions are marshalled back to the Tk loop with `app.after`.
"""

import logging
import sys

from app.core.constants import ASSETS_DIR

logger = logging.getLogger(__name__)

# What the window's close button does (setting "close_action").
CLOSE_ASK, CLOSE_TRAY, CLOSE_EXIT = "ask", "tray", "exit"
CLOSE_ACTIONS = (CLOSE_ASK, CLOSE_TRAY, CLOSE_EXIT)


def tray_supported() -> bool:
    """pystray works out of the box on Windows/macOS; on Linux it needs an
    AppIndicator/Xorg backend that may be missing, so don't offer it there."""
    if not sys.platform.startswith(("win", "darwin")):
        return False
    try:
        import pystray  # noqa: F401
    except Exception as e:  # missing or broken backend
        logger.info("System tray unavailable: %s", e)
        return False
    return True


def resolve_close_action(setting, tray_ok: bool) -> str:
    """What clicking X should do, given the saved preference. Without a
    tray there is nothing to minimize to, so X always exits."""
    if not tray_ok:
        return CLOSE_EXIT
    return setting if setting in CLOSE_ACTIONS else CLOSE_ASK


class TrayIcon:
    def __init__(self, app, on_open, on_exit):
        self._app = app
        self._on_open = on_open
        self._on_exit = on_exit
        self._icon = None
        self._notified = False

    @property
    def visible(self) -> bool:
        return self._icon is not None

    def show(self, status: str = "") -> None:
        if self._icon is not None:
            return
        import pystray
        from PIL import Image

        image = Image.open(ASSETS_DIR / "logo.png")
        menu = pystray.Menu(
            pystray.MenuItem("Open ZeroBlockBridge", self._marshal(self._on_open), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._marshal(self._on_exit)),
        )
        title = "ZeroBlockBridge" + (f" - {status}" if status else "")
        self._icon = pystray.Icon("ZeroBlockBridge", image, title, menu)
        self._icon.run_detached()
        if not self._notified:
            self._notified = True
            try:
                self._icon.notify("ZeroBlockBridge is still running here. "
                                  "Right-click the icon to open or exit.", "ZeroBlockBridge")
            except Exception as e:  # notifications are optional
                logger.debug("Tray notification failed: %s", e)

    def hide(self) -> None:
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception as e:
                logger.debug("Tray icon stop failed: %s", e)

    def _marshal(self, fn):
        def _callback(icon=None, item=None):
            try:
                self._app.after(0, fn)
            except RuntimeError as e:  # Tk already gone
                logger.debug("Tray action dropped: %s", e)
        return _callback
