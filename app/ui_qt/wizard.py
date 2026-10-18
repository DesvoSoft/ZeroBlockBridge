"""Engine & Version step of the server wizard, as one dialog (spike scope:
it returns the choice and creates nothing)."""

from __future__ import annotations

import re

from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QRadioButton,
    QVBoxLayout,
)

from app.core.i18n import _

ENGINES = ("Vanilla", "Paper", "Purpur", "Fabric", "Forge", "NeoForge")
MODDED_ENGINES = ("Fabric", "Forge", "NeoForge")
MAX_SHOWN = 100


def version_sort_key(version: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", version))


class EngineVersionDialog(QDialog):
    def __init__(self, api, run_async, parent=None):
        super().__init__(parent)
        self._api = api
        self._run_async = run_async
        self._versions: list[str] = []
        self._seq = 0
        self.modpack = None

        self.setWindowTitle(_("Engine & Version"))
        self.setMinimumSize(520, 560)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        title = QLabel(_("Engine & Version"), objectName="title")
        root.addWidget(title)

        root.addWidget(QLabel(_("Server Engine:"), objectName="heading"))
        grid = QGridLayout()
        self._engines = QButtonGroup(self)
        for i, engine in enumerate(ENGINES):
            rb = QRadioButton(engine)
            self._engines.addButton(rb, i)
            grid.addWidget(rb, i // 3, i % 3)
        self._engines.button(0).setChecked(True)
        self._engines.idToggled.connect(lambda _id, on: on and self._load_versions())
        root.addLayout(grid)

        root.addWidget(QLabel(_("Version:"), objectName="heading"))
        row = QHBoxLayout()
        self._search = QLineEdit(placeholderText=_("e.g. 1.20.1"))
        self._search.textChanged.connect(self._render_versions)
        self._btn_refresh = QPushButton(_("Refresh"))
        self._btn_refresh.clicked.connect(self._refresh)
        row.addWidget(self._search, 1)
        row.addWidget(self._btn_refresh)
        root.addLayout(row)
        self._list = QListWidget(objectName="versions")
        root.addWidget(self._list, 1)
        self._status = QLabel("", objectName="muted")
        root.addWidget(self._status)

        card = QFrame(objectName="card")
        cl = QVBoxLayout(card)
        cl.addWidget(QLabel(_("Modpack (optional)"), objectName="heading"))
        hint = QLabel(_("Import a Modrinth .mrpack or a modpack's Server Pack .zip. "
                        "Engine and version are set for you."), objectName="muted")
        hint.setWordWrap(True)
        cl.addWidget(hint)
        mrow = QHBoxLayout()
        self._btn_modpack = QPushButton(_("Import modpack…"))
        self._btn_modpack.clicked.connect(self._pick_modpack)
        self._btn_remove = QPushButton(_("Remove"))
        self._btn_remove.clicked.connect(self._remove_modpack)
        self._btn_remove.hide()
        self._modpack_label = QLabel("", objectName="muted")
        self._modpack_label.setWordWrap(True)
        mrow.addWidget(self._btn_modpack)
        mrow.addWidget(self._btn_remove)
        mrow.addWidget(self._modpack_label, 1)
        cl.addLayout(mrow)
        root.addWidget(card)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(_("Next"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._listener = api.creation.on_versions_refreshed(self._load_versions)
        self.finished.connect(lambda _r: self._listener.cancel())
        self._load_versions()

    # -- versions ----------------------------------------------------------
    @property
    def engine(self) -> str:
        return ENGINES[self._engines.checkedId()]

    @property
    def version(self) -> str | None:
        item = self._list.currentItem()
        return item.text() if item else None

    def _load_versions(self) -> None:
        # versions() may block on the first call (network): off the GUI thread,
        # and a newer request wins over a slower older one.
        self._seq += 1
        seq, engine = self._seq, self.engine
        self._set_status(_("Loading versions..."))

        def done(versions):
            if seq == self._seq:
                self._versions = sorted(versions or [], key=version_sort_key, reverse=True)
                self._render_versions()

        self._run_async(lambda: self._api.creation.versions(engine), done)

    def _render_versions(self) -> None:
        text = self._search.text().strip()
        shown = [v for v in self._versions if text in v]
        if self.modpack:
            shown = [v for v in shown if v == self.modpack.mc_version]
        self._list.clear()
        self._list.addItems(shown[:MAX_SHOWN])
        if shown:
            self._list.setCurrentRow(0)
        self._set_status("" if shown else _("No versions found."))

    def _set_status(self, text: str) -> None:
        self._status.setText(text)
        self._status.setVisible(bool(text))

    def _refresh(self) -> None:
        self._btn_refresh.setEnabled(False)
        self._run_async(self._api.creation.refresh_versions,
                        lambda _r: self._btn_refresh.setEnabled(True))

    # -- modpack -----------------------------------------------------------
    def _pick_modpack(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, _("Import modpack…"), "", _("Modpacks") + " (*.mrpack *.zip)")
        if not path:
            return
        self._modpack_label.setText(_("Reading modpack…"))

        def done(result):
            if isinstance(result, Exception):
                self._modpack_label.setText(str(result))
                return
            self._set_modpack(result)

        def inspect():
            try:
                return self._api.creation.inspect_modpack(path)
            except Exception as exc:  # ContentImportError carries a user message
                return exc

        self._run_async(inspect, done)

    def _set_modpack(self, info) -> None:
        self.modpack = info
        self._modpack_label.setText(info.describe())
        self._btn_remove.show()
        loader = (info.loader or "").lower()
        for i, engine in enumerate(ENGINES):
            button = self._engines.button(i)
            match = engine.lower() == loader
            button.setEnabled(match)
            if match:
                button.setChecked(True)
        self._render_versions()

    def _remove_modpack(self) -> None:
        self.modpack = None
        self._modpack_label.setText("")
        self._btn_remove.hide()
        for button in self._engines.buttons():
            button.setEnabled(True)
        self._render_versions()
