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
_SERVERPACK_SKIP_FILES = {"eula.txt", "user_jvm_args.txt", "variables.txt", "server-icon.png",
                          # Written by the Fabric installer; the pack's copy can name a
                          # server jar that was never copied (root jars are skipped).
                          "fabric-server-launcher.properties"}
# Never copied from a world: the running game's lock.
_WORLD_SKIP_FILES = {"session.lock"}
# Junk folder macOS adds to zips it creates.
_MACOS_JUNK = "__MACOSX/"

# Hard ceiling on what one archive may unpack to, on top of the free-space
# check: real worlds/modpacks stay far below it, a zip bomb doesn't.
MAX_UNPACKED_BYTES = 32 * 1024 ** 3
# Keep this much disk free after unpacking.
_DISK_MARGIN_BYTES = 1024 ** 3
_RESERVED_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                   *(f"lpt{i}" for i in range(1, 10))}
_INVALID_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')


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

    @property
    def pinned_loader_version(self) -> Optional[str]:
        """Loader build to install. Only meaningful together with the
        Minecraft version: a Forge build only exists for one MC version."""
        return self.loader_version if self.mc_version else None

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


def _invalid_component(part: str) -> bool:
    stem = part.split(".", 1)[0].strip().lower()
    return (stem in _RESERVED_NAMES or bool(_INVALID_CHARS.search(part))
            or part.endswith((" ", ".")) and part not in (".", ".."))


def check_members(members: list, dest_dir: str) -> None:
    """Reject archives that can't be unpacked safely here: names Windows
    can't create (CON, aux.txt, "a:b"...) and more data than fits on the
    disk or than MAX_UNPACKED_BYTES. Runs before anything is written, so a
    bad archive never leaves a half-copied server behind."""
    total = 0
    for member in members:
        total += member.file_size
        for part in member.filename.replace("\\", "/").split("/"):
            if part and _invalid_component(part):
                raise ContentImportError(
                    f"The archive contains a file name Windows can't create: {member.filename}")
    if total > MAX_UNPACKED_BYTES:
        raise ContentImportError(
            f"The archive unpacks to {total / 1024 ** 3:.1f} GB, more than the "
            f"{MAX_UNPACKED_BYTES // 1024 ** 3} GB limit.")
    probe = dest_dir
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError:
        return
    if total + _DISK_MARGIN_BYTES > free:
        raise ContentImportError(
            f"Not enough disk space: the archive needs {total / 1024 ** 3:.1f} GB "
            f"and only {free / 1024 ** 3:.1f} GB is free.")


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
            candidates = [n for n in (x.replace("\\", "/") for x in zf.namelist())
                          if n.split("/")[-1] == "level.dat" and not n.startswith(_MACOS_JUNK)]
        if not candidates:
            raise ContentImportError("No Minecraft world found in that .zip (it needs a level.dat).")
        # Shallowest level.dat is the world root (DIM folders hold none).
        best = min(candidates, key=lambda n: n.count("/"))
        prefix = best[: -len("level.dat")]
        name = prefix.rstrip("/").split("/")[-1] if prefix else _stem(path)
        return WorldInfo(path=path, name=name, is_zip=True, root=prefix)

    raise ContentImportError("That world file or folder doesn't exist.")


def _world_members(info: WorldInfo, zf: zipfile.ZipFile) -> list:
    """(member, path relative to the world root) for every file to copy."""
    out = []
    for member in zf.infolist():
        name = member.filename.replace("\\", "/")
        if not name.startswith(info.root) or name.endswith("/") or name.startswith(_MACOS_JUNK):
            continue
        rel = name[len(info.root):]
        if rel and rel.split("/")[-1] not in _WORLD_SKIP_FILES:
            out.append((member, rel))
    return out


def validate_world(info: WorldInfo, dest_dir: str) -> None:
    """Fail early (before a server is created) if the world can't be copied."""
    if info.is_zip:
        with _open_zip(info.path) as zf:
            check_members([m for m, _ in _world_members(info, zf)], dest_dir)


def import_world(info: WorldInfo, server_dir: str, level_name: str = "world",
                 progress: Optional[ProgressFn] = None) -> None:
    """Copy the world into `server_dir/level_name`, replacing what's there.
    `level_name` comes from server.properties, so it's confined to the
    server folder like any archive path."""
    dest = _safe_dest(server_dir, level_name or "world")
    if os.path.normcase(dest) == os.path.normcase(os.path.realpath(server_dir)):
        raise ContentImportError(f"Invalid level-name in server.properties: {level_name!r}")
    if progress:
        progress(f"Importing world '{info.name}'...")

    if not info.is_zip:
        _clear_dir(dest)
        shutil.copytree(info.root, dest, ignore=shutil.ignore_patterns(*_WORLD_SKIP_FILES))
        return

    with _open_zip(info.path) as zf:
        members = _world_members(info, zf)
        check_members([m for m, _ in members], server_dir)
        _clear_dir(dest)
        os.makedirs(dest, exist_ok=True)
        for member, rel in members:
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


