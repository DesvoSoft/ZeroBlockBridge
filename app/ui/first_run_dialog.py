"""Setup dialogs shown before the main window: first-run setup / install,
"already installed" for a second downloaded copy, and uninstall.

Runs from `app.core.bootstrap.resolve_data_dir()` (and the `--uninstall`
entry point), BEFORE `app.ui.main` (and therefore `app.core.constants`) is
ever imported -- see bootstrap.py. This module and everything it imports
must stay free of any `app.core.constants` dependency, directly or
transitively (that rules out `app.ui.ui_components`, which imports
SERVERS_DIR at module level). tests/test_bootstrap.py guards this.

No app window exists yet at this point, so each dialog is its own `ctk.CTk`
root rather than a `CTkToplevel`.
"""

import logging
import sys
import threading
import tkinter.filedialog
from pathlib import Path

import customtkinter as ctk

from app.core import installer
from app.core.app_config import AppConfig
from app.core.bootstrap import (
    MODE_INSTALLED, MODE_MANUAL, SetupResult, is_writable_dir, read_marker, write_marker,
    _marker_path,
)
from app.core.resources import assets_dir
from app.ui.icons import clear_cache, icon
from app.ui.win_effects import apply_rounded_corners

logger = logging.getLogger(__name__)

_WRAP = 420


def _init_theme() -> None:
    theme_path = assets_dir() / "zbb_theme.json"
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme(str(theme_path) if theme_path.exists() else "green")


def is_newer(this_version: str, other_version: str | None) -> bool:
    """True when `this_version` is strictly newer than `other_version`."""
    if not other_version:
        return True
    try:
        from packaging.version import Version
        return Version(this_version) > Version(other_version)
    except Exception:
        return this_version != other_version


