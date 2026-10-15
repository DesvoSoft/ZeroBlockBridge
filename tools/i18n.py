"""Translation catalogs (gettext, via Babel -- a dev dependency).

    py tools/i18n.py extract    # app/ -> assets/locales/zbb.pot
    py tools/i18n.py update     # merge the template into every <lang>/LC_MESSAGES/zbb.po
    py tools/i18n.py compile    # .po -> .mo (commit both)

Workflow for a new or changed string: wrap it in `_()` (or `N_()` for
module-level text), run extract + update, translate the new entries in each
.po, run compile and commit the .po and .mo together. The compiled .mo files
are committed so source runs and both packaging specs (which bundle assets/)
need no build step; tests/test_i18n.py fails when a .mo is stale or a marked
string has no translation.
"""

import argparse
import sys
from pathlib import Path

from babel.messages.frontend import CommandLineInterface

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "assets" / "locales"
TEMPLATE = LOCALES / "zbb.pot"
DOMAIN = "zbb"


def pybabel(*args: str) -> None:
    CommandLineInterface().run(["pybabel", "-q", *args])


def extract() -> None:
    pybabel("extract", "--no-location", "--sort-output", "--project=ZeroBlockBridge",
            "--copyright-holder=DesvoSoft", "-k", "N_", "-o", str(TEMPLATE), str(ROOT / "app"))


def update() -> None:
    pybabel("update", "--no-fuzzy-matching", "-D", DOMAIN, "-i", str(TEMPLATE), "-d", str(LOCALES))


def compile_catalogs() -> None:
    pybabel("compile", "--statistics", "-D", DOMAIN, "-d", str(LOCALES))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("extract", "update", "compile"))
    args = parser.parse_args()
    {"extract": extract, "update": update, "compile": compile_catalogs}[args.command]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