# Matched against one archive entry name at a time.
_FORGE_JAR_RE = re.compile(r"(?:^|/)forge-(\d+\.\d+(?:\.\d+)?)-(\d+(?:\.\d+)+)(?:-[a-z]+)?\.jar$")
_FORGE_LIB_RE = re.compile(r"^libraries/net/minecraftforge/forge/(\d+\.\d+(?:\.\d+)?)-(\d+(?:\.\d+)+)/")
_NEOFORGE_RE = re.compile(r"^libraries/net/neoforged/neoforge/\d|(?:^|/)neoforge-\d[\w.-]*\.jar$")
_FABRIC_LOADER_RE = re.compile(r"^libraries/net/fabricmc/fabric-loader/(\d+(?:\.\d+)+)/")
_FABRIC_MC_RE = re.compile(r"^libraries/net/fabricmc/intermediary/(\d+\.\d+(?:\.\d+)?)/")
_QUILT_RE = re.compile(r"^libraries/org/quiltmc/quilt-loader/")
_MOD_JAR_RE = re.compile(r"(?:^|/)mods/[^/]+\.jar$")


def _content_names(names: list) -> list:
    return [n for n in names if not n.startswith(_MACOS_JUNK)]


def _pack_root(names: list) -> str:
    """In-zip prefix of the pack's content. Server packs are often wrapped
    in a folder; the shallowest mods/*.jar tells where the pack starts, so
    a stray README or __MACOSX/ next to the wrapper doesn't matter."""
    mod_jars = [n for n in _content_names(names) if _MOD_JAR_RE.search(n)]
    if not mod_jars:
        return ""
    shallowest = min(mod_jars, key=lambda n: n.count("/"))
    return shallowest[: shallowest.rfind("mods/")]


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


def _first_match(regex, names):
    for name in names:
        m = regex.search(name)
        if m:
            return m
    return None


def _detect_from_files(names: list) -> tuple:
    """(loader, mc_version, loader_version) from the pack's files; each part
    may be None."""
    forge = _first_match(_FORGE_LIB_RE, names) or _first_match(_FORGE_JAR_RE, names)
    if forge:
        return "Forge", forge.group(1), forge.group(2)
    if _first_match(_NEOFORGE_RE, names):
        return "NeoForge", None, None
    if _first_match(_QUILT_RE, names):
        return "Quilt", None, None
    loader_m = _first_match(_FABRIC_LOADER_RE, names)
    if loader_m or any(n.split("/")[-1] == "fabric-server-launch.jar" for n in names):
        mc_m = _first_match(_FABRIC_MC_RE, names)
        return "Fabric", (mc_m.group(1) if mc_m else None), (loader_m.group(1) if loader_m else None)
    return None, None, None


_VARIABLE_LOADERS = {"forge": "Forge", "fabric": "Fabric", "neoforge": "NeoForge", "quilt": "Quilt"}


def _apply_variables(info: ModpackInfo, variables: dict) -> None:
    info.mc_version = variables.get("MINECRAFT_VERSION") or None
    loader_var = variables.get("MODLOADER", "")
    if loader_var:
        info.loader = _VARIABLE_LOADERS.get(loader_var.lower(), loader_var)
        info.loader_version = variables.get("MODLOADER_VERSION") or None


def _inspect_serverpack(path: str, zf: zipfile.ZipFile, names: list) -> ModpackInfo:
    root = _pack_root(names)
    rel_names = [n[len(root):] for n in _content_names(names) if n.startswith(root)]
    mods = [n for n in rel_names if n.startswith("mods/") and n.endswith(".jar")]
    if not mods:
        raise ContentImportError(
            "This .zip has no mods/ folder, so it doesn't look like a server pack. "
            "Use a Modrinth .mrpack or the pack's \"Server Pack\" download.")

    info = ModpackInfo(path=path, kind="serverpack", name=_stem(path), mod_count=len(mods), root=root)
    _apply_variables(info, _read_variables(zf, root))
    loader, mc, loader_version = _detect_from_files(rel_names)
    if info.loader is None:
        info.loader, info.loader_version = loader, loader_version
    elif info.loader == loader and not info.loader_version:
        info.loader_version = loader_version
    if info.mc_version is None and info.loader == loader:
        info.mc_version = mc
    if info.mc_version and info.loader_version and info.loader_version.startswith(info.mc_version + "-"):
        # variables.txt sometimes carries the full "1.20.1-47.2.0" build.
        info.loader_version = info.loader_version[len(info.mc_version) + 1:]

    if info.loader is None or info.mc_version is None:
        info.notes.append("Couldn't tell which loader/Minecraft version this pack needs. "
                          "Pick the same ones the pack's page lists.")
    return info


