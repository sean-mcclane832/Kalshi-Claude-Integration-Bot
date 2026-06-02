#!/usr/bin/env python3
"""
Build the Kalshi Assistant desktop app into a standalone executable.

Usage:
    python build.py           # build for the current platform
    python build.py --clean   # delete dist/ and build/ first
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", help="Remove dist/ and build/ before building")
    args = parser.parse_args()

    if args.clean:
        for d in ("dist", "build"):
            p = ROOT / d
            if p.exists():
                shutil.rmtree(p)
                print(f"Removed {p}")

    # Ensure PyInstaller is available
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not found — installing…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"])

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "app.spec"]
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)

    if result.returncode != 0:
        print("\nBuild FAILED.")
        sys.exit(result.returncode)

    exe_dir = ROOT / "dist" / "KalshiAssistant"
    print(f"\nBuild complete!  Output: {exe_dir}")
    print("\nNEXT STEPS:")
    print("  1. Copy dist/KalshiAssistant/ to any machine (no Python required).")
    print("  2. On first launch, open Settings and enter your API keys — they are")
    print("     saved to .env next to the executable (NOT bundled for security).")
    print("  3. On Linux, ensure a WebView backend is present:")
    print("       sudo apt install python3-gi python3-gi-cairo gir1.2-webkit2-4.0")
    print("     or install the Qt backend:")
    print("       pip install PyQtWebEngine  (then re-run build.py)")


if __name__ == "__main__":
    main()
