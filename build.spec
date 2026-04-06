# -*- mode: python ; coding: utf-8 -*-

# PyInstaller spec file for Facebook Clone App
# Build command: pyinstaller build.spec

import os

block_cipher = None

# Files cần include
added_files = [
    # Templates
    ('templates', 'templates'),
    # Utils modules
    ('utils', 'utils'),
]

# Hidden imports
hidden_imports = [
    'flask',
    'playwright.sync_api',
    'playwright.async_api',
    'openpyxl',
    'PIL',
    'PIL.Image',
    'requests',
    'nest_asyncio',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Build thành 1 thư mục (onedir) thay vì 1 file exe
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FacebookClone',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Thu thập tất cả files vào 1 thư mục
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FacebookClone',
)
