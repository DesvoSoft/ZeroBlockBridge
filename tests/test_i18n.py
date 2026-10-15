import ast
import ctypes
import datetime
import gettext
import re
import sys
from pathlib import Path

import pytest
from babel.messages.catalog import Catalog
from babel.messages.extract import extract_from_dir
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

from app.core import i18n
from app.services.backup_manager import BackupManager
from app.services.disk_usage import format_size
from app.ui import formatting

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "assets" / "locales"


@pytest.fixture
def spanish():
    assert i18n.set_language("es") == "es"


# ----------------------------------------------------------------------
# Language codes
# ----------------------------------------------------------------------
@pytest.mark.parametrize("code, expected", [
    ("es", "es"), ("es_ES", "es"), ("es-MX", "es"), ("ES", "es"), ("es_ES.UTF-8", "es"),
    ("Spanish_Spain.1252", "es"), ("en_US", "en"), ("English_United States", "en"),
    ("fr_FR", None), ("", None), ("  ", None), (None, None), (42, None),
])
def test_normalize(code, expected):
    assert i18n.normalize(code) == expected


def test_first_supported_skips_unknown_codes():
    assert i18n.first_supported(None, "de", "es_AR", "en") == "es"
    assert i18n.first_supported(None, "pt") is None


def test_code_for_name():
    assert i18n.code_for_name("Español") == "es"
    assert i18n.code_for_name("English") == "en"
    assert i18n.code_for_name("Klingon") is None


# ----------------------------------------------------------------------
# Switching and fallback
# ----------------------------------------------------------------------
def test_english_is_the_source_language():
    assert i18n.get_language() == "en"
    assert i18n._("Setup") == "Setup"


def test_spanish_catalog_translates(spanish):
    assert i18n.get_language() == "es"
    assert i18n._("Setup") == "Configuración"
    assert i18n.pgettext("decimal separator", ".") == ","


def test_unknown_message_falls_back_to_english(spanish):
    assert i18n._("Not a message anyone wrote") == "Not a message anyone wrote"


def test_unsupported_language_falls_back_to_english():
    assert i18n.set_language("fr") == "en"
    assert i18n._("Setup") == "Setup"


def test_missing_catalog_falls_back_to_english(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(i18n, "locale_dir", lambda: tmp_path)

    assert i18n.set_language("es") == "en"
    assert i18n.get_language() == "en"
    assert i18n._("Setup") == "Setup"
    assert "No usable es catalog" in caplog.text


def test_corrupt_catalog_falls_back_to_english(monkeypatch, tmp_path):
    (tmp_path / "es" / "LC_MESSAGES").mkdir(parents=True)
    (tmp_path / "es" / "LC_MESSAGES" / "zbb.mo").write_bytes(b"not a catalog at all")
    monkeypatch.setattr(i18n, "locale_dir", lambda: tmp_path)

    assert i18n.set_language("es") == "en"
    assert i18n._("Setup") == "Setup"


def test_switching_back_to_english_drops_the_catalog(spanish):
    assert i18n.set_language("en") == "en"
    assert i18n._("Setup") == "Setup"


def test_ngettext_uses_the_catalog_plural_forms(monkeypatch, tmp_path):
    catalog = Catalog(locale="es")
    catalog.add(("{n} file", "{n} files"), ("{n} archivo", "{n} archivos"))
    (tmp_path / "es" / "LC_MESSAGES").mkdir(parents=True)
    with open(tmp_path / "es" / "LC_MESSAGES" / "zbb.mo", "wb") as f:
        write_mo(f, catalog)
    monkeypatch.setattr(i18n, "locale_dir", lambda: tmp_path)
    i18n.set_language("es")

    assert i18n.ngettext("{n} file", "{n} files", 1) == "{n} archivo"
    assert i18n.ngettext("{n} file", "{n} files", 0) == "{n} archivos"
    assert i18n.ngettext("{n} file", "{n} files", 5) == "{n} archivos"


def test_ngettext_falls_back_to_english_plurals():
    assert i18n.ngettext("{n} file", "{n} files", 1) == "{n} file"
    assert i18n.ngettext("{n} file", "{n} files", 2) == "{n} files"


def test_n_marks_without_translating(spanish):
    assert i18n.N_("Setup") == "Setup"


# ----------------------------------------------------------------------
# OS language detection
# ----------------------------------------------------------------------
class _Kernel32:
    def __init__(self, langid):
        self.langid = langid

    def GetUserDefaultUILanguage(self):
        return self.langid


def _fake_windows(monkeypatch, langid):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", type("W", (), {"kernel32": _Kernel32(langid)})(), raising=False)


@pytest.mark.parametrize("langid, expected", [
    (0x0C0A, "es_ES"),   # Spanish (Spain), in locale.windows_locale
    (0x7C0A, "es"),      # an unlisted Spanish variant: primary language 0x0A
    (0x0409, "en_US"),
    (0x0407, "de_DE"),
])
def test_windows_ui_language(monkeypatch, langid, expected):
    _fake_windows(monkeypatch, langid)
    assert i18n._windows_ui_language() == expected


def test_windows_ui_language_without_windll(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delattr(ctypes, "windll", raising=False)
    assert i18n._windows_ui_language() is None


def test_windows_ui_language_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert i18n._windows_ui_language() is None


def _clear_locale_env(monkeypatch):
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)


def test_locale_language_reads_environment(monkeypatch):
    _clear_locale_env(monkeypatch)
    monkeypatch.setenv("LANGUAGE", "es_MX:en")
    assert i18n._locale_language() == "es_MX"


def test_locale_language_falls_back_to_process_locale(monkeypatch):
    _clear_locale_env(monkeypatch)
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: ("Spanish_Spain", "1252"))
    assert i18n._locale_language() == "Spanish_Spain"