def _is_curseforge_client(names: list) -> bool:
    """A CurseForge client export: manifest.json with its files under
    overrides/ and no server-ready mods/ folder next to it."""
    for name in _content_names(names):
        if name.split("/")[-1] != "manifest.json" or name.count("/") > 1:
            continue
        prefix = name[: -len("manifest.json")]
        has_mods = any(n.startswith(prefix + "mods/") for n in names)
        has_overrides = any(n.startswith(prefix + "overrides/") for n in names)
        if not has_mods and (has_overrides or not any(_MOD_JAR_RE.search(n) for n in names)):
            return True
    return False


def modpack_mismatch(info: ModpackInfo, engine: str, mc_version: str) -> Optional[str]:
    """Why `info` can't run on an `engine` server for `mc_version`, or None."""
    if engine not in SUPPORTED_LOADERS:
        return f"Modpacks need a {' or '.join(SUPPORTED_LOADERS)} server, not {engine}."
    if info.loader and info.loader != engine:
        return f"This modpack needs a {info.loader} server, not {engine}."
    if info.mc_version and info.mc_version != mc_version:
        return f"This modpack needs Minecraft {info.mc_version}, not {mc_version}."
    return None


def inspect_modpack(path: str) -> ModpackInfo:
    if not os.path.isfile(path):
        raise ContentImportError("That modpack file doesn't exist.")
    with _open_zip(path) as zf:
        names = [n.replace("\\", "/") for n in zf.namelist()]
        if "modrinth.index.json" in names:
            info = _inspect_mrpack(path, zf)
        elif _is_curseforge_client(names):
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


def _serverpack_members(info: ModpackInfo, zf: zipfile.ZipFile) -> list:
    """(member, path relative to the pack root) for every file to copy."""
    out = []
    for member in zf.infolist():
        name = member.filename.replace("\\", "/")
        if name.endswith("/") or not name.startswith(info.root) or name.startswith(_MACOS_JUNK):
            continue
        rel = name[len(info.root):]
        parts = rel.split("/")
        if parts[0] in _SERVERPACK_SKIP_DIRS:
            continue
        if len(parts) == 1 and (rel.lower().endswith(_SERVERPACK_SKIP_EXT)
                                or rel.lower() in _SERVERPACK_SKIP_FILES):
            continue
        out.append((member, rel))
    return out


def _mrpack_override_members(zf: zipfile.ZipFile) -> list:
    return [m for m in zf.infolist()
            if m.filename.startswith(("overrides/", "server-overrides/")) and not m.filename.endswith("/")]


def validate_modpack(info: ModpackInfo, dest_dir: str) -> None:
    """Fail early (before a server is created) if the pack can't be unpacked."""
    with _open_zip(info.path) as zf:
        if info.kind == "mrpack":
            members = _mrpack_override_members(zf)
        else:
            members = [m for m, _ in _serverpack_members(info, zf)]
        check_members(members, dest_dir)


def _copy_serverpack(info: ModpackInfo, server_dir: str, progress: Optional[ProgressFn]) -> int:
    copied = 0
    with _open_zip(info.path) as zf:
        members = _serverpack_members(info, zf)
        check_members([m for m, _ in members], server_dir)
        for member, rel in members:
            target = _safe_dest(server_dir, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            copied += 1
            if progress and copied % 50 == 0:
                progress(f"Copying modpack files ({copied})...")
    return copied


@dataclass
class ModpackInstall:
    summary: str
    failed: int = 0  # mods that could not be downloaded


def install_modpack(info: ModpackInfo, server_dir: str, server_type: str, mc_version: str,
                    progress: Optional[ProgressFn] = None) -> ModpackInstall:
    """Install the pack into `server_dir`."""
    if info.kind == "mrpack":
        from app.services.mrpack_installer import install_mrpack
        validate_modpack(info, server_dir)
        summary = install_mrpack(info.path, os.path.basename(server_dir), progress_callback=progress,
                                 server_type=server_type, mc_version=mc_version, server_dir=server_dir)
        text = f"{summary['installed']} mods installed"
        if summary["skipped_client"]:
            text += f", {summary['skipped_client']} client-only skipped"
        if summary["failed"]:
            text += f", {summary['failed']} failed to download"
        return ModpackInstall(text, summary["failed"])

    if progress:
        progress("Copying modpack files...")
    copied = _copy_serverpack(info, server_dir, progress)
    return ModpackInstall(f"{info.mod_count} mods ({copied} files) copied")
