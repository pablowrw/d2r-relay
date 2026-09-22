"""
tray - ikona w zasobniku systemowym (pystray), opcjonalna.

Bez pystray program dziala jak dawniej, tylko opcja zasobnika jest wylaczona.
Ikona chodzi w osobnym, malym procesie: GTK (menu pod prawym przyciskiem na
X11) chce wlasnego watku glownego, a w jednym procesie z Tk menu sie nie
otwieralo. Rozmowa rurami: GUI -> "state 0|1 <podpowiedz>" / "quit",
ikona -> "show" / "toggle" / "quit".
"""
import os
import subprocess
import sys
import threading

if sys.platform.startswith("linux") and not os.environ.get("PYSTRAY_BACKEND"):
    desk = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    # na X11 poza GNOME/KDE (bspwm, i3, openbox...) zasobnik to klasyczny
    # XEmbed w pasku (polybar, tint2) - appindicator by sie tam nie pokazal.
    # gtk, nie xorg: xorg nie ma menu pod prawym przyciskiem
    if os.environ.get("XDG_SESSION_TYPE") == "x11" and not any(
            d in desk for d in ("gnome", "kde", "unity", "ubuntu")):
        os.environ["PYSTRAY_BACKEND"] = "gtk"

try:
    import pystray
    from PIL import Image
except Exception:        # brak pakietu albo backendu - bez zasobnika
    pystray = None


def available():
    return pystray is not None


def install_command():
    """Polecenie instalacji pystray dla tej dystrybucji; '' poza Linuksem
    (na Windowsie pystray jest spakowany razem z programem)."""
    if not sys.platform.startswith("linux"):
        return ""
    ids = ""
    try:
        for line in open("/etc/os-release", encoding="utf-8"):
            if line.startswith(("ID=", "ID_LIKE=")):
                ids += " " + line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    ids = ids.split()
    for keys, cmd in ((("arch", "manjaro", "endeavouros"), "sudo pacman -S python-pystray"),
                      (("debian", "ubuntu"), "sudo apt install python3-pystray"),
                      (("fedora", "rhel"), "sudo dnf install python3-pystray"),
                      (("opensuse", "suse"), "sudo zypper install python3-pystray")):
        if any(k in ids for k in keys):
            return cmd
    return "pip install --user pystray"


class Tray:
    """Strona GUI: uruchamia proces ikony, a jego zdarzenia wrzuca przez
    put() do kolejki GUI jako '@@tray@@show' / '@@tray@@toggle' / '@@tray@@quit'."""

    def __init__(self, icon_path, title, put, labels=None):
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--tray-helper"]
        else:
            cmd = [sys.executable, os.path.abspath(__file__)]
        kw = {}
        if sys.platform == "win32":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        # labels: Pokaz okno, Start, Stop, Zakoncz - w jezyku okna
        cmd += [str(icon_path), title] + list(labels or [])
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, encoding="utf-8", bufsize=1,
                                     env=dict(os.environ, PYTHONIOENCODING="utf-8"), **kw)

        def pump():
            for line in self.proc.stdout:
                put("@@tray@@" + line.strip())
            self.proc.wait()                 # bez zombie po zamknieciu ikony
        threading.Thread(target=pump, daemon=True).start()

    def _send(self, line):
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def set_state(self, running, tip):
        self._send("state %d %s" % (running, tip))

    def stop(self):
        self._send("quit")
        try:
            self.proc.stdin.close()
        except OSError:
            pass


def helper_main(argv):
    """Proces ikony: petla pystray w watku glownym, polecenia ze stdin."""
    if sys.platform.startswith("linux"):
        try:
            import ctypes
            ctypes.CDLL(None).prctl(15, b"d2r-relay-tray", 0, 0, 0)
        except (OSError, AttributeError):
            pass
    icon_path, title = argv[0], argv[1]
    show, start, stop, quit_ = (argv[2:6] if len(argv) >= 6
                                else ("Pokaz okno", "Start", "Stop", "Zakoncz"))
    state = {"running": False}

    def say(ev):
        print(ev, flush=True)

    menu = pystray.Menu(
        pystray.MenuItem(show, lambda: say("show"), default=True),
        pystray.MenuItem(lambda _: stop if state["running"] else start,
                         lambda: say("toggle")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(quit_, lambda: say("quit")),
    )
    icon = pystray.Icon("d2r-relay", Image.open(icon_path), title, menu)

    def read():
        for line in sys.stdin:           # koniec rury = GUI zniknelo
            cmd, _, rest = line.strip().partition(" ")
            if cmd == "quit":
                break
            if cmd == "state":
                flag, _, tip = rest.partition(" ")
                state["running"] = flag == "1"
                try:
                    icon.title = tip
                    icon.update_menu()
                except Exception:
                    pass
        icon.stop()

    def setup(ic):
        ic.visible = True
        threading.Thread(target=read, daemon=True).start()

    icon.run(setup=setup)


if __name__ == "__main__":
    helper_main(sys.argv[1:])
