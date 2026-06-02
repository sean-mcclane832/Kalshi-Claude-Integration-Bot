# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Kalshi Supervised Trading Assistant
#
# Build:
#   pip install pyinstaller>=6.0
#   pyinstaller app.spec
#
# Output:  dist/KalshiAssistant/  (directory mode — smaller & faster)
#          dist/KalshiAssistant/KalshiAssistant(.exe on Windows)
#
# IMPORTANT: .env is NOT bundled (it contains API keys).
# On first launch the user opens Settings and saves keys there;
# the app writes .env next to the executable automatically.

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── hidden imports ────────────────────────────────────────────────────────────
hidden_imports = [
    # pywebview backends — include all so the correct one is picked at runtime
    "webview",
    "webview.platforms.winforms",   # Windows
    "webview.platforms.cocoa",      # macOS
    "webview.platforms.gtk",        # Linux GTK
    "webview.platforms.qt",         # Linux Qt
    "webview.js.css",
    "clr",                          # pythonnet (Windows EdgeChromium)
    # anthropic SDK internals
    "anthropic",
    "anthropic._client",
    "httpx",
    "httpcore",
    "anyio",
    "anyio._backends._asyncio",
    "anyio._backends._trio",
    # yfinance / pandas stack
    "yfinance",
    "pandas",
    "pandas._libs.tslibs.np_datetime",
    "pandas._libs.tslibs.nattype",
    "pandas._libs.tslibs.timezones",
    "numpy",
    # APScheduler
    "apscheduler",
    "apscheduler.schedulers.background",
    "apscheduler.triggers.interval",
    "apscheduler.executors.pool",
    "apscheduler.jobstores.memory",
    # SQLAlchemy
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.pool",
    # pydantic
    "pydantic",
    "pydantic.v1",
    # misc
    "bs4",
    "lxml",
    "lxml.etree",
    "cryptography",
    "tenacity",
    "dotenv",
    "yaml",
]

# Collect all APScheduler submodules (it uses dynamic imports heavily)
hidden_imports += collect_submodules("apscheduler")
hidden_imports += collect_submodules("anthropic")

# ── data files ────────────────────────────────────────────────────────────────
datas = [
    # Web UI assets (HTML/CSS/JS)
    ("desktop/web", "desktop/web"),
    # Default config (user-tunable thresholds; not secrets)
    ("config.yaml", "."),
]

# Collect pywebview's own data (JS glue code it ships internally)
datas += collect_data_files("webview")

# ── analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ["run_desktop.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "test",
        "unittest",
        "xmlrpc",
        "email",
        "html",
        "http",
        "urllib",       # keep urllib3 but remove stdlib urllib if desired
        "distutils",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # directory mode (faster startup)
    name="KalshiAssistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                  # no terminal window on Windows/macOS
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows only: give it an icon if you have one
    # icon="desktop/web/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="KalshiAssistant",
)

# ── macOS .app bundle (ignored on other platforms) ───────────────────────────
app = BUNDLE(
    coll,
    name="KalshiAssistant.app",
    icon=None,                      # set to "desktop/web/icon.icns" if available
    bundle_identifier="com.kalshi-assistant.desktop",
    info_plist={
        "NSHighResolutionCapable": True,
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleName": "Kalshi Assistant",
        "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True},
    },
)
