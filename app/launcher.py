import sys
import os

# Ensure the project root is in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app.core.installer import UNINSTALL_ARG

if UNINSTALL_ARG in sys.argv:
    # Settings > Apps > Uninstall runs `ZeroBlockBridge.exe --uninstall`.
    from app.ui.first_run_dialog import run_uninstall
    sys.exit(run_uninstall())

# Must resolve before any `app.core.constants` import -- it fixes
# BASE_DIR (and everything derived from it) at import time.
from app.core.bootstrap import resolve_data_dir
resolve_data_dir()

if "--ui=qt" in sys.argv:
    # Roadmap 8c spike: the PySide6 UI (needs requirements-qt.txt).
    from app.ui_qt.app import main
else:
    from app.ui.main import main

if __name__ == "__main__":
    main()
