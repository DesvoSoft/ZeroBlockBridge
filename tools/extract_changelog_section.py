"""Extract a single version's section from docs/changelog.md.

Usage: python tools/extract_changelog_section.py <version> [--strict]
Prints the section body (heading excluded) for "## [<version>]" up to the
next "## [" heading or end of file. Used by the release workflow to feed
a curated release body instead of GitHub's auto-generated commit dump.

A prerelease tag (v2.1.0-rc1) falls back to the base version's section
(2.1.0) when no exact entry exists. With --strict, a missing section exits
non-zero so a tagged release build fails instead of publishing empty notes.
"""
import re
import sys
from pathlib import Path

CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "docs" / "changelog.md"


def extract_section(changelog_text: str, version: str) -> str | None:
    # [^\n]* for the heading tail: DOTALL would let .* swallow the whole file.
    pattern = re.compile(
        rf"^##\s*\[{re.escape(version)}\][^\n]*\n(.*?)(?=^##\s*\[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(changelog_text)
    if not match:
        return None
    return match.group(1).strip() or None


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--strict"]
    strict = "--strict" in sys.argv[1:]
    if len(args) != 1:
        print("usage: extract_changelog_section.py <version> [--strict]", file=sys.stderr)
        return 1

    # Release notes carry em dashes and other non-cp1252 glyphs; the Windows
    # runner would otherwise die on the redirect to release_notes.md.
    sys.stdout.reconfigure(encoding="utf-8")

    version = args[0].removeprefix("v")
    text = CHANGELOG_PATH.read_text(encoding="utf-8")

    section = extract_section(text, version)
    if section is None and "-" in version:
        section = extract_section(text, version.split("-")[0])

    if section is None:
        message = f"No changelog entry found for {version} in docs/changelog.md"
        if strict:
            print(message, file=sys.stderr)
            return 1
        print(f"_{message}._")
        return 0

    print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
