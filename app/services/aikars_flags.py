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


def calculate_flags(ram_mb: int) -> list:
    """
    Calculate Aikar's JVM flags based on RAM allocation.

    Args:
        ram_mb: RAM allocation in megabytes (e.g., 2048, 4096, 8192).

    Returns:
        List of JVM argument strings.
    """
    flags = [
        f"-Xms{ram_mb}M",
        f"-Xmx{ram_mb}M",
        "--add-modules=jdk.incubator.vector",
        "-XX:+UseG1GC",
        "-XX:+ParallelRefProcEnabled",
        "-XX:MaxGCPauseMillis=200",
        "-XX:+UnlockExperimentalVMOptions",
        "-XX:+DisableExplicitGC",
        "-XX:+AlwaysPreTouch",
    ]

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


def flags_to_string(ram_mb: int) -> str:
    """
    Return Aikar's flags as a space-separated string.

    Useful for display in Advanced View or raw editing.
    """
    return " ".join(calculate_flags(ram_mb))


def build_java_command(
    java_path: str,
    ram_mb: int,
    jar_file: str,
    use_aikars: bool = True,
    extra_args: list = None,
) -> list:
    """
    Build the complete java command line for starting a Minecraft server.

    Args:
        java_path: Path to java binary (or "java" for PATH).
        ram_mb: RAM allocation in MB.
        jar_file: Server jar filename.
        use_aikars: Whether to apply Aikar's flags.
        extra_args: Additional JVM arguments.

    Returns:
        List of command-line arguments for subprocess.Popen.
    """
    cmd = [java_path]

    if use_aikars:
        cmd.extend(calculate_flags(ram_mb))
    else:
        cmd.extend([f"-Xms{ram_mb}M", f"-Xmx{ram_mb}M"])

    if extra_args:
        cmd.extend(extra_args)

    cmd.extend(["-jar", jar_file, "nogui"])
    return cmd
