"""Extract a single version's section from docs/changelog.md.

Usage: python tools/extract_changelog_section.py <version>
Prints the section body (heading excluded) for "## [<version>]" up to the
next "## [" heading or end of file. Used by the release workflow to feed
a curated release body instead of GitHub's auto-generated commit dump.
"""
import re
import sys
from pathlib import Path

CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "docs" / "changelog.md"


def extract_section(changelog_text: str, version: str) -> str | None:
    pattern = re.compile(
        rf"^##\s*\[{re.escape(version)}\].*$\n(.*?)(?=^##\s*\[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(changelog_text)
    if not match:
        return None
    return match.group(1).strip()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: extract_changelog_section.py <version>", file=sys.stderr)
        return 1

    version = sys.argv[1].lstrip("v")
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    section = extract_section(text, version)

    if section is None:
        print(f"_No changelog entry found for {version} in docs/changelog.md._")
        return 0

    print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
