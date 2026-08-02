import sys
import os

# Ensure the project root is in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Must resolve before any `app.core.constants` import -- it fixes
# BASE_DIR (and everything derived from it) at import time.
from app.core.bootstrap import resolve_data_dir
resolve_data_dir()

from app.ui.main import main

if __name__ == "__main__":
    main()
