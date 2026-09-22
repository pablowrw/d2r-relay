"""
autostart - uruchamianie programu razem z systemem.

Linux: plik .desktop w ~/.config/autostart (standard XDG - GNOME, KDE, XFCE,
Cinnamon; goly menedzer okien jak bspwm/i3 potrzebuje np. 'dex -a').
Windows: wpis w HKCU\\...\\Run, bez uprawnien administratora.
Program startuje z --autostart: od razu schowany do zasobnika, jesli sie da.
"""
import os
import shlex
import sys
from pathlib import Path

NAME = "d2r-relay"
OLD_NAME = "d2r-gamereader"      # dawna nazwa programu - wpis przenosi sie sam
HERE = Path(__file__).resolve().parent
WINDOWS = sys.platform == "win32"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def command():
    """Polecenie uruchamiajace GUI - exe po spakowaniu, inaczej python + skrypt."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--autostart"]
    py = sys.executable
    if WINDOWS:
        w = Path(py).with_name("pythonw.exe")      # bez czarnego okna konsoli
        py = str(w) if w.exists() else py
    return [py, str(HERE / "d2rgui.py"), "--autostart"]


def _desktop_file(name=NAME):
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "autostart" / (name + ".desktop")


def _migrate():
    """Wpis pod dawna nazwa -> usuniety i zapisany od nowa (nowa sciezka exe)."""
    if WINDOWS:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
                winreg.QueryValueEx(k, OLD_NAME)
                winreg.DeleteValue(k, OLD_NAME)
        except OSError:
            return
    else:
        old = _desktop_file(OLD_NAME)
        if not old.exists():
            return
        old.unlink(missing_ok=True)
    set_enabled(True)


def enabled():
    _migrate()
    if WINDOWS:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, NAME)
            return True
        except OSError:
            return False
    return _desktop_file().exists()


def set_enabled(on):
    if WINDOWS:
        import subprocess
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command()))
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except FileNotFoundError:
                    pass
        return
    f = _desktop_file()
    if not on:
        f.unlink(missing_ok=True)
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("[Desktop Entry]\n"
                 "Type=Application\n"
                 "Name=D2R Relay\n"
                 "Exec=%s\n"
                 "Icon=%s\n"
                 "Terminal=false\n"
                 "X-GNOME-Autostart-enabled=true\n"
                 % (" ".join(shlex.quote(a) for a in command()), HERE / "icon.png"),
                 encoding="utf-8")
