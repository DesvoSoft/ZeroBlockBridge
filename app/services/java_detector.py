"""
PROV-01 / INTEG-03 — Java Version Detection & MC Version Matching.

Provides cross-platform Java installation discovery (Windows registry,
PATH, JAVA_HOME, well-known paths) and a Minecraft-to-Java version
compatibility matrix.

All methods are synchronous and intended for daemon thread execution.
"""

import glob
import logging
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.core.constants import JDK_CACHE_DIR, subprocess_flags

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------
@dataclass
class JavaInstallation:
    """Represents a discovered Java installation."""
    path: str               # Full path to java / java.exe binary
    version_string: str     # Raw output from `java -version`
    major: int              # Parsed major version (8, 11, 17, 21, …)
    minor: int = 0          # Parsed minor version
    patch: int = 0          # Parsed patch version
    vendor: str = ""        # e.g. "Oracle", "Eclipse Adoptium", "GraalVM"
    source: str = ""        # How it was discovered: "PATH", "REGISTRY", "JAVA_HOME", "SCAN"
    is_jdk: bool = False    # True if JDK (has javac), False if JRE

    @property
    def label(self) -> str:
        """Human-readable label for UI dropdowns."""
        jdk_tag = "JDK" if self.is_jdk else "JRE"
        return f"Java {self.major} ({jdk_tag}) — {self.source}"


# ---------------------------------------------------------------------------
# MC → Java Version Compatibility Matrix  (INTEG-03)
# ---------------------------------------------------------------------------
# Source: https://minecraft.wiki/w/Tutorials/Update_Java
_MC_JAVA_MAP: List[tuple] = [
    # (mc_version_min, mc_version_max, required_java_major)
    ("1.0",    "1.11.2", 8),
    ("1.12",   "1.16.5", 8),
    ("1.17",   "1.17.1", 16),
    ("1.18",   "1.20.4", 17),
    ("1.20.5", "1.99.0", 21),
]


