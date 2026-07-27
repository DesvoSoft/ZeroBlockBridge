"""Bump the app version across all source-of-truth files before a release.

Usage: python tools/bump_version.py 2.1.0

Updates app_config.APP_VERSION, packaging/version_info.txt, and inserts a
changelog.md template section for the new version (left for manual editing).
Does not commit or tag -- review the diff, fill in the changelog, then
commit and `git tag vX.Y.Z` yourself.
"""
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_CONFIG_PATH = ROOT / "app" / "core" / "app_config.py"
VERSION_INFO_PATH = ROOT / "packaging" / "version_info.txt"
CHANGELOG_PATH = ROOT / "docs" / "changelog.md"

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def bump_app_config(version: str) -> None:
    text = APP_CONFIG_PATH.read_text(encoding="utf-8")
    new_text = re.sub(r'APP_VERSION = "[^"]*"', f'APP_VERSION = "{version}"', text)
    APP_CONFIG_PATH.write_text(new_text, encoding="utf-8")


def bump_version_info(version: str) -> None:
    major, minor, patch = (int(p) for p in version.split("."))
    tup = f"({major}, {minor}, {patch}, 0)"
    dotted = f"{major}.{minor}.{patch}.0"

    text = VERSION_INFO_PATH.read_text(encoding="utf-8")
    text = re.sub(r"filevers=\([^)]*\)", f"filevers={tup}", text)
    text = re.sub(r"prodvers=\([^)]*\)", f"prodvers={tup}", text)
    text = re.sub(
        r"(StringStruct\('FileVersion', ')[^']*(')", rf"\g<1>{dotted}\g<2>", text
    )
    text = re.sub(
        r"(StringStruct\('ProductVersion', ')[^']*(')", rf"\g<1>{dotted}\g<2>", text
    )
    VERSION_INFO_PATH.write_text(text, encoding="utf-8")


def insert_changelog_template(version: str) -> None:
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    today = date.today().isoformat()
    template = (
        f"## [{version}] — {today}\n\n"
        "### Added\n- \n\n"
        "### Changed\n- \n\n"
        "### Fixed\n- \n\n"
    )
    marker = "---\n"
    idx = text.find(marker)
    if idx == -1:
        new_text = template + text
    else:
        insert_at = idx + len(marker)
        new_text = text[:insert_at] + "\n" + template + text[insert_at:]
    CHANGELOG_PATH.write_text(new_text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2 or not VERSION_RE.match(sys.argv[1]):
        print("usage: bump_version.py X.Y.Z", file=sys.stderr)
        return 1

    version = sys.argv[1]
    bump_app_config(version)
    bump_version_info(version)
    insert_changelog_template(version)

    print(f"Bumped to {version}. Fill in docs/changelog.md, then:")
    print(f'  git add -A && git commit -m "chore: bump version to {version}"')
    print(f"  git tag v{version} && git push origin main --tags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
