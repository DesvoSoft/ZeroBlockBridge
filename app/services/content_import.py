"""Import an existing world or a modpack into a server being created.

Worlds: a world folder (the one holding level.dat, e.g. from
.minecraft/saves) or a .zip of one -- wrapper folders are fine.

Modpacks:
  * Modrinth .mrpack (or a .zip that contains modrinth.index.json): mods are
    downloaded from the manifest, see mrpack_installer.
  * Server pack .zip (what CurseForge/most pack authors publish as "Server
    Pack"): its mods/config/etc. are copied in; ZBB installs the loader.
  * A CurseForge *client* export (manifest.json) can't be installed without
    CurseForge's API key -- rejected with a pointer to the server pack.

`inspect_*` read only; `import_world` / `install_modpack` write into a
server folder.
"""

import json
import logging
import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.core.fs_links import is_link, remove_link

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]

SUPPORTED_LOADERS = ("Fabric", "Forge")

# mrpack dependency key -> loader display name
_MRPACK_LOADERS = {
    "fabric-loader": "Fabric",
    "forge": "Forge",
    "neoforge": "NeoForge",
    "quilt-loader": "Quilt",
}

# Never copied from a server pack: ZBB installs the loader/jars itself and
# writes its own launch config and EULA.
_SERVERPACK_SKIP_DIRS = {"libraries", ".fabric", "versions", "logs", "crash-reports", "jre", "java"}
_SERVERPACK_SKIP_EXT = (".jar", ".bat", ".cmd", ".sh", ".ps1", ".command", ".exe")
_SERVERPACK_SKIP_FILES = {"eula.txt", "user_jvm_args.txt", "variables.txt", "server-icon.png"}
# Never copied from a world: the running game's lock.
_WORLD_SKIP_FILES = {"session.lock"}


class ContentImportError(ValueError):
    """Friendly, user-facing reason a world/modpack can't be imported."""


@dataclass
class WorldInfo:
    path: str
    name: str
    is_zip: bool
    root: str  # folder holding level.dat: a path, or an in-zip prefix ("" or "x/")


@dataclass
class ModpackInfo:
    path: str
    kind: str  # "mrpack" | "serverpack"
    name: str
    mc_version: Optional[str] = None
    loader: Optional[str] = None
    loader_version: Optional[str] = None
    mod_count: int = 0
    root: str = ""  # server pack: in-zip prefix of the pack's top folder
    notes: list = field(default_factory=list)

    @property
    def supported(self) -> bool:
        return self.loader is None or self.loader in SUPPORTED_LOADERS

    def describe(self) -> str:
        parts = []
        if self.loader:
            parts.append(f"{self.loader} {self.loader_version or ''}".strip())
        if self.mc_version:
            parts.append(f"Minecraft {self.mc_version}")
        if self.mod_count:
            parts.append(f"{self.mod_count} mods")
        return " · ".join(parts)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _safe_dest(base_dir: str, rel_path: str) -> str:
    """Join rel_path under base_dir, rejecting traversal outside it (zip-slip)."""
    base = os.path.realpath(base_dir)
    dest = os.path.realpath(os.path.join(base, rel_path.replace("\\", "/")))
    if os.path.commonpath([base, dest]) != base:
        raise ContentImportError(f"Unsafe path in archive: {rel_path}")
    return dest


def _open_zip(path: str) -> zipfile.ZipFile:
    if not zipfile.is_zipfile(path):
        raise ContentImportError("That file isn't a valid .zip archive.")
    return zipfile.ZipFile(path, "r")


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path.rstrip("\\/")))[0]