def _parse_mc_version(version: str) -> tuple:
    """Parse '1.20.4' into (1, 20, 4) for comparison."""
    parts = []
    for p in version.split("."):
        match = re.match(r"(\d+)", p)
        parts.append(int(match.group(1)) if match else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def get_required_java(mc_version: str) -> int:
    """
    Return the minimum required Java major version for a given MC version.

    Args:
        mc_version: e.g. "1.20.1"

    Returns:
        Java major version (8, 16, 17, 21) or 17 as default.
    """
    mc = _parse_mc_version(mc_version)
    for mc_min, mc_max, java_major in _MC_JAVA_MAP:
        if _parse_mc_version(mc_min) <= mc <= _parse_mc_version(mc_max):
            return java_major
    # Default to Java 17 if unknown
    return 17





# ---------------------------------------------------------------------------
# Version String Parsing
# ---------------------------------------------------------------------------
_VERSION_RE = re.compile(
    r'(?:version\s+")?(1\.\d+[\.\d]*|[0-9]+[\.\d]*)(?:[\._](\d+))?(?:[\._](\d+))?',
    re.IGNORECASE,
)


def parse_java_version(version_output: str) -> tuple:
    """
    Parse version from `java -version` stderr output.

    Examples:
        'openjdk version "17.0.8" 2023-07-18' → (17, 0, 8)
        'java version "1.8.0_381"'             → (8, 0, 381)
        'openjdk version "21.0.1" 2023-10-17'  → (21, 0, 1)

    Returns:
        (major, minor, patch) tuple. (0, 0, 0) on failure.
    """
    for line in version_output.strip().splitlines():
        m = _VERSION_RE.search(line)
        if m:
            raw = m.group(1)
            parts = re.split(r'[._]', raw)
            nums = []
            for p in parts:
                try:
                    nums.append(int(p))
                except ValueError:
                    nums.append(0)

            # Legacy 1.x format → actual major is second number
            if len(nums) >= 2 and nums[0] == 1 and nums[1] <= 8:
                major = nums[1]
                minor = nums[2] if len(nums) > 2 else 0
                patch_part = m.group(2) or m.group(3)
                patch = int(patch_part) if patch_part else (nums[3] if len(nums) > 3 else 0)
                return major, minor, patch

            major = nums[0]
            minor = nums[1] if len(nums) > 1 else 0
            patch = nums[2] if len(nums) > 2 else 0
            return major, minor, patch

    return 0, 0, 0


def _detect_vendor(version_output: str) -> str:
    """Heuristic vendor detection from version string."""
    lower = version_output.lower()
    if "graalvm" in lower:
        return "GraalVM"
    if "eclipse" in lower or "adoptium" in lower or "temurin" in lower:
        return "Eclipse Adoptium"
    if "corretto" in lower:
        return "Amazon Corretto"
    if "zulu" in lower:
        return "Azul Zulu"
    if "openjdk" in lower:
        return "OpenJDK"
    if "oracle" in lower or "java(tm)" in lower:
        return "Oracle"
    return "Unknown"


# ---------------------------------------------------------------------------
# Java Binary Probing
# ---------------------------------------------------------------------------
def _probe_java(java_path: str, source: str) -> Optional[JavaInstallation]:
    """
    Run `java -version` on the given path and return a JavaInstallation or None.
    """
    try:
        result = subprocess.run(
            [java_path, "-version"],
            capture_output=True, text=True, timeout=10,
            **subprocess_flags(),
        )
        output = result.stderr or result.stdout
        if not output:
            return None

        major, minor, patch = parse_java_version(output)
        if major == 0:
            return None

        # Check for JDK by looking for javac next to java
        javac_name = "javac.exe" if platform.system() == "Windows" else "javac"
        java_dir = os.path.dirname(java_path)
        is_jdk = os.path.exists(os.path.join(java_dir, javac_name))

        return JavaInstallation(
            path=java_path,
            version_string=output.strip().splitlines()[0],
            major=major,
            minor=minor,
            patch=patch,
            vendor=_detect_vendor(output),
            source=source,
            is_jdk=is_jdk,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.debug("Probe failed for %s: %s", java_path, exc)
        return None


def probe_java(java_path: str, source: str = "PROBE") -> Optional[JavaInstallation]:
    """Public wrapper around _probe_java for use outside this module."""
    return _probe_java(java_path, source)


# ---------------------------------------------------------------------------
# Discovery Sources
# ---------------------------------------------------------------------------
class JavaDetector:
    """
    Cross-platform Java installation discoverer.

    Searches: PATH, JAVA_HOME, Windows Registry, and well-known directories.
    Results are deduplicated by resolved absolute path.
    """

    _shared_cache: Optional[List[JavaInstallation]] = None

    def __init__(self):
        self._cache: Optional[List[JavaInstallation]] = None

    def detect_all(self, force_refresh: bool = False) -> List[JavaInstallation]:
        """
        Discover all Java installations on the system.

        Results are cached after the first scan. Use force_refresh=True
        to re-scan.

        Returns:
            List of JavaInstallation objects, sorted by major version descending.
        """
        if self._cache is not None and not force_refresh:
            return self._cache

        if JavaDetector._shared_cache is not None and not force_refresh:
            self._cache = JavaDetector._shared_cache
            return self._cache

        found: Dict[str, JavaInstallation] = {}

        # 1. PATH scan
        for inst in self._scan_path():
            key = os.path.realpath(inst.path)
            if key not in found:
                found[key] = inst

        # 2. JAVA_HOME
        for inst in self._scan_java_home():
            key = os.path.realpath(inst.path)
            if key not in found:
                found[key] = inst

        # 3. Platform-specific
        if platform.system() == "Windows":
            for inst in self._scan_windows_registry():
                key = os.path.realpath(inst.path)
                if key not in found:
                    found[key] = inst

        # 4. Well-known paths
        for inst in self._scan_well_known():
            key = os.path.realpath(inst.path)
            if key not in found:
                found[key] = inst

        result = sorted(found.values(), key=lambda j: j.major, reverse=True)
        JavaDetector._shared_cache = result
        self._cache = result
        logger.info("Detected %d Java installations", len(result))
        return result

    # ------------------------------------------------------------------
    # Source: PATH
    # ------------------------------------------------------------------
    def _scan_path(self) -> List[JavaInstallation]:
        results = []
        java_name = "java.exe" if platform.system() == "Windows" else "java"
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)

        for d in path_dirs:
            candidate = os.path.join(d, java_name)
            if os.path.isfile(candidate):
                inst = _probe_java(candidate, "PATH")
                if inst:
                    results.append(inst)
        return results

    # ------------------------------------------------------------------
    # Source: JAVA_HOME
    # ------------------------------------------------------------------
    def _scan_java_home(self) -> List[JavaInstallation]:
        results = []
        java_home = os.environ.get("JAVA_HOME")
        if not java_home or not os.path.isdir(java_home):
            return results

        java_name = "java.exe" if platform.system() == "Windows" else "java"
        candidate = os.path.join(java_home, "bin", java_name)
        if os.path.isfile(candidate):
            inst = _probe_java(candidate, "JAVA_HOME")
            if inst:
                results.append(inst)
        return results

    # ------------------------------------------------------------------
    # Source: Windows Registry
    # ------------------------------------------------------------------
    def _scan_windows_registry(self) -> List[JavaInstallation]:
        results = []
        if platform.system() != "Windows":
            return results

        try:
            import winreg
        except ImportError:
            return results

        registry_keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Runtime Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Development Kit"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\JDK"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\JRE"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Eclipse Adoptium\JDK"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Eclipse Adoptium\JRE"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\AdoptOpenJDK\JDK"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\JDK"),
        ]

        for hive, base_key in registry_keys:
            try:
                with winreg.OpenKey(hive, base_key) as key:
                    i = 0
                    while True:
                        try:
                            sub_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, sub_name) as sub:
                                try:
                                    java_home, _ = winreg.QueryValueEx(sub, "JavaHome")
                                    candidate = os.path.join(java_home, "bin", "java.exe")
                                    if os.path.isfile(candidate):
                                        inst = _probe_java(candidate, "REGISTRY")
                                        if inst:
                                            results.append(inst)
                                except FileNotFoundError:
                                    pass
                            i += 1
                        except OSError:
                            break
            except FileNotFoundError:
                continue
            except Exception as exc:
                logger.debug("Registry scan error for %s: %s", base_key, exc)

        return results

    # ------------------------------------------------------------------
    # Source: Well-Known Paths
    # ------------------------------------------------------------------
    def _scan_well_known(self) -> List[JavaInstallation]:
        results = []
        system = platform.system()

        if system == "Windows":
            patterns = [
                r"C:\Program Files\Java\*\bin\java.exe",
                r"C:\Program Files (x86)\Java\*\bin\java.exe",
                r"C:\Program Files\Eclipse Adoptium\*\bin\java.exe",
                r"C:\Program Files\AdoptOpenJDK\*\bin\java.exe",
                r"C:\Program Files\Microsoft\*\bin\java.exe",
                r"C:\Program Files\Zulu\*\bin\java.exe",
                r"C:\Program Files\Amazon Corretto\*\bin\java.exe",
                r"C:\Program Files\BellSoft\*\bin\java.exe",
            ]
        elif system == "Linux":
            patterns = [
                "/usr/lib/jvm/*/bin/java",
                "/usr/java/*/bin/java",
                "/opt/java/*/bin/java",
                "/opt/jdk*/bin/java",
                os.path.expanduser("~/.sdkman/candidates/java/*/bin/java"),
            ]
        elif system == "Darwin":
            patterns = [
                "/Library/Java/JavaVirtualMachines/*/Contents/Home/bin/java",
                "/usr/local/opt/openjdk*/bin/java",
                os.path.expanduser("~/.sdkman/candidates/java/*/bin/java"),
            ]
        else:
            return results

        for pattern in patterns:
            for match in glob.glob(pattern):
                if os.path.isfile(match):
                    inst = _probe_java(match, "SCAN")
                    if inst:
                        results.append(inst)

        # Portable JDKs downloaded by JdkManager
        jdk_cache = str(JDK_CACHE_DIR)
        if os.path.isdir(jdk_cache):
            jdk_pattern = os.path.join(jdk_cache, "*", "bin", "java.exe" if platform.system() == "Windows" else "java")
            for match in glob.glob(jdk_pattern):
                inst = _probe_java(match, "PORTABLE")
                if inst:
                    results.append(inst)
                    logger.debug("Found portable JDK: %s (Java %d)", match, inst.major)

        return results

    def find_best_for_mc(self, mc_version: str) -> Optional[JavaInstallation]:
        required = get_required_java(mc_version)
        candidates = [j for j in self.detect_all() if j.major == required]
        if not candidates:
            return None
        candidates.sort(key=lambda j: j.is_jdk, reverse=True)
        return candidates[0]
