import sys
import os
import faulthandler
import matplotlib
matplotlib.use('Agg')
# QtWebEngine (Chromium) flags applied before QApplication starts.
#   --log-level=3            : silence DirectComposition warnings.
# The remaining flags force software rendering so the embedded browser still
# paints on locked-down machines (university/VDI/remote desktop) where the GPU
# process is blocked or sandboxed. Without these, every QWebEngineView — the map
# and the plotly 3D / sediment-timeline plots — renders blank even though the
# HTML is generated correctly and opens fine in a normal browser.
#   --ignore-gpu-blocklist   : don't refuse the GPU just because it's blocklisted.
#   --enable-unsafe-swiftshader : allow SwiftShader (software) WebGL, which
#                                 plotly 3D and MapLibre need.
#   --disable-gpu-sandbox    : the GPU sandbox is the usual thing locked down.
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--log-level=3 --ignore-gpu-blocklist --enable-unsafe-swiftshader --disable-gpu-sandbox",
)

# ---------------------------------------------------------------------------
# Windows / conda DLL-shadowing workaround.
# Conda injects <env>\Library\bin into the DLL search path, and DLLs in there
# (shipped by GDAL/PROJ/etc.) can shadow same-named dependencies of the Qt6
# DLLs bundled with pip's PyQt6, producing:
#   ImportError: DLL load failed while importing QtCore:
#   The specified procedure could not be found.
# Pre-loading the Qt DLLs with an isolated search path (their own folder plus
# System32 only) resolves their dependencies correctly; every later import of
# PyQt6 then binds to these already-loaded copies by name. Harmless when run
# outside conda or on non-Windows platforms.
# This MUST run before the first PyQt6 import anywhere in the process.
if sys.platform == "win32":
    import ctypes
    import PyQt6

    _qt_bin = os.path.join(os.path.dirname(PyQt6.__file__), "Qt6", "bin")
    # LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR (0x100) | LOAD_LIBRARY_SEARCH_SYSTEM32 (0x800)
    _WINMODE = 0x00000100 | 0x00000800
    for _dll in (
        "Qt6Core.dll",
        "Qt6Gui.dll",
        "Qt6Widgets.dll",
        "Qt6Network.dll",
        "Qt6WebChannel.dll",
        "Qt6WebEngineCore.dll",
        "Qt6WebEngineWidgets.dll",
    ):
        _path = os.path.join(_qt_bin, _dll)
        if os.path.exists(_path):
            try:
                ctypes.WinDLL(_path, winmode=_WINMODE)
            except OSError:
                # Fall through: the normal import will surface a clearer error.
                pass
# ---------------------------------------------------------------------------

from PyQt6.QtWidgets import QApplication
from app.ui.views.home_window import HomeWindow
from app.ui.themes import ThemeManager
from app.core.config import Config
from app.data.database import db_manager

from app.core.logging import LogManager

# Module-level so the open file object outlives main()'s local scope for the
# whole process lifetime instead of being eligible for garbage collection.
_crash_log_file = None

def main():
    """Start the application, initialize theme, and show the main window."""
    LogManager.setup()
    Config.init_directories()

    # A native crash (segfault / access violation in a C extension such as
    # GDAL, rasterio, or matplotlib's Agg backend) kills the whole process
    # instantly -- no Python exception, no traceback, every window just
    # vanishes. That bypasses normal exception handling, so there's nothing
    # for a try/except to catch. faulthandler installs a low-level signal
    # handler that writes the Python frame (on every thread, including the
    # simulation's background QThread) that was executing at the moment of
    # the fault to this file just before the process dies -- diagnosable
    # without Event Viewer or admin rights. dump_traceback_later is a
    # heartbeat that periodically dumps all thread stacks too, so a genuine
    # hang (not a crash) leaves the same kind of evidence behind.
    global _crash_log_file
    _crash_log_file = open(Config.LOGS_DIR / "crash.log", "w", buffering=1, encoding="utf-8")
    faulthandler.enable(file=_crash_log_file)
    faulthandler.dump_traceback_later(300, repeat=True, file=_crash_log_file)

    # Initialize database: create the schema, then seed the reference data
    # (locations, DEMs, components, lithologies, vegetation classes) if the
    # tables are empty. This regenerates a working DB from source, so the
    # SQLite binary does not need to be committed.
    db_manager.create_tables()
    from app.data.seed import seed_database
    session = db_manager.get_session()
    try:
        seed_database(session)
    finally:
        session.close()

    app = QApplication(sys.argv)

    # Initialize theme manager
    theme_manager = ThemeManager()
    theme_manager.set_theme(ThemeManager.DARK)

    # Create and show the main application window
    # This is the starting point of the User Interface
    main_window = HomeWindow()
    main_window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
