"""Entry of the Qt spike exe (packaging/qt_spike.spec): the regular
launcher with ``--ui=qt``."""
import runpy
import sys

if "--ui=qt" not in sys.argv:
    sys.argv.insert(1, "--ui=qt")
runpy.run_module("app.launcher", run_name="__main__", alter_sys=True)
