import hashlib
import logging
import os
import platform
import shutil
import sys
import zipfile
import io
from pathlib import Path
from typing import Optional

import requests

from app.core.constants import BASE_DIR, JDK_CACHE_DIR

logger = logging.getLogger(__name__)

_ADOPTIUM_API = "https://api.adoptium.net/v3/assets/latest/{version}/hotspot"

_OS_MAP = {
    "win32": "windows",
    "linux": "linux",
    "darwin": "mac",
}

_ARCH_MAP = {
    "x86_64": "x64",
    "amd64": "x64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv7l": "arm",
}

_JDK_CACHE_DIR = JDK_CACHE_DIR

MAX_RETRIES = 2
RETRY_DELAY = 3


class JdkError(Exception):
    pass


class JdkDownloadError(JdkError):
    pass


class JdkIntegrityError(JdkError):
    pass


def _platform_os() -> str:
    return _OS_MAP.get(sys.platform, "linux")


def _platform_arch() -> str:
    raw = platform.machine().lower()
    return _ARCH_MAP.get(raw, "x64")


def _java_exe_name() -> str:
    return "java.exe" if sys.platform == "win32" else "java"


def _jdk_cache_dir(version: int) -> Path:
    return _JDK_CACHE_DIR / f"jdk{version}"


def _checksum_path(version: int) -> Path:
    return _JDK_CACHE_DIR / f"jdk{version}" / ".checksum"


def _verify_checksum(file_path: Path, expected: str) -> bool:
    expected = expected.lower()
    if len(expected) == 128:
        h = hashlib.sha512()
    elif len(expected) == 64:
        h = hashlib.sha256()
    else:
        logger.warning("Unknown checksum length %d — skipping verification", len(expected))
        return True
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower() == expected


def _find_java_binary(extract_dir: Path) -> Optional[Path]:
    exe_name = _java_exe_name()
    for root, _dirs, files in os.walk(extract_dir):
        if exe_name in files:
            return Path(root) / exe_name
    return None


def _chmod_plusx(path: Path):
    try:
        current = path.stat().st_mode
        path.chmod(current | 0o111)
    except OSError as exc:
        logger.warning("Failed to set executable permission on %s: %s", path, exc)


