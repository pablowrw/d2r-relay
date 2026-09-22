# PyInstaller: jeden katalog (onedir), bez konsoli.
# Onedir, nie onefile: exe uruchamia sam siebie jeszcze dwa razy (czytnik
# --reader i ikona --tray-helper) - onefile rozpakowywalby wszystko 3 razy
# przy kazdym starcie, a antywirusy czesciej go zatrzymuja.
# Budowanie: windows\build.bat (z katalogu projektu albo z windows\).
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [(os.path.join(ROOT, f), ".") for f in
         ("icon.png", "icon-48.png", "icon-64.png", "icon-128.png", "lobby_ref.png")]

a = Analysis(
    [os.path.join(ROOT, "d2rgui.py")],
    pathex=[ROOT],
    datas=datas,
    # backend pystray i moduly importowane dopiero w funkcjach
    hiddenimports=["pystray._win32", "PIL.ImageGrab", "presence", "webhook"],
    excludes=["pystray._xorg", "pystray._gtk", "pystray._appindicator"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="D2R-Relay",
    icon=os.path.join(SPECPATH, "icon.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="D2R-Relay", upx=False)