def test_locale_language_survives_a_broken_locale(monkeypatch):
    _clear_locale_env(monkeypatch)

    def _broken():
        raise ValueError("unknown locale")
    monkeypatch.setattr(i18n.locale, "getlocale", _broken)
    assert i18n._locale_language() is None


def test_system_language_prefers_windows_ui_language(monkeypatch):
    monkeypatch.setattr(i18n, "_windows_ui_language", lambda: "es_ES")
    monkeypatch.setattr(i18n, "_locale_language", lambda: "en_US")
    assert i18n.system_language() == "es"


def test_system_language_falls_back_to_locale_then_english(monkeypatch):
    monkeypatch.setattr(i18n, "_windows_ui_language", lambda: "de_DE")
    monkeypatch.setattr(i18n, "_locale_language", lambda: "es_CR")
    assert i18n.system_language() == "es"
    monkeypatch.setattr(i18n, "_locale_language", lambda: None)
    assert i18n.system_language() == "en"


# ----------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------
def test_number_formats():
    assert i18n.format_number(2.345, 1) == "2.3"
    assert i18n.format_number(1234.5, 1) == "1234.5"
    assert i18n.format_percent(45) == "45%"


def test_number_formats_spanish(spanish):
    assert i18n.format_number(2.345, 1) == "2,3"
    assert i18n.format_number(7, 0) == "7"
    assert i18n.format_percent(45) == "45 %"
    assert i18n.format_percent(12.5, 1) == "12,5 %"


@pytest.mark.parametrize("value, en, es", [
    (0, "0 B", "0 B"),
    (512, "512 B", "512 B"),
    (2048, "2.0 KB", "2,0 KB"),
    (5 * 1024 ** 2, "5.0 MB", "5,0 MB"),
    (3 * 1024 ** 3, "3.0 GB", "3,0 GB"),
    (2 * 1024 ** 4, "2048.0 GB", "2048,0 GB"),
])
def test_format_size(value, en, es):
    assert i18n.format_size(value) == en == format_size(value)
    i18n.set_language("es")
    assert i18n.format_size(value) == es == format_size(value)


@pytest.mark.parametrize("count, en, es", [
    (950, "950", "950"),
    (15_300, "15.3K", "15,3 k"),
    (1_234_567, "1.2M", "1,2 M"),
])
def test_format_count(count, en, es):
    assert i18n.format_count(count) == en
    i18n.set_language("es")
    assert i18n.format_count(count) == es


def test_format_datetime_never_uses_the_process_locale(monkeypatch):
    moment = datetime.datetime(2026, 5, 2, 9, 5)
    assert i18n.format_datetime(moment) == "02 May 2026 09:05"
    i18n.set_language("es")
    assert i18n.format_datetime(moment) == "02 may 2026 09:05"
    assert i18n.format_datetime(datetime.datetime(2026, 9, 30, 23, 59)) == "30 sept 2026 23:59"


def test_every_month_has_a_spanish_abbreviation(spanish):
    names = [i18n.format_datetime(datetime.datetime(2026, m, 1)).split()[1] for m in range(1, 13)]
    assert names == ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"]


def test_ui_formatting_spanish(spanish):
    now = datetime.datetime(2026, 9, 16, 20, 0, 0)
    assert formatting.format_duration(45) == "45 s"
    assert formatting.format_duration(4800) == "1 h 20 min"
    assert formatting.format_duration(2 * 86400 + 3 * 3600) == "2 d 3 h"
    assert formatting.format_relative("2026-09-16T19:59:30", now) == "ahora mismo"
    assert formatting.format_relative("2026-09-16T19:55:00", now) == "hace 5 min"
    assert formatting.format_relative("2026-09-16T17:00:00", now) == "hace 3 h"
    assert formatting.format_relative("2026-09-14T20:00:00", now) == "hace 2 d"
    assert formatting.format_relative("2026-07-01T10:00:00", now) == "2026-07-01"
    assert formatting.format_memory(int(2.34 * 1024 ** 3)) == "RAM 2,3 GB"


