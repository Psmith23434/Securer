"""
Snippet Tool — entry point.
Runs the CustomTkinter GUI. All sensitive logic lives in core/ (compiled to .pyd).
"""
import sys
import threading
from pathlib import Path

# Allow imports from project root (shared/)
sys.path.insert(0, str(Path(__file__).parent.parent))

from snippet_tool.gui.app import SnippetApp
from shared.updater import check_for_update

APP_NAME = "snippet_tool"
VERSION = (Path(__file__).parent / "version.txt").read_text().strip()


def _background_update_check(app):
    result = check_for_update(APP_NAME, VERSION)
    if result:
        # Safe: schedule UI update on main thread via CTk's after()
        app.after(0, lambda: app.show_update_banner(result))


def main():
    app = SnippetApp(version=VERSION)
    threading.Thread(target=_background_update_check, args=(app,), daemon=True).start()
    app.mainloop()


if __name__ == "__main__":
    main()