def _clear_dir(path: str) -> None:
    if is_link(path):
        remove_link(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


# ----------------------------------------------------------------------
# Worlds
# ----------------------------------------------------------------------
def _find_world_dir(folder: str, max_depth: int = 2) -> Optional[str]:
    if os.path.isfile(os.path.join(folder, "level.dat")):
        return folder
    if max_depth <= 0:
        return None
    try:
        children = sorted(e for e in os.listdir(folder) if os.path.isdir(os.path.join(folder, e)))
    except OSError:
        return None
    for child in children:
        found = _find_world_dir(os.path.join(folder, child), max_depth - 1)
        if found:
            return found
    return None


def inspect_world(path: str) -> WorldInfo:
    if os.path.isdir(path):
        root = _find_world_dir(path)
        if root is None:
            raise ContentImportError(
                "No Minecraft world found in that folder (it needs a level.dat). "
                "Pick the world's own folder, e.g. .minecraft/saves/<world>.")
        return WorldInfo(path=path, name=os.path.basename(root.rstrip("\\/")), is_zip=False, root=root)

    if os.path.isfile(path):
        with _open_zip(path) as zf:
            candidates = [n for n in zf.namelist()
                          if n.replace("\\", "/").split("/")[-1] == "level.dat"]
        if not candidates:
            raise ContentImportError("No Minecraft world found in that .zip (it needs a level.dat).")
        # Shallowest level.dat is the world root (DIM folders hold none).
        best = min(candidates, key=lambda n: n.count("/"))
        prefix = best[: -len("level.dat")]
        name = prefix.rstrip("/").split("/")[-1] if prefix else _stem(path)
        return WorldInfo(path=path, name=name, is_zip=True, root=prefix)

    raise ContentImportError("That world file or folder doesn't exist.")


def import_world(info: WorldInfo, server_dir: str, level_name: str = "world",
                 progress: Optional[ProgressFn] = None) -> None:
    """Copy the world into `server_dir/level_name`, replacing what's there."""
    dest = os.path.join(server_dir, level_name)
    if progress:
        progress(f"Importing world '{info.name}'...")
    _clear_dir(dest)

    if not info.is_zip:
        shutil.copytree(info.root, dest, ignore=shutil.ignore_patterns(*_WORLD_SKIP_FILES))
        return

    os.makedirs(dest, exist_ok=True)
    with _open_zip(info.path) as zf:
        for member in zf.infolist():
            name = member.filename.replace("\\", "/")
            if not name.startswith(info.root) or name.endswith("/"):
                continue
            rel = name[len(info.root):]
            if not rel or rel.split("/")[-1] in _WORLD_SKIP_FILES:
                continue
            target = _safe_dest(dest, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


# ----------------------------------------------------------------------
# Modpacks
# ----------------------------------------------------------------------
def _inspect_mrpack(path: str, zf: zipfile.ZipFile) -> ModpackInfo:
    try:
        manifest = json.loads(zf.read("modrinth.index.json").decode("utf-8"))
    except (KeyError, ValueError) as e:
        raise ContentImportError(f"The modpack manifest is unreadable: {e}") from e
    deps = manifest.get("dependencies", {}) or {}
    loader = loader_version = None
    for key, display in _MRPACK_LOADERS.items():
        if key in deps:
            loader, loader_version = display, deps[key]
            break
    files = manifest.get("files", []) or []
    server_files = [f for f in files if (f.get("env") or {}).get("server") != "unsupported"]
    return ModpackInfo(
        path=path, kind="mrpack", name=manifest.get("name") or _stem(path),
        mc_version=deps.get("minecraft"), loader=loader, loader_version=loader_version,
        mod_count=len(server_files),
    )


_FORGE_JAR_RE = re.compile(r"(?:^|/)forge-(\d+\.\d+(?:\.\d+)?)-(\d+(?:\.\d+)+)(?:-[a-z]+)?\.jar$")
_FORGE_LIB_RE = re.compile(r"libraries/net/minecraftforge/forge/(\d+\.\d+(?:\.\d+)?)-(\d+(?:\.\d+)+)/")
_NEOFORGE_RE = re.compile(r"(?:^|/)(?:libraries/net/neoforged/neoforge/|neoforge-)(\d+(?:\.\d+)+)")
_FABRIC_LOADER_RE = re.compile(r"libraries/net/fabricmc/fabric-loader/(\d+(?:\.\d+)+)/")
_FABRIC_MC_RE = re.compile(r"libraries/net/fabricmc/intermediary/(\d+\.\d+(?:\.\d+)?)/")
_QUILT_RE = re.compile(r"libraries/org/quiltmc/quilt-loader/")


def _pack_root(names: list) -> str:
    """In-zip prefix of the pack's content: server packs are often wrapped
    in one top-level folder."""
    if any(n.startswith("mods/") for n in names):
        return ""
    tops = {n.split("/", 1)[0] for n in names if n.strip("/")}
    if len(tops) == 1:
        top = next(iter(tops))
        if any(n.startswith(top + "/") for n in names):
            return top + "/"
    return ""


def _read_variables(zf: zipfile.ZipFile, root: str) -> dict:
    """ServerStarter-style variables.txt (MINECRAFT_VERSION=..., MODLOADER=...)."""
    try:
        text = zf.read(root + "variables.txt").decode("utf-8", "replace")
    except KeyError:
        return {}
    out = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip().upper()] = value.strip().strip('"')
    return out


def _inspect_serverpack(path: str, zf: zipfile.ZipFile, names: list) -> ModpackInfo:
    root = _pack_root(names)
    rel_names = [n[len(root):] for n in names if n.startswith(root)]
    mods = [n for n in rel_names if n.startswith("mods/") and n.endswith(".jar")]
    if not mods:
        raise ContentImportError(
            "This .zip has no mods/ folder, so it doesn't look like a server pack. "
            "Use a Modrinth .mrpack or the pack's \"Server Pack\" download.")

    info = ModpackInfo(path=path, kind="serverpack", name=_stem(path), mod_count=len(mods), root=root)
    joined = "\n".join(rel_names)

    variables = _read_variables(zf, root)
    loader_var = variables.get("MODLOADER", "").lower()
    if variables.get("MINECRAFT_VERSION"):
        info.mc_version = variables["MINECRAFT_VERSION"]
    if loader_var:
        info.loader = {"forge": "Forge", "fabric": "Fabric", "neoforge": "NeoForge",
                       "quilt": "Quilt"}.get(loader_var, variables["MODLOADER"])
        info.loader_version = variables.get("MODLOADER_VERSION") or None

    if info.loader is None:
        m = _FORGE_LIB_RE.search(joined) or _FORGE_JAR_RE.search(joined)
        if m:
            info.loader, info.mc_version, info.loader_version = "Forge", m.group(1), m.group(2)
        elif _NEOFORGE_RE.search(joined):
            info.loader = "NeoForge"
        elif _QUILT_RE.search(joined):
            info.loader = "Quilt"
        elif "fabric-server-launch.jar" in joined or _FABRIC_LOADER_RE.search(joined):
            info.loader = "Fabric"
            loader_m = _FABRIC_LOADER_RE.search(joined)
            mc_m = _FABRIC_MC_RE.search(joined)
            info.loader_version = loader_m.group(1) if loader_m else None
            info.mc_version = info.mc_version or (mc_m.group(1) if mc_m else None)

    if info.loader is None or info.mc_version is None:
        info.notes.append("Couldn't tell which loader/Minecraft version this pack needs. "
                          "Pick the same ones the pack's page lists.")
    return info


def inspect_modpack(path: str) -> ModpackInfo:
    if not os.path.isfile(path):
        raise ContentImportError("That modpack file doesn't exist.")
    with _open_zip(path) as zf:
        names = [n.replace("\\", "/") for n in zf.namelist()]
        if "modrinth.index.json" in names:
            info = _inspect_mrpack(path, zf)
        elif any(n.split("/")[-1] == "manifest.json" and n.count("/") <= 1 for n in names) \
                and not any("/mods/" in "/" + n for n in names):
            raise ContentImportError(
                "This is a CurseForge client modpack. On the pack's CurseForge page, open "
                "Files, download the \"Server Pack\" and import that .zip instead.")
        else:
            info = _inspect_serverpack(path, zf, names)

    if not info.supported:
        raise ContentImportError(
            f"This modpack needs {info.loader}, which ZeroBlockBridge doesn't support yet "
            f"(supported: {', '.join(SUPPORTED_LOADERS)}).")
    return info


def _copy_serverpack(info: ModpackInfo, server_dir: str, progress: Optional[ProgressFn]) -> int:
    copied = 0
    with _open_zip(info.path) as zf:
        members = [m for m in zf.infolist() if not m.filename.endswith("/")]
        for member in members:
            name = member.filename.replace("\\", "/")
            if not name.startswith(info.root):
                continue
            rel = name[len(info.root):]
            parts = rel.split("/")
            if parts[0] in _SERVERPACK_SKIP_DIRS:
                continue
            if len(parts) == 1 and (rel.lower().endswith(_SERVERPACK_SKIP_EXT)
                                    or rel.lower() in _SERVERPACK_SKIP_FILES):
                continue
            target = _safe_dest(server_dir, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            copied += 1
            if progress and copied % 50 == 0:
                progress(f"Copying modpack files ({copied})...")
    return copied


def install_modpack(info: ModpackInfo, server_dir: str, server_type: str, mc_version: str,
                    progress: Optional[ProgressFn] = None) -> str:
    """Install the pack into `server_dir`; returns a one-line summary."""
    if info.kind == "mrpack":
        from app.services.mrpack_installer import install_mrpack
        summary = install_mrpack(info.path, os.path.basename(server_dir), progress_callback=progress,
                                 server_type=server_type, mc_version=mc_version, server_dir=server_dir)
        text = f"{summary['installed']} mods installed"
        if summary["skipped_client"]:
            text += f", {summary['skipped_client']} client-only skipped"
        if summary["failed"]:
            text += f", {summary['failed']} failed to download"
        return text

    if progress:
        progress("Copying modpack files...")
    copied = _copy_serverpack(info, server_dir, progress)
    return f"{info.mod_count} mods ({copied} files) copied"
