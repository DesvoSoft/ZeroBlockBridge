"""Server provisioning pipeline: everything between "wizard finished" and
"server ready to start".

Lives in core (not the UI) so it can be tested and reused; the UI only
passes a progress callback and reacts to the returned result. Console
output goes through the injected `log` callable (ZBBManager wires it to
CONSOLE_LINE).
"""

import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.core import logic
from app.core.constants import SERVERS_DIR

logger = logging.getLogger(__name__)

ProgressFn = Callable[[float, Optional[str]], None]

# Progress bands, so the bar only ever moves forward.
_JAR_BAND = (0.0, 0.25)
_P_MODPACK = 0.26
_P_WORLD = 0.28
_P_ICON = 0.30
_P_SCAFFOLD = 0.35
_P_ANALYZE = 0.50
_P_JDK = 0.65
_P_TUNNEL = 0.90
_P_DONE = 1.0

SIMPLE_JAR_ENGINES = ("Vanilla", "Paper", "Purpur")
INSTALLER_ENGINES = ("Fabric", "Forge")


class ProvisionCancelled(Exception):
    """The user cancelled the creation (or the app is closing)."""


@dataclass
class ProvisionResult:
    ok: bool
    name: str
    error: Optional[str] = None
    required_java: Optional[int] = None
    # Created, but the user should know (e.g. modpack mods that failed to download).
    warnings: list = field(default_factory=list)
    # Something was created and then removed again (vs. failing up front).
    rolled_back: bool = False
    # Stopped by the user: not an error to report.
    cancelled: bool = False


def resolve_required_java(bytecode_java: Optional[int], version_map_java: int) -> int:
    """Final Java major for a new server.

    The bytecode scan wins only when it asks for at least the version-map
    Java: Forge ships a Java 8 bootstrap shim that would otherwise downgrade
    a modern server.
    """
    if bytecode_java and bytecode_java >= version_map_java:
        return bytecode_java
    return version_map_java


