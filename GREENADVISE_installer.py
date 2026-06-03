"""
GREENADVISE V1.1 - First-Time Setup Installer
Run once before launching the app:
    python GREENADVISE_installer.py

Pinned package versions (tested and confirmed working):
  PyQt5 5.15.11, PyQtWebEngine 5.15.7, matplotlib 3.10.9,
  numpy 2.3.5, pandas 2.3.3, pyomo 6.9.5, requests 2.32.5,
  openpyxl 3.1.5, scipy 1.17.0, numpy-financial 1.0.0,
  reportlab 4.5.1, torch 2.7.0 (CPU)

To upgrade to newer versions, update the version strings below
and re-run this script.
"""

import sys
import subprocess
import importlib.util
import platform
import os
import tempfile
import urllib.request

PACKAGES = [
    # (pip_spec, import_name, description, extra_pip_args)
    # pip_spec uses == for exact version pinning — change here to upgrade
    ("PyQt5==5.15.11",          "PyQt5",                   "Qt5 GUI framework — all windows, buttons, and layouts",        []),
    ("PyQtWebEngine==5.15.7",   "PyQt5.QtWebEngineWidgets", "Qt WebEngine — interactive Leaflet map display",               []),
    ("matplotlib==3.10.9",      "matplotlib",               "Plotting library — charts, pie charts, time-series plots",     []),
    ("numpy==2.3.5",            "numpy",                    "Numerical computing — arrays and math operations",             []),
    ("pandas==2.3.3",           "pandas",                   "Data manipulation — CSV/Excel reading, DataFrames",            []),
    ("pyomo==6.9.5",            "pyomo",                    "Optimization modeling framework — energy system models",       []),
    ("requests==2.32.5",        "requests",                 "HTTP client — Renewables.ninja API calls",                     []),
    ("openpyxl==3.1.5",         "openpyxl",                 "Excel file support — export results to .xlsx",                 []),
    ("scipy==1.17.0",           "scipy",                    "Scientific computing — used internally by Pyomo",              []),
    ("numpy-financial==1.0.0",  "numpy_financial",           "Financial functions — ROIcalculations in results",       []),
    ("reportlab==4.5.1",        "reportlab",                "PDF report generation — export optimization results to PDF",   []),
    # PyTorch CPU-only (~250 MB). For NVIDIA GPU support run manually:
    #   pip install torch --index-url https://download.pytorch.org/whl/cu121
    ("torch==2.7.0",            "torch",                    "PyTorch — LSTM-VAE neural network for stochastic scenarios",
     ["--index-url", "https://download.pytorch.org/whl/cpu"]),
]

MIN_PYTHON = (3, 9)
W = 60

VCREDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"


def separator(char="─"):
    print(char * W, flush=True)


def check_python() -> bool:
    v  = sys.version_info
    pv = sys.version.split()[0]
    ok = v.major > MIN_PYTHON[0] or (v.major == MIN_PYTHON[0] and v.minor >= MIN_PYTHON[1])
    status = "OK" if ok else f"WARNING — Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required"
    print(f"  Python version : {pv}  [{status}]")
    if not ok:
        print()
        print(f"  ERROR: Found Python {pv}, but {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required.")
        print(f"  Download a newer version: https://www.python.org/downloads/")
        print()
    return ok


def check_pip() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            ver = result.stdout.strip().split()[1]
            print(f"  pip version    : {ver}  [OK]")
            return True
        else:
            print("  pip            : NOT FOUND")
            print("  Try: python -m ensurepip --upgrade")
            return False
    except Exception as e:
        print(f"  pip check      : ERROR ({e})")
        return False


def check_vcredist():
    """Returns True if installed, False if not found, None if cannot determine."""
    if platform.system() != "Windows":
        return True
    try:
        import winreg
        keys = [
            r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
            r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
        ]
        for key_path in keys:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                    installed, _ = winreg.QueryValueEx(key, "Installed")
                    if installed:
                        return True
            except FileNotFoundError:
                continue
        return False
    except Exception:
        return None


def install_vcredist() -> bool:
    """Download and silently install Visual C++ Redistributable 2015-2022 x64."""
    tmp = tempfile.mktemp(suffix="_vc_redist.x64.exe")
    try:
        print(f"  Downloading VC++ Redistributable (~25 MB)...")
        print(f"  Source: {VCREDIST_URL}")

        def _progress(count, block_size, total_size):
            if total_size > 0:
                pct = min(int(count * block_size * 100 / total_size), 100)
                print(f"\r  Progress: {pct}%", end="", flush=True)

        urllib.request.urlretrieve(VCREDIST_URL, tmp, reporthook=_progress)
        print()

        print("  Running installer (silent, no restart)...")
        result = subprocess.run([tmp, "/quiet", "/norestart"], capture_output=True)
        if result.returncode in (0, 3010):  # 3010 = success, reboot later
            print("  ✔  VC++ Redistributable installed successfully.")
            if result.returncode == 3010:
                print("  NOTE: A system restart may be required later.")
            return True
        else:
            print(f"  ✘  Installer exited with code {result.returncode}.")
            print("     Try running as Administrator, or install manually:")
            print(f"     {VCREDIST_URL}")
            return False
    except Exception as e:
        print(f"  ✘  Failed to install VC++ Redistributable: {e}")
        print(f"     Download manually: {VCREDIST_URL}")
        return False
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def ensure_vcredist():
    if platform.system() != "Windows":
        return
    vcredist = check_vcredist()
    if vcredist is True:
        print("  VC++ Redist    : Installed  [OK]")
        return
    if vcredist is False:
        print("  VC++ Redist    : NOT FOUND  — installing automatically...")
    else:
        print("  VC++ Redist    : Could not determine — attempting install anyway...")
    print()
    install_vcredist()