def _backup(tmp_path, name):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(exist_ok=True)
    (backup_dir / name).write_bytes(b"x" * 1024 * 1024)
    manager = BackupManager.__new__(BackupManager)
    manager.backup_dir = backup_dir
    return manager


def test_backup_dates_and_sizes_follow_the_language(tmp_path):
    manager = _backup(tmp_path, "2025-05-02_00-00-00__auto.zip")
    assert manager.list_backups()[0]["date"] == "02 May 2025 00:00"
    assert manager.list_backups()[0]["size"] == "1.00 MB"

    i18n.set_language("es")
    entry = manager.list_backups()[0]
    assert entry["date"] == "02 may 2025 00:00"
    assert entry["size"] == "1,00 MB"
    assert manager.get_latest_backup()["date"] == "02 may 2025 00:00"


# ----------------------------------------------------------------------
# Catalogs
# ----------------------------------------------------------------------
def _po(lang):
    with open(LOCALES / lang / "LC_MESSAGES" / "zbb.po", "rb") as f:
        return read_po(f, locale=lang)


def _languages():
    return [code for code in i18n.LANGUAGES if code != i18n.DEFAULT_LANGUAGE]


@pytest.mark.parametrize("lang", _languages())
def test_compiled_catalog_matches_po(lang):
    """The committed .mo must be compiled from the committed .po
    (py tools/i18n.py compile)."""
    with open(LOCALES / lang / "LC_MESSAGES" / "zbb.mo", "rb") as f:
        compiled = gettext.GNUTranslations(f)
    for message in _po(lang):
        if not message.id or not message.string:
            continue
        if message.pluralizable:
            assert compiled.ngettext(message.id[0], message.id[1], 1) == message.string[0]
        elif message.context:
            assert compiled.pgettext(message.context, message.id) == message.string, message.id
        else:
            assert compiled.gettext(message.id) == message.string, message.id


@pytest.mark.parametrize("lang", _languages())
def test_every_marked_string_is_translated(lang):
    """Each string wrapped in _()/N_()/ngettext/pgettext under app/ has a
    non-fuzzy translation (run tools/i18n.py extract + update, translate,
    compile)."""
    catalog = _po(lang)
    missing, seen = [], 0
    for _file, _line, message, _comments, context in extract_from_dir(
            str(ROOT / "app"), keywords={"_": None, "N_": None, "ngettext": (1, 2), "pgettext": ((1, "c"), 2)}):
        msgid = message[0] if isinstance(message, (tuple, list)) else message
        entry = catalog.get(msgid, context=context)
        seen += 1
        if entry is None or not entry.string or entry.fuzzy:
            missing.append(msgid)
    assert seen > 50
    assert missing == []


_PLACEHOLDER = re.compile(r"\{(\w*)\}")


@pytest.mark.parametrize("lang", _languages())
def test_translations_keep_placeholders(lang):
    """A translation that drops or renames {name} would raise KeyError (or
    lose information) when formatted."""
    for message in _po(lang):
        if not message.id or not message.string:
            continue
        ids = message.id if message.pluralizable else (message.id,)
        strings = message.string if message.pluralizable else (message.string,)
        expected = set(_PLACEHOLDER.findall(ids[0]))
        for text in strings:
            assert set(_PLACEHOLDER.findall(text)) == expected, message.id


def _module_imports_translate(tree) -> bool:
    return any(isinstance(node, ast.ImportFrom) and node.module == "app.core.i18n"
               and any(alias.name == "_" and alias.asname is None for alias in node.names)
               for node in ast.walk(tree))


def _own_nodes(func):
    """Nodes of `func` excluding nested functions/classes/lambdas/comprehensions."""
    stack = list(func.body)
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
                                      ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                stack.append(child)


def test_no_function_shadows_the_translation_function():
    """`buttons, _, _ = ...` in a function that also calls `_()` makes `_`
    local to it and the call fails with UnboundLocalError."""
    offenders = []
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not _module_imports_translate(tree):
            continue
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            nodes = list(_own_nodes(func))
            assigns = any(isinstance(n, ast.Name) and n.id == "_" and isinstance(n.ctx, ast.Store) for n in nodes)
            calls = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_"
                        for n in nodes)
            if assigns and calls:
                offenders.append(f"{path.relative_to(ROOT)}:{func.lineno} {func.name}")
    assert offenders == []
