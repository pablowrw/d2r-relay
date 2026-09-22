#!/usr/bin/env python3
"""
d2rgui - okienko do d2rread: start/stop pilnowania gry i cala konfiguracja.

Tkinter, bo siedzi w bibliotece standardowej i wyglada tak samo na Linuksie
i na Windowsie - nic do doinstalowania poza tym, czego czytnik i tak potrzebuje.

Sam odczyt chodzi w osobnym procesie (`d2rread.py watch`), a nie w watku tego
okna: dzieki temu wywrotka czytnika nie zabiera ze soba UI, a Stop naprawde
konczy robote, zamiast prosic petle, zeby laskawie zauwazyla flage.

Ustawienia pokazuje sie przez podglad, a nie przez skladnie: zamiast tlumaczyc,
co robi '{name}', okno rysuje makiete tego, co zobacza ludzie na Discordzie.
"""
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import d2rread
import autostart
import i18n
import platformdirs_lite as dirs
import single
import tray
import tkgfx
import webhook
from i18n import T, TR

READER = HERE / "d2rread.py"
OFFICIAL_ID = "1471657242729255086"     # wpis D2R z bazy wykrywanych gier Discorda
OFFICIAL_TITLE = "Diablo II: Resurrected"
WINDOWS = sys.platform == "win32"
FROZEN = getattr(sys, "frozen", False)        # exe z PyInstallera
LOG_LINES = 400
SAMPLE = "chaos-run-12"                  # nazwa gry uzywana w podgladach

C = {
    "bg":     "#22242b",
    "panel":  "#2b2e37",
    "card":   "#1c1e24",
    "fg":     "#e8e8ea",
    "muted":  "#9aa0ab",
    "gold":   "#d4a24a",
    "ok":     "#5fb87a",
    "warn":   "#d0806b",
    "line":   "#3a3e49",
    "field":  "#191b20",
}


