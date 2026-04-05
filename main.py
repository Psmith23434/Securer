"""
Securer — GUI entry point.
Run this file to launch the desktop application.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent))

from gui.app import SecurerApp

if __name__ == "__main__":
    app = SecurerApp()
    app.mainloop()