def _installed_version(import_name: str) -> str | None:
    """Return the installed version string for a package, or None."""
    try:
        import importlib.metadata
        # Map import name to distribution name for lookup
        dist_map = {
            "PyQt5":                   "PyQt5",
            "PyQt5.QtWebEngineWidgets": "PyQtWebEngine",
            "matplotlib":              "matplotlib",
            "numpy":                   "numpy",
            "pandas":                  "pandas",
            "pyomo":                   "pyomo",
            "requests":                "requests",
            "openpyxl":                "openpyxl",
            "scipy":                   "scipy",
            "numpy_financial":         "numpy-financial",
            "reportlab":               "reportlab",
            "torch":                   "torch",
        }
        dist_name = dist_map.get(import_name, import_name)
        return importlib.metadata.version(dist_name)
    except Exception:
        return None


def is_installed(import_name):
    try:
        if "." in import_name:
            mod = importlib.import_module(import_name.split(".")[0])
            for part in import_name.split(".")[1:]:
                mod = getattr(mod, part, None)
                if mod is None:
                    return False
            return True
        return importlib.util.find_spec(import_name) is not None
    except Exception:
        return False


def install_package(pip_spec, extra_args=None):
    cmd = [sys.executable, "-m", "pip", "install", pip_spec]
    if extra_args:
        cmd.extend(extra_args)
    print(f"  $ {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in proc.stdout:
        print("  " + line, end="", flush=True)
    proc.wait()
    return proc.returncode == 0


def main():
    print()
    separator("=")
    print("  GREENADVISE V1.1  —  First-Time Setup Installer")
    separator("=")
    print()

    # ── Prerequisites check ───────────────────────────────────────────────────
    print("  PREREQUISITES CHECK")
    separator()

    python_ok = check_python()
    pip_ok    = check_pip()
    ensure_vcredist()

    print()

    if not python_ok:
        sys.exit(1)
    if not pip_ok:
        sys.exit(1)

    # ── Pre-install status check ──────────────────────────────────────────────
    print(f"  {'Package':<22} {'Required':<12} {'Installed':<12} Status")
    separator()
    for pip_spec, import_name, description, *_ in PACKAGES:
        # pip_spec is e.g. "numpy==2.3.5" or "torch==2.7.0"
        if "==" in pip_spec:
            pkg_name, required_ver = pip_spec.split("==", 1)
        else:
            pkg_name, required_ver = pip_spec, "any"

        current = _installed_version(import_name)
        if current is None:
            status = "Will install"
        elif current == required_ver:
            status = "OK"
        else:
            status = f"Will change ({current} → {required_ver})"

        print(f"  {pkg_name:<22} {required_ver:<12} {(current or '—'):<12} {status}")
    print()

    # ── Confirm ───────────────────────────────────────────────────────────────
    try:
        answer = input("  Press ENTER to install / pin all packages, or type 'q' to quit: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Aborted.")
        sys.exit(0)

    if answer == "q":
        print("  Aborted.")
        sys.exit(0)

    # ── Install ───────────────────────────────────────────────────────────────
    print()
    total  = len(PACKAGES)
    failed = []

    for i, (pip_spec, import_name, description, extra_args) in enumerate(PACKAGES, 1):
        print()
        separator()
        pkg_name = pip_spec.split("==")[0] if "==" in pip_spec else pip_spec
        note = "  (CPU-only, ~250 MB — see top of file for GPU version)" if pkg_name == "torch" else ""
        print(f"  [{i}/{total}]  Installing: {pip_spec}{note}")
        separator()

        ok       = install_package(pip_spec, extra_args)
        verified = ok or is_installed(import_name)

        if verified:
            print(f"  ✔  {pip_spec}  —  OK")
        else:
            print(f"  ✘  {pip_spec}  —  FAILED")
            failed.append(pip_spec)

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    separator("=")
    if failed:
        print(f"  Finished with {len(failed)} error(s):")
        for p in failed:
            print(f"    •  {p}")
        print()
        print("  Try installing them manually:")
        print(f"    pip install {' '.join(failed)}")
    else:
        print("  All packages installed successfully.")
        print("  You can now launch GREENADVISE.")
    separator("=")
    print()


if __name__ == "__main__":
    main()
