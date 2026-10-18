import ast
import ctypes
import datetime
import gettext
import io
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
    assert i18n._("Setup") == "Instalación"
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


@pytest.mark.parametrize("size", [6, 20, 100])
def test_truncated_catalog_falls_back_to_english(monkeypatch, tmp_path, size):
    """A cut-off .mo raises struct.error, not OSError: it must not crash the
    app before any window exists."""
    real = (LOCALES / "es" / "LC_MESSAGES" / "zbb.mo").read_bytes()
    (tmp_path / "es" / "LC_MESSAGES").mkdir(parents=True)
    (tmp_path / "es" / "LC_MESSAGES" / "zbb.mo").write_bytes(real[:size])
    monkeypatch.setattr(i18n, "locale_dir", lambda: tmp_path)

    assert i18n.set_language("es") == "en"


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
    """The committed .mo holds exactly the messages the committed .po compiles
    to (py tools/i18n.py compile) -- also catches translations removed from
    the .po but still in the .mo. Compared as messages, not bytes: Babel
    versions lay the file out differently and stamp their own version in
    the header entry ("")."""
    compiled = io.BytesIO()
    write_mo(compiled, _po(lang))
    compiled.seek(0)
    expected = gettext.GNUTranslations(compiled)._catalog
    with open(LOCALES / lang / "LC_MESSAGES" / "zbb.mo", "rb") as committed:
        actual = gettext.GNUTranslations(committed)._catalog
    actual.pop("", None)
    expected.pop("", None)
    assert actual == expected


@pytest.mark.parametrize("lang", _languages())
def test_every_marked_string_is_translated(lang):
    """Each string wrapped in _()/N_()/ngettext/pgettext under app/ has a
    non-fuzzy translation (run tools/i18n.py extract + update, translate,
    compile)."""
    catalog = _po(lang)
    missing, seen = [], 0
    for _file, _line, message, _comments, context in extract_from_dir(
            str(ROOT / "app"), keywords={"_": None, "N_": None, "ngettext": (1, 2), "pgettext": ((1, "c"), 2),
                      "bilingual": None, "bilingual_n": (1, 2)}):
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


_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _scope_nodes(scope, stop):
    """Nodes inside `scope`, not descending into nested nodes of type `stop`."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, stop):
            stack.extend(ast.iter_child_nodes(node))


def _binds_underscore(scope) -> bool:
    """`_` is local to this function/lambda: assigned, a parameter, or an
    `except ... as _` name (comprehension targets have their own scope)."""
    args = scope.args
    params = args.posonlyargs + args.args + args.kwonlyargs + [a for a in (args.vararg, args.kwarg) if a]
    if any(a.arg == "_" for a in params):
        return True
    comprehensions = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
    for node in _scope_nodes(scope, _SCOPES + (ast.ClassDef,) + comprehensions):
        if isinstance(node, ast.Name) and node.id == "_" and isinstance(node.ctx, ast.Store):
            return True
        if isinstance(node, ast.ExceptHandler) and node.name == "_":
            return True
    return False


def _shadowing_offenders(source: str) -> list[int]:
    """Line numbers of functions/lambdas where `_` is local but `_()` is
    called in them or in a nested lambda/comprehension that doesn't rebind it."""
    tree = ast.parse(source)
    offenders = []
    for scope in ast.walk(tree):
        if not isinstance(scope, _SCOPES) or not _binds_underscore(scope):
            continue
        nested = [n for n in _scope_nodes(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                  if isinstance(n, ast.Lambda) and n is not scope]
        rebinding = {id(n) for n in nested if _binds_underscore(n)}
        for node in _scope_nodes(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if isinstance(node, ast.Lambda) and id(node) in rebinding:
                continue
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_":
                offenders.append(scope.lineno)
                break
    return offenders


@pytest.mark.parametrize("source", [
    "def f():\n    a, _, _ = g()\n    return _('x')\n",
    "def f():\n    a, _ = g()\n    btn(command=lambda: _('x'))\n",
    "def f(_):\n    return _('x')\n",
    "f = lambda _: _('x')\n",
    "def f():\n    try:\n        g()\n    except OSError as _:\n        pass\n    return _('x')\n",
    "def f():\n    for _ in range(3):\n        h(_('x'))\n",
])
def test_shadowing_check_catches(source):
    assert _shadowing_offenders(source)


@pytest.mark.parametrize("source", [
    "def f():\n    return _('x')\n",
    "def f():\n    return [_('x') for _y in ()]\n",
    "def f():\n    a = [1 for _ in ()]\n    return _('x')\n",
    "def f():\n    a, _ = g()\n    return a\n",
    "def f():\n    btn(command=lambda _v: _('x'))\n",
])
def test_shadowing_check_allows(source):
    assert _shadowing_offenders(source) == []


def test_no_function_shadows_the_translation_function():
    """`buttons, _, _ = ...` in a function that also calls `_()` makes `_`
    local to it and the call fails with UnboundLocalError (or calls the
    tuple element)."""
    offenders = []
    for path in (ROOT / "app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if not _module_imports_translate(ast.parse(source)):
            continue
        offenders += [f"{path.relative_to(ROOT)}:{line}" for line in _shadowing_offenders(source)]
    assert offenders == []
