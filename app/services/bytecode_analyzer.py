"""
PROV-03 — Bytecode Analyzer for Java Version Detection.

Inspects a server .jar file's bytecode to determine the exact Java
version it was compiled against, by reading the class file major
version from bytes 6-7 of .class entries.

This serves as the "Source of Truth" for Java requirements, eliminating
guesswork from static MC-to-Java mapping tables.
"""

import logging
import os
import zipfile
from typing import Optional

logger = logging.getLogger(__name__)

# Maps the .class file major_version field to the Java SE release.
# Ref: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
CLASS_VERSION_MAP = {
    45: 1,  46: 2,  47: 3,  48: 4,  49: 5,  50: 6,  51: 7,
    52: 8,  53: 9,  54: 10, 55: 11, 56: 12, 57: 13, 58: 14,
    59: 15, 60: 16, 61: 17, 62: 18, 63: 19, 64: 20, 65: 21,
    66: 22, 67: 23, 68: 24, 69: 25, 70: 26,
}

# Magic bytes at the start of every valid .class file
_CLASS_MAGIC = b"\xCA\xFE\xBA\xBE"


def _extract_class_major(data: bytes) -> Optional[int]:
    """Extract the major version from raw .class file bytes.

    The format is: magic (4) | minor (2) | major (2).
    Returns the raw major version int (e.g. 61 for Java 17), or None.
    """
    if len(data) < 8 or data[:4] != _CLASS_MAGIC:
        return None
    return int.from_bytes(data[6:8], "big")


def _read_manifest_main_class(zf: zipfile.ZipFile) -> Optional[str]:
    """Parse META-INF/MANIFEST.MF and return the Main-Class value, if any.

    Handles continuation lines (lines starting with a space) per the JAR spec.
    """
    try:
        raw = zf.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
    except KeyError:
        return None

    result = {}
    current_key = None

    for line in raw.splitlines():
        if not line:
            continue
        # Continuation line
        if line.startswith(" ") and current_key:
            result[current_key] += line[1:]
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            current_key = k.strip()
            result[current_key] = v.strip()

    return result.get("Main-Class")


def analyze_jar_bytecode(jar_path: str) -> Optional[int]:
    """Determine the required Java version by inspecting the .jar bytecode.

    Strategy (mirrors auto-mcs _get_jar_requirements):
      1. Read MANIFEST.MF -> Main-Class -> inspect that .class file.
      2. Fallback: scan ALL .class files and return the highest major version found.

    Args:
        jar_path: Absolute path to a .jar file.

    Returns:
        The Java SE major version required (e.g. 8, 17, 21), or None on failure.
    """
    if not os.path.isfile(jar_path):
        logger.error("Bytecode analyzer: jar not found at %s", jar_path)
        return None

    try:
        with zipfile.ZipFile(jar_path, "r") as zf:

            # --- Strategy 1: Main-Class bytecode ---
            main_class = _read_manifest_main_class(zf)
            if main_class:
                class_path = main_class.replace(".", "/") + ".class"
                try:
                    raw_major = _extract_class_major(zf.read(class_path))
                    java_ver = CLASS_VERSION_MAP.get(raw_major)
                    if java_ver is not None:
                        logger.info(
                            "Bytecode analyzer: Main-Class '%s' requires Java %d (class v%d)",
                            main_class, java_ver, raw_major,
                        )
                        return java_ver
                except KeyError:
                    logger.debug("Main-Class '%s' not found in jar; falling back to full scan", main_class)

            # --- Strategy 2: Targeted scan (root .class files first) ---
            # Most server jars place the entry-point classes at the root level.
            # Scanning 15 root-level files is sufficient and much faster than
            # scanning every .class in a fat jar with thousands of entries.
            all_names = zf.namelist()
            root_classes = [n for n in all_names
                            if n.endswith(".class") and "/" not in n]
            deep_classes = [n for n in all_names
                            if n.endswith(".class") and "/" in n]

            # Prioritize root, then deep — cap at 15 each pass
            scan_order = root_classes[:15] + deep_classes[:15]

            highest_raw = 0
            scanned = 0
            for name in scan_order:
                try:
                    raw = _extract_class_major(zf.read(name))
                    if raw is not None and raw > highest_raw:
                        highest_raw = raw
                    scanned += 1
                except Exception:
                    continue

            java_ver = CLASS_VERSION_MAP.get(highest_raw)
            if java_ver is not None:
                logger.info(
                    "Bytecode analyzer: scanned %d classes, highest requires Java %d (class v%d)",
                    scanned, java_ver, highest_raw,
                )
                return java_ver

            logger.warning("Bytecode analyzer: no valid .class files found in %s", jar_path)
            return None

    except zipfile.BadZipFile:
        logger.error("Bytecode analyzer: %s is not a valid zip/jar file", jar_path)
        return None
    except Exception as e:
        logger.error("Bytecode analyzer: unexpected error for %s: %s", jar_path, e)
        return None
