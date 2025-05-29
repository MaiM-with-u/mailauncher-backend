# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for MaiLauncher Backend
# This file contains the configuration for building the MaiLauncher Backend executable
# Company: MaiM-with-u
# Product: MaiLauncher Backend v0.0.1
# Description: MaiBot实例管理和部署工具的后端服务


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('data', 'data'), ('src', 'src')],
    hiddenimports=[
        'uvicorn',
        'fastapi',
        'sqlalchemy',
        'sqlite3',
        'asyncio',
        'pathlib',
        'httpx',
        'pydantic',
        'toml',
        'loguru',
        'websockets',
        'psutil'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MaiLauncher-Backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['.\\assets\\maimai.ico'],
    version='version_info.txt',
)
