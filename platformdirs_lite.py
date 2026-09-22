#!/usr/bin/env python3
"""
platformdirs_lite - gdzie trzymac config i dane, osobno dla Linuksa i Windowsa.

Male, wlasne, bez zaleznosci. Linux: ~/.config/d2r-relay i ~/.local/share/d2r-relay
(XDG), Windows: %APPDATA%\\d2r-relay i %LOCALAPPDATA%\\d2r-relay.
Katalogi z dawnej nazwy programu (d2r-gamereader) przenosza sie same przy
pierwszym starcie.
"""
import os
import shutil
import sys
from pathlib import Path

APP = "d2r-relay"
OLD_APP = "d2r-gamereader"
WINDOWS = sys.platform == "win32"


def _config_base():
    if WINDOWS:
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _data_base():
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def config_dir():
    return _config_base() / APP


def data_dir():
    return _data_base() / APP


def _migrate():
    """Przeniesienie ustawien spod dawnej nazwy; nowe katalogi maja pierwszenstwo."""
    for base in (_config_base(), _data_base()):
        old, new = base / OLD_APP, base / APP
        if not old.is_dir() or new.exists():
            continue
        try:
            old.rename(new)
        except OSError:             # np. inny dysk albo plik zajety - kopia
            try:
                shutil.copytree(old, new)
            except OSError:
                pass


def secure_write(path, text):
    """Zapis poswiadczenia (adres webhooka). Na Linuksie 0600; na Windowsie
    prawa dziedzicza sie z katalogu uzytkownika i chmod jest bez znaczenia."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if not WINDOWS:
        os.chmod(path, 0o600)


_migrate()
