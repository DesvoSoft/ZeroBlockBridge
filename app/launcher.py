import sys
import os

# Ensure the project root is in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app.ui.main import main

if __name__ == "__main__":
    main()
