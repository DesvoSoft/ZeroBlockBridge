"""Entry of the visual-ceiling exes (packaging/qt_visual.spec): the regular
launcher with ``--ui=qt --variant=<widgets|qml>`` (variant baked in at build)."""
import runpy
import sys

VARIANT = "qml"  # rewritten by qt_visual.spec

for arg in ("--ui=qt", f"--variant={VARIANT}"):
    if arg not in sys.argv:
        sys.argv.insert(1, arg)
runpy.run_module("app.launcher", run_name="__main__", alter_sys=True)
