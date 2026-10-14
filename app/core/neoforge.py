"""NeoForge build <-> Minecraft version mapping (pure, no I/O).

NeoForge numbers its builds after the Minecraft version they target:
  * 1.x era:  "<minor>.<patch>.<build>"        21.1.77  -> MC 1.21.1
                                               21.0.167 -> MC 1.21
                                               20.4.251 -> MC 1.20.4
  * 26.x era: "<year>.<drop>.<patch>.<build>"  26.1.2.117 -> MC 26.1.2
                                               26.3.0.77  -> MC 26.3
Builds may end in "-beta"; NeoForge for MC 1.20.1 was published as
net/neoforged/forge (Forge-compatible) and isn't covered here.
Source: https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge
"""

import re
from typing import Iterable, Optional

MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"
VERSIONS_API = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"

_BUILD_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?(-beta)?$")


def _parts(build: str):
    match = _BUILD_RE.match(build or "")
    if not match:
        return None
    major, minor, third, fourth, beta = match.groups()
    return int(major), int(minor), int(third), (int(fourth) if fourth is not None else None), bool(beta)


def mc_version(build: str) -> Optional[str]:
    """Minecraft version a NeoForge build targets, or None if unrecognised
    (e.g. April-fools "0.25w14craftmine.3-beta")."""
    parts = _parts(build)
    if parts is None:
        return None
    major, minor, third, fourth, _beta = parts
    if fourth is None:
        if major < 20:
            return None
        return f"1.{major}" if minor == 0 else f"1.{major}.{minor}"
    return f"{major}.{minor}" if third == 0 else f"{major}.{minor}.{third}"


def is_stable(build: str) -> bool:
    parts = _parts(build)
    return parts is not None and not parts[4]


def _sort_key(build: str):
    major, minor, third, fourth, beta = _parts(build)
    return (major, minor, third, fourth or 0, 0 if beta else 1)


def best_build(builds: Iterable[str], minecraft: str) -> Optional[str]:
    """Newest stable build for `minecraft`, else the newest beta, else None."""
    matching = [b for b in builds if mc_version(b) == minecraft]
    if not matching:
        return None
    stable = [b for b in matching if is_stable(b)]
    return max(stable or matching, key=_sort_key)


def supported_mc_versions(builds: Iterable[str]) -> list:
    """Minecraft versions with at least one NeoForge build, newest first."""
    found = {}
    for build in builds:
        mc = mc_version(build)
        if mc:
            found[mc] = True
    return sorted(found, key=lambda v: tuple(int(n) for n in v.split(".")), reverse=True)


def installer_url(build: str) -> str:
    return f"{MAVEN}/{build}/neoforge-{build}-installer.jar"
