"""Validation of server names used to build paths under SERVERS_DIR."""

import os
import re
import sys


class UnsafePathError(ValueError):
    """A name or path that would reach outside the place it must stay in."""


# Windows strips trailing dots/spaces ("x." is "x", "..." is the parent
# folder itself) and maps device names to devices, whatever the extension.
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$", re.IGNORECASE)
_CONTROL_CHARS = {chr(c) for c in range(32)}
# Only Windows forbids these in names; elsewhere a server folder may use them.
_WINDOWS_CHARS = set('<>:"|?*')


def _forbidden_chars() -> set:
    chars = _CONTROL_CHARS | {"/", "\\"}
    return chars | _WINDOWS_CHARS if sys.platform == "win32" else chars


def check_server_name(server_name: str) -> str:
    """A server name is one folder directly under SERVERS_DIR, never a path,
    on every platform: no separators or control characters (on Windows also
    none of <>:"|?* and no device name like NUL), no trailing dot or space."""
    if (not isinstance(server_name, str) or not server_name.strip()
            or server_name in (".", "..") or server_name.endswith((".", " "))
            or set(server_name) & _forbidden_chars() or os.sep in server_name
            or (sys.platform == "win32" and _RESERVED.match(server_name))):
        raise UnsafePathError(f"Not a server name: {server_name!r}")
    return server_name


def is_valid_server_name(server_name: str) -> bool:
    try:
        check_server_name(server_name)
    except UnsafePathError:
        return False
    return True
