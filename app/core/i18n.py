"""Translations and locale-aware formatting.

Plain gettext: catalogs live in `assets/locales/<lang>/LC_MESSAGES/zbb.mo`
(compiled from the `.po` next to it, see tools/i18n.py) and English is the
source language, so a missing catalog or message falls back to English.

The language is chosen once at startup (`set_language`) and kept for the
whole run; changing it in Settings takes effect after a restart. Strings
must therefore be translated when they are shown, not at import time: mark
module-level text with `N_()` and pass it through `_()` where it is used.

Importable before the data directory is resolved (stdlib +
`app.core.resources` only) -- the setup dialogs use it, and they must never
pull in `app.core.constants` (see bootstrap.py).
"""

import datetime
import gettext
import locale
import logging
import os
import struct
import sys

from app.core.resources import assets_dir

logger = logging.getLogger(__name__)

DOMAIN = "zbb"
DEFAULT_LANGUAGE = "en"
# Shown in each language's own name, so never translated.
LANGUAGES = {"en": "English", "es": "Español"}

# Windows primary language IDs (low 10 bits of a LANGID).
_WINDOWS_PRIMARY = {0x09: "en", 0x0A: "es"}
# What `locale.getlocale()` returns on Windows ("Spanish_Spain").
_LOCALE_NAMES = {"english": "en", "spanish": "es"}

_translations: gettext.NullTranslations = gettext.NullTranslations()
_language = DEFAULT_LANGUAGE


def locale_dir():
    return assets_dir() / "locales"


def normalize(code) -> str | None:
    """'es_ES', 'es-MX', 'Spanish_Spain.1252' -> 'es'; None when the
    language isn't one ZBB ships."""
    if not isinstance(code, str) or not code.strip():
        return None
    base = code.strip().lower().replace("-", "_")
    for sep in ("_", ".", "@"):
        base = base.split(sep, 1)[0]
    base = _LOCALE_NAMES.get(base, base)
    return base if base in LANGUAGES else None


def first_supported(*codes) -> str | None:
    """The first of `codes` that names a supported language."""
    for code in codes:
        lang = normalize(code)
        if lang:
            return lang
    return None


def _windows_ui_language() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError) as e:
        logger.debug("GetUserDefaultUILanguage failed: %s", e)
        return None
    return locale.windows_locale.get(langid) or _WINDOWS_PRIMARY.get(langid & 0x3FF)


def _locale_language() -> str | None:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        if os.environ.get(var):
            return os.environ[var].split(":", 1)[0]
    try:
        return locale.getlocale()[0]
    except ValueError as e:
        logger.debug("Could not read the process locale: %s", e)
        return None


def code_for_name(name: str) -> str | None:
    """'Español' -> 'es' (the names shown in language pickers)."""
    return next((code for code, shown in LANGUAGES.items() if shown == name), None)


def system_language() -> str:
    """The OS display language when ZBB has it, otherwise English."""
    return first_supported(_windows_ui_language(), _locale_language()) or DEFAULT_LANGUAGE


def set_language(code) -> str:
    """Switch every later `_()` to `code` (unsupported -> English).
    Returns the language actually in use."""
    global _translations, _language
    lang = normalize(code) or DEFAULT_LANGUAGE
    translations = gettext.NullTranslations()
    if lang != DEFAULT_LANGUAGE:
        try:
            translations = gettext.translation(DOMAIN, localedir=str(locale_dir()), languages=[lang])
        except (OSError, ValueError, struct.error) as e:  # missing, corrupt or truncated: English
            logger.warning("No usable %s catalog, using English: %s", lang, e)
            lang = DEFAULT_LANGUAGE
    _translations, _language = translations, lang
    return lang


def get_language() -> str:
    return _language


_catalogs: dict = {}


def catalog(code) -> gettext.NullTranslations:
    """The catalog for `code`, independent of the language the app runs in
    (`_()` and friends always use the app's). For text rendered for another
    audience than the UI, e.g. a Discord channel. Unsupported or unreadable
    -> English. Cached, and safe to call from any thread."""
    lang = normalize(code) or DEFAULT_LANGUAGE
    cached = _catalogs.get(lang)
    if cached is not None:
        return cached
    translations = gettext.NullTranslations()
    if lang != DEFAULT_LANGUAGE:
        try:
            translations = gettext.translation(DOMAIN, localedir=str(locale_dir()), languages=[lang])
        except (OSError, ValueError, struct.error) as e:
            logger.warning("No usable %s catalog, using English: %s", lang, e)
    _catalogs[lang] = translations
    return translations


