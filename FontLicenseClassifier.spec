# -*- mode: python ; coding: utf-8 -*-
"""
Configuration PyInstaller pour FontLicenseClassifier.

Utilisation (depuis Windows, avec le venv active) :
    pyinstaller FontLicenseClassifier.spec

Voir build.ps1 pour un script pret a l'emploi qui installe pyinstaller et
lance la compilation en une seule commande.
"""
from PyInstaller.utils.hooks import collect_data_files

# CustomTkinter embarque ses propres fichiers de theme (JSON) et assets
# (images des widgets) qui doivent etre copies tels quels dans l'exe.
customtkinter_datas = collect_data_files("customtkinter")

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('data/known_licenses.json', 'data'),
        ('FontCheck_tool/FontCheck.ico', 'FontCheck_tool'),
        ('FontCheck_tool/FontCheck.png', 'FontCheck_tool'),
        *customtkinter_datas,
    ],
    hiddenimports=[
        'customtkinter',
        'PIL._tkinter_finder',
        'aiohttp',
        'bs4',
        'openpyxl',
        'pandas',
        'fontTools.ttLib',
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
    name='FontLicenseClassifier',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # False = fenetre sans console (application graphique)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['FontLicenseClassifier.ico'],
)
