"""
ZeroBlockBridge — Profileador de Rendimiento
Ejecuta este script con la app cerrada para medir línea base.
Uso: python scripts/profile_app.py
"""

import time
import os
import sys
import threading
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def measure_import_time():
    """Mide tiempo de importación de cada módulo principal."""
    modules = [
        "app.core.constants",
        "app.core.app_config",
        "app.core.server_events",
        "app.core.logic",
        "app.services.playit_api",
        "app.core.playit_manager",
        "app.core.version_manager",
        "app.services.java_detector",
        "app.services.java_installer",
        "app.services.modrinth",
        "app.ui.toast",
        "app.services.sanitizer",
        "app.services.scaffolder",
        "app.services.server_properties",
        "app.services.sha1_validator",
        "app.services.bytecode_analyzer",
        "app.services.console_buffer",
        "app.services.settings_manager",
        "app.core.single_instance",
        "app.core.statemanager",
        "app.core.core",
    ]
    print("=" * 60)
    print("IMPORT TIMES")
    print("=" * 60)
    total = 0.0
    for mod_name in modules:
        t0 = time.perf_counter()
        try:
            __import__(mod_name)
            t = (time.perf_counter() - t0) * 1000
            total += t
            print(f"  {mod_name:45s} {t:8.2f}ms")
        except Exception as e:
            print(f"  {mod_name:45s} FAILED: {e}")
    print(f"  {'TOTAL':45s} {total:8.2f}ms")
    print()

def measure_json_io():
    """Mide tiempo de lectura/escritura de metadata.json."""
    print("=" * 60)
    print("JSON I/O BENCHMARK (100 operations)")
    print("=" * 60)
    import json
    import tempfile

    data = {
        "name": "test_server",
        "ram": 2048,
        "type": "Vanilla",
        "version": "1.20.1",
        "java_path": "auto",
        "auto_install_jdk": False,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(json.dumps(data, indent=4))
        tmp = f.name

    # Read benchmark
    t0 = time.perf_counter()
    for _ in range(100):
        with open(tmp, "r") as f:
            json.load(f)
    read_ms = (time.perf_counter() - t0) * 1000

    # Write benchmark
    t0 = time.perf_counter()
    for _ in range(100):
        with open(tmp, "w") as f:
            json.dump(data, f, indent=4)
    write_ms = (time.perf_counter() - t0) * 1000

    os.unlink(tmp)
    print(f"  Read 100x:  {read_ms:8.2f}ms  ({read_ms/100:.3f}ms avg)")
    print(f"  Write 100x: {write_ms:8.2f}ms  ({write_ms/100:.3f}ms avg)")
    print()

def measure_thread_overhead():
    """Mide overhead de crear un thread vs llamada directa."""
    print("=" * 60)
    print("THREAD OVERHEAD BENCHMARK")
    print("=" * 60)

    def nothing():
        pass

    # Direct call
    t0 = time.perf_counter()
    for _ in range(1000):
        nothing()
    direct_ms = (time.perf_counter() - t0) * 1000

    # Thread creation
    t0 = time.perf_counter()
    threads = []
    for _ in range(1000):
        t = threading.Thread(target=nothing, daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    thread_ms = (time.perf_counter() - t0) * 1000

    print(f"  1000x direct call: {direct_ms:8.2f}ms  ({direct_ms/1000:.3f}ms per call)")
    print(f"  1000x thread:      {thread_ms:8.2f}ms  ({thread_ms/1000:.3f}ms per thread)")
    print(f"  Thread overhead:   {thread_ms/direct_ms:.0f}x slower")
    print()

def measure_os_listdir():
    """Mide tiempo de os.listdir() vs thread creation."""
    print("=" * 60)
    print("FILESYSTEM vs THREAD OVERHEAD")
    print("=" * 60)
    import tempfile

    # Create temp dir with files
    tmpdir = tempfile.mkdtemp()
    for i in range(10):
        open(os.path.join(tmpdir, f"file{i}.txt"), "w").close()

    t0 = time.perf_counter()
    for _ in range(100):
        os.listdir(tmpdir)
    listdir_ms = (time.perf_counter() - t0) * 1000

    import shutil
    shutil.rmtree(tmpdir)

    print(f"  os.listdir() 100x: {listdir_ms:8.2f}ms  ({listdir_ms/100:.3f}ms avg)")
    print(f"  -> Thread creation is ~{1000*listdir_ms/100:.0f}x more expensive than listdir")
    print()

def measure_memory():
    """Mide huella de memoria después de imports clave."""
    print("=" * 60)
    print("MEMORY USAGE (tracemalloc)")
    print("=" * 60)
    try:
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        import app.core.core
        import app.ui.main as _  # Only imports, doesn't instantiate GUI

        snapshot2 = tracemalloc.take_snapshot()
        stats = snapshot2.compare_to(snapshot1, "lineno")

        current, peak = tracemalloc.get_traced_memory()
        print(f"  Current memory: {current / 1024:.1f} KB")
        print(f"  Peak memory:    {peak / 1024:.1f} KB")
        print()
        print("  Top 10 allocations:")
        for stat in stats[:10]:
            print(f"    {stat}")
        tracemalloc.stop()
    except Exception as e:
        print(f"  Memory measurement failed: {e}")
    print()

def check_locks():
    """Verifica presencia de RLock/Lock que puedan causar contención."""
    print("=" * 60)
    print("LOCK ANALYSIS (static)")
    print("=" * 60)
    import ast
    import glob as glob_mod

    lock_files = []
    for fpath in glob_mod.glob("app/**/*.py", recursive=True):
        with open(fpath, "r") as f:
            try:
                tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Attribute) and node.func.attr in ("RLock", "Lock"):
                            lock_files.append((fpath, node.lineno, node.func.attr))
                        elif isinstance(node.func, ast.Name) and node.id in ("RLock", "Lock"):
                            lock_files.append((fpath, node.lineno, node.id))
            except SyntaxError:
                pass

    if lock_files:
        print(f"  Found {len(lock_files)} lock creations:")
        for f, lineno, lock_type in lock_files:
            print(f"    {f}:{lineno} ({lock_type})")
    else:
        print("  No locks found.")
    print()

if __name__ == "__main__":
    print()
    print("  ZERO BLOCK BRIDGE — Performance Profiler")
    print("  " + "=" * 36)
    print()

    measure_import_time()
    measure_json_io()
    measure_thread_overhead()
    measure_os_listdir()
    measure_memory()
    check_locks()

    print("=" * 60)
    print("DONE. Review the numbers above for baseline.")
    print("=" * 60)