class ServerProvisioner:
    def __init__(
        self,
        log: Callable[[str], None],
        get_server_port: Callable[[str], int],
        create_tunnel: Callable[[str], None],
        jdk_manager=None,
        servers_dir: str = str(SERVERS_DIR),
        jar_wait_seconds: float = 10.0,
        jar_poll_interval: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        cancel_event=None,
    ):
        self._log = log
        self._cancel_event = cancel_event
        self._get_server_port = get_server_port
        self._create_tunnel = create_tunnel
        self._jdk_manager = jdk_manager
        self._servers_dir = servers_dir
        self._jar_wait_seconds = jar_wait_seconds
        self._jar_poll_interval = jar_poll_interval
        self._sleep = sleep
        # Per-run state, reset by provision()
        self._modpack = None
        self._world = None
        self._created: list = []
        self._warnings: list = []
        self._kept_existing_target = False
        self._target_entries_before: Optional[set] = None
        self._existing_target: Optional[str] = None
        self._required_java: Optional[int] = None

    @property
    def jdk_manager(self):
        if self._jdk_manager is None:
            from app.services.java_installer import JdkManagerInstance
            self._jdk_manager = JdkManagerInstance
        return self._jdk_manager

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def provision(self, config: dict, progress: Optional[ProgressFn] = None) -> ProvisionResult:
        raw_progress = progress or (lambda value, text=None: None)
        progress = self._cancellable(raw_progress)
        name = config["name"]
        self._modpack = self._world = None
        self._created, self._warnings = [], []
        self._kept_existing_target = False
        self._target_entries_before = self._existing_target = None
        try:
            error = self._build(config, progress)
            if error:
                self._log(f"[Error] {error}")
        except ProvisionCancelled:
            return self._cancelled(name)
        except Exception as e:
            if self._cancel_requested():
                # e.g. an interrupted JDK download: a cancel, not a failure.
                return self._cancelled(name)
            logger.exception("Provisioning failed for %s", name)
            self._log(f"[Error] Installation failed: {e}")
            error = str(e)
        if error:
            rolled_back = bool(self._created)
            self._rollback(name)
            return ProvisionResult(False, name, error, rolled_back=rolled_back)

        # Point of no return: the server is complete. Report with the raw
        # callback -- the cancellable one would raise here, and the tunnel
        # handler below would mistake that for a tunnel failure.
        required_java = self._required_java
        try:
            raw_progress(_P_TUNNEL, "Setting up Playit tunnel...")
            self._log(f"[System] Server '{name}' created successfully.")
            self._create_tunnel(name)
            raw_progress(_P_DONE, "Server ready!")
        except Exception as e:
            # The server itself is complete; a tunnel can be set up later.
            logger.exception("Tunnel setup failed for %s", name)
            reason = str(e) or type(e).__name__
            self._log(f"[Warning] Tunnel setup failed: {reason}")
            self._warnings.append(f"The Playit tunnel couldn't be set up ({reason}). Start it from the Tunnel panel.")
        return ProvisionResult(True, name, required_java=required_java, warnings=list(self._warnings))

    def _build(self, config: dict, progress: ProgressFn) -> Optional[str]:
        """Every step that leaves a usable server behind. Returns an error
        message (or raises); the caller rolls back whatever was created.
        Raises ProvisionCancelled between steps (and from `progress` during
        downloads) once the cancel event is set."""
        self._check_cancel()
        error = self._preflight_content(config) or self._prepare_location(config)
        if error:
            return error
        self._check_cancel()
        if not self._install_server_jar(config, progress):
            self._check_cancel()  # a cancelled installer reports failure: say why
            return f"Failed to create server '{config['name']}'. Check the log for details."
        for step in (self._import_content, self._apply_settings):
            self._check_cancel()
            if step is self._apply_settings:
                self._log("[System] Installation success. Applying settings...")
            step(config, progress)
        self._check_cancel()
        self._required_java = self._resolve_and_install_java(config, progress)
        self._check_cancel()  # a cancel during the (swallowed-on-failure) JDK step
        return None

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------
    def _cancel_requested(self) -> bool:
        return self._cancel_event is not None and self._cancel_event.is_set()

    def _check_cancel(self) -> None:
        if self._cancel_requested():
            raise ProvisionCancelled()

    def _ensure_java(self, version: int) -> str:
        """JDK install that a cancel interrupts mid-download."""
        if self._cancel_event is None:
            return self.jdk_manager.ensure_java(version)
        return self.jdk_manager.ensure_java(version, cancel_event=self._cancel_event)

    def _cancellable(self, progress: ProgressFn) -> ProgressFn:
        """Progress reporting doubles as a cancellation point: downloads call
        it per chunk, so a cancel stops a jar download mid-stream."""
        def report(value, text=None):
            self._check_cancel()
            progress(value, text)
        return report

    def _cancelled(self, name: str) -> ProvisionResult:
        rolled_back = bool(self._created)
        self._rollback(name)
        self._log(f"[System] Creation of '{name}' cancelled.")
        return ProvisionResult(False, name, "Cancelled", rolled_back=rolled_back, cancelled=True)

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------
    def _preflight_content(self, config: dict) -> Optional[str]:
        """Check imported modpack/world BEFORE anything is created, so a bad
        archive never leaves a half-built server behind."""
        from app.services import content_import

        dest = config.get("location") or self._servers_dir
        try:
            if config.get("modpack_path"):
                info = content_import.inspect_modpack(config["modpack_path"])
                mismatch = content_import.modpack_mismatch(info, config["type"], config["version"])
                if mismatch:
                    return mismatch
                content_import.validate_modpack(info, dest)
                self._modpack = info
            if config.get("world_path"):
                world = content_import.inspect_world(config["world_path"])
                content_import.validate_world(world, dest)
                self._world = world
        except content_import.ContentImportError as e:
            return str(e)
        return None

    def _prepare_location(self, config: dict) -> Optional[str]:
        """Reject duplicates and link a custom location into servers/.
        Returns an error message, or None when the target is ready. Records
        only what it creates, so a rollback never touches what existed."""
        name = config["name"]
        link_path = os.path.join(self._servers_dir, name)
        if os.path.lexists(link_path):
            return f"Server '{name}' already exists."

        custom_loc = config.get("location") or self._servers_dir
        if os.path.normpath(custom_loc) == os.path.normpath(self._servers_dir):
            # Claim the name atomically: a second creation with the same name
            # (the progress dialog isn't modal) fails here instead of sharing
            # -- and on rollback deleting -- this run's folder.
            try:
                os.makedirs(self._servers_dir, exist_ok=True)
                os.mkdir(link_path)
            except FileExistsError:
                return f"Server '{name}' already exists."
            self._created.append(("dir", link_path))
            return None
        target_path = os.path.join(custom_loc, name)
        try:
            if os.path.exists(target_path):
                self._kept_existing_target = True
                self._existing_target = target_path
                self._target_entries_before = set(os.listdir(target_path))
            else:
                os.makedirs(target_path)
                self._created.append(("dir", target_path))
            logic.create_junction(target_path, link_path)
            self._created.append(("link", link_path))
        except OSError as e:
            return f"Failed to map custom location: {e}"
        self._log(f"[System] Created link for custom location: {target_path}")
        return None

    def _rollback(self, name: str) -> None:
        """Undo a failed creation: drop the link first (never follow it),
        then delete only folders this run created."""
        from app.core.fs_links import is_link, remove_link

        if not self._created:
            return  # e.g. "already exists": nothing of ours to undo
        self._remove_additions_to_existing_target()
        for kind, path in reversed(self._created):
            try:
                if kind == "link" and os.path.lexists(path):
                    remove_link(path)
                elif kind == "dir" and os.path.isdir(path) and not is_link(path):
                    shutil.rmtree(path)
            except OSError as e:
                logger.warning("Rollback could not remove %s: %s", path, e)
        if self._kept_existing_target:
            self._log("[System] The chosen folder already existed: only what this attempt added "
                      "to it was removed.")
        self._created = []
        logic.invalidate_meta_cache(name)
        self._log(f"[System] Removed the partially created server '{name}'.")

    def _remove_additions_to_existing_target(self) -> None:
        """In a custom folder that existed before, delete only the entries
        this run added (jar, .part downloads, libraries...), never the
        user's own files."""
        from app.core.fs_links import is_link, remove_link

        target = self._existing_target
        if self._target_entries_before is None or not target or not os.path.isdir(target):
            return
        for entry in set(os.listdir(target)) - self._target_entries_before:
            path = os.path.join(target, entry)
            try:
                if is_link(path):
                    remove_link(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except OSError as e:
                logger.warning("Rollback could not remove %s: %s", path, e)

    def _install_server_jar(self, config: dict, progress: ProgressFn) -> bool:
        name, version, engine = config["name"], config["version"], config["type"]
        low, high = _JAR_BAND
        label = f"Downloading {engine} {version} server jar..."
        progress(low, label)

        def jar_progress(value, *_):
            progress(low + (high - low) * max(0.0, min(float(value), 1.0)), label)

        if engine in SIMPLE_JAR_ENGINES:
            self._log(f"[System] Downloading {engine} {version}...")
            return bool(logic.download_server(name, engine, version, jar_progress))
        if engine in INSTALLER_ENGINES:
            self._log(f"[System] Installing {engine} {version}...")
            from app.services.java_detector import get_required_java
            java_bin = self._ensure_java(get_required_java(version)) or "java"
            installer = logic.install_fabric if engine == "Fabric" else logic.install_forge
            # A modpack pins its loader build; otherwise the installer picks one.
            extra = {"loader_version": config["loader_version"]} \
                if config.get("loader_version") and engine == config.get("modpack_loader", engine) else {}
            if self._cancel_event is not None:
                extra["cancel_event"] = self._cancel_event  # kills a running installer
            return bool(installer(name, version, jar_progress, java_bin=java_bin, **extra))
        self._log(f"[Error] Unknown server type: {engine}")
        return False

    def _import_content(self, config: dict, progress: ProgressFn) -> None:
        """Modpack first (its overrides may ship a world and set level-name),
        then the imported world, which replaces whatever is there."""
        from app.services import content_import
        from app.services.server_properties import load_server_properties

        name, server_dir = config["name"], self._server_dir(config["name"])
        if self._modpack is not None:
            info = self._modpack
            progress(_P_MODPACK, f"Installing modpack {info.name}...")
            self._log(f"[System] Installing modpack '{info.name}'...")
            installed = content_import.install_modpack(
                info, server_dir, config["type"], config["version"],
                progress=lambda msg: progress(_P_MODPACK, msg),
            )
            self._log(f"[System] Modpack ready: {installed.summary}.")
            if installed.failed:
                self._log(f"[Warning] {installed.failed} modpack mod(s) failed to download.")
                self._warnings.append(
                    f"{installed.failed} mod(s) from the modpack couldn't be downloaded, so the server "
                    "may not start. Check the console, then retry by importing the pack again.")
            logic.update_server_meta(name, {"modpack": info.name})
        if self._world is not None:
            level_name = load_server_properties(server_dir=server_dir).get("level-name") or "world"
            progress(_P_WORLD, f"Importing world {self._world.name}...")
            content_import.import_world(self._world, server_dir, level_name=level_name)
            self._log(f"[System] World '{self._world.name}' imported as '{level_name}'.")

    def _apply_settings(self, config: dict, progress: ProgressFn) -> None:
        name = config["name"]
        if config.get("icon_path"):
            progress(_P_ICON, "Applying server icon...")
            logic.save_server_icon(name, config["icon_path"])

        progress(_P_SCAFFOLD, "Configuring server environment...")
        self._log("[System] Scaffolding server environment...")
        from app.services.scaffolder import pre_boot_scaffold
        port_str = config.get("playit_port")
        port = int(port_str) if port_str and str(port_str).isdigit() else self._get_server_port(name)
        # A modpack may ship its own server.properties: the choices made in the
        # wizard (game mode, difficulty, whitelist...) still win.
        pre_boot_scaffold(self._server_dir(name), port=port, eula_accepted=True, config=config,
                          override_existing=self._modpack is not None)
        self._log("[System] Environment ready (eula.txt, server.properties, directories).")
        if "auto_install_jdk" in config:
            logic.update_server_meta(name, {"auto_install_jdk": config["auto_install_jdk"]})

    def _resolve_and_install_java(self, config: dict, progress: ProgressFn) -> int:
        from app.services.java_detector import get_required_java
        from app.services.java_installer import get_release_label

        name, version = config["name"], config["version"]
        progress(_P_ANALYZE, "Analyzing Java requirements from server jar...")
        self._log("[System] Analyzing Java requirements from server jar...")
        bytecode_java = self._analyze_jar(os.path.join(self._server_dir(name), "server.jar"))

        version_map_java = get_required_java(version)
        final_java = resolve_required_java(bytecode_java, version_map_java)
        self._log(f"[System] Detected Minecraft {version} → requires Java {final_java}.")
        if bytecode_java and bytecode_java != version_map_java:
            # Modded/shaded jars can bundle classes for a different Java major
            # than the plain MC-version mapping predicts.
            self._log(
                f"[System] Bytecode scan found this jar needs Java {bytecode_java} "
                f"(standard mapping for MC {version} would be Java {version_map_java})."
            )
        logic.update_server_meta(name, {"required_java": final_java})

        if not self.jdk_manager.get_java_path(final_java):
            label = get_release_label(final_java) or f"Java {final_java}"
            progress(_P_JDK, f"Installing {label}...")
            self._log(f"[System] Installing {label}...")
            try:
                self._ensure_java(final_java)
                self._log(f"[System] {label} ready.")
            except Exception as e:
                # Not fatal: the server can still be started later, when
                # ZBBManager retries the JDK resolution at launch.
                self._log(f"[Warning] Java {final_java} download failed: {e}")
        return final_java

    def _analyze_jar(self, jar_path: str) -> Optional[int]:
        """Bytecode Java major of server.jar, or None. Forge normalizes the
        jar name after its installer exits, so wait briefly for it."""
        waited = 0.0
        while not self._jar_ready(jar_path):
            if waited >= self._jar_wait_seconds:
                self._log(f"[Warning] server.jar not found after {self._jar_wait_seconds:.0f}s. "
                          "Skipping bytecode analysis.")
                return None
            self._sleep(self._jar_poll_interval)
            waited += self._jar_poll_interval

        from app.services.bytecode_analyzer import analyze_jar_bytecode
        try:
            return analyze_jar_bytecode(jar_path)
        except Exception as e:
            self._log(f"[Warning] Bytecode analysis failed: {e}")
            return None

    # ------------------------------------------------------------------
    def _server_dir(self, name: str) -> str:
        return os.path.join(self._servers_dir, name)

    @staticmethod
    def _jar_ready(jar_path: str) -> bool:
        try:
            return os.path.getsize(jar_path) > 0
        except OSError:
            return False