class _BootDialog(ctk.CTk):
    """Shared chrome: one card with pages swapped in place."""

    def __init__(self, title: str):
        super().__init__()
        self.title(f"Zero Block Bridge - {title}")
        self.resizable(False, False)
        self.configure(fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.page = None

    # -- layout helpers --------------------------------------------------
    def new_page(self):
        if self.page is not None:
            self.page.destroy()
        self.page = ctk.CTkFrame(self, fg_color="transparent")
        self.page.pack(padx=30, pady=25, fill="both", expand=True)
        return self.page

    def heading(self, icon_name: str, title: str, text: str = "", color=None):
        ctk.CTkLabel(self.page, text="", image=icon(icon_name, 28, color or AppConfig.COLOR_BTN_PRIMARY),
                     ).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(self.page, text=title, font=AppConfig.FONT_HEADING,
                     wraplength=_WRAP, justify="left").pack(anchor="w", pady=(0, 6))
        if text:
            self.body(text, pady=(0, 14))

    def body(self, text: str, muted: bool = False, pady=(0, 8), parent=None):
        label = ctk.CTkLabel(
            parent or self.page, text=text, justify="left", anchor="w", wraplength=_WRAP,
            font=AppConfig.FONT_BODY_SMALL if muted else AppConfig.FONT_BODY,
            text_color=AppConfig.COLOR_TEXT_GRAY if muted else AppConfig.COLOR_TEXT_PRIMARY,
        )
        label.pack(anchor="w", fill="x", pady=pady)
        return label

    def error_label(self):
        label = ctk.CTkLabel(self.page, text="", font=AppConfig.FONT_BODY_SMALL, justify="left",
                             wraplength=_WRAP, text_color=AppConfig.COLOR_STATUS_ERROR)
        label.pack(anchor="w", pady=(6, 0))
        return label

    def button_row(self):
        row = ctk.CTkFrame(self.page, fg_color="transparent")
        row.pack(fill="x", pady=(16, 0))
        return row

    @staticmethod
    def primary(parent, text, command, danger=False, width=170):
        return ctk.CTkButton(
            parent, text=text, command=command, width=width, height=36,
            corner_radius=AppConfig.RADIUS_BTN,
            fg_color=AppConfig.COLOR_BTN_DANGER if danger else AppConfig.COLOR_BTN_PRIMARY,
            hover_color=AppConfig.COLOR_BTN_DANGER_HOVER if danger else AppConfig.COLOR_BTN_PRIMARY_HOVER,
        )

    @staticmethod
    def ghost(parent, text, command, width=150):
        return ctk.CTkButton(
            parent, text=text, command=command, width=width, height=36,
            corner_radius=AppConfig.RADIUS_BTN, fg_color=AppConfig.COLOR_BTN_GHOST,
            hover_color=AppConfig.COLOR_BTN_GHOST_HOVER, text_color=AppConfig.COLOR_TEXT_PRIMARY,
        )

    def run_in_background(self, work, on_done):
        """Run `work()` off the Tk thread; `on_done(error_or_None, value)`
        runs back on it."""
        box = {}

        def _worker():
            try:
                box["value"] = work()
            except Exception as e:  # surfaced in the dialog, not swallowed
                logger.exception("Setup step failed")
                box["error"] = e

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        def _poll():
            if thread.is_alive():
                self.after(100, _poll)
            else:
                on_done(box.get("error"), box.get("value"))
        self.after(100, _poll)

    def show(self):
        apply_rounded_corners(self)
        self.refit()
        self.focus_force()
        self.mainloop()

    def refit(self):
        try:
            self.update_idletasks()
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self.geometry(f"{w}x{h}+{max((sw - w) // 2, 0)}+{max((sh - h) // 3, 0)}")
        except Exception as e:
            logger.debug("Setup dialog centering failed: %s", e)

    def _on_close(self):
        self.destroy()

    def destroy(self):
        super().destroy()
        # Another Tk root (the next dialog or the main window) comes next.
        clear_cache()


# ----------------------------------------------------------------------
# First run / install offer
# ----------------------------------------------------------------------
class _SetupDialog(_BootDialog):
    def __init__(self, exe: Path, data_dir: Path | None):
        super().__init__("Setup")
        self.result: SetupResult | None = None
        self._exe = exe
        self._existing_data = data_dir
        self._data_dir = data_dir or installer.standard_data_dir()
        self._windows = sys.platform == "win32"
        self._choice = ctk.StringVar(value="install" if self._windows else "standard")
        self._var_start_menu = ctk.BooleanVar(value=True)
        self._var_desktop = ctk.BooleanVar(value=True)
        self._custom_picked = False
        self._build_choice_page()

    def _build_choice_page(self):
        self.new_page()
        upgrade = self._existing_data is not None
        if upgrade:
            self.heading("download", "Install ZeroBlockBridge?",
                         "Install it on this PC so it opens from the Start menu and always "
                         "finds your servers. Nothing in your data folder changes.")
        else:
            self.heading("folder", "Welcome to ZeroBlockBridge",
                         "Choose how to set it up on this PC.")

        if self._windows:
            install_card = self._option(
                "install", "Install on this PC (recommended)",
                f"App: {installer.default_install_dir()}",
            )
            self._data_label = self.body(f"Servers and backups: {self._data_dir}", muted=True,
                                         pady=(0, 2), parent=install_card)
            self._data_label.pack_configure(padx=(28, 0))
            extras = ctk.CTkFrame(install_card, fg_color="transparent")
            extras.pack(anchor="w", padx=(28, 0), pady=(4, 0))
            ctk.CTkCheckBox(extras, text="Start menu shortcut", variable=self._var_start_menu,
                            font=AppConfig.FONT_BODY_SMALL, fg_color=AppConfig.COLOR_BTN_PRIMARY,
                            corner_radius=AppConfig.RADIUS_BADGE).pack(anchor="w", pady=2)
            ctk.CTkCheckBox(extras, text="Desktop shortcut", variable=self._var_desktop,
                            font=AppConfig.FONT_BODY_SMALL, fg_color=AppConfig.COLOR_BTN_PRIMARY,
                            corner_radius=AppConfig.RADIUS_BADGE).pack(anchor="w", pady=2)
            if not upgrade:
                ctk.CTkButton(
                    extras, text="Change data folder...", command=self._pick_data_dir,
                    height=24, width=10, fg_color="transparent", hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                    text_color=AppConfig.COLOR_LINK, font=AppConfig.FONT_BODY_SMALL,
                ).pack(anchor="w", pady=(2, 0))
            if upgrade:
                self._option("manual", "Not now", "Keep running this file. You won't be asked again.")
            else:
                self._option("portable", "Portable (no install)",
                             f"Runs from this folder and keeps servers next to the app:\n{self._exe.parent}")
        else:
            self._option("standard", "Standard (recommended)", str(installer.standard_data_dir()))
            self._option("portable", "Portable (next to the app)", str(self._exe.parent))
            self._custom_card = self._option("custom", "Choose folder...", "No folder selected yet")

        self._error = self.error_label()
        row = self.button_row()
        self._btn_continue = self.primary(row, "", self._confirm)
        self._btn_continue.pack(side="right")
        self._refresh_button()

    def _option(self, value, title, subtitle):
        card = ctk.CTkFrame(self.page, fg_color="transparent")
        card.pack(fill="x", pady=5)
        ctk.CTkRadioButton(
            card, text=title, variable=self._choice, value=value, font=AppConfig.FONT_LABEL,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, command=lambda: self._on_pick(value),
        ).pack(anchor="w")
        sub = self.body(subtitle, muted=True, pady=(2, 0), parent=card)
        sub.pack_configure(padx=(28, 0))
        card.subtitle = sub
        return card

    def _on_pick(self, value):
        self._error.configure(text="")
        if value == "custom":
            self._pick_data_dir()
        self._refresh_button()

    def _refresh_button(self):
        text = "Install" if self._choice.get() == "install" else "Continue"
        self._btn_continue.configure(text=text, state="normal")

    def _pick_data_dir(self):
        chosen = tkinter.filedialog.askdirectory(title="Choose data folder", mustexist=False)
        if not chosen:
            if self._choice.get() == "custom" and not self._custom_picked:
                # Cancelled with nothing picked before: don't leave "custom"
                # selected while it points at nothing.
                self._choice.set("standard")
                self._refresh_button()
            return
        self._custom_picked = True
        self._data_dir = Path(chosen)
        if self._windows:
            self._data_label.configure(text=f"Servers and backups: {self._data_dir}")
        else:
            self._custom_card.subtitle.configure(text=str(self._data_dir))

    def _confirm(self):
        choice = self._choice.get()
        if choice == "portable":
            if not is_writable_dir(self._exe.parent):
                self._error.configure(text=f"Can't write to {self._exe.parent}. Move the app "
                                           "to another folder or install it instead.")
                return
            self.result = SetupResult("portable", self._exe.parent)
            self.destroy()
            return
        if choice == "manual":
            self.result = SetupResult(MODE_MANUAL, self._data_dir)
            self.destroy()
            return
        if choice in ("standard", "custom"):
            target = installer.standard_data_dir() if choice == "standard" else self._data_dir
            if not is_writable_dir(target):
                self._error.configure(text=f"Can't write to {target}. Pick another folder.")
                return
            self.result = SetupResult(MODE_MANUAL, target)
            self.destroy()
            return

        if not is_writable_dir(self._data_dir):
            self._error.configure(text=f"Can't write to {self._data_dir}. Pick another folder.")
            return
        self._btn_continue.configure(text="Installing...", state="disabled")
        start_menu, desktop = self._var_start_menu.get(), self._var_desktop.get()
        self.run_in_background(
            lambda: installer.install(self._exe, AppConfig.APP_VERSION,
                                      start_menu=start_menu, desktop=desktop),
            self._on_installed,
        )

    def _on_installed(self, error, value):
        if error is not None:
            self._error.configure(text=f"Install failed: {error}")
            self._refresh_button()
            return
        installed, failures = value
        self.result = SetupResult(MODE_INSTALLED, self._data_dir, installed)
        if installer.same_path(installed, self._exe):
            self.destroy()  # already running the installed copy
            return
        self._build_done_page(installed, failures)

    def _build_done_page(self, installed: Path, failures: list[str]):
        self.new_page()
        self.heading("check", "ZeroBlockBridge is installed",
                     "From now on, open it from the Start menu or the desktop shortcut.")
        self.body(f"Installed at:\n{installed}", muted=True)
        self.body(f"You can delete the file you downloaded:\n{self._exe}", muted=True)
        if failures:
            self.body("Some shortcuts couldn't be created (you can add them later in "
                      "Settings > Storage):\n" + "\n".join(failures), muted=True)
        row = self.button_row()
        self.primary(row, "Open ZeroBlockBridge", self.destroy, width=200).pack(side="right")
        self.refit()


def ask_setup(exe: Path, data_dir: Path | None) -> SetupResult | None:
    """First-run setup (`data_dir` None) or install offer for a data folder
    chosen earlier. Returns None if the window was closed without choosing."""
    _init_theme()
    dialog = _SetupDialog(exe, data_dir)
    dialog.show()
    return dialog.result


# ----------------------------------------------------------------------
# A second (downloaded) copy while an installed one exists
# ----------------------------------------------------------------------
class _AlreadyInstalledDialog(_BootDialog):
    def __init__(self, exe: Path, installed: Path, installed_version: str | None):
        super().__init__("Already installed")
        self.result = "cancel"
        self._exe = exe
        self._installed = installed
        this_version = AppConfig.APP_VERSION
        newer = is_newer(this_version, installed_version)

        self.new_page()
        self.heading("check", "ZeroBlockBridge is already installed",
                     "Open the installed app from the Start menu or the desktop shortcut. "
                     "That's the one to use.")
        self.body(f"Installed app (version {installed_version or 'unknown'}):\n{installed}", muted=True)
        if newer:
            self.body(f"The file you opened is version {this_version}, newer than the "
                      "installed one. Update to keep using the same shortcuts and servers.",
                      pady=(6, 8))
        else:
            self.body(f"You opened another copy (version {this_version}):\n{exe}\n"
                      "You can delete it.", muted=True)
        self._error = self.error_label()

        row = self.button_row()
        if newer:
            self._btn_main = self.primary(row, f"Update to {this_version}", self._update)
        else:
            self._btn_main = self.primary(row, "Open installed app", self._open)
        self._btn_main.pack(side="right")
        self.ghost(row, "Run this copy", self._run, width=130).pack(side="right", padx=(0, 8))

    def _open(self):
        self.result = "open"
        self.destroy()

    def _run(self):
        self.result = "run"
        self.destroy()

    def _update(self):
        self._btn_main.configure(text="Updating...", state="disabled")
        self.run_in_background(
            lambda: installer.update(self._exe, self._installed, AppConfig.APP_VERSION),
            self._on_updated,
        )

    def _on_updated(self, error, _value):
        if error is None:
            self.result = "updated"
            self.destroy()
            return
        if isinstance(error, PermissionError):
            msg = "The installed app is open. Close ZeroBlockBridge and try again."
        else:
            msg = f"Update failed: {error}"
        self._error.configure(text=msg)
        self._btn_main.configure(text=f"Update to {AppConfig.APP_VERSION}", state="normal")


def ask_already_installed(exe: Path, installed: Path, installed_version: str | None) -> str:
    """Returns "updated", "open", "run" or "cancel"."""
    _init_theme()
    dialog = _AlreadyInstalledDialog(exe, installed, installed_version)
    dialog.show()
    return dialog.result


# ----------------------------------------------------------------------
# Uninstall (Settings > Apps runs `ZeroBlockBridge.exe --uninstall`)
# ----------------------------------------------------------------------
def _app_is_running(data_dir: Path | None) -> bool:
    if data_dir is None:
        return False
    lock = data_dir / "config" / ".zbb.lock"
    try:
        pid = int(lock.read_text().strip())
    except (OSError, ValueError):
        return False
    from app.core.single_instance import SingleInstanceLock
    return SingleInstanceLock._is_pid_alive(pid)


class _UninstallDialog(_BootDialog):
    def __init__(self, exe: Path, marker: dict):
        super().__init__("Uninstall")
        self.exit_code = 1
        self._exe = exe
        self._marker = marker
        self._data_dir = Path(marker["data_dir"]) if marker.get("data_dir") else None
        self._var_delete_data = ctk.BooleanVar(value=False)

        self.new_page()
        if _app_is_running(self._data_dir):
            self.heading("warning", "Close ZeroBlockBridge first",
                         "ZeroBlockBridge is running. Close it (and stop any server), "
                         "then uninstall again.", color=AppConfig.COLOR_ACCENT_AMBER)
            row = self.button_row()
            self.primary(row, "OK", self.destroy, width=120).pack(side="right")
            return

        self.heading("trash", "Uninstall ZeroBlockBridge?",
                     "Removes the app, its shortcuts and its entry in Windows Settings.",
                     color=AppConfig.COLOR_BTN_DANGER)
        if self._data_dir is not None:
            ctk.CTkCheckBox(
                self.page, text="Also delete my servers, backups and settings",
                variable=self._var_delete_data, font=AppConfig.FONT_BODY,
                fg_color=AppConfig.COLOR_BTN_DANGER, corner_radius=AppConfig.RADIUS_BADGE,
            ).pack(anchor="w", pady=(0, 4))
            self.body(f"{self._data_dir}\nServers you created in other folders are never deleted.",
                      muted=True)
        self._error = self.error_label()
        row = self.button_row()
        self._btn_uninstall = self.primary(row, "Uninstall", self._uninstall, danger=True, width=140)
        self._btn_uninstall.pack(side="right")
        self.ghost(row, "Cancel", self.destroy, width=100).pack(side="right", padx=(0, 8))

    def _uninstall(self):
        self._btn_uninstall.configure(text="Removing...", state="disabled")
        delete_data = self._var_delete_data.get()
        self.run_in_background(lambda: self._do_uninstall(delete_data), self._on_done)

    def _do_uninstall(self, delete_data: bool):
        installer.remove_shortcuts()
        installer.unregister_uninstall()
        marker_path = _marker_path()
        if delete_data and self._data_dir is not None:
            installer.remove_data_dir(self._data_dir)
            marker_path.unlink(missing_ok=True)
        else:
            # Keep pointing at the data so a later download finds the servers.
            keep = {k: v for k, v in self._marker.items() if k not in ("mode", "exe_path", "version")}
            write_marker(keep, marker_path)
        installer.schedule_removal(self._exe)

    def _on_done(self, error, _value):
        if error is not None:
            self._error.configure(text=f"Uninstall failed: {error}")
            self._btn_uninstall.configure(text="Uninstall", state="normal")
            return
        self.exit_code = 0
        self.new_page()
        self.heading("check", "ZeroBlockBridge was uninstalled")
        row = self.button_row()
        self.primary(row, "Close", self.destroy, width=120).pack(side="right")
        self.refit()


def run_uninstall() -> int:
    _init_theme()
    dialog = _UninstallDialog(Path(sys.executable).resolve(), read_marker())
    dialog.show()
    return dialog.exit_code
