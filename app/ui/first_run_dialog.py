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

from app.core import i18n, installer
from app.core.app_config import AppConfig
from app.core.bootstrap import (
    MODE_INSTALLED, MODE_MANUAL, SetupResult, is_writable_dir, read_marker, use_stored_language,
    write_marker, _marker_path,
)
from app.core.i18n import _
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
        self.set_title(title)
        self.resizable(False, False)
        self.configure(fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.page = None
        self._busy = False

    def set_title(self, title: str):
        self.title(f"Zero Block Bridge - {title}")

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
        self._busy = True

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
                self._busy = False
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
        # Closing mid-install/uninstall would kill the (daemon) worker half
        # way and leave a partial copy or a half-deleted folder.
        if not self._busy:
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
        super().__init__(_("Setup"))
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

    def _language_row(self):
        """Language picker, top right of the first page: picking one
        rebuilds the page in it (and it is saved with the setup choice)."""
        row = ctk.CTkFrame(self.page, fg_color="transparent")
        row.pack(fill="x", pady=(0, 4))
        menu = ctk.CTkOptionMenu(
            row, values=list(i18n.LANGUAGES.values()), command=self._on_language, width=120, height=28,
            corner_radius=AppConfig.RADIUS_INPUT, font=AppConfig.FONT_BODY_SMALL,
            fg_color=AppConfig.COLOR_BTN_GHOST, button_color=AppConfig.COLOR_BTN_GHOST,
            button_hover_color=AppConfig.COLOR_BTN_GHOST_HOVER, text_color=AppConfig.COLOR_TEXT_PRIMARY,
        )
        menu.set(i18n.LANGUAGES[i18n.get_language()])
        menu.pack(side="right")
        ctk.CTkLabel(row, text=_("Language"), font=AppConfig.FONT_BODY_SMALL,
                     text_color=AppConfig.COLOR_TEXT_GRAY).pack(side="right", padx=(0, 8))

    def _on_language(self, name: str):
        code = i18n.code_for_name(name)
        if code is None or code == i18n.get_language():
            return
        i18n.set_language(code)
        self.set_title(_("Setup"))
        self._build_choice_page()
        self.refit()

    def _build_choice_page(self):
        self.new_page()
        self._language_row()
        upgrade = self._existing_data is not None
        if upgrade:
            self.heading("download", _("Install ZeroBlockBridge?"),
                         _("Install it on this PC so it opens from the Start menu and always "
                           "finds your servers. Nothing in your data folder changes."))
        else:
            self.heading("folder", _("Welcome to ZeroBlockBridge"),
                         _("Choose how to set it up on this PC."))

        if self._windows:
            install_card = self._option(
                "install", _("Install on this PC (recommended)"),
                _("App: {path}").format(path=installer.default_install_dir()),
            )
            self._data_label = self.body(self._data_text(), muted=True, pady=(0, 2), parent=install_card)
            self._data_label.pack_configure(padx=(28, 0))
            extras = ctk.CTkFrame(install_card, fg_color="transparent")
            extras.pack(anchor="w", padx=(28, 0), pady=(4, 0))
            ctk.CTkCheckBox(extras, text=_("Start menu shortcut"), variable=self._var_start_menu,
                            font=AppConfig.FONT_BODY_SMALL, fg_color=AppConfig.COLOR_BTN_PRIMARY,
                            corner_radius=AppConfig.RADIUS_BADGE).pack(anchor="w", pady=2)
            ctk.CTkCheckBox(extras, text=_("Desktop shortcut"), variable=self._var_desktop,
                            font=AppConfig.FONT_BODY_SMALL, fg_color=AppConfig.COLOR_BTN_PRIMARY,
                            corner_radius=AppConfig.RADIUS_BADGE).pack(anchor="w", pady=2)
            if not upgrade:
                ctk.CTkButton(
                    extras, text=_("Change data folder..."), command=self._pick_data_dir,
                    height=24, width=10, fg_color="transparent", hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                    text_color=AppConfig.COLOR_LINK, font=AppConfig.FONT_BODY_SMALL,
                ).pack(anchor="w", pady=(2, 0))
            if upgrade:
                self._option("manual", _("Not now"), _("Keep running this file. You won't be asked again."))
            else:
                self._option("portable", _("Portable (no install)"),
                             _("Runs from this folder and keeps servers next to the app:\n{path}").format(
                                 path=self._exe.parent))
        else:
            self._option("standard", _("Standard (recommended)"), str(installer.standard_data_dir()))
            self._option("portable", _("Portable (next to the app)"), str(self._exe.parent))
            self._custom_card = self._option(
                "custom", _("Choose folder..."),
                str(self._data_dir) if self._custom_picked else _("No folder selected yet"))

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
        text = _("Install") if self._choice.get() == "install" else _("Continue")
        self._btn_continue.configure(text=text, state="normal")

    def _data_text(self) -> str:
        return _("Servers and backups: {path}").format(path=self._data_dir)

    def _pick_data_dir(self):
        chosen = tkinter.filedialog.askdirectory(title=_("Choose data folder"), mustexist=False)
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
            self._data_label.configure(text=self._data_text())
        else:
            self._custom_card.subtitle.configure(text=str(self._data_dir))

    def _confirm(self):
        choice = self._choice.get()
        language = i18n.get_language()
        if choice == "portable":
            if not is_writable_dir(self._exe.parent):
                self._error.configure(text=_("Can't write to {path}. Move the app to another folder "
                                             "or install it instead.").format(path=self._exe.parent))
                return
            self.result = SetupResult("portable", self._exe.parent, language=language)
            self.destroy()
            return
        if choice == "manual":
            self.result = SetupResult(MODE_MANUAL, self._data_dir, language=language)
            self.destroy()
            return
        if choice in ("standard", "custom"):
            target = installer.standard_data_dir() if choice == "standard" else self._data_dir
            if not is_writable_dir(target):
                self._error.configure(text=_("Can't write to {path}. Pick another folder.").format(path=target))
                return
            self.result = SetupResult(MODE_MANUAL, target, language=language)
            self.destroy()
            return

        if not is_writable_dir(self._data_dir):
            self._error.configure(text=_("Can't write to {path}. Pick another folder.").format(path=self._data_dir))
            return
        self._btn_continue.configure(text=_("Installing..."), state="disabled")
        start_menu, desktop = self._var_start_menu.get(), self._var_desktop.get()
        self.run_in_background(
            lambda: installer.install(self._exe, AppConfig.APP_VERSION,
                                      start_menu=start_menu, desktop=desktop),
            self._on_installed,
        )

    def _on_installed(self, error, value):
        if error is not None:
            self._error.configure(text=_("Install failed: {error}").format(error=error))
            self._refresh_button()
            return
        installed, failures = value
        self.result = SetupResult(MODE_INSTALLED, self._data_dir, installed, language=i18n.get_language())
        if installer.same_path(installed, self._exe):
            self.destroy()  # already running the installed copy
            return
        self._build_done_page(installed, failures)

    def _build_done_page(self, installed: Path, failures: list[str]):
        self.new_page()
        self.heading("check", _("ZeroBlockBridge is installed"),
                     _("From now on, open it from the Start menu or the desktop shortcut."))
        self.body(_("Installed at:\n{path}").format(path=installed), muted=True)
        self.body(_("You can delete the file you downloaded:\n{path}").format(path=self._exe), muted=True)
        if failures:
            self.body(_("Some shortcuts couldn't be created (you can add them later in "
                        "Settings > Storage):\n{failures}").format(failures="\n".join(failures)), muted=True)
        row = self.button_row()
        self.primary(row, _("Open ZeroBlockBridge"), self.destroy, width=200).pack(side="right")
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
        super().__init__(_("Already installed"))
        self.result = "cancel"
        self._exe = exe
        self._installed = installed
        this_version = AppConfig.APP_VERSION
        newer = is_newer(this_version, installed_version)

        self.new_page()
        self.heading("check", _("ZeroBlockBridge is already installed"),
                     _("Open the installed app from the Start menu or the desktop shortcut. "
                       "That's the one to use."))
        self.body(_("Installed app (version {version}):\n{path}").format(
            version=installed_version or _("unknown"), path=installed), muted=True)
        if newer:
            self.body(_("The file you opened is version {version}, newer than the installed one. "
                        "Update to keep using the same shortcuts and servers.").format(version=this_version),
                      pady=(6, 8))
        else:
            self.body(_("You opened another copy (version {version}):\n{path}\nYou can delete it.").format(
                version=this_version, path=exe), muted=True)
        self._error = self.error_label()

        row = self.button_row()
        if newer:
            self._btn_main = self.primary(row, self._update_text(), self._update)
        else:
            self._btn_main = self.primary(row, _("Open installed app"), self._open)
        self._btn_main.pack(side="right")
        self.ghost(row, _("Run this copy"), self._run, width=130).pack(side="right", padx=(0, 8))

    @staticmethod
    def _update_text() -> str:
        return _("Update to {version}").format(version=AppConfig.APP_VERSION)

    def _open(self):
        self.result = "open"
        self.destroy()

    def _run(self):
        if self._busy:  # an update is copying over the installed exe
            return
        self.result = "run"
        self.destroy()

    def _update(self):
        self._btn_main.configure(text=_("Updating..."), state="disabled")
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
            msg = _("The installed app is open. Close ZeroBlockBridge and try again.")
        else:
            msg = _("Update failed: {error}").format(error=error)
        self._error.configure(text=msg)
        self._btn_main.configure(text=self._update_text(), state="normal")


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


def uninstall_target(running_exe: Path, marker: dict) -> Path:
    """The exe to remove: the recorded install, even when the uninstall was
    started from some other copy."""
    if marker.get("mode") == MODE_INSTALLED and marker.get("exe_path"):
        return Path(marker["exe_path"])
    return running_exe


class _UninstallDialog(_BootDialog):
    def __init__(self, exe: Path, marker: dict):
        super().__init__(_("Uninstall"))
        self.exit_code = 1
        self.remove_on_exit: Path | None = None
        self._exe = uninstall_target(exe, marker)
        self._marker = marker
        self._data_dir = Path(marker["data_dir"]) if marker.get("data_dir") else None
        self._var_delete_data = ctk.BooleanVar(value=False)

        self.new_page()
        if _app_is_running(self._data_dir):
            self.heading("warning", _("Close ZeroBlockBridge first"),
                         _("ZeroBlockBridge is running. Close it (and stop any server), "
                           "then uninstall again."), color=AppConfig.COLOR_ACCENT_AMBER)
            row = self.button_row()
            self.primary(row, _("OK"), self.destroy, width=120).pack(side="right")
            return

        self.heading("trash", _("Uninstall ZeroBlockBridge?"),
                     _("Removes the app, its shortcuts and its entry in Windows Settings."),
                     color=AppConfig.COLOR_BTN_DANGER)
        if self._data_dir is not None:
            ctk.CTkCheckBox(
                self.page, text=_("Also delete my servers, backups and settings"),
                variable=self._var_delete_data, font=AppConfig.FONT_BODY,
                fg_color=AppConfig.COLOR_BTN_DANGER, corner_radius=AppConfig.RADIUS_BADGE,
            ).pack(anchor="w", pady=(0, 4))
            self.body(_("{path}\nServers you created in other folders are never deleted.").format(
                path=self._data_dir), muted=True)
        self._error = self.error_label()
        row = self.button_row()
        self._btn_uninstall = self.primary(row, _("Uninstall"), self._uninstall, danger=True, width=140)
        self._btn_uninstall.pack(side="right")
        # Through _on_close: ignored while removing, like the window's X.
        self.ghost(row, _("Cancel"), self._on_close, width=100).pack(side="right", padx=(0, 8))

    def _uninstall(self):
        self._btn_uninstall.configure(text=_("Removing..."), state="disabled")
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
        # The exe is deleted once this process has exited (see run_uninstall).
        self.remove_on_exit = self._exe

    def _on_done(self, error, _value):
        if error is not None:
            self._error.configure(text=_("Uninstall failed: {error}").format(error=error))
            self._btn_uninstall.configure(text=_("Uninstall"), state="normal")
            return
        self.exit_code = 0
        self.new_page()
        self.heading("check", _("ZeroBlockBridge was uninstalled"))
        row = self.button_row()
        self.primary(row, _("Close"), self.destroy, width=120).pack(side="right")
        self.refit()


def run_uninstall() -> int:
    _init_theme()
    marker = read_marker()
    use_stored_language(marker)
    dialog = _UninstallDialog(Path(sys.executable).resolve(), marker)
    dialog.show()
    if dialog.remove_on_exit is not None:
        installer.schedule_removal(dialog.remove_on_exit)
    return dialog.exit_code
