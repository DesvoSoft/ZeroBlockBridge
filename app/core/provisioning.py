"""Server provisioning pipeline: everything between "wizard finished" and
"server ready to start".

Lives in core (not the UI) so it can be tested and reused; the UI only
passes a progress callback and reacts to the returned result. Console
output goes through the injected `log` callable (ZBBManager wires it to
CONSOLE_LINE).
"""

import logging
import os
import time
from dataclasses import dataclass
from typing import Callable, Optional

from app.core import logic
from app.core.constants import SERVERS_DIR

logger = logging.getLogger(__name__)

ProgressFn = Callable[[float, Optional[str]], None]

# Progress bands, so the bar only ever moves forward.
_JAR_BAND = (0.0, 0.25)
_P_ICON = 0.30
_P_SCAFFOLD = 0.35
_P_ANALYZE = 0.50
_P_JDK = 0.65
_P_TUNNEL = 0.90
_P_DONE = 1.0

SIMPLE_JAR_ENGINES = ("Vanilla", "Paper", "Purpur")
INSTALLER_ENGINES = ("Fabric", "Forge")


@dataclass
class ProvisionResult:
    ok: bool
    name: str
    error: Optional[str] = None
    required_java: Optional[int] = None


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
    ):
        self._log = log
        self._get_server_port = get_server_port
        self._create_tunnel = create_tunnel
        self._jdk_manager = jdk_manager
        self._servers_dir = servers_dir
        self._jar_wait_seconds = jar_wait_seconds
        self._jar_poll_interval = jar_poll_interval
        self._sleep = sleep

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
        progress = progress or (lambda value, text=None: None)
        name = config["name"]
        try:
            error = self._prepare_location(config)
            if error:
                self._log(f"[Error] {error}")
                return ProvisionResult(False, name, error)

            if not self._install_server_jar(config, progress):
                error = f"Failed to create server '{name}'. Check the log for details."
                self._log(f"[Error] {error}")
                return ProvisionResult(False, name, error)

            self._log("[System] Installation success. Applying settings...")
            self._apply_settings(config, progress)
            required_java = self._resolve_and_install_java(config, progress)

            progress(_P_TUNNEL, "Setting up Playit tunnel...")
            self._log(f"[System] Server '{name}' created successfully.")
            self._create_tunnel(name)
            progress(_P_DONE, "Server ready!")
            return ProvisionResult(True, name, required_java=required_java)
        except Exception as e:
            logger.exception("Provisioning failed for %s", name)
            self._log(f"[Error] Installation failed: {e}")
            return ProvisionResult(False, name, str(e))

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------
    def _prepare_location(self, config: dict) -> Optional[str]:
        """Reject duplicates and link a custom location into servers/.
        Returns an error message, or None when the target is ready."""
        name = config["name"]
        link_path = os.path.join(self._servers_dir, name)
        if os.path.exists(link_path):
            return f"Server '{name}' already exists."

        custom_loc = config.get("location") or self._servers_dir
        if os.path.normpath(custom_loc) == os.path.normpath(self._servers_dir):
            return None
        target_path = os.path.join(custom_loc, name)
        try:
            os.makedirs(target_path, exist_ok=True)
            logic.create_junction(target_path, link_path)
        except OSError as e:
            return f"Failed to map custom location: {e}"
        self._log(f"[System] Created link for custom location: {target_path}")
        return None

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
            java_bin = self.jdk_manager.ensure_java(get_required_java(version)) or "java"
            installer = logic.install_fabric if engine == "Fabric" else logic.install_forge
            return bool(installer(name, version, jar_progress, java_bin=java_bin))
        self._log(f"[Error] Unknown server type: {engine}")
        return False

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
        pre_boot_scaffold(self._server_dir(name), port=port, eula_accepted=True, config=config)
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
                self.jdk_manager.ensure_java(final_java)
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