def _fetch_asset_info(version: int) -> dict:
    os_name = _platform_os()
    arch = _platform_arch()
    url = _ADOPTIUM_API.format(version=version)
    params = {
        "architecture": arch,
        "image_type": "jdk",
        "os": os_name,
        "vendor": "eclipse",
        "heap_size": "normal",
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        assets = resp.json()
    except requests.ConnectionError:
        raise JdkDownloadError("No internet connection — cannot download JDK")
    except requests.Timeout:
        raise JdkDownloadError("Adoptium API timed out")
    except requests.RequestException as exc:
        raise JdkDownloadError(f"Adoptium API request failed: {exc}")

    if not assets:
        raise JdkDownloadError(
            f"No JDK {version} asset found for {os_name}/{arch}"
        )

    asset = assets[0]
    binary = asset.get("binary", {})
    pkg = binary.get("package", {})

    download_url = pkg.get("link")
    checksum = pkg.get("checksum", "").strip()

    if not download_url:
        raise JdkDownloadError("Adoptium response missing package link")

    return {
        "url": download_url,
        "checksum": checksum.upper() if checksum else "",
        "version": asset.get("version_data", {}).get("semver", str(version)),
    }


class JdkManager:

    def get_java_path(self, version: int) -> Optional[str]:
        cache_dir = _jdk_cache_dir(version)
        if not cache_dir.exists():
            return None
        binary = _find_java_binary(cache_dir)
        if binary is None:
            logger.warning("JDK %d cache dir exists but no java binary found — marking invalid", version)
            shutil.rmtree(cache_dir, ignore_errors=True)
            return None
        return str(binary)

    def ensure_java(self, version: int) -> str:
        cached = self.get_java_path(version)
        if cached:
            logger.info("Using cached JDK %d at %s", version, cached)
            return cached

        logger.info("JDK %d not in cache — downloading", version)
        path = self._download_and_install(version)

        binary = _find_java_binary(Path(path).parent.parent)
        if binary:
            if sys.platform != "win32":
                _chmod_plusx(binary)

        logger.info("JDK %d installed at %s", version, path)
        return path

    def _download_and_install(self, version: int) -> str:
        info = _fetch_asset_info(version)
        url = info["url"]
        expected_checksum = info["checksum"]
        cache_dir = _jdk_cache_dir(version)
        tmp_dir = cache_dir.with_suffix(".tmp")

        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)

        tmp_dir.mkdir(parents=True, exist_ok=True)
        zip_path = tmp_dir / "jdk.zip"

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._download_file(url, zip_path)
                if expected_checksum:
                    if not _verify_checksum(zip_path, expected_checksum):
                        zip_path.unlink(missing_ok=True)
                        raise JdkIntegrityError(f"Checksum mismatch for JDK {version}")
                else:
                    logger.warning("No checksum available for JDK %d — skipping verification", version)

                self._extract_zip(zip_path, cache_dir)
                zip_path.unlink(missing_ok=True)
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return str(cache_dir)

            except (JdkDownloadError, JdkIntegrityError):
                raise
            except Exception as exc:
                last_error = str(exc)
                logger.warning("JDK download attempt %d/%d failed: %s", attempt, MAX_RETRIES, last_error)
                if attempt < MAX_RETRIES:
                    import time
                    time.sleep(RETRY_DELAY)
                else:
                    raise JdkDownloadError(f"JDK download failed after {MAX_RETRIES} attempts: {last_error}")

        raise JdkDownloadError(f"JDK download failed: {last_error}")

    def _download_file(self, url: str, dest: Path):
        try:
            resp = requests.get(url, stream=True, timeout=120)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=32768):
                    if chunk:
                        f.write(chunk)
        except requests.ConnectionError:
            raise JdkDownloadError("No internet connection during JDK download")
        except requests.Timeout:
            raise JdkDownloadError("JDK download timed out")
        except requests.RequestException as exc:
            raise JdkDownloadError(f"JDK download failed: {exc}")

    def _extract_zip(self, zip_path: Path, dest_dir: Path):
        dest_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.namelist()

            common_prefix = _get_common_prefix(members)
            if common_prefix:
                for name in members:
                    rel = name[len(common_prefix):]
                    if not rel:
                        continue
                    target = dest_dir / rel
                    if name.endswith("/"):
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(name) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        if sys.platform != "win32":
                            _chmod_plusx(target)
            else:
                zf.extractall(dest_dir)

    def purge_unused_jdks(self, active_versions: set = None):
        """Remove JDK directories not in active_versions.
        If active_versions is None, lists server metadata to determine which
        JDK versions are still referenced."""
        if active_versions is None:
            active_versions = set()
            from app.core.constants import SERVERS_DIR
            if SERVERS_DIR.exists():
                for folder in SERVERS_DIR.iterdir():
                    meta_file = folder / "metadata.json"
                    if meta_file.exists():
                        try:
                            import json
                            with open(meta_file) as f:
                                meta = json.load(f)
                            rj = meta.get("required_java")
                            if rj:
                                active_versions.add(int(rj))
                        except Exception as e:
                            logger.debug("Failed parsing server meta: %s", e)
        if not _JDK_CACHE_DIR.exists():
            return
        for entry in _JDK_CACHE_DIR.iterdir():
            if entry.is_dir() and entry.name.startswith("jdk"):
                try:
                    ver = int(entry.name.replace("jdk", ""))
                    if ver not in active_versions:
                        shutil.rmtree(entry, ignore_errors=True)
                        logger.info("Purged unused JDK %d", ver)
                except ValueError:
                    pass

    def purge_cache(self, version: Optional[int] = None):
        if version is not None:
            target = _jdk_cache_dir(version)
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                logger.info("Purged JDK %d cache", version)
            return
        if _JDK_CACHE_DIR.exists():
            shutil.rmtree(_JDK_CACHE_DIR, ignore_errors=True)
            logger.info("Purged entire JDK cache")


def _get_common_prefix(paths: list[str]) -> str:
    if not paths:
        return ""
    parts = [p.split("/") for p in paths]
    i = 0
    while i < min(len(x) for x in parts):
        val = parts[0][i]
        if all(p[i] == val for p in parts):
            i += 1
        else:
            break
    if i == 0:
        return ""
    return "/".join(parts[0][:i]) + "/"


JdkManagerInstance = JdkManager()
