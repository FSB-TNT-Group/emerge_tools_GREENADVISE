from pathlib import Path
import sys

def resource_path(rel_path: str) -> str:
    """
    Returns an absolute path to a resource that works both:
    - when running from source, and
    - when running a PyInstaller build (uses sys._MEIPASS).
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str((base / rel_path).resolve())