def resolve_language(preference) -> str:
    """A language preference ("auto", "en", "es", anything else) -> a code.
    "auto" and unknown values follow the app's language."""
    return normalize(preference) or _language


def _(message: str) -> str:
    return _translations.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translations.ngettext(singular, plural, n)


def pgettext(context: str, message: str) -> str:
    return _translations.pgettext(context, message)


def N_(message: str) -> str:
    """Marks text for extraction without translating it yet (module-level
    labels); translate it with `_()` where it is shown."""
    return message


# ----------------------------------------------------------------------
# Text shown to the user that must also reach an English-only place
# ----------------------------------------------------------------------
class Bilingual(str):
    """Translated text that remembers its English source. It is a plain
    `str` (the translation) for toasts and dialogs; `english()` gives what
    the console, logs and Discord use."""
    english: str

    def __new__(cls, translated: str, english: str):
        text = super().__new__(cls, translated)
        text.english = english
        return text


def bilingual(message: str, **fields) -> Bilingual:
    """`_(message).format(**fields)`, keeping the English rendering."""
    return Bilingual(_(message).format(**fields), message.format(**fields))


def bilingual_n(singular: str, plural: str, n: int, **fields) -> Bilingual:
    english = singular if n == 1 else plural
    return Bilingual(ngettext(singular, plural, n).format(**fields), english.format(**fields))


def english(text) -> str:
    """The English form of a `Bilingual`; any other text as it is."""
    return getattr(text, "english", text)


# ----------------------------------------------------------------------
# Choices: an internal key per option, a translated label to show
# ----------------------------------------------------------------------
# A choice list is `((key, N_("Label")), ...)`. Widgets show the labels and
# hand the chosen label back; code compares and stores only the key, so a
# translation can never change what is saved or matched.

def choice_labels(choices) -> list[str]:
    """The translated labels, in order."""
    return [_(label) for _key, label in choices]


def choice_label(choices, key) -> str:
    """The translated label of `key`; the first option's when `key` is unknown."""
    label = next((label for k, label in choices if k == key), choices[0][1])
    return _(label)


def choice_key(choices, label, default=None):
    """The key whose translated label is `label`; `default` when none is."""
    return next((key for key, text in choices if _(text) == label), default)


# ----------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------
_MONTHS = (N_("Jan"), N_("Feb"), N_("Mar"), N_("Apr"), N_("May"), N_("Jun"),
           N_("Jul"), N_("Aug"), N_("Sep"), N_("Oct"), N_("Nov"), N_("Dec"))


def format_number(value: float, decimals: int = 0, language=None) -> str:
    """2.5 -> '2.5' in English, '2,5' in Spanish. No digit grouping: the
    numbers shown are sizes and compact counts, never long figures.
    `language` renders for that language instead of the app's."""
    separator = (catalog(language).pgettext("decimal separator", ".") if language
                 else pgettext("decimal separator", "."))
    return f"{value:.{decimals}f}".replace(".", separator)


def format_percent(value: float, decimals: int = 0) -> str:
    """'45%' / '45 %'."""
    return _("{value}%").format(value=format_number(value, decimals))


def format_size(num_bytes: int) -> str:
    """Human-readable size: 1234 -> '1.2 KB' ('1,2 KB'), 0 -> '0 B'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{format_number(size, 0 if unit == 'B' else 1)} {unit}"
        size /= 1024
    return f"{format_number(size, 1)} GB"


def format_count(count: int) -> str:
    """Compact large counts: 950, '15.3K', '1.2M' ('15,3 k', '1,2 M')."""
    if count >= 1_000_000:
        return _("{value}M").format(value=format_number(count / 1_000_000, 1))
    if count >= 1_000:
        return _("{value}K").format(value=format_number(count / 1_000, 1))
    return str(count)


def format_datetime(moment: datetime.datetime) -> str:
    """'15 Oct 2026 14:30' / '15 oct 2026 14:30' -- month names come from
    the catalog, never from the process locale (strftime's %b)."""
    month = _(_MONTHS[moment.month - 1])
    return f"{moment.day:02d} {month} {moment.year} {moment:%H:%M}"
