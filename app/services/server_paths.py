"""Validation of server names used to build paths under SERVERS_DIR."""

import os


class UnsafePathError(ValueError):
    """A name or path that would reach outside the place it must stay in."""


def check_server_name(server_name: str) -> str:
    """A server name is one folder under SERVERS_DIR, never a path."""
    if (not isinstance(server_name, str) or not server_name.strip() or server_name in (".", "..")
            or "/" in server_name or "\\" in server_name or os.sep in server_name or ":" in server_name):
        raise UnsafePathError(f"Not a server name: {server_name!r}")
    return server_name
