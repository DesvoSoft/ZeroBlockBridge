"""Directory links (Windows junctions / POSIX symlinks) used to keep servers
that live in a custom folder visible under SERVERS_DIR.

Free of any `app.core.constants` dependency: `app.core.bootstrap` uses it
before the data directory is decided.
"""

import os
import stat
import subprocess
import sys

_CREATE_NO_WINDOW = 0x08000000


def create_junction(source: str, dest: str) -> None:
    """Link an external server folder into SERVERS_DIR.

    On Windows use a real junction (mklink /J): unlike symlinks it requires
    no admin rights or Developer Mode, so imports work on stock machines.
    Elsewhere a plain directory symlink works.
    """
    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", dest, source],
            capture_output=True, text=True, creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            raise OSError(f"mklink /J failed: {(result.stderr or result.stdout).strip()}")
    else:
        os.symlink(source, dest, target_is_directory=True)


def is_link(path) -> bool:
    """True for a symlink or a Windows junction (any reparse point) --
    os.path.islink() misses junctions on Python < 3.12."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def link_target(path) -> str:
    """Where a symlink/junction points, without the \\\\?\\ prefix Windows
    reports for junctions."""
    target = os.readlink(path)
    for prefix in ("\\\\?\\", "\\??\\"):
        if target.startswith(prefix):
            target = target[len(prefix):]
    return target


def remove_link(path) -> None:
    """Remove only the link itself, never the target's contents: junctions
    delete via rmdir, symlinks via unlink."""
    try:
        os.unlink(path)
    except OSError:
        os.rmdir(path)
