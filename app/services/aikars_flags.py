"""
PROV-05 — Aikar's JVM Flags Calculator.

Generates optimized JVM arguments for Minecraft servers based on
RAM allocation, following Aikar's flags specification.

Reference: https://docs.papermc.io/paper/aikars-flags
"""

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Aikar's Flags Tiers
# ---------------------------------------------------------------------------
# These are the recommended JVM arguments for Minecraft servers,
# tuned by Aikar for GC performance. The key differentiator is
# the G1NewSizePercent and G1MaxNewSizePercent based on available RAM.


def calculate_flags(ram_mb: int, java_major: int = 17) -> list:
    """
    Calculate Aikar's JVM flags based on RAM allocation.

    Args:
        ram_mb: RAM allocation in megabytes (e.g., 2048, 4096, 8192).
        java_major: Java major version (to omit deprecated flags like ParallelRefProcEnabled).

    Returns:
        List of JVM argument strings.
    """
    flags = [
        f"-Xms{ram_mb}M",
        f"-Xmx{ram_mb}M",
        "--add-modules=jdk.incubator.vector",
        "-XX:+UseG1GC",
    ]
    if java_major < 26:
        flags.append("-XX:+ParallelRefProcEnabled")
        
    flags.extend([
        "-XX:MaxGCPauseMillis=200",
        "-XX:+UnlockExperimentalVMOptions",
        "-XX:+DisableExplicitGC",
        "-XX:+AlwaysPreTouch",
    ])

    # RAM-tier-specific G1 tuning
    if ram_mb >= 12288:  # 12G+
        flags.extend([
            "-XX:G1NewSizePercent=40",
            "-XX:G1MaxNewSizePercent=50",
            "-XX:G1HeapRegionSize=16M",
            "-XX:G1ReservePercent=15",
        ])
    elif ram_mb >= 8192:  # 8G–12G
        flags.extend([
            "-XX:G1NewSizePercent=35",
            "-XX:G1MaxNewSizePercent=50",
            "-XX:G1HeapRegionSize=16M",
            "-XX:G1ReservePercent=15",
        ])
    else:  # <8G (default tier)
        flags.extend([
            "-XX:G1NewSizePercent=30",
            "-XX:G1MaxNewSizePercent=40",
            "-XX:G1HeapRegionSize=8M",
            "-XX:G1ReservePercent=20",
        ])

    # Common GC tuning (all tiers)
    flags.extend([
        "-XX:G1HeapWastePercent=5",
        "-XX:G1MixedGCCountTarget=4",
        "-XX:InitiatingHeapOccupancyPercent=15",
        "-XX:G1MixedGCLiveThresholdPercent=90",
        "-XX:G1RSetUpdatingPauseTimePercent=5",
        "-XX:SurvivorRatio=32",
        "-XX:+PerfDisableSharedMem",
        "-XX:MaxTenuringThreshold=1",
        "-Dusing.aikars.flags=https://mcflags.emc.gs",
        "-Daikars.new.flags=true",
    ])

    return flags