def spawn(args, stdin=False):
    """Uruchamia d2rread bez migajacej konsoli na Windowsie. stdin=True daje
    rure, przez ktora okno odpowiada na pytania '> ... [Enter]'."""
    # UTF-8 w obie strony: na Windowsie rura mialaby kodowanie cp1250/cp1252
    kw = {"env": dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")}
    if stdin:
        kw["stdin"] = subprocess.PIPE
    if WINDOWS:
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    # spakowany exe nie ma d2rread.py obok - ten sam plik gra czytnik
    cmd = [sys.executable, "--reader"] if FROZEN else [sys.executable, str(READER)]
    return subprocess.Popen(cmd + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", bufsize=1, **kw)


def _button_layout(elem):
    return [(elem, {"sticky": "nsew", "children": [
        ("Button.padding", {"sticky": "nsew", "children": [
            ("Button.label", {"sticky": "nsew"})]})]})]


def _thin_scrollbar(st, name, trough):
    st.layout(name, [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    st.configure(name, troughcolor=trough, background=C["line"], bordercolor=trough,
                 lightcolor=C["line"], darkcolor=C["line"], arrowsize=8, gripcount=0)
    st.map(name, background=[("active", "#4a4f5c")])


def apply_theme(root):
    """Ciemny motyw w kolorach gry. Baza to 'clam' (jedyny wbudowany motyw,
    ktory daje sie przemalowac na obu systemach), ale przyciski, pola wyboru i
    kolka sa wlasnymi, wygladzonymi obrazkami z tkgfx - clam rysuje je
    kanciasto i z obrysami, ktorych kolorow nie da sie opanowac."""
    base = "Segoe UI" if WINDOWS else "DejaVu Sans"
    if base not in tkfont.families(root):
        base = tkfont.nametofont("TkDefaultFont").actual("family")
    for name, size, weight in (("TkDefaultFont", 10, "normal"),
                               ("TkTextFont", 10, "normal"),
                               ("TkHeadingFont", 10, "bold")):
        tkfont.nametofont(name).configure(family=base, size=size, weight=weight)

    st = ttk.Style(root)
    st.theme_use("clam")
    root.configure(background=C["bg"])
    st.configure(".", background=C["bg"], foreground=C["fg"],
                 fieldbackground=C["field"], bordercolor=C["line"],
                 lightcolor=C["line"], darkcolor=C["line"], focuscolor=C["bg"])
    st.configure("TFrame", background=C["bg"])
    st.configure("TLabel", background=C["bg"], foreground=C["fg"])
    st.configure("Muted.TLabel", background=C["bg"], foreground=C["muted"])
    st.configure("State.TLabel", background=C["panel"], foreground=C["fg"],
                 font=(base, 14, "bold"))
    st.configure("Game.TLabel", background=C["panel"], foreground=C["gold"],
                 font=(base, 11))
    st.configure("Head.TLabel", background=C["bg"], foreground=C["fg"],
                 font=(base, 11, "bold"))
    st.configure("Link.TLabel", background=C["bg"], foreground=C["gold"])

    st.configure("TEntry", foreground=C["fg"], insertcolor=C["fg"],
                 fieldbackground=C["field"], bordercolor=C["line"],
                 lightcolor=C["field"], darkcolor=C["field"], padding=5)
    st.map("TEntry", bordercolor=[("focus", C["gold"])],
           lightcolor=[("focus", C["field"])])
    # miejsce z prawej na ikonke oka w polu adresu webhooka
    st.configure("Hook.TEntry", padding=(5, 5, 32, 5))

    # Obrazki trzeba trzymac przy zyciu - Tk nie liczy referencji z Pythona.
    g = root._d2gfx = []

    def elem(name, *states, **kw):
        imgs = [img for *_, img in states]
        g.extend(imgs)
        st.element_create(name, "image", imgs[-1], *states[:-1], **kw)

    # Tk miesza polprzezroczyste rogi obrazka z tlem stylu, a clam podmienia to
    # tlo na jasne w stanach active/pressed/disabled - stad jasne narozniki.
    # Dlatego kazdy przycisk ma tlo przybite na stale do koloru powierzchni,
    # na ktorej lezy (surf), a zamiast 'disabled' jest osobny styl Idle.TButton.
    def btn(name, fill, hover, press, fg, surf=C["bg"]):
        mk = tkgfx.button
        elem(name + ".bg", ("pressed", mk(press)), ("active", mk(hover)),
             ("", mk(fill)), border=8, sticky="nsew")
        st.layout(name, _button_layout(name + ".bg"))
        st.configure(name, foreground=fg, background=surf, padding=(14, 6),
                     anchor="center")
        st.map(name, background=[(s, surf) for s in ("pressed", "active", "disabled")],
               foreground=[("active", fg)])

    btn("TButton", "#363a46", "#414654", "#2e313b", C["fg"])
    btn("Field.TButton", "#363a46", "#414654", "#2e313b", C["fg"], C["field"])
    btn("Accent.TButton", C["gold"], "#e2b35f", "#bf8f3c", "#20160a", C["panel"])
    btn("Danger.TButton", "#b9534b", "#c9635b", "#a4473f", "#ffffff", C["panel"])
    btn("Go.TButton", C["gold"], "#e2b35f", "#bf8f3c", "#20160a")
    btn("Halt.TButton", "#b9534b", "#c9635b", "#a4473f", "#ffffff")
    btn("Idle.TButton", "#2a2c33", "#2a2c33", "#2a2c33", C["muted"])
    # to samo na karcie (tlo panel) - etapy kalibracji
    btn("PGo.TButton", C["gold"], "#e2b35f", "#bf8f3c", "#20160a", C["panel"])
    btn("PBtn.TButton", "#3b3f4b", "#464b59", "#33363f", C["fg"], C["panel"])
    btn("PHalt.TButton", "#b9534b", "#c9635b", "#a4473f", "#ffffff", C["panel"])
    btn("PIdle.TButton", "#30333c", "#30333c", "#30333c", C["muted"], C["panel"])
    for s in ("Accent.TButton", "Danger.TButton"):
        st.configure(s, font=(base, 11, "bold"), padding=(26, 10))

    ck, rd = tkgfx.checkbox, tkgfx.radio
    edge, hover = "#5a606d", "#7b8290"
    elem("d2.check", ("selected", ck(True, C["field"], edge, C["gold"], "#20160a")),
         ("active", ck(False, C["field"], hover, C["gold"], "#20160a")),
         ("", ck(False, C["field"], edge, C["gold"], "#20160a")), sticky="")
    elem("d2.radio", ("selected", rd(True, C["field"], edge, C["gold"])),
         ("active", rd(False, C["field"], hover, C["gold"])),
         ("", rd(False, C["field"], edge, C["gold"])), sticky="")
    for s, ind in (("TCheckbutton", "d2.check"), ("TRadiobutton", "d2.radio")):
        st.layout(s, [(s[1:] + ".padding", {"sticky": "nswe", "children": [
            (ind, {"side": "left", "sticky": ""}),
            (s[1:] + ".label", {"side": "left", "sticky": "nswe"})]})])
        st.configure(s, background=C["bg"], foreground=C["fg"], padding=(0, 3))
        st.map(s, background=[("active", C["bg"])], foreground=[("active", "#ffffff")])
    st.configure("Panel.TCheckbutton", background=C["panel"])
    st.map("Panel.TCheckbutton", background=[("active", C["panel"])])

    # Zakladki rysuje TabBar; notatnikowi zostaje sama zawartosc, bez ramki.
    st.layout("Bare.TNotebook.Tab", [])
    st.configure("Bare.TNotebook", background=C["bg"], borderwidth=0, tabmargins=0,
                 bordercolor=C["bg"], lightcolor=C["bg"], darkcolor=C["bg"])

    _thin_scrollbar(st, "Thin.Vertical.TScrollbar", C["bg"])
    _thin_scrollbar(st, "Log.Vertical.TScrollbar", C["card"])
    return base


class TabBar(tk.Frame):
    """Zakladki jako sam tekst ze zlota kreska pod wybrana - bez pudelek."""

    def __init__(self, master, nb, base):
        super().__init__(master, background=C["bg"])
        self.nb = nb
        self.items = []
        for i, tab in enumerate(nb.tabs()):
            cell = tk.Frame(self, background=C["bg"])
            cell.pack(side="left", padx=(0, 22))
            lbl = tk.Label(cell, text=nb.tab(tab, "text"), background=C["bg"],
                           foreground=C["muted"], font=(base, 10, "bold"),
                           cursor="hand2", padx=2, pady=7)
            lbl.pack()
            bar = tk.Frame(cell, height=3, background=C["bg"])
            bar.pack(fill="x")
            lbl.bind("<Button-1>", lambda e, i=i: nb.select(i))
            lbl.bind("<Enter>", lambda e, l=lbl: self._hover(l, True))
            lbl.bind("<Leave>", lambda e, l=lbl: self._hover(l, False))
            self.items.append((lbl, bar))
        nb.bind("<<NotebookTabChanged>>", lambda e: self._paint(), add="+")
        self._paint()

    def _current(self):
        return self.nb.index(self.nb.select())

    def _hover(self, lbl, inside):
        if lbl is not self.items[self._current()][0]:
            lbl.configure(foreground=C["fg"] if inside else C["muted"])

    def _paint(self):
        cur = self._current()
        for i, (lbl, bar) in enumerate(self.items):
            lbl.configure(foreground=C["gold"] if i == cur else C["muted"])
            bar.configure(background=C["gold"] if i == cur else C["bg"])


class Card(tk.Frame):
    """Makieta statusu tak, jak widza go inni na Discordzie: wiersz na liscie
    osob na serwerze i ramka "Gra" w mini profilu po kliknieciu."""

    D = {"list": "#2b2d31", "box": "#2b2d31", "edge": "#3f4147",
         "name": "#f2f3f5", "sub": "#b5bac1", "muted": "#949ba4", "green": "#23a55a"}

    def __init__(self, master, icon=None):
        super().__init__(master, background=C["bg"])
        d = self.D
        self.imgs = [tkgfx.user_avatar(32, d["green"]),
                     tkgfx.controller(d["green"])]
        self.labels = {}

        def cap(col, text):
            lbl = tk.Label(self, text=text, background=C["bg"], foreground=C["muted"])
            lbl.grid(row=0, column=col, sticky="w", pady=(0, 4))
            self.labels["cap%d" % col] = lbl

        cap(0, T("Lista uzytkownikow"))
        cap(1, T("Profil"))

        # --- wiersz na liscie osob ---
        # obie ramki tej samej wysokosci, wiersz listy wysrodkowany w pionie
        row = tk.Frame(self, background=d["list"], highlightthickness=1,
                       highlightbackground=d["edge"], highlightcolor=d["edge"],
                       padx=10, pady=8)
        row.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        row.rowconfigure(0, weight=1); row.rowconfigure(3, weight=1)
        tk.Label(row, image=self.imgs[0], background=d["list"]).grid(
            row=1, column=0, rowspan=2, padx=(0, 10))
        self.labels["lname"] = tk.Label(row, text=T("Ty"), background=d["list"],
                                        foreground=d["sub"], anchor="w")
        self.labels["lname"].grid(row=1, column=1, sticky="w")
        act = tk.Frame(row, background=d["list"])
        act.grid(row=2, column=1, sticky="w")
        tk.Label(act, image=self.imgs[1], background=d["list"]).pack(side="left", padx=(0, 4))
        self.labels["lact"] = tk.Label(act, text="", background=d["list"],
                                       foreground=d["muted"], anchor="w")
        self.labels["lact"].pack(side="left")

        # --- ramka "Gra" w mini profilu ---
        box = tk.Frame(self, background=d["box"], highlightthickness=1,
                       highlightbackground=d["edge"], highlightcolor=d["edge"],
                       padx=10, pady=8)
        box.grid(row=1, column=1, sticky="nsew")
        self.labels["head"] = tk.Label(box, text="Playing" if i18n.LANG == "en" else "Gra",
                                       background=d["box"],
                                       foreground=d["sub"], anchor="w")
        self.labels["head"].grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        if icon:
            tk.Label(box, image=icon, background=d["box"]).grid(
                row=1, column=0, rowspan=3, sticky="n", padx=(0, 10))
        else:
            tk.Label(box, text="D2R", background="#3a2f18", foreground=C["gold"],
                     width=6, height=3).grid(row=1, column=0, rowspan=3, padx=(0, 10))
        self.title = tk.Label(box, text="", background=d["box"], foreground=d["name"],
                              anchor="w", justify="left")
        self.title.grid(row=1, column=1, sticky="w")
        self.line1 = tk.Label(box, text="", background=d["box"], foreground=d["sub"],
                              anchor="w", justify="left")
        self.line1.grid(row=2, column=1, sticky="w")
        tm = tk.Frame(box, background=d["box"])
        tm.grid(row=3, column=1, sticky="w", pady=(2, 0))
        tk.Label(tm, image=self.imgs[1], background=d["box"]).pack(side="left", padx=(0, 5))
        self.labels["time"] = tk.Label(tm, text="4:16", background=d["box"],
                                       foreground=d["green"])
        self.labels["time"].pack(side="left")

    def set_fonts(self, base):
        L = self.labels
        for k in ("cap0", "cap1"):
            L[k].configure(font=(base, 9))
        L["lname"].configure(font=(base, 11))
        L["lact"].configure(font=(base, 9))
        L["head"].configure(font=(base, 9, "bold"))
        L["time"].configure(font=("TkFixedFont", 9))
        self.title.configure(font=(base, 10, "bold"))
        self.line1.configure(font=(base, 9))

    def show(self, title, line1):
        self.title.configure(text=title)
        self.line1.configure(text=line1 or "")
        if line1:
            self.line1.grid()
        else:
            self.line1.grid_remove()
        # lista osob pokazuje tylko tytul - dlatego tryb "nazwa gry zamiast
        # tytulu" jest najlepiej widoczny
        self.labels["lact"].configure(text=title)


class LogBox(tk.Frame):
    """Okienko z wpisami 'godzina + zdanie' - dziennik czytnika i przebieg nauki.
    Pasek przewijania tylko wtedy, gdy jest co przewijac."""

    def __init__(self, master, height=8):
        super().__init__(master, background=C["card"], highlightthickness=1,
                         highlightbackground=C["line"], highlightcolor=C["line"])
        self.columnconfigure(0, weight=1); self.rowconfigure(0, weight=1)
        self.text = tk.Text(self, height=height, wrap="word", state="disabled",
                            font=("TkFixedFont", 9), relief="flat", borderwidth=0,
                            background=C["card"], foreground="#cfd2d8",
                            padx=10, pady=8, insertbackground=C["fg"],
                            highlightthickness=0)
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.tag_configure("time", foreground=C["muted"])
        self.text.tag_configure("info", foreground="#cfd2d8")
        self.text.tag_configure("game", foreground=C["gold"])
        self.text.tag_configure("ok", foreground=C["ok"])
        self.text.tag_configure("warn", foreground=C["warn"])
        self.sb = ttk.Scrollbar(self, command=self.text.yview,
                                style="Log.Vertical.TScrollbar")
        self.text.config(yscrollcommand=self._scrolled)
        self.last = None

    def _scrolled(self, lo, hi):
        self.sb.set(lo, hi)
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.sb.grid_remove()
        else:
            self.sb.grid(row=0, column=1, sticky="ns", padx=(0, 2), pady=2)

    def add(self, msg, kind="info"):
        """kind: info, game, ok, warn. Ten sam wpis dwa razy z rzedu nie wchodzi -
        czekajace petle powtarzaja swoje co kilka sekund."""
        if msg == self.last:
            return
        self.last = msg
        self.text.config(state="normal")
        self.text.insert("end", time.strftime("%H:%M  "), "time")
        self.text.insert("end", msg.rstrip() + "\n", kind)
        if float(self.text.index("end-1c").split(".")[0]) > LOG_LINES:
            self.text.delete("1.0", "2.0")
        self.text.see("end")
        self.text.config(state="disabled")

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")
        self.last = None


class Scrollable(ttk.Frame):
    """Zawartosc zakladki w przewijanym plotnie. U kafelkujacych menedzerow okien
    wysokosc jest narzucona z gory i formularz musi sie zmiescic tak czy inaczej,
    wiec zamiast obcinac pola - przewijamy. Pasek pojawia sie tylko, gdy trzeba."""

    def __init__(self, master, fill=False):
        super().__init__(master)
        self.fill = fill      # tresc wypelnia wysokosc okna (rosnace wiersze rosna)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, background=C["bg"], highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                style="Thin.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.body = ttk.Frame(self.canvas, padding=14)
        self.win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._fit)
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.bind("<Configure>", self._fit, add="+")   # pasek po zmianie wysokosci
        self.canvas.bind("<Enter>", self._grab_wheel)
        self.canvas.bind("<Leave>", self._drop_wheel)

    def _fit(self, _=None):
        need = self.body.winfo_reqheight() > self.canvas.winfo_height()
        if self.fill:
            # przy narzuconej wysokosci samo body nie zglasza zmian - pilnuja dzieci
            for w in self.body.winfo_children():
                if not getattr(w, "_sc_watch", False):
                    w._sc_watch = True
                    w.bind("<Configure>", lambda _e: self.after_idle(self._fit), add="+")
            self.canvas.itemconfigure(self.win, height=max(self.body.winfo_reqheight(),
                                                           self.canvas.winfo_height()))
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.sb.grid(row=0, column=1, sticky="ns") if need else self.sb.grid_remove()

    def _grab_wheel(self, _=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(seq, self._wheel)

    def _drop_wheel(self, _=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(seq)

    def _wheel(self, e):
        step = -1 if getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0 else 1
        self.canvas.yview_scroll(step, "units")


class App(ttk.Frame):
    WRAP = 480

    def __init__(self, master, base, autostarted=False, resume=False):
        super().__init__(master, padding=12)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1); master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)

        self.base = base
        self.cfg = d2rread.load_config()
        c = self.cfg
        try:
            n = float(c.get("discord_dedupe", 90))
            if n == int(n):
                c["discord_dedupe"] = int(n)    # w polu 90 zamiast 90.0
        except (TypeError, ValueError):
            pass
        if (c.get("presence_name") == "{name}" and not c.get("presence_details")
                and c.get("presence_mode", "title") == "title"):
            # starszy tryb "nazwa gry w tytule" gubil tytul D2R - teraz idzie w opis
            c["presence_details"] = OFFICIAL_TITLE
            d2rread.save_config(c)
        if i18n.localize_defaults(c):
            d2rread.save_config(c)          # domyslne teksty w wybranym jezyku
        self.proc = None
        self.test_proc = None
        self.teach_proc = None
        self.lines = queue.Queue()
        self.tlines = queue.Queue()
        self.vars = {}
        self.dirty = False
        self._save_job = None
        self._told_restart = False
        self.icon = self._load_icon()

        self._build_header()
        self._build_tabs()
        self._build_footer()
        self._set_state(False)
        self._refresh_preview()
        self.after(150, self._drain)
        master.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tray = None
        self._tray_changed()
        master.bind("<Unmap>", self._on_unmap, add="+")
        if autostarted and self.tray:
            master.withdraw()               # start z systemem - od razu w zasobniku
        elif autostarted:
            master.iconify()
        if self.cfg.get("auto_read") or resume:
            self.after(300, self.start)

    def _load_icon(self):
        for n in ("icon-64.png", "icon.png"):
            p = HERE / n
            if p.exists():
                try:
                    return tk.PhotoImage(file=str(p)).subsample(1 if n == "icon-64.png" else 4)
                except tk.TclError:
                    pass
        return None

    # ---------- gorny pasek ----------

    def _build_header(self):
        bar = tk.Frame(self, background=C["panel"], highlightthickness=1,
                       highlightbackground=C["line"], highlightcolor=C["line"], padx=14, pady=12)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        bar.columnconfigure(1, weight=1)

        self.dots = {False: tkgfx.dot(C["muted"]), True: tkgfx.dot(C["ok"], halo=True)}
        self.dot = tk.Label(bar, image=self.dots[False], background=C["panel"])
        self.dot.grid(row=0, column=0, rowspan=2, padx=(0, 10))

        self.state_lbl = ttk.Label(bar, text="", style="State.TLabel")
        self.state_lbl.grid(row=0, column=1, sticky="w")
        self.game_lbl = ttk.Label(bar, text="", style="Game.TLabel")
        self.game_lbl.grid(row=1, column=1, sticky="w")

        self.btn = ttk.Button(bar, text=T("Start"), style="Accent.TButton", command=self.toggle)
        self.btn.grid(row=0, column=2, rowspan=2, sticky="e")

        opts = tk.Frame(bar, background=C["panel"])
        opts.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.use_presence = tk.BooleanVar(value=True)
        self.use_discord = tk.BooleanVar(value=bool(webhook.load_url()))
        for i, (txt, var) in enumerate(((T("Pokazuj status na moim profilu"), self.use_presence),
                                        (T("Wysylaj wiadomosc na kanal"), self.use_discord))):
            ttk.Checkbutton(opts, text=txt, variable=var, style="Panel.TCheckbutton",
                            command=self._restart_hint).grid(row=0, column=i,
                                                             sticky="w", padx=(0, 18))

    def _restart_hint(self):
        if self.proc:
            self.flash(T("Zmiana zadziala po Stop i Start"))

    def _set_state(self, running):
        self.dot.configure(image=self.dots[running])
        self.state_lbl.configure(text=T("Wlaczony") if running else T("Wylaczony"))
        self.game_lbl.configure(text=T("Oczekiwanie na wejscie do gry") if running
                                else T("Kliknij Start, aby rozpoczac"))
        self.btn.configure(text=T("Stop") if running else T("Start"),
                           style="Danger.TButton" if running else "Accent.TButton")
        if hasattr(self, "test_btn"):
            # dwa programy naraz ustawiajace status wchodza sobie w droge
            self.test_btn.state(["disabled"] if running else ["!disabled"])
            self.test_btn.configure(style="Idle.TButton" if running else "TButton")
            self.test_note.configure(text=T("Niedostepne podczas odczytu") if running else "")
        if getattr(self, "tray", None):
            self.tray.set_state(running, T("D2R Relay - odczyt wlaczony") if running
                                else T("D2R Relay - odczyt wylaczony"))

    # ---------- zakladki ----------

    def _build_tabs(self):
        box = ttk.Frame(self)
        box.grid(row=1, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1); box.rowconfigure(2, weight=1)
        nb = ttk.Notebook(box, style="Bare.TNotebook")
        nb.add(self._tab_presence(nb), text=T("Status na profilu"))
        nb.add(self._tab_webhook(nb), text=T("Wiadomosci na kanal"))
        nb.add(self._tab_reader(nb), text=T("Kalibracja"))
        nb.add(self._tab_general(nb), text=T("Ogolne"))
        nb.enable_traversal()                     # Ctrl+Tab dalej przelacza
        TabBar(box, nb, self.base).grid(row=0, column=0, sticky="w")
        tk.Frame(box, height=1, background=C["line"]).grid(row=1, column=0, sticky="ew")
        nb.grid(row=2, column=0, sticky="nsew")

    def _track(self, key, default=""):
        val = self.cfg.get(key, default)
        var = tk.BooleanVar(value=bool(val)) if isinstance(default, bool) \
            else tk.StringVar(value=str(val))
        var.trace_add("write", lambda *_: self._changed())
        self.vars[key] = var
        return var

    def _changed(self):
        # ustawienia zapisuja sie same, chwile po ostatniej zmianie
        self.dirty = True
        self._refresh_preview()
        if self._save_job:
            self.after_cancel(self._save_job)
        self._save_job = self.after(800, self._autosave)

    def _autosave(self):
        self._save_job = None
        if self.dirty and self.save() and self.proc and not self._told_restart:
            self._told_restart = True
            self.flash(T("Zmiany zadzialaja po Stop i Start"))

    def _hint(self, parent, r, text, col=1):
        self._wrap(ttk.Label(parent, text=text, style="Muted.TLabel", justify="left",
                             wraplength=self.WRAP)).grid(row=r, column=col, sticky="w",
                                                         pady=(0, 6))

    def _wrap(self, lbl):
        """Zawijanie do szerokosci okna, a nie na sztywno - w waskim oknie
        (pol ekranu, kafelki) opisy nie wypychaja pol poza krawedz."""
        def fit(_=None):
            room = self.winfo_width() - lbl.winfo_rootx() + self.winfo_rootx() - 40
            w = max(160, min(self.WRAP, room))
            if int(str(lbl.cget("wraplength")) or 0) != w:
                lbl.configure(wraplength=w)
        lbl.bind("<Map>", fit, add="+")
        self.bind("<Configure>", lambda e: self.after_idle(fit), add="+")
        return lbl

    # --- status na profilu ---

    def _tab_presence(self, nb):
        # Na gorze ustawienia (przewijane, gdy okno za niskie), pod nimi dziennik
        # czytnika jak przebieg nauki w zakladce Czytnik - bierze reszte miejsca.
        tab = ttk.Frame(nb)
        tab.columnconfigure(0, weight=1); tab.rowconfigure(2, weight=1)
        sc = Scrollable(tab); f = sc.body; f.columnconfigure(0, weight=1)
        sc.grid(row=0, column=0, sticky="nsew")
        self.status_sc = sc
        head = ttk.Label(tab, text=T("Historia"), style="Head.TLabel")
        head.grid(row=1, column=0, sticky="w", padx=14)
        self.logframe = LogBox(tab, height=6)
        self.logframe.grid(row=2, column=0, sticky="nsew", padx=14, pady=(6, 14))
        fit = lambda _=None: self._fit_status(tab, head)
        tab.bind("<Configure>", fit, add="+")
        f.bind("<Configure>", fit, add="+")

        self.test_btn, self.test_note = self._preview_head(
            f, self.TEST_LABEL, self.test_presence, width=20)
        self.card = Card(f, self.icon)
        self.card.set_fonts(self.base)
        self.card.grid(row=1, column=0, sticky="w", pady=(6, 12))

        # zapamietany wybor; stare configi bez niego - zgadujemy z pol
        # podglad pokazuje, co gdzie trafia, wiec opcje moga byc krotkie
        self.mode = self._track("presence_mode", self._detect_mode())
        # dwie kolumny: wybor tytulu i wyglad nazwy; opis wyboru pod obiema,
        # zeby prawa kolumna nie skakala przy zmianie opcji
        opts = ttk.Frame(f)
        opts.grid(row=2, column=0, sticky="w")
        pick = ttk.Frame(opts)
        pick.grid(row=0, column=0, sticky="nw")
        ttk.Label(pick, text=T("Tytul statusu"), style="Head.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        for i, (val, txt) in enumerate((("title", T("Nazwa gry (zalecane)")),
                                        ("details", T("Standardowy")),
                                        ("custom", T("Wlasny")))):
            ttk.Radiobutton(pick, text=txt, value=val, variable=self.mode,
                            command=self._mode_changed).grid(row=1 + i, column=0, sticky="w")
        self.mode_hint = self._wrap(ttk.Label(opts, text="", style="Muted.TLabel",
                                              justify="left", wraplength=560))
        self.mode_hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        look = ttk.Frame(opts)
        look.grid(row=0, column=1, sticky="nw", padx=(64, 0))
        ttk.Label(look, text=T("Wyglad"), style="Head.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Checkbutton(look, text=T("Nazwa gry duzymi literami"),
                        variable=self._track("presence_upper", False)).grid(
            row=1, column=0, sticky="w")

        self.adv = ttk.Frame(f)
        self.adv.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        self.adv.columnconfigure(1, weight=1)
        # jedna forma podpowiedzi: co robi pole, potem co daje puste/domyslne
        self._entry(self.adv, 0, T("Tytul"), "presence_name",
                    T("{name} wstawia nazwe gry. Puste - tytul z Application ID."), maxlen=128)
        self._entry(self.adv, 2, T("Opis"), "presence_details",
                    T("{name} wstawia nazwe gry. Puste - bez opisu."), maxlen=128)
        self._entry(self.adv, 4, T("W lobby"), "presence_idle",
                    T("Pokazywane zamiast nazwy gry, gdy jestes w lobby."), maxlen=128)
        self._entry(self.adv, 6, "Application ID", "presence_id",
                    T("Skad Discord bierze ikone i tytul. Domyslnie oficjalny wpis gry."),
                    width=24, maxlen=20, digits=True)
        ttk.Button(self.adv, text=T("Przywroc oficjalne ID"),
                   command=lambda: self.vars["presence_id"].set(OFFICIAL_ID)
                   ).grid(row=8, column=1, sticky="w", pady=(0, 4))
        self._mode_changed(first=True)

        return tab

    def _preview_head(self, f, text, cmd, width=20):
        """Naglowek 'Podglad' z przyciskiem proby po prawej - przycisk stoi przy
        tym, co sprawdza, i nie ucieka pod rozwijane ustawienia."""
        head = ttk.Frame(f)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(1, weight=1)
        ttk.Label(head, text=T("Podglad"), style="Head.TLabel").grid(row=0, column=0, sticky="w")
        note = ttk.Label(head, text="", style="Muted.TLabel")
        note.grid(row=0, column=1, sticky="e", padx=(0, 10))
        # stala szerokosc - odliczanie nie szarpie przyciskiem
        btn = ttk.Button(head, text=text, width=width, command=cmd)
        btn.grid(row=0, column=2, sticky="e")
        return btn, note

    LOG_MIN = 64

    def _fit_status(self, tab, head):
        """Ustawienia dostaja tyle, ile potrzebuja, a dziennik reszte, ale nie
        mniej niz LOG_MIN. W ciasnym oknie ustawienia zachowuja ponad pol
        zakladki (reszte przewijaja), bo to glowna rzecz na tej zakladce."""
        need = self.status_sc.body.winfo_reqheight()
        th = tab.winfo_height()
        room = th - head.winfo_reqheight() - 20 - self.LOG_MIN
        h = max(min(need, room), min(need, int(th * 0.55))) if th > 1 else need
        if int(self.status_sc.canvas.cget("height")) != h:
            self.status_sc.canvas.configure(height=h)

    def _entry(self, parent, r, label, key, hint="", width=36, maxlen=0, digits=False):
        # szerokosc na tresc, a nie na cale okno - w szerokim oknie pole na 2 m
        # tylko udaje, ze trzeba tam cos dlugiego wpisac
        # odstep po stronie etykiety - pole, podpowiedz i przyciski pod nim
        # zaczynaja sie w tej samej linii
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 12))
        var = self._track(key)
        e = ttk.Entry(parent, textvariable=var, width=width)
        if maxlen or digits:
            # limity Discorda - wiecej i tak zostaloby uciete albo odrzucone.
            # Za dluga wklejka jest przycinana, a nie odrzucana w calosci.
            def ok(new):
                fix = "".join(ch for ch in new if ch.isdigit()) if digits else new
                fix = fix[:maxlen] if maxlen else fix
                if fix == new:
                    return True
                self.after_idle(lambda: (var.set(fix), e.icursor("end")))
                return False
            e.configure(validate="key", validatecommand=(e.register(ok), "%P"))
        e.grid(row=r, column=1, sticky="w", pady=3)
        if hint:
            self._hint(parent, r + 1, hint)
        return e

    def _detect_mode(self):
        name = self.cfg.get("presence_name", "")
        det = self.cfg.get("presence_details", "")
        if name == "{name}" and det in ("", OFFICIAL_TITLE):
            return "title"
        if not name and det in tuple(i18n.TEXT_DEFAULTS["presence_details_std"].values()) \
                + ("{name}",):
            return "details"
        return "custom"

    # krotko i rownolegle; wlasny tryb nie potrzebuje opisu - pola sa tuz pod
    MODE_HINTS = {
        "title": T("Tytul: nazwa gry. Opis: %s.") % OFFICIAL_TITLE,
        "details": T("Tytul: %s. Opis: nazwa gry.") % OFFICIAL_TITLE,
        "custom": "",
    }

    def _mode_changed(self, first=False):
        mode = self.mode.get()
        if not first:
            if mode == "title":
                self.vars["presence_name"].set("{name}")
                self.vars["presence_details"].set(OFFICIAL_TITLE)
            elif mode == "details":
                self.vars["presence_name"].set("")
                self.vars["presence_details"].set(i18n.text_default("presence_details_std"))
        hint = self.MODE_HINTS[mode]
        self.mode_hint.configure(text=hint)
        (self.mode_hint.grid if hint else self.mode_hint.grid_remove)()
        if mode == "custom":
            self.adv.grid()
        else:
            self.adv.grid_remove()      # proste ustawienia nie strasza skladnia
        self._refresh_preview()

    def _refresh_preview(self):
        if not hasattr(self, "card"):
            return
        shown = SAMPLE.upper() if self.vars["presence_upper"].get() else SAMPLE
        title = (self.vars["presence_name"].get() or "").format(name=shown)
        det = (self.vars["presence_details"].get() or "").format(name=shown)
        self.card.show(title or OFFICIAL_TITLE, det)
        if hasattr(self, "bubble"):
            self._render_bubble()

    # Discord, motyw ciemny, widok domyslny - tak jak wyglada to na kanale.
    DC = {"bg": "#313338", "text": "#dbdee1", "name": "#f2f3f5", "time": "#949ba4",
          "badge": "#5865f2"}
    MD = re.compile(r"(\*\*.+?\*\*|__.+?__|\*[^*]+?\*|_[^_]+?_)")

    def _render_bubble(self):
        now = time.strftime("%H:%M")
        tmpl = self.vars["discord_template"].get() or "{name}"
        who = self.vars["discord_user"].get().strip() or T("nazwa webhooka")
        try:
            body = tmpl.format(name=SAMPLE.upper() if self.vars["discord_upper"].get()
                               else SAMPLE, time=now)
        except (KeyError, IndexError, ValueError):
            body = tmpl
        t = self.bubble
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", who + " ", "name")
        t.insert("end", "\u2009%s\u2009" % T("APL."), "badge")
        t.insert("end", " " + now + "\n", "time")
        for part in self.MD.split(body):
            if not part:
                continue
            for mark, tag in (("**", "b"), ("__", "u"), ("*", "i"), ("_", "i")):
                if len(part) > 2 * len(mark) and part.startswith(mark) and part.endswith(mark):
                    t.insert("end", part[len(mark):-len(mark)], tag)
                    break
            else:
                t.insert("end", part)
        t.configure(state="disabled")
        self._fit_bubble()

    def _fit_bubble(self, _=None):
        t = self.bubble
        n = t.count("1.0", "end", "displaylines")
        n = n[0] if isinstance(n, tuple) else n
        if n and int(t.cget("height")) != n:
            t.configure(height=n)

    # --- kanal ---

    def _tab_webhook(self, nb):
        sc = Scrollable(nb); f = sc.body; f.columnconfigure(0, weight=1)

        self._preview_head(f, T("Wyprobuj na kanale"), self.test_webhook)
        dc = self.DC
        box = tk.Frame(f, background=dc["bg"], highlightthickness=1,
                       highlightbackground=C["line"], highlightcolor=C["line"], padx=12, pady=10)
        box.grid(row=1, column=0, sticky="ew", pady=(6, 12))
        self.dc_avatar = tkgfx.discord_avatar(40, dc["badge"])
        tk.Label(box, image=self.dc_avatar, background=dc["bg"], borderwidth=0).pack(
            side="left", anchor="n", padx=(0, 12), pady=(2, 0))
        self.bubble = tk.Text(box, height=1, width=20, wrap="word", background=dc["bg"],
                              foreground=dc["text"], font=(self.base, 10), borderwidth=0,
                              highlightthickness=0, padx=0, pady=0, cursor="arrow",
                              spacing1=2, spacing3=2)
        self.bubble.pack(side="left", fill="x", expand=True)
        self.bubble.tag_configure("time", foreground=dc["time"], font=(self.base, 8))
        self.bubble.tag_configure("badge", background=dc["badge"], foreground="#ffffff",
                                  font=(self.base, 7, "bold"))
        self.bubble.tag_configure("name", foreground=dc["name"], font=(self.base, 10, "bold"))
        self.bubble.tag_configure("b", font=(self.base, 10, "bold"))
        self.bubble.tag_configure("i", font=(self.base, 10, "italic"))
        self.bubble.tag_configure("u", underline=True)
        self.bubble.bind("<Configure>", self._fit_bubble)

        body = ttk.Frame(f); body.grid(row=2, column=0, sticky="ew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text=T("Adres webhooka")).grid(row=0, column=0, sticky="w", pady=3,
                                                    padx=(0, 12))
        self.hook_var = tk.StringVar(value=webhook.load_url())
        self.hook_var.trace_add("write", lambda *_: self._changed())
        self.hook_entry = ttk.Entry(body, textvariable=self.hook_var, width=36, show="*",
                                    style="Hook.TEntry")
        self.hook_entry.grid(row=0, column=1, sticky="w", pady=3)
        # oko w polu zamiast osobnego pola "Pokaz adres"
        g = self.winfo_toplevel()._d2gfx
        self.eyes = {(shown, hot): tkgfx.eye(shown, C["fg"] if hot else C["muted"])
                     for shown in (False, True) for hot in (False, True)}
        g.extend(self.eyes.values())
        self.hook_shown = False
        self.eye = tk.Label(self.hook_entry, image=self.eyes[(True, False)],
                            background=C["field"], cursor="hand2", borderwidth=0)
        self.eye.place(relx=1.0, x=-8, rely=0.5, anchor="e")
        self.eye.bind("<Button-1>", lambda e: self._toggle_hook_shown())
        self.eye.bind("<Enter>", lambda e: self._eye_paint(True))
        self.eye.bind("<Leave>", lambda e: self._eye_paint(False))
        self._hint(body, 1, T("Edytuj kanal > Integracje > Webhooki > Kopiuj adres URL webhooka.\n"
                              "Adres jest zapisywany tylko na tym komputerze."))

        self._entry(body, 3, T("Nazwa nadawcy"), "discord_user",
                    T("Puste - nazwa ustawiona przy webhooku."), maxlen=80)
        self._entry(body, 5, T("Tresc"), "discord_template",
                    T("{name} - nazwa gry, {time} - godzina, **tekst** - pogrubienie."), width=36,
                    maxlen=1900)
        ttk.Checkbutton(body, text=T("Nazwa gry duzymi literami"),
                        variable=self._track("discord_upper", False)).grid(
            row=7, column=1, sticky="w", pady=(3, 8))
        self._entry(body, 8, T("Awatar"), "discord_avatar",
                    T("Adres URL obrazka. Puste - awatar webhooka."), width=36, maxlen=2048)
        self._entry(body, 10, T("Blokada powtorzen"), "discord_dedupe",
                    T("Sekundy, przez ktore ta sama gra nie zostanie wyslana ponownie."), width=8,
                    maxlen=5, digits=True)
        ttk.Button(body, text=T("Przywroc domyslne"), command=self._msg_defaults
                   ).grid(row=12, column=1, sticky="w", pady=(8, 4))
        return sc

    MSG_KEYS = ("discord_user", "discord_template", "discord_upper", "discord_avatar",
                "discord_dedupe")

    def _msg_defaults(self):
        # adres webhooka zostaje - to nie ustawienie, tylko dostep do kanalu
        for key in self.MSG_KEYS:
            self.vars[key].set(i18n.text_default(key) if key in i18n.TEXT_DEFAULTS
                               else d2rread.DEFAULTS[key])

    def _toggle_hook_shown(self):
        self.hook_shown = not self.hook_shown
        self.hook_entry.configure(show="" if self.hook_shown else "*")
        self._eye_paint(True)

    def _eye_paint(self, hot):
        # oko pokazuje, co zrobi klikniecie: otwarte = pokaz, przekreslone = ukryj
        self.eye.configure(image=self.eyes[(not self.hook_shown, hot)])

    # --- czytnik ---

    def _tab_reader(self, nb):
        # Kalibracja prowadzi za reke: dwa etapy po kolei, karta "co teraz"
        # i historia, ktora rosnie razem z oknem; gdy brakuje miejsca - przewijanie.
        sc = self.reader_sc = Scrollable(nb, fill=True); f = sc.body
        f.columnconfigure(0, weight=1); f.rowconfigure(3, weight=1)
        g = self.winfo_toplevel()._d2gfx
        self.step_icons = {st: tkgfx.step_icon(st) for st in ("done", "next", "todo")}
        g.extend(self.step_icons.values())

        stages = tk.Frame(f, background=C["panel"], highlightthickness=1,
                          highlightbackground=C["line"], highlightcolor=C["line"])
        stages.grid(row=0, column=0, sticky="ew")
        stages.columnconfigure(0, weight=1)
        self.stages = {}
        for i, (key, title, cmd) in enumerate((
                ("lobby", T("Rozpoznawanie lobby"), self.start_calibrate),
                ("font", T("Nauka nazw gier"), self.start_teach))):
            if i:
                tk.Frame(stages, height=1, background=C["line"]).grid(
                    row=2 * i - 1, column=0, sticky="ew")
            row = tk.Frame(stages, background=C["panel"], padx=14, pady=10)
            row.grid(row=2 * i, column=0, sticky="ew")
            row.columnconfigure(2, weight=1)
            icon = tk.Label(row, background=C["panel"])
            icon.grid(row=0, column=0, rowspan=2, padx=(0, 12))
            tk.Label(row, text=T("Krok %d") % (i + 1), background=C["panel"],
                     foreground=C["muted"], font=(self.base, 9)).grid(
                row=0, column=1, sticky="w")
            tk.Label(row, text=title, background=C["panel"], foreground=C["fg"],
                     font=(self.base, 11, "bold")).grid(row=1, column=1, sticky="w")
            status = tk.Label(row, background=C["panel"], foreground=C["muted"],
                              font=(self.base, 10))
            status.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 12))
            btn = ttk.Button(row, width=12, command=lambda k=key, c=cmd: self._stage_click(k, c))
            btn.grid(row=0, column=3, rowspan=2, sticky="e")
            self.stages[key] = (icon, status, btn)

        card = tk.Frame(f, background=C["panel"], highlightthickness=1,
                        highlightbackground=C["line"], highlightcolor=C["line"],
                        padx=14, pady=10)
        card.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        card.columnconfigure(0, weight=1)
        self.here_btn = ttk.Button(card, text=T("Zrob zrzut"), style="Accent.TButton",
                                   command=self.confirm_step)
        self.here_btn.grid(row=0, column=1, rowspan=4, sticky="e", padx=(12, 0))
        self.here_btn.grid_remove()
        lbl = lambda **kw: tk.Label(card, background=C["panel"], anchor="w",
                                    justify="left", **kw)
        self.step_top = lbl(foreground=C["muted"], font=(self.base, 9))
        self.step_main = lbl(foreground=C["fg"], font=(self.base, 12, "bold"))
        # nazwa gry do zalozenia + Kopiuj (w grze wklejasz Ctrl+V w pole Game Name)
        self.name_row = tk.Frame(card, background=C["panel"])
        self.step_name = tk.Label(self.name_row, background=C["panel"], anchor="w",
                                  foreground=C["gold"], font=("TkFixedFont", 18, "bold"))
        self.step_name.pack(side="left")
        self.copy_btn = ttk.Button(self.name_row, text=T("Kopiuj"), style="PBtn.TButton",
                                   width=10, command=self.copy_name)
        self.copy_btn.pack(side="left", padx=(14, 0))
        self.step_hint = lbl(foreground=C["muted"], font=(self.base, 10),
                             wraplength=self.WRAP + 150)
        for i, w in enumerate((self.step_top, self.step_main, self.name_row, self.step_hint)):
            w.grid(row=i, column=0, sticky="w", pady=(4, 4) if w is self.name_row else 0)

        ttk.Label(f, text=T("Historia"), style="Head.TLabel").grid(
            row=2, column=0, sticky="w", pady=(12, 0))
        self.teach_log = LogBox(f, height=5)
        self.teach_log.grid(row=3, column=0, sticky="nsew", pady=(6, 10))

        self.running_stage = None
        self._refresh_stages()
        return sc

    FULL_SET = len(set("".join(d2rread.TEACH_NAMES) + d2rread.TEACH_EXTRA))

    def _stage_state(self):
        """Co juz zrobione: lobby z calib.json, czcionka z liczby znakow."""
        lobby = bool(d2rread.load_calib().get("lobby"))
        fonts, meta = d2rread.load_glyphs()
        sets = d2rread.glyph_sets(fonts, meta)
        full = [h for h, n in sets.items() if n >= self.FULL_SET]
        best = max(sets.values(), default=0)
        return lobby, full, best

    def _refresh_stages(self):
        lobby, full, best = self._stage_state()
        done = {"lobby": lobby, "font": bool(full)}
        nxt = next((k for k in ("lobby", "font") if not done[k]), None)
        status = {
            "lobby": T("Gotowe") if lobby else T("Do zrobienia"),
            "font": (T("Gotowe (%s)") % ", ".join("%dp" % h for h in full)) if full
            else (T("%d z %d znakow") % (best, self.FULL_SET)) if best else T("Do zrobienia"),
        }
        busy = self.running_stage
        for key, (icon, st, btn) in self.stages.items():
            icon.configure(image=self.step_icons["done" if done[key]
                                                 else "next" if key == nxt else "todo"])
            st.configure(text=status[key])
            if busy == key:
                btn.configure(text=T("Przerwij"), style="PHalt.TButton")
                btn.state(["!disabled"])
                continue
            label = T("Powtorz") if done[key] else \
                T("Kontynuuj") if key == "font" and best else T("Rozpocznij")
            btn.configure(text=label, style="PGo.TButton" if key == nxt and not busy
                          else "PIdle.TButton" if busy else "PBtn.TButton")
            btn.state(["disabled"] if busy else ["!disabled"])
        if not busy:
            self._idle_step(nxt)

    def _idle_step(self, nxt):
        if nxt == "lobby":
            self._step(main=T("Zacznij od rozpoznania lobby"),
                       hint=T("Wlacz gre i przejdz do lobby, potem kliknij Rozpocznij przy kroku 1."))
        elif nxt == "font":
            self._step(main=T("Teraz nauka nazw gier"),
                       hint=T("Zalozysz kilka gier o podanych nazwach. Postep zapisuje sie "
                              "po kazdej grze."))
        else:
            self._step(main=T("Wszystko gotowe"), hint=T("Kliknij Start na gorze okna."))

    def _font_summary(self):
        self._refresh_stages()

    def _step(self, top="", main="", name="", hint=""):
        for w, t in ((self.step_top, top), (self.step_main, main),
                     (self.step_name, name), (self.step_hint, hint)):
            w.configure(text=t)
            row = self.name_row if w is self.step_name else w
            row.grid() if t else row.grid_remove()
        self.copy_btn.configure(text=T("Kopiuj"))

    def copy_name(self):
        name = self.step_name.cget("text")
        if not name:
            return
        # Tk przejmuje schowek tylko raz; kolejne kopie nie oglaszaja zmiany i
        # Wine/Proton oraz menedzery schowka trzymaja stara tresc. Oddanie
        # schowka przed kopia wymusza nowe przejecie.
        try:
            self.selection_clear(selection="CLIPBOARD")
        except tk.TclError:
            pass
        self.clipboard_clear()
        self.clipboard_append(name)
        self.update_idletasks()
        self.copy_btn.configure(text=T("Skopiowano"))
        self.after(1500, lambda: self.step_name.cget("text") == name
                   and self.copy_btn.configure(text=T("Kopiuj")))

    # --- nauka ---

    def _stage_click(self, key, start):
        if self.running_stage == key:
            self.stop_teach()
        elif not self.running_stage:
            start()

    def _can_teach(self):
        if self.proc:
            # czytnik wyslalby na Discorda kazda gre-cwiczenie
            self.flash(T("Najpierw zatrzymaj odczyt (Stop na gorze)"), warn=True)
            return False
        return True

    def start_teach(self, key="font"):
        if not self._can_teach():
            return
        # Powtorz przy ukonczonej nauce = cala seria jeszcze raz (wiecej probek
        # tych samych znakow); Kontynuuj pomija nazwy, ktorych znaki juz zna.
        again = key == "font" and bool(self._stage_state()[1])
        args = ["teach"] + (["--again"] if again else [])
        self.teach_log.clear()
        self._teach_cur = ""
        self.teach_log.add(T("Nauka nazw gier - cala seria") if again else T("Nauka nazw gier"))
        self._run_teach(args, key)
        self._step(main=T("Wejdz do lobby"), hint=T("Na ekran z zakladkami Create / Join."))

    def start_calibrate(self):
        if not self._can_teach():
            return
        self.teach_log.clear()
        self.teach_log.add(T("Start rozpoznawania lobby"))
        self._run_teach(["calibrate"], "lobby")
        self._step(main=T("Rozpoznawanie lobby"), hint=T("Program zapamieta, jak wyglada lobby "
                                                      "na Twoim ekranie."))

    def _run_teach(self, args, key):
        self.teach_proc = spawn(args, stdin=True)
        threading.Thread(target=self._pump, args=(self.teach_proc, self.tlines),
                         daemon=True).start()
        self.running_stage = key
        self._refresh_stages()

    SHOT_HINT = T("Nastepnie kliknij Zrob zrzut i wroc do okna gry.")
    SHOT_WAIT = T("Zrzut zostanie wykonany, gdy okno gry bedzie na wierzchu.")

    def confirm_step(self):
        """Odpowiedz na '> ... [Enter]' - gracz potwierdza, ze jest na miejscu."""
        self.here_btn.grid_remove()
        proc = self.teach_proc
        if proc and proc.poll() is None and proc.stdin:
            try:
                proc.stdin.write("\n")
                proc.stdin.flush()
            except OSError:
                pass
        self.step_main.configure(text=T("Wroc do okna gry"))
        self.step_hint.configure(text=self.SHOT_WAIT)

    def stop_teach(self):
        if self.teach_proc and self.teach_proc.poll() is None:
            self.teach_proc.terminate()
        # nauka zapisuje sie po kazdej grze; lobby dopiero na koncu
        self.teach_log.add(T("Nauka przerwana - dotychczasowy postep zostal zapisany")
                           if self.running_stage == "font"
                           else T("Rozpoznawanie lobby przerwane"), "warn")
        self._teach_done(stopped=True)

    def _teach_done(self, stopped=False, failed=False):
        self.teach_proc = None
        self.running_stage = None
        self.here_btn.grid_remove()
        if failed:
            self._refresh_stages_keep_step()
            return
        self._refresh_stages()
        if stopped:
            self._step(main=T("Przerwane"), hint=T("Postep zostal zapisany - mozesz kontynuowac "
                                                 "w dowolnej chwili."))

    def _refresh_stages_keep_step(self):
        # stan przyciskow tak, ale karta zostaje z komunikatem o bledzie
        texts = [w.cget("text") for w in (self.step_top, self.step_main,
                                          self.step_name, self.step_hint)]
        self._refresh_stages()
        self._step(*texts)

    def _drain_teach(self):
        while True:
            try:
                line = self.tlines.get_nowait()
            except queue.Empty:
                return
            if line is None:
                if self.teach_proc:            # sam sie skonczyl, nie przez Przerwij
                    code = self.teach_proc.wait()
                    self._teach_done(failed=code != 0)
                    if code:
                        self.teach_log.add(T("Nauka przerwana bledem"), "warn")
                continue
            self._teach_line(line.strip())

    def _teach_line(self, line):
        """Wyjscie 'd2rread.py teach' na karte kroku i zdania w przebiegu."""
        if not line:
            return
        low = line.lower()
        if line.startswith("> "):             # pytanie - czeka na "Zrob zrzut"
            q = line[2:].replace("[Enter]", "").strip()
            m = re.match(r"\[lobby (\d)/(\d)\]\s*(.+)", q)
            if m:
                n, total, what = m.groups()
                main = {"1": T("Otworz w grze lobby na zakladce Create Game"),
                        "2": T("Przelacz lobby na zakladke Join Game")}.get(
                            n, what[0].upper() + what[1:])
                self._step(T("Rozpoznawanie lobby - ekran %s z %s") % (n, total), main,
                           hint=self.SHOT_HINT)
                self.teach_log.add(T("Ekran %s z %s: %s") % (n, total, main), "game")
            else:
                self._step(main=q[0].upper() + q[1:], hint=self.SHOT_HINT)
            self.here_btn.grid()
            return
        if low.startswith(("przelacz sie do gry", "czekam, az okno gry")):
            self.step_hint.configure(text=self.SHOT_WAIT)
            return
        if low.startswith("kalibracja lobby:"):
            return
        if low.startswith("lobby zapamietane"):
            self.teach_log.add(T("Lobby zapamietane"), "ok")
            self._font_summary()
            return
        if low.startswith(("nie widze przelaczenia zakladki", "nie widze stalych")):
            msg = (T("Nie wykryto zmiany zakladki - powtorz ten ekran") if "zakladki" in low
                   else T("Nie wykryto lobby na ekranie - powtorz ten ekran"))
            self.teach_log.add(msg, "warn")
            return
        if low.startswith("kalibracja lobby nie wyszla"):
            self._step(main=T("Nie udalo sie rozpoznac lobby"),
                       hint=T("Upewnij sie, ze w grze jest lobby z zakladkami Create / Join, "
                              "i kliknij Rozpocznij przy kroku 1."))
            self.teach_log.add(T("Nie udalo sie rozpoznac lobby"), "warn")
            return
        if low.startswith("nowa rozdzielczosc"):
            h = re.search(r"\((\d+)p\)", line)
            self.teach_log.add(T("Nowa rozdzielczosc%s - nauka liter od poczatku")
                               % (" " + h.group(1) + "p" if h else ""), "info")
            return
        if low.startswith("uwaga: znacznik lobby"):
            self.teach_log.add(T("Lobby rozpoznaje sie tez w grze - po nauce powtorz krok 1"),
                               "warn")
            return
        if low.startswith("gotowe. lobby"):
            self.teach_log.add(T("Lobby rozpoznane"), "ok")
            return
        m = re.match(r"\[(\d+)(?:/(\d+))?\] (zaloz gre o nazwie|wpisz w pole game name):\s+(.+)",
                     line, re.I)
        if m:
            n, total, what, name = m.groups()
            game = what.lower().startswith("zaloz")
            top = (T("Gra %s") if game else T("Wpis %s")) % n + (T(" z %s") % total if total else "")
            # biezaca nazwa jest na karcie; do przebiegu trafia dopiero wynik
            self._teach_cur = "%s (%s)" % (top, name)
            if game:
                self._step(top, T("Zaloz gre o tej nazwie i wejdz do niej"), name,
                           T("Wielkosc liter ma znaczenie."))
            else:
                self._step(top, T("Wpisz w pole Game Name"), name,
                           T("Nie zakladaj gry - wystarczy sam wpis."))
                self.teach_log.add(self._teach_cur, "game")
            return
        if low.startswith("czekam, az wrocisz do lobby"):
            self._step(main=T("Wroc do lobby"), hint=T("Na ekran z zakladkami Create / Join."))
            return
        if low.startswith("czekam, az wejdziesz do gry"):
            self.step_hint.configure(text=T("Oczekiwanie na wejscie do gry..."))
            return
        if low.startswith("czekam na wyczyszczenie pola"):
            self._step(main=T("Wyczysc pole Game Name"), hint=T("Ctrl+A, potem Backspace."))
            return
        if low.startswith("teraz wyjdz z gry"):
            self._step(main=T("Wyjdz z gry"), hint=T("Save and Exit, potem wroc do lobby."))
            return
        if low.startswith("ok ("):
            cur = getattr(self, "_teach_cur", "") or T("Gra")
            if "czyta poprawnie" in low:
                self.teach_log.add(T("%s - zaliczona") % cur, "ok")
            else:
                self.teach_log.add(T("%s - zaliczona, odczyt jeszcze niepewny") % cur, "info")
            return
        if low.startswith("pomijam"):
            self.teach_log.add(T("Pominieta %s - znaki juz znane") % line.split()[1])
            return
        if low.startswith("brakuje jeszcze:"):
            self.teach_log.add(T("Dodatkowa gra dla znakow: %s")
                               % line.split(":", 1)[1].split(" - ")[0].strip())
            return
        if low.startswith("widze "):
            m = re.match(r"widze (\d+) glifow zamiast (\d+)", low)
            msg = (T("Wykryto %s znakow zamiast %s - popraw wpis") % m.groups() if m
                   else line[0].upper() + line[1:])
            self.step_hint.configure(text=msg)
            self.teach_log.add(msg, "warn")
            return
        if low.startswith("nie widze okna"):
            self._step(main=T("Nie znaleziono okna gry"), hint=T("Wlacz Diablo II: Resurrected "
                                                               "i sprobuj ponownie."))
            self.teach_log.add(T("Nie znaleziono okna gry"), "warn")
            return
        if low.startswith("gotowe"):
            if self.running_stage == "font":
                best = self._stage_state()[2]
                self.teach_log.add(T("Nauka zakonczona - program zna %d z %d znakow")
                                   % (best, self.FULL_SET), "ok")
            else:
                self.teach_log.add(T("Nauka zakonczona"), "ok")
            return
        if low.startswith("zadna probka"):
            cur = getattr(self, "_teach_cur", "") or T("Gra")
            self.teach_log.add(T("%s - nie widac calej nazwy. Sprawdz, czy gra przyjela "
                                 "ja w calosci.") % cur, "warn")
            return
        if low.startswith("nie udalo sie nauczyc:"):
            self.teach_log.add(T("Nie udalo sie nauczyc znakow: %s - jesli gra nie "
                                 "przyjmuje ich w nazwie, mozna to pominac")
                               % line.split(":", 1)[1].strip(), "warn")
            return
        if low.startswith("jesli gra nie przyjmuje"):
            return                             # zawarte w linii wyzej
        if (low.startswith("nauka czcionki") or low.startswith("dla kazdej nazwy")
                or low.startswith("niej, poczekaj") or low.startswith("po kazdym kroku")):
            return                             # wstep - karta kroku mowi to samo
        kind = "warn" if low.startswith(("zadna probka", "nie udalo", "jesli gra",
                                         "traceback", "error")) else "info"
        self.teach_log.add(line, kind)

    # ---------- dol okna ----------

    def _build_footer(self):
        foot = ttk.Frame(self)
        foot.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        foot.columnconfigure(1, weight=1)

        self.msg = ttk.Label(foot, text="", style="Muted.TLabel")
        self.msg.grid(row=0, column=1, sticky="w")


    def flash(self, msg, warn=False):
        self.msg.configure(text=msg, foreground=C["warn"] if warn else C["ok"])
        # licznik starego komunikatu nie moze skasowac nowego przed czasem
        if getattr(self, "_flash_job", None):
            self.after_cancel(self._flash_job)
        self._flash_job = self.after(6000, lambda: self.msg.configure(text=""))

    def log(self, msg, kind="info"):
        """Wpis w dzienniku: godzina + zdanie. kind: info, game, ok, warn."""
        self.logframe.add(msg, kind)

    # ---------- konfiguracja ----------

    def save(self):
        for key, var in self.vars.items():
            val = var.get()
            if key == "discord_dedupe":
                try:
                    val = float(val)
                except ValueError:
                    self.flash(T("Blokada powtorzen: podaj liczbe sekund"), warn=True)
                    return False
            self.cfg[key] = val
        who = self.cfg.get("discord_user", "").lower()
        if "discord" in who or "clyde" in who:
            self.flash(T("Nazwa nadawcy nie moze zawierac slow discord ani clyde"), warn=True)
            return False
        url = self.hook_var.get().strip()
        try:
            webhook.save_url(url) if url else webhook.forget()
        except webhook.WebhookError as e:
            self.flash(TR(str(e)), warn=True)
            return False
        d2rread.save_config(self.cfg)
        self.dirty = False
        return True

    # ---------- testy ----------

    TEST_SECS = 10
    TEST_LABEL = T("Wyprobuj na profilu")

    def test_presence(self):
        if self.proc:
            return
        if self.test_proc:              # drugie klikniecie konczy test
            self._stop_test()
            return
        if not self.save():
            return
        self.test_proc = spawn(["presence", "--test", SAMPLE])
        self.flash(T("Status testowy jest na Twoim profilu"))
        threading.Thread(target=self._pump, args=(self.test_proc,), daemon=True).start()
        self._test_tick(self.test_proc, self.TEST_SECS)

    def _test_tick(self, proc, left):
        # odliczanie na przycisku; proc pilnuje, zeby stary licznik nie
        # zakonczyl nowszego testu
        if proc is not self.test_proc:
            return
        if left <= 0:
            self._stop_test()
            return
        self.test_btn.configure(text=T("Zakoncz test (%d s)") % left)
        self.after(1000, self._test_tick, proc, left - 1)

    def _stop_test(self):
        if self.test_proc and self.test_proc.poll() is None:
            self.test_proc.terminate()
        self.test_proc = None
        if hasattr(self, "test_btn"):
            self.test_btn.configure(text=self.TEST_LABEL)

    def test_webhook(self):
        if not self.save():
            return
        url = self.hook_var.get().strip()
        if not url:
            self.flash(T("Uzupelnij adres webhooka"), warn=True)
            return

        def work():
            p = webhook.Poster(url, self.cfg["discord_template"], self.cfg["discord_user"],
                               self.cfg["discord_avatar"], upper=self.cfg["discord_upper"])
            ok = p.send("test-gry-01", force=True)
            self.lines.put("@@ok@@" + T("Wiadomosc testowa wyslana") if ok
                           else "@@err@@" + T("Nie udalo sie wyslac: %s") % TR(p.error))

        threading.Thread(target=work, daemon=True).start()

    # ---------- czytnik ----------

    def toggle(self):
        self.stop() if self.proc else self.start()

    def start(self):
        if self.teach_proc:
            # czytnik wyslalby na Discorda kazda gre-cwiczenie z nauki
            self.flash(T("Najpierw dokoncz albo przerwij kalibracje (zakladka Kalibracja)"), warn=True)
            return
        if not self.save():
            return
        self._told_restart = False
        args = ["watch"]
        if self.use_presence.get():
            args.append("--presence")
        if self.use_discord.get():
            if not webhook.load_url():
                self.flash(T("Brak adresu webhooka - uzupelnij go w zakladce Wiadomosci na kanal"),
                           warn=True)
                return
            args.append("--discord")
        self._stop_test()               # status testowy ustepuje prawdziwemu
        self.proc = spawn(args)
        threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()
        self._set_state(True)
        what = [n for n, on in ((T("status na profilu"), "--presence" in args),
                                (T("wiadomosci na kanal"), "--discord" in args)) if on]
        self.log(T("Wlaczono") + (" (%s)" % ", ".join(what) if what else ""))

    def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        self._set_state(False)
        self.log(T("Wylaczono"))

    def _pump(self, proc, q=None):
        q = q or self.lines
        for line in proc.stdout:
            q.put(line)
        q.put(None)

    def _drain(self):
        while True:
            try:
                line = self.lines.get_nowait()
            except queue.Empty:
                break
            if line is None:
                if self.proc and self.proc.poll() is not None:
                    self.log(T("Odczyt sam sie wylaczyl"), "warn")
                    self.proc = None
                    self._set_state(False)
                continue
            if line.startswith("@@tray@@"):
                self._tray_event(line[8:]); continue
            if line.startswith("@@ok@@"):
                self.flash(line[6:]); continue
            if line.startswith("@@err@@"):
                self.flash(line[7:], warn=True); continue
            name = self._name_of(line)
            if line.strip() == "powrot do lobby":
                self.game_lbl.configure(text=T("Lobby"))
            entry = self._friendly(line, name)
            if entry:
                self.log(*entry)
            if name:
                self.game_lbl.configure(text=T("Gra: %s") % name)
                self.flash(T("Nowa gra: %s") % name)
        self._drain_teach()
        self.after(150, self._drain)

    @staticmethod
    def _friendly(line, name):
        """Tlumaczy wyjscie czytnika (pisane pod terminal) na zdania do dziennika.
        None = linia bez znaczenia dla kogos, kto patrzy w okno."""
        line = line.strip()
        if not line:
            return None

        def inner(prefix):                # '(status Discord: X)' -> 'X'
            body = line[len(prefix):].strip()
            return body[:-1] if body.endswith(")") else body

        if name:
            return T("Nowa gra: %s") % name, "game"
        low = line.lower()
        if low == "powrot do lobby":
            return T("Powrot do lobby"), "info"
        if low.startswith("czekam na wejscie do gry"):
            return T("Oczekiwanie na wejscie do gry"), "info"
        if low.startswith("inna rozdzielczosc:"):
            h = re.search(r"(\d+)p", line)
            return (T("Gra ma inna rozdzielczosc%s - powtorz krok 2 w zakladce Kalibracja")
                    % (" (" + h.group(1) + "p)" if h else "")), "warn"
        if low.startswith("lobby nieskalibrowane"):
            return T("Lobby nierozpoznane - wykonaj krok 1 w zakladce Kalibracja"), "warn"
        if line.startswith("(status Discord:"):
            return T("Nie udalo sie ustawic statusu: %s") % TR(inner("(status Discord:")), "warn"
        if line.startswith("(kanal Discord:"):
            return T("Nie udalo sie wyslac na kanal: %s") % TR(inner("(kanal Discord:")), "warn"
        if low.startswith("blad odczytu"):
            return T("Nie udalo sie odczytac ekranu: %s") % line.split(":", 1)[-1].strip(), "warn"
        if low.startswith("brak wzorcow"):
            return (T("Program nie zna jeszcze czcionki gry - wykonaj krok 2 w zakladce Kalibracja"),
                    "warn")
        if low.startswith("brak client id"):
            return (T("Brak Application ID - wybierz tryb albo wpisz ID w zakladce "
                      "Status na profilu"), "warn")
        if low.startswith("brak webhooka"):
            return T("Brak adresu webhooka - wklej go w zakladce Wiadomosci na kanal"), "warn"
        if low.startswith("status ustawiony"):
            return T("Status testowy ustawiony - zerknij na swoj profil"), "info"
        if low.startswith("status zdjety"):
            return T("Status testowy zdjety"), "info"
        if low.startswith("nie poszlo:"):
            return T("Status testowy nie wyszedl: %s") % line[11:].strip(), "warn"
        if line.startswith("(") or low.startswith("lobby"):
            return None               # dopiski do komunikatow powyzej, podpowiedzi CLI
        return line, "info"

    @staticmethod
    def _name_of(line):
        # watch wypisuje '[HH:MM:SS] <nazwa>' przy kazdej nowej grze.
        line = line.strip()
        if line.startswith("[") and "]" in line:
            return line.split("]", 1)[1].strip() or None
        return None

    # ---------- zasobnik ----------

    def _tab_general(self, nb):
        sc = Scrollable(nb); f = sc.body; f.columnconfigure(0, weight=1)
        ttk.Label(f, text=T("Jezyk"), style="Head.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        lang = self._track("language", i18n.LANG)
        langs = ttk.Frame(f)
        langs.grid(row=1, column=0, sticky="w")
        for i, (code, name) in enumerate(i18n.LANGS):
            # nazwy jezykow zawsze w ich wlasnym jezyku - kazdy znajdzie swoj
            ttk.Radiobutton(langs, text=name, value=code, variable=lang,
                            command=self._lang_changed).grid(row=0, column=i, sticky="w",
                                                             padx=(0, 24))
        self.lang_note = ttk.Frame(f)
        self.lang_note.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.lang_msg = self._wrap(ttk.Label(self.lang_note, style="Muted.TLabel",
                                             wraplength=self.WRAP, justify="left"))
        self.lang_msg.grid(row=0, column=0, sticky="w")
        self.lang_btn = ttk.Button(self.lang_note, command=self.restart)
        self.lang_btn.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.lang_note.grid_remove()
        ttk.Label(f, text=T("Uruchamianie"), style="Head.TLabel").grid(
            row=3, column=0, sticky="w", pady=(16, 4))
        self.autostart_var = tk.BooleanVar(value=autostart.enabled())
        ttk.Checkbutton(f, text=T("Uruchamiaj razem z systemem"), variable=self.autostart_var,
                        command=self._autostart_changed).grid(row=4, column=0, sticky="w")
        ttk.Checkbutton(f, text=T("Wlaczaj odczyt po uruchomieniu programu"),
                        variable=self._track("auto_read", False)).grid(
            row=5, column=0, sticky="w")

        var = self._track("tray", True)
        cmd = tray.install_command()
        if not tray.available() and not cmd:
            return sc       # Windows: pystray jest w exe - brak = po prostu bez sekcji
        ttk.Label(f, text=T("Zasobnik systemowy"), style="Head.TLabel").grid(
            row=6, column=0, sticky="w", pady=(16, 4))
        cb = ttk.Checkbutton(f, text=T("Zamykanie i minimalizacja chowaja okno do zasobnika"),
                             variable=var, command=self._tray_changed)
        cb.grid(row=7, column=0, sticky="w")
        if tray.available():
            note = T("Program dziala dalej w tle. Menu ikony: Pokaz okno, Start/Stop, Zakoncz.")
        else:
            # wylaczone i puste - zaznaczone, a niedostepne wyglada jak blad
            cb.configure(variable=tk.BooleanVar(value=False))
            cb.state(["disabled"])
            note = T("Wymaga pakietu pystray. Zainstaluj go w terminalu i uruchom "
                     "program ponownie:")
        self._wrap(ttk.Label(f, text=note, style="Muted.TLabel", wraplength=self.WRAP,
                             justify="left")).grid(row=8, column=0, sticky="w", pady=(2, 0))
        if not tray.available():
            row = ttk.Frame(f)
            row.grid(row=9, column=0, sticky="w", pady=(6, 0))
            self._cmd_var = cmd_var = tk.StringVar(value=cmd)    # bez referencji Tk gubi tekst
            ttk.Entry(row, textvariable=cmd_var, width=len(cmd) + 2, state="readonly").pack(
                side="left")
            btn = ttk.Button(row, text=T("Kopiuj"), width=10)
            btn.configure(command=lambda: self._copy(cmd, btn))
            btn.pack(side="left", padx=(10, 0))
        return sc

    def _lang_changed(self):
        # po wybraniu z powrotem biezacego jezyka nie ma czego restartowac
        new = self.vars["language"].get()
        # podpowiedz w wybranym jezyku - ten, kto go wybral, ma ja zrozumiec
        tr = (lambda t: i18n.EN.get(t, t)) if new == "en" else (lambda t: t)
        self.lang_msg.configure(text=tr("Jezyk zmieni sie po ponownym uruchomieniu programu."))
        self.lang_btn.configure(text=tr("Uruchom ponownie"))
        (self.lang_note.grid if new != i18n.LANG else self.lang_note.grid_remove)()

    def restart(self):
        """Ponowne uruchomienie po zmianie jezyka - odczyt wraca, jesli chodzil."""
        if self.dirty and not self.save():
            return                          # komunikat o bledzie juz na dole okna
        if FROZEN:
            cmd = [sys.executable]
        else:
            cmd = [sys.executable, str(HERE / "d2rgui.py")]
        if self.proc:
            cmd.append("--resume")
        if not self.quit_app():
            return                          # "nie zamykaj" - zostajemy
        INSTANCE.release()                  # nowa kopia nie moze trafic na blokade
        kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if WINDOWS else {}
        subprocess.Popen(cmd, **kw)

    def _copy(self, text, btn):
        try:                    # patrz copy_name - wymusza nowe przejecie schowka
            self.selection_clear(selection="CLIPBOARD")
        except tk.TclError:
            pass
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
        btn.configure(text=T("Skopiowano"))
        self.after(1500, lambda: btn.configure(text=T("Kopiuj")))

    def _autostart_changed(self):
        try:
            autostart.set_enabled(self.autostart_var.get())
        except OSError as e:
            self.autostart_var.set(autostart.enabled())
            self.flash(T("Nie udalo sie zmienic autostartu: %s") % e, warn=True)

    def _tray_on(self):
        return tray.available() and bool(self.vars["tray"].get())

    def _tray_changed(self):
        if self._tray_on() and not self.tray:
            try:
                icon = HERE / "icon-64.png"
                self.tray = tray.Tray(icon if icon.exists() else HERE / "icon.png",
                                      T("D2R Relay - odczyt wylaczony"), self.lines.put,
                                      [T(t) for t in ("Pokaz okno", "Start", "Stop",
                                                      "Zakoncz")])
            except Exception as e:           # np. brak zasobnika w pasku
                self.tray = None
                self.flash(T("Nie udalo sie dodac ikony do zasobnika: %s") % e, warn=True)
                return
            self._set_state(bool(self.proc))
        elif not self._tray_on() and self.tray:
            self.tray.stop()
            self.tray = None
            self.master.deiconify()

    def _on_unmap(self, e):
        if e.widget is self.master and self.tray and self.master.state() == "iconic":
            self.master.withdraw()

    def show_window(self):
        self.master.deiconify()
        self.master.lift()
        self.master.focus_force()

    def _tray_event(self, ev):
        if ev == "show":
            self.show_window()
        elif ev == "toggle":
            self.toggle()
        elif ev == "quit":
            self.quit_app()

    def on_close(self):
        if self.tray:
            if self.dirty:
                self.save()
            self.master.withdraw()
            return
        self.quit_app()

    def quit_app(self):
        if self.dirty and not self.save():
            self.show_window()              # pytanie z zasobnika - okno musi byc widac
            if not messagebox.askyesno(T("Niezapisane zmiany"), T(
                    "Czesci ustawien nie da sie zapisac (komunikat na dole okna). "
                    "Zamknac mimo to?")):
                return False
        self._stop_test()
        if self.proc:
            self.stop()
        if self.teach_proc:
            self.teach_proc.terminate()
        if self.tray:
            self.tray.stop()
        self.master.destroy()
        return True


INSTANCE = single.Instance()


def set_process_name(name):
    """Nazwa w btop/top/ps zamiast 'python3' (Linux, max 15 znakow)."""
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes
        ctypes.CDLL(None).prctl(15, name.encode()[:15], 0, 0, 0)     # PR_SET_NAME
    except (OSError, AttributeError):
        pass


def main():
    if FROZEN and ("--tray-helper" in sys.argv or "--reader" in sys.argv):
        # exe ignoruje PYTHONUNBUFFERED/PYTHONIOENCODING - rury ustawiamy sami
        for st in (sys.stdin, sys.stdout, sys.stderr):
            if st:
                st.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    if "--tray-helper" in sys.argv[1:]:      # exe: ten sam plik gra proces ikony
        i = sys.argv.index("--tray-helper")
        tray.helper_main(sys.argv[i + 1:])
        return
    if "--reader" in sys.argv[1:]:           # exe: ten sam plik gra czytnik
        i = sys.argv.index("--reader")
        sys.argv = [sys.argv[0]] + sys.argv[i + 1:]
        d2rread.main()
        return
    set_process_name("d2r-relay")
    if not INSTANCE.acquire():
        # juz dziala - pokaz tamto okno (start z systemem niczego nie wyciaga)
        if "--autostart" not in sys.argv[1:]:
            INSTANCE.notify("show")
        return
    root = tk.Tk(className="d2r-relay")
    root.title("D2R Relay")
    base = apply_theme(root)
    root.minsize(480, 560)
    root.geometry("560x760")
    try:
        icon = HERE / "icon.png"
        if icon.exists():
            root.iconphoto(True, tk.PhotoImage(file=str(icon)))
    except tk.TclError:
        pass          # brak ikony to nie powod, zeby nie wstac
    app = App(root, base, autostarted="--autostart" in sys.argv[1:],
              resume="--resume" in sys.argv[1:])
    INSTANCE.serve(lambda: app.lines.put("@@tray@@show"))
    root.mainloop()


if __name__ == "__main__":
    main()
