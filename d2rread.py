#!/usr/bin/env python3
"""
d2rread - czytnik nazwy gry z Diablo II: Resurrected (Linux/X11).

Zrodla nazwy:
  * HUD w grze - linia "Game: <nazwa>" w prawym gornym rogu. Dziala tak samo
    dla gry zalozonej, jak i dla dolaczonej. To zrodlo glowne.
  * lobby - pole Game Name (Create/Join) i podswietlony wpis z listy gier.

Nie czyta pamieci procesu i nic nie wstrzykuje - robi tylko zrzut wlasnego
okna (maim) i rozpoznaje tekst dopasowaniem wzorcow glifow czcionki D2R.
Hasla sie nie da odczytac: gra maskuje pole gwiazdkami.

Komendy: calibrate | teach | teach --lobby | once | now | watch | check | hud | regions | bump
Discord: presence (status na profilu) | discord (wiadomosc na kanal)
         watch --presence --discord
"""
import argparse, collections, io, json, os, subprocess, sys, tempfile, time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import platformdirs_lite as dirs

HOME = Path.home()
CFG_DIR = dirs.config_dir()
DATA_DIR = dirs.data_dir()
CONFIG = CFG_DIR / "config.json"
GLYPHS = CFG_DIR / "glyphs.json"
CURRENT = DATA_DIR / "current.txt"
CURRENT_JSON = DATA_DIR / "current.json"
LOG = DATA_DIR / "games.log"
CALIB = CFG_DIR / "calib.json"
# Stary znacznik lobby zlapany na jednym ekranie 1920x1080 - zostaje tylko jako
# zapas dla nieskalibrowanych instalacji. Kalibracja lapie wlasny (calibrate).
LOBBY_REF = Path(__file__).resolve().parent / "lobby_ref.png"

WIN_TITLE = "Diablo II: Resurrected"
WINDOWS = sys.platform == "win32"
REF_W, REF_H = 1920, 1080
HUD_PREFIX = "Game:"
# Znaczniki stanu dla petli watch. Podkreslenia gra nie przyjmuje w nazwie
# gry, wiec zadna prawdziwa nazwa sie z nimi nie zrowna.
LOBBY, CLOSED = "__lobby__", "__closed__"

DEFAULT_REGIONS = {
    "tab_create":  (1185, 58, 180, 40),
    "tab_join":    (1380, 58, 180, 40),
    "create_name": (1291, 161, 358, 24),
    "join_name":   (1205, 137, 255, 24),
    "join_list":   (1204, 258, 286, 374),
    "lobby_mark":  (1190, 746, 570, 38),    # pasek "Exit Lobby" - znacznik lobby
    "hud_game":    (1380, 56, 516, 20),     # linia "Game: <nazwa>"
}

DEFAULTS = {
    "regions": DEFAULT_REGIONS,
    "ink_abs": 55,           # podloga progu dla tekstu w lobby (ciemne tlo)
    "gold_abs": 25,          # podloga progu "zlotosci" (r-b) dla HUD na tle gry
    "frames": 2,             # ile klatek AND-owac (gasi migajacy kursor)
    "frame_gap": 0.3,
    "space_ratio": 1.9,      # przerwa > ratio * mediana = spacja
    "space_min_px": 5,
    "match_max": 0.34,       # maks. niedopasowanie glifu (miara tolerancyjna)
    "poll": 1.5,
    "lobby_corr": 0.80,
    "hud_gap": 26,           # wieksza przerwa = obcy napis obok linii HUD
    "merge_max": 3,          # ile sasiednich runow wolno skleic w jedna litere
    "hud_levels": ["otsu", 0.30, 0.35, 0.42, 0.50],   # progi maski HUD po kolei
    "hud_votes": 2,          # tyle progow musi dac te sama nazwe (patrz hud_game_name)
    # Oficjalny wpis D2R z bazy wykrywanych gier Discorda. Dzieki niemu status
    # niesie prawdziwa nazwe i grafike gry, a wykrywanie procesu przez Discorda
    # sie z nim sklei, zamiast zrobic drugi wpis obok. Wlasna aplikacja z
    # Developer Portalu tez zadziala - wtedy naglowkiem jest jej nazwa.
    "presence_id": "1471657242729255086",
    "presence_details": "Gra: {name}",   # linia opisu pod naglowkiem, {name}
    # Puste = w naglowku zostaje nazwa gry spod presence_id. Wpisane (np.
    # "{name}") podmienia sam naglowek na nazwe gry D2R - ikona i tak zostaje
    # ta spod presence_id. Lobby idzie tam, gdzie nazwa gry (patrz lobby_activity).
    "presence_name": "",
    "presence_upper": False,     # nazwa gry WERSALIKAMI - czytelniejsza z daleka
    "presence_idle": "Lobby",       # co pokazac miedzy grami
    "discord_template": "Gra: **{name}**",   # {name}, {time}
    "discord_user": "D2R Relay",   # nazwa nadawcy wiadomosci (plakietki APP nie zdejmie)
    "discord_upper": False,  # nazwa gry WERSALIKAMI w wiadomosci
    "discord_avatar": "",    # URL awatara nadawcy, pusty = domyslny webhooka
    "discord_dedupe": 90,    # sekundy, przez ktore nie powtarzamy tej samej nazwy
    "tray": True,            # GUI: zamykanie/minimalizacja chowa okno do zasobnika
    "auto_read": False,      # GUI: odczyt wlacza sie sam po uruchomieniu programu
    # "language" (pl/en) celowo bez wartosci domyslnej - patrz i18n.detect()
}


# ---------- konfiguracja ----------

def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    if CONFIG.exists():
        user = json.loads(CONFIG.read_text(encoding="utf-8"))
        cfg["regions"].update({k: tuple(v) for k, v in user.pop("regions", {}).items()})
        regs = cfg["regions"]; cfg.update(user); cfg["regions"] = regs
        if cfg.get("discord_user") == "D2R Status":     # dawna nazwa programu
            cfg["discord_user"] = DEFAULTS["discord_user"]
    cfg["regions"] = {k: tuple(v) for k, v in cfg["regions"].items()}
    return cfg


def save_config(cfg):
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    out = {k: v for k, v in cfg.items() if k != "regions"}
    out["regions"] = {k: list(v) for k, v in cfg["regions"].items()}
    CONFIG.write_text(json.dumps(out, indent=2), encoding="utf-8")


# ---------- okno i zrzuty ----------

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def _user32():
    """user32 z DPI awareness: bez niej Windows przy skalowaniu 125/150%
    podaje wspolrzedne okna przeliczone, a zrzut jest w pikselach fizycznych."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    if not getattr(_user32, "dpi", False):
        _user32.dpi = True
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)     # per monitor
        except (OSError, AttributeError):
            try:
                u.SetProcessDPIAware()
            except (OSError, AttributeError):
                pass
    u.FindWindowW.restype = wintypes.HWND
    u.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    u.GetForegroundWindow.restype = wintypes.HWND
    return u, ctypes, wintypes


def _win_window():
    u, ctypes, wintypes = _user32()
    hwnd = u.FindWindowW(None, WIN_TITLE)
    if not hwnd or u.IsIconic(hwnd):
        return None                     # brak gry albo zminimalizowana
    rect = wintypes.RECT()
    u.GetClientRect(hwnd, ctypes.byref(rect))
    pt = wintypes.POINT(0, 0)           # obszar gry bez paska tytulu i ramek
    u.ClientToScreen(hwnd, ctypes.byref(pt))
    if rect.right <= 0 or rect.bottom <= 0:
        return None
    return (int(hwnd), pt.x, pt.y, rect.right, rect.bottom)


def d2r_window():
    if WINDOWS:
        return _win_window()
    for wid in run(["xdotool", "search", "--name", WIN_TITLE]).split():
        if run(["xdotool", "getwindowname", wid]).strip() == WIN_TITLE:
            d = dict(l.split("=", 1) for l in
                     run(["xdotool", "getwindowgeometry", "--shell", wid]).strip().splitlines()
                     if "=" in l)
            if "WIDTH" in d:
                return (wid, int(d["X"]), int(d["Y"]), int(d["WIDTH"]), int(d["HEIGHT"]))
    return None


def d2r_is_active(win):
    if WINDOWS:
        u = _user32()[0]
        return int(u.GetForegroundWindow() or 0) == win[0]
    wid = run(["xdotool", "getactivewindow"]).strip()
    if not wid:
        return False
    return wid == str(win[0]) or run(["xdotool", "getwindowname", wid]).strip() == WIN_TITLE


def scale_region(region, win):
    x, y, rw, rh = region
    sx, sy = win[3] / REF_W, win[4] / REF_H
    return (round(x * sx), round(y * sy), max(1, round(rw * sx)), max(1, round(rh * sy)))


def grab(win, region=None, px=None):
    """Zrzut fragmentu okna: region w ukladzie 1920x1080 albo px w pikselach okna."""
    if px is not None:
        gx, gy, gw, gh = px
    else:
        gx, gy, gw, gh = (0, 0, win[3], win[4]) if region is None else scale_region(region, win)
    if WINDOWS:
        from PIL import ImageGrab
        x, y = win[1] + gx, win[2] + gy
        # all_screens: okno na drugim monitorze ma wspolrzedne spoza glownego
        return ImageGrab.grab(bbox=(x, y, x + gw, y + gh), all_screens=True).convert("RGB")
    geo = "%dx%d+%d+%d" % (gw, gh, win[1] + gx, win[2] + gy)
    data = subprocess.run(["maim", "-u", "-g", geo], capture_output=True).stdout
    if not data:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = f.name
        subprocess.run(["maim", "-u", "-g", geo, tmp], capture_output=True)
        data = Path(tmp).read_bytes(); os.unlink(tmp)
    return Image.open(io.BytesIO(data)).convert("RGB")


# ---------- maski tekstu ----------
# Prog musi byc adaptacyjny (Otsu): przy sztywnym progu grubosc kreski zalezy
# od tla i te same litery daja rozne bitmapy - wzorce wtedy nie pasuja.

def otsu(v):
    hist, edges = np.histogram(v, bins=64)
    mids = (edges[:-1] + edges[1:]) / 2
    w = np.cumsum(hist); tot = v.size
    s = np.cumsum(hist * mids); s_all = s[-1]
    best_var, best_t = -1.0, float(edges[1])
    for i in range(63):
        wb = w[i]; wf = tot - wb
        if wb == 0 or wf == 0:
            continue
        var = wb * wf * (s[i] / wb - (s_all - s[i]) / wf) ** 2
        if var > best_var:
            best_var, best_t = var, float(edges[i + 1])
    return best_t


def gray(img):
    return np.asarray(img.convert("L"), dtype=np.float32)


def mask_lobby(img, cfg):
    g = gray(img)
    return g > max(otsu(g), cfg["ink_abs"])


def mask_hud(img, cfg, level="otsu"):
    """Maska zlotego tekstu HUD.

    Nad ciemnym tlem wystarczy Otsu, ale nad jasna scena Otsu wpada w tlo i
    zjada litery, wiec drugi wariant bierze prog wzgledem kontrastu
    tlo -> tekst. Zaden prog nie dziala na kazdym tle, dlatego czytamy kilkoma
    i bierzemy pierwszy odczyt bez znakow zapytania.
    """
    a = np.asarray(img, dtype=np.float32)
    gold = a[..., 0] - a[..., 2]          # zlotosc: czerwony minus niebieski
    if level == "otsu":
        t = otsu(gold)
    else:
        bg = float(np.median(gold))
        t = bg + level * (float(np.percentile(gold, 99.5)) - bg)
    return gold > max(t, cfg["gold_abs"])


def stable_mask(win, region, cfg, fn=mask_lobby):
    m = None
    for i in range(max(1, cfg["frames"])):
        if i:
            time.sleep(cfg["frame_gap"])
        cur = fn(grab(win, region), cfg)
        m = cur if m is None or m.shape != cur.shape else (m & cur)
    return m


# ---------- glify ----------

Box = collections.namedtuple("Box", "x0 x1 piece top bot")


def glyph_boxes(mask, min_ink=2):
    """Runy tuszu w jednej linii tekstu.

    Cienkie znaki ('-', ':', '.') maja tylko 1-2 wiersze tuszu, wiec nie wolno
    ich odsiewac po wysokosci - bez nich 'baalwalk-06' czyta sie 'baalwalk06'.
    Kazdy glif niesie tez swoje polozenie w pionie wzgledem linii, bo '-' i '_'
    maja identyczny ksztalt i roznia sie wylacznie wysokoscia nad podstawa.
    """
    if mask is None or not mask.any():
        return []
    cols = mask.any(axis=0).astype(np.int8)
    d = np.diff(np.concatenate(([0], cols, [0])))
    runs = zip(np.where(d == 1)[0].tolist(), np.where(d == -1)[0].tolist())
    raw = []
    for x0, x1 in runs:
        sub = mask[:, x0:x1]
        if sub.sum() < min_ink:
            continue
        rows = np.where(sub.any(axis=1))[0]
        raw.append((x0, x1, sub[rows[0]:rows[-1] + 1, :], int(rows[0]), int(rows[-1])))
    if not raw:
        return []
    top = min(r[3] for r in raw)
    bot = max(r[4] for r in raw)
    return [Box(x0, x1, piece, y0 - top, bot - y1) for x0, x1, piece, y0, y1 in raw]


def rescale(piece, f):
    """Kawalek z okna o innej rozdzielczosci sprowadzony do skali wzorcow."""
    if abs(f - 1.0) < 0.03:
        return piece
    h, w = piece.shape
    nh, nw = max(1, int(round(h * f))), max(1, int(round(w * f)))
    im = Image.fromarray((piece * 255).astype(np.uint8)).resize((nw, nh), Image.BILINEAR)
    return np.asarray(im, dtype=np.float32) / 255.0 > 0.5


def shift_dist(p, t):
    """XOR dwoch bitmap z tolerancja przesuniecia o 1 px.

    Skala jest stala (to samo okno), wiec porownujemy w natywnym rozmiarze -
    normalizacja malego glifu (4x7 px) do siatki gubila roznice miedzy literami.
    """
    ph, pw = p.shape; th, tw = t.shape
    H, W = max(ph, th) + 2, max(pw, tw) + 2
    cp = np.zeros((H, W), bool); cp[1:1 + ph, 1:1 + pw] = p
    n = float(max(p.sum(), t.sum())) or 1.0
    best = 9.0
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            ct = np.zeros((H, W), bool); ct[dy:dy + th, dx:dx + tw] = t
            d = float((cp ^ ct).sum()) / n
            if d < best:
                best = d
    return best


def trim_piece(sub):
    if sub.shape[1] == 0 or not sub[:, 0].any() or not sub[:, -1].any():
        return None
    rows = np.where(sub.any(axis=1))[0]
    return sub[rows[0]:rows[-1] + 1, :] if len(rows) else None


# ---------- baza wzorcow ----------
# Font D2R to male kapitaliki: 'a' ma ksztalt 'A', tylko nizszy. Ksztalt sam
# nie wystarczy, wiec wzorzec trzyma bitmape w natywnym rozmiarze razem z
# wysokoscia i polozeniem nad podstawa linii. Osobne zestawy per font: HUD w
# prawym gornym rogu jest wiekszy od czcionki lobby.

FONTS = ("hud", "lobby")
MAX_PER_CHAR = 6


def load_glyphs():
    if not GLYPHS.exists():
        return {f: [] for f in FONTS}, {}
    d = json.loads(GLYPHS.read_text(encoding="utf-8"))
    fonts = d.get("fonts") or {}
    out = {}
    for f in FONTS:
        v = fonts.get(f)
        out[f] = v if isinstance(v, list) else []      # stary format -> od nowa
    return out, d.get("meta", {})


def save_glyphs(fonts, meta):
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    meta = dict(meta); meta["format"] = 2
    # 'arr' to podreczna bitmapa trzymana przy wzorcu tylko w pamieci
    clean = {f: [{k: v for k, v in t.items() if k != "arr"} for t in lst]
             for f, lst in fonts.items()}
    tmp = GLYPHS.with_suffix(".tmp")
    tmp.write_text(json.dumps({"meta": meta, "fonts": clean}, indent=1), encoding="utf-8")
    tmp.replace(GLYPHS)          # podmiana w calosci: nauka nie zostawi ogryzka


# Wzorce sa osobno dla kazdej wysokosci okna ("res"). Przeskalowana bitmapa
# litery 10 px nie pasuje do tej samej litery narysowanej przez gre w 13 px,
# wiec zamiast skalowac uczymy sie przy kazdej rozdzielczosci od nowa, a odczyt
# bierze zestaw dla biezacego okna (awaryjnie najblizszy, ze skalowaniem).

def tmpl_res(t, meta):
    return t.get("res") or meta.get("ref_win_h") or REF_H


def glyph_sets(fonts, meta):
    """{wysokosc okna: liczba znakow HUD, ktore moga byc w nazwie gry}"""
    out = collections.defaultdict(set)
    for t in fonts["hud"]:
        if t["c"] in NAME_CHARS:          # bez ":" z samego "Game:"
            out[tmpl_res(t, meta)].add(t["c"])
    return {r: len(c) for r, c in sorted(out.items())}


def for_window(fonts, meta, h, exact=False):
    """Wzorce dla okna wysokosci h. meta['ref_win_h'] w wyniku to wysokosc,
    przy ktorej powstaly - win_scale liczy z niej skale."""
    have = {tmpl_res(t, meta) for f in FONTS for t in fonts[f]}
    res = h if exact or h in have or not have else min(have, key=lambda r: abs(r - h))
    view = {f: [t for t in fonts[f] if tmpl_res(t, meta) == res] for f in FONTS}
    m = dict(meta)
    m["ref_win_h"] = res
    return view, m


def merge_view(fonts, meta, view, h):
    """Wzorce z nauki przy wysokosci h wracaja do pelnej bazy, reszta zostaje."""
    out = {}
    for f in FONTS:
        keep = [dict(t, res=tmpl_res(t, meta)) for t in fonts[f] if tmpl_res(t, meta) != h]
        out[f] = keep + [dict(t, res=h) for t in view[f]]
    return out


def bits_of(arr):
    return "".join("1" if v else "0" for v in arr.flatten())


def arr_of(t):
    if "arr" not in t:
        t["arr"] = np.array([c == "1" for c in t["bits"]], bool).reshape(t["h"], t["w"])
    return t["arr"]


def add_glyph(glyphs, box, ch):
    h, w = box.piece.shape
    for t in glyphs:
        if t["c"] != ch and t["w"] == w and t["h"] == h and t["bits"] == bits_of(box.piece):
            return False          # ta sama bitmapa pod innym znakiem = pomylka
    same = [t for t in glyphs if t["c"] == ch]
    for t in same:
        if t["w"] == w and t["h"] == h and shift_dist(box.piece, arr_of(t)) < 0.12:
            return False
    if len(same) >= MAX_PER_CHAR:
        return False
    glyphs.append({"c": ch, "w": w, "h": h, "t": int(box.top), "b": int(box.bot),
                   "bits": bits_of(box.piece)})
    return True


def match_glyph(piece, glyphs, cfg, scale=1.0, box=None, allow_split=True):
    if not glyphs:
        return "?", 1.0
    p = rescale(piece, 1.0 / scale) if scale else piece
    h, w = p.shape
    best_ch, best_d = "?", 9.0
    for t in glyphs:
        dh, dw = abs(t["h"] - h), abs(t["w"] - w)
        if dh > 1 or dw > 2:
            continue
        if box is not None:
            dt, db = abs(t["t"] - box.top), abs(t["b"] - box.bot)
            if max(t["h"], h) <= 3 and max(dt, db) > 1:
                continue                      # '-' kontra '_': decyduje wysokosc
        else:
            dt = db = 0
        d = shift_dist(p, arr_of(t)) + 0.12 * (dh + dw) + 0.06 * (dt + db)
        if d < best_d:
            best_d, best_ch = d, t["c"]
    if best_d <= cfg["match_max"]:
        return best_ch, best_d
    if allow_split and w > 6 and h > 2:       # plaskiej kreski nie tniemy na '-'
        txt, d = split_run(piece, glyphs, cfg, scale)
        if txt:
            return txt, d
    return "?", best_d


def split_run(piece, glyphs, cfg, scale):
    """Sklejone litery: tnie run tak, by kazdy kawalek pasowal do wzorca."""
    W = piece.shape[1]
    maxw = int(max([t["w"] for t in glyphs] or [10]) * scale) + 2
    INF = 9e9
    dp = [(INF, "")] * (W + 1)
    dp[0] = (0.0, "")
    for j in range(1, W + 1):
        for i in range(max(0, j - maxw), j):
            if dp[i][0] >= INF:
                continue
            sub = trim_piece(piece[:, i:j])
            if sub is None:
                continue
            ch, d = match_glyph(sub, glyphs, cfg, scale, allow_split=False)
            if ch == "?":
                continue
            cost = dp[i][0] + d + 0.03
            if cost < dp[j][0]:
                dp[j] = (cost, dp[i][1] + ch)
    if dp[W][0] >= INF:
        return None, 1.0
    return dp[W][1], dp[W][0] / max(1, len(dp[W][1]))


def merge_boxes(bs):
    """Skleja sasiednie runy w jeden glif (litera potrafi sie rozpasc na dwa)."""
    if len(bs) == 1:
        return bs[0]
    top = min(b.top for b in bs)
    bot = min(b.bot for b in bs)
    h = max(b.top - top + b.piece.shape[0] for b in bs)
    w = bs[-1].x1 - bs[0].x0
    canvas = np.zeros((h, w), bool)
    for b in bs:
        y, x = b.top - top, b.x0 - bs[0].x0
        canvas[y:y + b.piece.shape[0], x:x + b.piece.shape[1]] |= b.piece
    return Box(bs[0].x0, bs[-1].x1, canvas, top, bot)


def text_from_boxes(boxes, glyphs, cfg, scale=1.0):
    """Czyta linie DP po granicach runow.

    Prog jasnosci raz sklei dwie litery, raz rozerwie jedna na pol, wiec run
    nie jest rownoznaczny z litera. DP probuje tez laczyc do 3 sasiednich runow
    i bierze wariant o najmniejszym koszcie dopasowania.
    """
    if not boxes:
        return ""
    gaps = [boxes[i + 1].x0 - boxes[i].x1 for i in range(len(boxes) - 1)]
    space_at = max(cfg["space_min_px"] * scale,
                   float(np.median(gaps)) * cfg["space_ratio"]) if gaps else 9e9
    n = len(boxes)
    INF = 9e9
    dp = [(0.0, "")] + [(INF, "")] * n
    for j in range(1, n + 1):
        for k in range(1, min(cfg["merge_max"], j) + 1):
            i = j - k
            if dp[i][0] >= INF:
                continue
            if any(gaps[t] >= space_at for t in range(i, j - 1)):
                continue                       # nie sklejamy przez spacje
            b = merge_boxes(boxes[i:j])
            ch, d = match_glyph(b.piece, glyphs, cfg, scale, box=b)
            if ch == "?":
                continue
            sep = " " if i and gaps[i - 1] >= space_at else ""
            cost = dp[i][0] + d + 0.03
            if cost < dp[j][0]:
                dp[j] = (cost, dp[i][1] + sep + ch)
    if dp[n][0] < INF:
        return dp[n][1].strip()
    # nic nie sklada sie w cala linie - czytamy run po runie, brak oznaczamy '?'
    out = []
    for i, b in enumerate(boxes):
        if i and gaps[i - 1] >= space_at:
            out.append(" ")
        out.append(match_glyph(b.piece, glyphs, cfg, scale, box=b)[0])
    return "".join(out).strip()


def read_text(mask, glyphs, cfg, scale=1.0):
    return text_from_boxes(glyph_boxes(mask), glyphs, cfg, scale)


def win_scale(win, meta):
    ref = meta.get("ref_win_h")
    return (win[4] / ref) if ref else 1.0


def template_h(glyphs, ch):
    hs = [t["h"] for t in glyphs if t["c"] == ch and t["h"]]
    return float(np.median(hs)) if hs else 0.0


# ---------- rozpoznanie ekranu ----------

def ui_scale(win):
    """Wielkosc interfejsu gry wzgledem 1080p - D2R skaluje go wysokoscia okna."""
    return win[4] / REF_H


def hud_boxes(win, cfg, level="otsu", img=None):
    """Glify linii 'Game: ...' - bez obcych napisow obok i bez elementow sceny."""
    if img is None:
        img = grab(win, px=hud_rect(win, cfg))
    ui = ui_scale(win)
    mask = mask_hud(img, cfg, level)
    boxes = glyph_boxes(mask)
    # plamy ze sceny bywaja zlote, ale nie maja rozmiarow litery; cienkie znaki
    # ('-', ':') zostaja - odsiewamy tylko to, co jest za duze
    boxes = [b for b in boxes
             if b.piece.shape[1] <= 20 * ui and b.piece.shape[0] <= 16 * ui]
    if len(boxes) < 6:
        return []
    # '_' przed cieciem po przerwach: kilka '_' pod rzad to dla maski dziura
    # szersza niz odstep miedzy napisami
    boxes = hud_underscores(img, mask, boxes, ui)
    for i in range(len(boxes) - 1, 0, -1):
        if boxes[i].x0 - boxes[i - 1].x1 > cfg["hud_gap"] * ui:
            boxes = boxes[i:]
            break
    # linia jest wyrownana do prawej - inaczej to nie ona
    if img.width - boxes[-1].x1 > 60 * ui:
        return []
    # tusz na gornej albo dolnej krawedzi wycinka = linia ucieta (duze litery
    # czytalyby sie jak male) albo doklejony kawalek zegara / nazwy lokacji
    if mask[[0, -1], boxes[0].x0:boxes[-1].x1].any():
        return []
    return boxes if len(boxes) >= 6 else []


def hud_underscores(img, mask, boxes, ui):
    """Dokleja '_', ktorego maska nie widzi.

    Przy 1080p gra rysuje '_' jako linie 1 px o czwartej czesci jasnosci
    liter - zaden prog maski jej nie zlapie, nie zjadajac przy tym tla. Szukamy
    jej osobno: w przerwach miedzy glifami (i za ostatnim), tuz pod linia
    bazowa, jako poziomego paska wyraznie jasniejszego od pikseli nad i pod nim.
    """
    a = np.asarray(img, dtype=np.float32)
    gold = a[..., 0] - a[..., 2]
    H, W = gold.shape
    tops, bots = [], []
    for b in boxes:
        rows = np.where(mask[:, b.x0:b.x1].any(axis=1))[0]
        tops.append(int(rows[0])); bots.append(int(rows[-1]))
    ref_top = tops[0] - boxes[0].top          # te same granice linii co w glyph_boxes
    ref_bot = bots[0] + boxes[0].bot
    base = int(np.median(bots))               # wiekszosc znakow stoi na linii bazowej
    d = max(2, round(2 * ui))                 # sasiad nad/pod paskiem (pasek 1-2 px)
    minw = max(3, round(4 * ui))
    ys = range(max(d, base + 1), min(H - d, base + max(3, round(5 * ui)) + 1))
    gaps = [(boxes[i].x1, boxes[i + 1].x0) for i in range(len(boxes) - 1)]
    gaps.append((boxes[-1].x1, W))
    pitch = 7.8 * ui                          # co tyle stoi kolejny '_' (1080p: ~7.8 px)
    out = list(boxes)
    for gx0, gx1 in gaps:
        if gx1 - gx0 <= minw:
            continue
        best = None
        for y in ys:
            row = gold[y, gx0:gx1]
            near = np.maximum(gold[y - d, gx0:gx1], gold[y + d, gx0:gx1])
            hit = np.concatenate(([0], ((row >= 12) & (row - near >= 6)).astype(np.int8), [0]))
            e = np.diff(hit)
            for r0, r1 in zip(np.where(e == 1)[0], np.where(e == -1)[0]):
                if r1 - r0 >= minw and (best is None or r1 - r0 > best[2] - best[1]):
                    best = (y, gx0 + int(r0), gx0 + int(r1))
        if best:
            # kilka '_' pod rzad zlewa sie w jedna kreske - dzielimy ja po rowno
            y, x0, x1 = best
            k = max(1, round((x1 - x0 + 2 * ui) / pitch))
            cuts = [x0 + round(i * (x1 - x0) / k) for i in range(k + 1)]
            for c0, c1 in zip(cuts, cuts[1:]):
                out.append(Box(c0, c1, np.ones((1, c1 - c0), bool), y - ref_top, ref_bot - y))
    return sorted(out, key=lambda b: b.x0)


# ---------- kalibracja ----------
# Stale wspolrzedne dzialaly tylko na 16:9. Na 21:9 czy 16:10 gra przykleja
# linie 'Game:' do prawego rogu, a panel lobby do srodka, wiec proporcjonalne
# przeliczanie trafialo obok. Dlatego oba miejsca znajdujemy na ekranie
# uzytkownika i zapamietujemy razem z rozmiarem okna.

def load_calib():
    try:
        return json.loads(CALIB.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_calib(c):
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CALIB.with_suffix(".tmp")
    tmp.write_text(json.dumps(c, indent=1), encoding="utf-8")
    tmp.replace(CALIB)


def hud_rect(win, cfg, calib=None):
    """Linia 'Game:' w pikselach okna: znaleziona dla tego rozmiaru okna albo
    domyslna (przeliczona z 1920x1080)."""
    h = (calib if calib is not None else load_calib()).get("hud")
    if h and h.get("win") == [win[3], win[4]]:
        return tuple(h["rect"])
    return scale_region(cfg["regions"]["hud_game"], win)


def remember_hud(win, rect):
    c = load_calib()
    c["hud"] = {"win": [win[3], win[4]], "rect": list(rect)}
    save_calib(c)


def hud_calibrated(win):
    h = load_calib().get("hud")
    return bool(h and h.get("win") == [win[3], win[4]])


def game_line(boxes, cfg, ui, glyphs=None, expect=0):
    """Czy te glify to linia 'Game: <nazwa>' (a nie 'Password:' pod nia).

    Przy odczycie - pierwsze cztery glify musza czytac sie 'Game'. Przy nauce
    (wzorcow moze jeszcze nie byc) - liczba glifow zgodna z nazwa, o ktora prosilismy,
    wysokie 'G' przed nizszym 'a' i waski dwukropek na piatym miejscu, a za nim
    przerwa. 'Password:' i 'Difficulty:' maja dwukropek dalej.
    """
    if len(boxes) < 6 or (expect and len(boxes) != expect):
        return False
    if glyphs and not expect and set("Game") <= learned(glyphs):
        scale = boxes[0].piece.shape[0] / template_h(glyphs, "G")
        if not 0.3 < scale < 4.0:
            return False
        got = "".join(match_glyph(b.piece, glyphs, cfg, scale, box=b, allow_split=False)[0]
                      for b in boxes[:4])
        return got == "Game"
    g, a, colon = boxes[0].piece, boxes[1].piece, boxes[4].piece
    return (g.shape[0] > a.shape[0] and colon.shape[1] <= 3 * ui + 1
            and colon.shape[0] < g.shape[0]
            and boxes[5].x0 - boxes[4].x1 >= cfg["space_min_px"] * ui)


def locate_hud(win, cfg, glyphs=None, expect=0):
    """Szuka linii 'Game:' w prawym gornym rogu. Zwraca prostokat w pikselach
    okna albo None. Jeden zrzut, potem pasy wysokosci linii co kilka pikseli."""
    W, H = win[3], win[4]
    ui = ui_scale(win)
    x0 = int(W * 0.40)
    area = (x0, 0, W - x0, int(H * 0.25))
    img = grab(win, px=area)
    bh = max(10, round(20 * ui))
    step = max(1, bh // 5)
    hits = []
    for y in range(0, img.height - bh + 1, step):
        band = img.crop((0, y, img.width, y + bh))
        for level in cfg["hud_levels"]:
            if game_line(hud_boxes(win, cfg, level, img=band), cfg, ui, glyphs, expect):
                hits.append(y)
                break
    if not hits:
        return None
    # Linia trafia w kilka sasiednich pasow - bierzemy srodek najwyzszej grupy.
    group = [hits[0]]
    for y in hits[1:]:
        if y - group[-1] > step:
            break
        group.append(y)
    y = group[len(group) // 2]
    # Pasek ustawiamy wzgledem gory 'G' z 'Game:' (jest zawsze): ~3 px nad nia,
    # a pod linia zostaje miejsce na slabe '_' i ogonki g/p/y. Srodek grupy
    # trafien potrafil wypasc tak, ze '_' lezalo juz pod paskiem.
    band = img.crop((0, y, img.width, y + bh))
    for level in cfg["hud_levels"]:
        bs = hud_boxes(win, cfg, level, img=band)
        if bs:
            rows = np.where(mask_hud(band, cfg, level)[:, bs[0].x0:bs[0].x1].any(axis=1))[0]
            if len(rows):
                y = min(max(0, y + int(rows[0]) - round(3 * ui)), img.height - bh)
            break
    left = max(x0, W - round(560 * ui))
    return (left, y, W - left, bh)


def hud_name_at(img, win, cfg, glyphs, base, level):
    boxes = hud_boxes(win, cfg, level, img=img)
    if len(boxes) <= len(HUD_PREFIX):
        return ""
    gt = template_h(glyphs, "G")            # skala fontu HUD z prefiksu "Game:"
    scale = boxes[0].piece.shape[0] / gt if gt else base
    if not 0.3 < scale < 4.0:
        scale = base
    # Nazwa zaczyna sie za szeroka przerwa po prefiksie. Nie szukamy dwukropka:
    # to 2 px tuszu, ktore przy slabym kontrascie potrafia zniknac z maski.
    start = 0
    for i in range(1, min(len(boxes), len(HUD_PREFIX) + 2)):
        if boxes[i].x0 - boxes[i - 1].x1 >= cfg["space_min_px"] * scale:
            start = i
            break
    if not start:
        return ""
    return text_from_boxes(boxes[start:], glyphs, cfg, scale).strip()


def hud_game_name(win, cfg, glyphs, meta):
    """Nazwa gry z prawego gornego rogu - pewna albo zadna.

    Odczyt z choc jednym '?' odrzucamy: lepiej nie podac nazwy i sprobowac za
    chwile niz zapisac zmyslona.

    Progi maski daja czasem rozne ciecia tej samej linii i przy jednym z nich
    cienka kreska dokleja sie jako osobna litera. Dlatego
    nazwa musi wyjsc tak samo przy kilku progach; pojedynczy odczyt odrzucamy
    i probujemy przy nastepnym zrzucie.
    """
    base = win_scale(win, meta)
    if not hud_calibrated(win):
        # Jeszcze nie wiemy, gdzie na tym ekranie jest linia - szukamy, ale nie
        # czesciej niz co kilka sekund, bo przeszukanie rogu kosztuje.
        now = time.time()
        if now - _hud_search["t"] < 3.0:
            return ""
        _hud_search["t"] = now
        rect = locate_hud(win, cfg, glyphs)
        if not rect:
            return ""
        remember_hud(win, rect)
    img = grab(win, px=hud_rect(win, cfg))
    votes = collections.Counter()
    for level in cfg["hud_levels"]:
        name = hud_name_at(img, win, cfg, glyphs, base, level)
        if name and "?" not in name:
            votes[name] += 1
            if votes[name] >= cfg["hud_votes"]:
                return name
    return ""


_hud_search = {"t": 0.0}


THUMB_W = 240          # miniatura okna do znacznika lobby: 8x mniej przy 1920
MARK_W, MARK_H = 4, 2  # znacznik = tyle komorek miniatury
CELL = 8


def thumb(img):
    """Szara miniatura okna o stalej szerokosci. Zalezy tylko od proporcji
    okna, wiec ten sam znacznik pasuje przy 1080p i 1440p."""
    w, h = img.size
    return np.asarray(img.convert("L").resize((THUMB_W, max(1, round(THUMB_W * h / w))),
                                              Image.BOX), dtype=np.float32)


def corr(a, b):
    a, b = a - a.mean(), b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den else 0.0


def lobby_marks(win, calib=None):
    lob = (calib if calib is not None else load_calib()).get("lobby")
    if not lob:
        return None
    w, h = lob["win"]
    if abs(w / h - win[3] / win[4]) > 0.01:
        return None          # inne proporcje okna - trzeba skalibrowac od nowa
    return lob["marks"]


def pick_marks(frames_a, frames_b, n=5, n_tab=3):
    """Wybiera znaczniki lobby z miniatur dwoch zakladek (Create i Join).

    Dobre miejsce jest nieruchome we wszystkich klatkach (tlo lobby sie rusza,
    zakladki sie zmieniaja, panel stoi) i ma wyrazny rysunek - plaskiej plamy
    nie da sie odroznic od innej plaskiej plamy. Takie miejsce bywa jednak
    ulotne (linia czatu, tabliczka postaci), wiec to tylko zapas.

    Glowne sa znaczniki zakladki: miejsca stale w obrebie kazdej zakladki, a
    rozne miedzy nimi (naglowek Create/Join, etykiety panelu). Nie zaleza od
    postaci ani czatu i sa tylko w lobby; trzymaja po wzorcu na zakladke.
    Zwraca (znaczniki, czy widac przelaczenie zakladki).
    """
    a, b = np.stack(frames_a), np.stack(frames_b)
    allf = np.concatenate([a, b])
    mean = allf.mean(0)
    motion = np.abs(allf - mean).max(0)
    th, tw = mean.shape
    rows, cols = th // CELL, tw // CELL
    cm = np.zeros((rows, cols)); ctex = np.zeros((rows, cols))
    ctab = np.zeros((rows, cols))
    ma, mb = a.mean(0), b.mean(0)
    for r in range(rows):
        for c in range(cols):
            sl = (slice(r * CELL, (r + 1) * CELL), slice(c * CELL, (c + 1) * CELL))
            cm[r, c] = np.percentile(motion[sl], 90)
            ctex[r, c] = mean[sl].std()
            # stoi w obrebie kazdej zakladki, a miedzy nimi sie zmienia = zakladka
            inside = max(np.abs(a[:, sl[0], sl[1]] - a[:, sl[0], sl[1]].mean(0)).max(),
                         np.abs(b[:, sl[0], sl[1]] - b[:, sl[0], sl[1]].mean(0)).max())
            between = np.abs(a[:, sl[0], sl[1]].mean(0) - b[:, sl[0], sl[1]].mean(0)).mean()
            if inside < 8 and between > 12:
                ctab[r, c] = between
    cands = []
    for r in range(rows - MARK_H + 1):
        for c in range(cols - MARK_W + 1):
            if (cm[r:r + MARK_H, c:c + MARK_W] < 6).all():
                tex = ctex[r:r + MARK_H, c:c + MARK_W]
                if tex.mean() > 5 and tex.min() > 1.5:
                    cands.append((float(tex.sum()), r, c))
    cands.sort(reverse=True)
    box = lambda r, c: {"x": c * CELL, "y": r * CELL, "w": MARK_W * CELL, "h": MARK_H * CELL}
    cut = lambda img, r, c: np.round(img[r * CELL:(r + MARK_H) * CELL,
                                         c * CELL:(c + MARK_W) * CELL]).astype(np.uint8).tolist()
    apart = lambda r, c, used: not any(abs(r - ur) < MARK_H + 1 and abs(c - uc) < MARK_W + 1
                                       for ur, uc in used)
    marks, used = [], []
    # zakladki: okna z najwieksza liczba komorek zakladki, z rysunkiem w obu wersjach
    tcands = []
    for r in range(rows - MARK_H + 1):
        for c in range(cols - MARK_W + 1):
            t = ctab[r:r + MARK_H, c:c + MARK_W]
            k = int((t > 0).sum())
            if k < 3:
                continue
            ys, xs = slice(r * CELL, (r + MARK_H) * CELL), slice(c * CELL, (c + MARK_W) * CELL)
            if min(ma[ys, xs].std(), mb[ys, xs].std()) < 5:
                continue
            tcands.append((r, -k, -float(t.sum()), c))
    # najwyzej: naglowek zakladek jest na gorze panelu, nizej bywa lista gier,
    # ktora zmienia sie z kazda nowa gra
    tcands.sort()
    for r, _, _, c in tcands:
        if not apart(r, c, used):
            continue
        used.append((r, c))
        marks.append(dict(box(r, c), refs=[cut(ma, r, c), cut(mb, r, c)]))
        if len(used) == n_tab:
            break
    n_tabs = len(marks)
    for score, r, c in cands:
        if not apart(r, c, used):
            continue                # znaczniki rozrzucone, nie jeden obok drugiego
        used.append((r, c))
        marks.append(dict(box(r, c), ref=cut(mean, r, c)))
        if len(marks) - n_tabs == n:
            break
    return marks, int((ctab > 0).sum()) >= 2


def mark_hits(th, marks, cfg):
    out = []
    for m in marks:
        cur = th[m["y"]:m["y"] + m["h"], m["x"]:m["x"] + m["w"]]
        refs = m.get("refs") or [m["ref"]]
        out.append(cur.shape == (m["h"], m["w"]) and
                   max(corr(cur, np.array(r, np.float32)) for r in refs) >= cfg["lobby_corr"])
    return out


def marks_match(th, marks, cfg, hits=None):
    """Lobby, gdy pasuje choc jeden znacznik zakladki (Create albo Join) albo
    dwa stale. Stare kalibracje (same stale) - wiekszosc, jak dawniej."""
    hits = mark_hits(th, marks, cfg) if hits is None else hits
    tabs = any(h for h, m in zip(hits, marks) if "refs" in m)
    n = sum(h for h, m in zip(hits, marks) if "refs" not in m)
    static = sum("refs" not in m for m in marks)
    if static == len(marks):
        return n >= static // 2 + 1
    return tabs or (static > 0 and n >= min(2, static))


# Samoczyszczenie znacznikow. Kalibracja trwa pare sekund, wiec nie odrozni
# stalego ramienia panelu od linii czatu czy gracza, ktory akurat stal. Po
# kazdej pewnej wizycie w lobby (pasuje zakladka i cos stalego) znacznik, ktory
# ani razu nie pasowal, dostaje minus; po MISS_MAX wizytach z rzedu wylatuje.
MISS_MAX = 3
_visit = {"seen": None, "sure": False}


def _key(m):
    return (m["x"], m["y"], "refs" in m)


def _end_visit():
    seen, sure = _visit["seen"], _visit["sure"]
    _visit.update(seen=None, sure=False)
    if not seen or not sure:
        return
    c = load_calib()
    lob = c.get("lobby")
    if not lob:
        return
    for m in lob["marks"]:
        m["miss"] = 0 if _key(m) in seen else m.get("miss", 0) + 1
    keep = list(lob["marks"])
    for m in sorted(lob["marks"], key=lambda m: -m["miss"]):
        if m["miss"] < MISS_MAX:
            break
        same = [k for k in keep if ("refs" in k) == ("refs" in m)]
        if len(same) > (1 if "refs" in m else 2):
            keep.remove(m)
    lob["marks"] = keep
    save_calib(c)


def _track(marks, hits, lobby):
    if not lobby:
        if _visit["seen"] is not None:
            _end_visit()
        return
    if _visit["seen"] is None:
        _visit["seen"] = set()
    _visit["seen"] |= {_key(m) for m, h in zip(marks, hits) if h}
    tab = any(h and "refs" in m for m, h in zip(marks, hits))
    stat = any(h and "refs" not in m for m, h in zip(marks, hits))
    _visit["sure"] |= tab and stat


def lobby_visible(win, cfg):
    marks = lobby_marks(win)
    if marks:
        hits = mark_hits(thumb(grab(win)), marks, cfg)
        lobby = marks_match(None, marks, cfg, hits)
        if any("refs" in m for m in marks):
            _track(marks, hits, lobby)
        return lobby
    if not LOBBY_REF.exists():
        a = gray(grab(win, cfg["regions"]["tab_create"])).mean()
        b = gray(grab(win, cfg["regions"]["tab_join"])).mean()
        return max(a, b) > 22 and min(a, b) > 0 and max(a, b) / min(a, b) > 1.5
    ref = np.asarray(Image.open(LOBBY_REF).convert("L").resize((96, 12)), dtype=np.float32)
    cur = np.asarray(grab(win, cfg["regions"]["lobby_mark"]).convert("L").resize((96, 12)),
                     dtype=np.float32)
    a, b = ref - ref.mean(), cur - cur.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return (float((a * b).sum() / den) if den else 0.0) >= cfg["lobby_corr"]


def active_tab(win, cfg):
    a = gray(grab(win, cfg["regions"]["tab_create"])).mean()
    b = gray(grab(win, cfg["regions"]["tab_join"])).mean()
    return "create" if a >= b else "join"


def selected_row(win, cfg, glyphs, scale=1.0):
    """Podswietlony wpis listy gier: ramka to pelna pozioma linia jasnych pikseli."""
    img = grab(win, cfg["regions"]["join_list"])
    g = gray(img)
    if g.size == 0:
        return ""
    lines = np.where((g > g.max() * 0.6).mean(axis=1) > 0.6)[0]
    pair = next(((lines[i], lines[i + 1]) for i in range(len(lines) - 1)
                 if 14 <= lines[i + 1] - lines[i] <= 34), None)
    if not pair:
        return ""
    sub = img.crop((4, pair[0] + 2, max(10, int(img.width * 0.80)), pair[1] - 1))
    return read_text(mask_lobby(sub, cfg), glyphs, cfg, scale)


def read_screen(win, cfg, fonts, meta):
    fonts, meta = for_window(fonts, meta, win[4])
    out = {"in_game": "", "lobby": False, "tab": None, "name": "", "selected": ""}
    out["in_game"] = hud_game_name(win, cfg, fonts["hud"], meta)
    if out["in_game"]:
        return out
    if not lobby_visible(win, cfg):
        return out
    sc = win_scale(win, meta)
    out["lobby"] = True
    out["tab"] = tab = active_tab(win, cfg)
    reg = cfg["regions"]["create_name" if tab == "create" else "join_name"]
    out["name"] = read_text(stable_mask(win, reg, cfg), fonts["lobby"], cfg, sc)
    if tab == "join":
        out["selected"] = selected_row(win, cfg, fonts["lobby"], sc)
    return out


# ---------- wyjscie ----------

def notify(title, body):
    """Dymek systemowy - tylko Linux (notify-send); na Windowsie wszystko
    pokazuje okno programu. Brak narzedzia nie przerywa odczytu."""
    if WINDOWS:
        return
    try:
        subprocess.run(["notify-send", "-a", "d2r-relay", title, body], capture_output=True)
    except OSError:
        pass


LOG_KEEP = 1000        # historia gier: tyle ostatnich wpisow zostaje w games.log


def trim_log():
    """Przyciecie historii; przepisywana dopiero przy 20% nadwyzki, nie co gre."""
    try:
        lines = LOG.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return
    if len(lines) > LOG_KEEP * 1.2:
        LOG.write_text("".join(lines[-LOG_KEEP:]), encoding="utf-8")


def commit(name, source):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    CURRENT.write_text(name + "\n", encoding="utf-8")
    CURRENT_JSON.write_text(json.dumps({"name": name, "source": source, "time": ts},
                                       ensure_ascii=False) + "\n", encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as f:
        f.write("%s\t%s\t%s\n" % (ts, name, source))
    trim_log()
    notify("D2R - nazwa gry", name)
    return name


# ---------- komendy ----------

def need_window():
    win = d2r_window()
    if not win:
        print("Nie widze okna '%s' - czy gra chodzi?" % WIN_TITLE, file=sys.stderr)
        sys.exit(2)
    return win


def cmd_once(args, cfg):
    win = need_window()
    fonts, meta = load_glyphs()
    if not fonts["hud"] and not fonts["lobby"]:
        print("Brak nauczonych glifow - odpal najpierw: d2rread.py teach", file=sys.stderr)
    print(json.dumps(read_screen(win, cfg, fonts, meta), ensure_ascii=False, indent=2))


def cmd_now(args, cfg):
    win = need_window()
    fonts, meta = load_glyphs()
    # Pojedyncza klatka bywa nieczytelna (jasna scena pod napisem), wiec pod
    # skrotem probujemy przez ~2 s. Nazwy z '?' nie zapisujemy.
    dirty = ""
    for i in range(6):
        if i:
            time.sleep(0.35)
        d = read_screen(win, cfg, fonts, meta)
        name = d["in_game"] or d["name"] or d["selected"]
        if not name:
            continue
        if "?" not in name:
            print(commit(name, "hud" if d["in_game"] else "lobby"))
            if getattr(args, "discord", False):
                poster = webhook_poster(cfg)
                print("wyslane na kanal" if poster.send(name, force=True)
                      else "kanal Discord: %s" % poster.error)
            return
        dirty = dirty or name
    if dirty:
        notify("D2R", "odczyt niepewny: %s" % dirty)
        print("odczyt niepewny: %s (nie zapisuje)" % dirty)
        return
    notify("D2R", "nie widze nazwy gry (ani w HUD, ani w lobby)")
    print("brak nazwy")


def cmd_watch(args, cfg):
    fonts, meta = load_glyphs()
    if not fonts["hud"]:
        print("Brak wzorcow HUD - odpal najpierw: d2rread.py teach", file=sys.stderr)
        sys.exit(2)
    keeper = presence_keeper(cfg) if getattr(args, "presence", False) else None
    poster = webhook_poster(cfg) if getattr(args, "discord", False) else None
    extra = ("".join([" + status Discord" if keeper else "",
                      " + kanal Discord" if poster else ""]))
    print("czekam na wejscie do gry...%s (Ctrl-C konczy)" % extra, flush=True)
    last, seen_size = "", None
    try:
        while True:
            win = d2r_window()
            if not win:
                if keeper and last != CLOSED:
                    last = CLOSED           # gra zamknieta: status znika
                    keeper.clear()
                time.sleep(cfg["poll"]); continue
            if (win[3], win[4]) != seen_size:
                seen_size = (win[3], win[4])
                sets = glyph_sets(fonts, meta)
                if win[4] not in sets:
                    print("inna rozdzielczosc: %dp, wzorce sa z %s - naucz czytnik przy"
                          " tej rozdzielczosci" % (win[4], ", ".join("%dp" % r for r in sets)),
                          flush=True)
                if not lobby_marks(win):
                    print("lobby nieskalibrowane dla tego okna - skalibruj lobby", flush=True)
            if not d2r_is_active(win):
                # Alt-tab: nie da sie czytac przykrytego okna, wiec status
                # zostawiamy taki, jaki byl - lepszy ostatni znany niz zaden.
                time.sleep(cfg["poll"]); continue
            try:
                d = read_screen(win, cfg, fonts, meta)
            except Exception as e:
                print("blad odczytu: %s" % e, file=sys.stderr)
                time.sleep(cfg["poll"]); continue
            if d["in_game"] and d["in_game"] != last:
                last = d["in_game"]
                print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), commit(last, "hud")), flush=True)
                shown = presence_text(cfg, last)
                if keeper and not keeper.set(
                        cfg["presence_details"].format(name=shown) or None,
                        start=time.time(),
                        name=cfg["presence_name"].format(name=shown) or None):
                    print("  (status Discord: %s)" % keeper.error, flush=True)
                if poster and not poster.send(last):
                    print("  (kanal Discord: %s)" % poster.error, flush=True)
            elif d["lobby"] and last != LOBBY:
                # Kasujemy 'last', bo ta sama nazwa gry moze sie powtorzyc.
                # LOBBY ma podkreslenie, ktorego gra nie przyjmuje w nazwie,
                # wiec nie pomyli sie z prawdziwa nazwa.
                last = LOBBY
                print("powrot do lobby", flush=True)
                if keeper and not keeper.set(start=time.time(), **lobby_activity(cfg)):
                    print("  (status Discord: %s)" % keeper.error, flush=True)
            if d["lobby"] and args.verbose:
                print("  lobby (%s): %s" % (d["tab"], d["name"] or d["selected"]), flush=True)
            time.sleep(cfg["poll"])
    except KeyboardInterrupt:
        pass
    finally:
        if keeper:
            keeper.close()          # nie zostawiamy wiszacego statusu


# ---------- Discord Rich Presence ----------

def lobby_activity(cfg):
    """Status w lobby. Tekst idzie tam, gdzie w grze stoi nazwa gry: gdy nazwa
    siedzi w naglowku, samo 'Lobby' w opisie wygladalo jak oryginalny status
    (naglowek wracal do nazwy aplikacji, a opis widac dopiero w profilu)."""
    idle = cfg.get("presence_idle") or "Lobby"
    if "{name}" in (cfg.get("presence_name") or ""):
        det = cfg.get("presence_details") or ""
        # staly opis (np. tytul gry) zostaje, zeby profil nie mrugal
        return {"name": idle, "details": det} if det and "{name}" not in det \
            else {"name": idle}
    return {"details": idle}


def presence_text(cfg, name):
    """Nazwa gry tak, jak ma wygladac na Discordzie: opcjonalnie wersalikami."""
    return name.upper() if cfg.get("presence_upper") else name


def presence_keeper(cfg):
    if not cfg.get("presence_id"):
        print("Brak Client ID - ustaw je raz: d2rread.py presence --id <ID>\n"
              "(aplikacje zakladasz na discord.com/developers/applications,"
              " jej nazwa bedzie widoczna w statusie)", file=sys.stderr)
        sys.exit(2)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import presence
    return presence.Keeper(cfg["presence_id"])


def webhook_poster(cfg):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import webhook
    url = webhook.load_url()
    if not url:
        print("Brak webhooka - ustaw go raz: d2rread.py discord --url <adres>\n"
              "(adres bierzesz z: kanal -> Edytuj kanal -> Integracje -> Webhooki)",
              file=sys.stderr)
        sys.exit(2)
    return webhook.Poster(url, cfg["discord_template"], cfg["discord_user"],
                          cfg["discord_avatar"], float(cfg["discord_dedupe"]),
                          upper=bool(cfg.get("discord_upper")))


def cmd_discord(args, cfg):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import webhook
    if args.off:
        print("webhook skasowany" if webhook.forget() else "nie bylo zadnego webhooka")
        return
    if args.url:
        try:
            webhook.save_url(args.url)
        except webhook.WebhookError as e:
            print(e, file=sys.stderr); sys.exit(2)
        print("webhook zapisany w %s (prawa 0600)" % webhook.HOOK_FILE)
        if not args.test:
            return
    if not args.test:
        url = webhook.load_url()
        print("webhook: %s\nnadawca: %s\nszablon: %s\n"
              "proba: d2rread.py discord --test   |   na zywo: d2rread.py watch --discord"
              % (_hide(url) if url else "(brak)", cfg["discord_user"], cfg["discord_template"]))
        return
    poster = webhook_poster(cfg)
    name = args.test if isinstance(args.test, str) else "test-gry-01"
    if poster.send(name, force=True):
        print("wyslane na kanal: %s" % poster.template.format(name=name, time="--:--"))
    else:
        print("nie poszlo: %s" % poster.error, file=sys.stderr); sys.exit(1)


def _hide(url):
    # Adres webhooka to poswiadczenie - na ekran tylko poczatek i ogon.
    return url[:48] + "..." + url[-4:] if len(url) > 60 else url


def cmd_presence(args, cfg):
    if args.id:
        cfg["presence_id"] = args.id.strip()
        save_config(cfg)
        print("zapisane Client ID: %s" % cfg["presence_id"])
        if not args.test:
            return
    if not (args.test or args.off):
        print("Client ID: %s\nopis: %s\nnaglowek: %s\nstatus miedzy grami: %s\n"
              "proba: d2rread.py presence --test   |   na zywo: d2rread.py watch --presence"
              % (cfg.get("presence_id") or "(brak)", cfg["presence_details"],
                 cfg["presence_name"] or "(nazwa gry spod Client ID)",
                 cfg["presence_idle"]))
        return
    keeper = presence_keeper(cfg)
    if args.off:
        keeper.set()
        print("status wyczyszczony" if not keeper.error else keeper.error)
        return
    name = args.test if isinstance(args.test, str) else "test-gry-01"
    shown = presence_text(cfg, name)
    if not keeper.set(cfg["presence_details"].format(name=shown) or None,
                      start=time.time(),
                      name=cfg["presence_name"].format(name=shown) or None):
        print("nie poszlo: %s" % keeper.error, file=sys.stderr)
        sys.exit(1)
    print("status ustawiony na '%s' - zerknij na swoj profil. Ctrl-C konczy." % name)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        keeper.close()
        print("\nstatus zdjety")


def cmd_check(args, cfg):
    """Audyt bazy wzorcow - czy nic sie nie pomieszalo i czego brakuje."""
    fonts, meta = load_glyphs()
    alnum = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    bad = 0
    for font in FONTS:
        glyphs = fonts[font]
        if not glyphs:
            print("%-6s: pusto" % font)
            continue
        have = learned(glyphs)
        seen, clash = {}, []
        for t in glyphs:
            k = (t["w"], t["h"], t["bits"])
            if k in seen and seen[k] != t["c"]:
                clash.append((seen[k], t["c"]))
            seen[k] = t["c"]
        miss = "".join(sorted(alnum - have))
        print("%-6s: %d wzorcow, %d znakow" % (font, len(glyphs), len(have)))
        print("        brakuje: %s" % (miss or "nic"))
        if clash:
            bad += len(clash)
            print("        POMYLONE (ta sama bitmapa pod dwoma znakami): %s"
                  % ", ".join("%s=%s" % c for c in clash))
    print("meta: %s" % meta)
    if bad:
        print("\nBaza jest pomylona - naucz od nowa: usun %s i odpal teach" % GLYPHS,
              file=sys.stderr)
        sys.exit(1)


def cmd_hud(args, cfg):
    """Diagnostyka linii 'Game:' - co widzi kazdy prog maski.

    Uruchamiane recznie, gdy nazwa czyta sie z dodatkowa litera. Zapisuje
    wycinek linii do pliku i wypisuje odczyt wraz z szerokoscia i odstepem
    kazdego glifu, zeby bylo widac, skad bierze sie nadmiarowy znak.
    """
    win = need_window()
    fonts, meta = load_glyphs()
    fonts, meta = for_window(fonts, meta, win[4])
    glyphs = fonts["hud"]
    base = win_scale(win, meta)
    if args.wait:
        print("mam %d s - przejdz do gry i otworz mape (Tab)" % args.wait, flush=True)
        time.sleep(args.wait)
    if not hud_calibrated(win):
        rect = locate_hud(win, cfg, glyphs)
        if not rect:
            print("nie znalazlem linii 'Game:' - czy mapa jest otwarta?", file=sys.stderr)
            sys.exit(2)
        remember_hud(win, rect)
    for shot in range(args.shots):
        if shot:
            time.sleep(1.0)
        img = grab(win, px=hud_rect(win, cfg))
        out = "%s-%d.png" % (args.out.removesuffix(".png"), shot + 1)
        img.save(out)
        print("\nzrzut %d: %s" % (shot + 1, out))
        for level in cfg["hud_levels"]:
            boxes = hud_boxes(win, cfg, level, img=img)
            name = hud_name_at(img, win, cfg, glyphs, base, level)
            geo = " ".join("%s%dx%d" % ("+%d " % (b.x0 - boxes[i - 1].x1) if i else "",
                                        b.piece.shape[1], b.piece.shape[0])
                           for i, b in enumerate(boxes))
            print("  prog %-5s glifow %2d  nazwa %-20s %s"
                  % (level, len(boxes), repr(name), geo))


def cmd_regions(args, cfg):
    win = need_window()
    img = grab(win)
    d = ImageDraw.Draw(img)
    for name, reg in cfg["regions"].items():
        x, y, w, h = scale_region(reg, win)
        d.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=2)
        d.text((x, max(0, y - 12)), name, fill=(255, 80, 80))
    # skalibrowane: linia 'Game:' i znaczniki lobby (zielone)
    if hud_calibrated(win):
        x, y, w, h = hud_rect(win, cfg)
        d.rectangle([x, y, x + w, y + h], outline=(0, 255, 0), width=2)
        d.text((x, y + h + 2), "hud (kalibracja)", fill=(80, 255, 80))
    k = win[3] / THUMB_W
    for m in lobby_marks(win) or []:
        x, y, w, h = (round(v * k) for v in (m["x"], m["y"], m["w"], m["h"]))
        d.rectangle([x, y, x + w, y + h], outline=(0, 255, 0), width=2)
        d.text((x, max(0, y - 12)), "lobby", fill=(80, 255, 80))
    out = args.out or "/tmp/d2r-regions.png"
    img.save(out)
    print("zapisane: %s" % out)


def cmd_bump(args, cfg):
    reg = cfg["regions"].get(args.region)
    if not reg:
        print("nie znam obszaru %s; mam: %s" % (args.region, ", ".join(cfg["regions"])),
              file=sys.stderr)
        sys.exit(2)
    cfg["regions"][args.region] = (reg[0] + args.dx, reg[1] + args.dy,
                                   reg[2] + args.dw, reg[3] + args.dh)
    save_config(cfg)
    print("%s: %s -> %s" % (args.region, reg, cfg["regions"][args.region]))


# ---------- nauka ----------

def wait_for(fn, note=None, every=12):
    n = 0
    while True:
        time.sleep(0.6)
        v = fn()
        if v:
            return v
        n += 1
        if note and n % every == 0:
            print("    " + note, flush=True)


TEACH_NAMES = ["AaBbCcDdEeFfGg", "HhIiJjKkLlMmNn", "OoPpQqRrSsTtUu",
               "VvWwXxYyZz0123", "456789-AaZz"]
# Znaki, ktorych gra moze nie przyjac w nazwie gry. Ucza sie w osobnych,
# jednoznakowych rundach na koncu - w rundzie zbiorczej jeden taki znak
# przewracal cala reszte (cyfry przepadaly razem z '_').
TEACH_EXTRA = "_"
NAME_CHARS = set("".join(TEACH_NAMES) + TEACH_EXTRA)
TEACH_LOBBY = ["AaBbCcDdEe", "FfGgHhIiJj", "KkLlMmNnOo",
               "PpQqRrSsTt", "UuVvWwXxYy", "Zz012345", "A6789-_"]


def learn_line(boxes, chars, glyphs, cfg=None, scale=1.0):
    """Uczy sie tylko z probki, ktora na pewno pokazuje to, o co prosilismy.

    Dwa warunki. Liczba glifow musi zgadzac sie ze znakami - wczesniej brakujace
    glify dopychane byly cieciem litery na pol i taka polowka ladowala w bazie.
    Drugi warunek: znaki, ktore juz umiemy, musza czytac sie zgodnie z nazwa -
    inaczej patrzymy na inna gre niz ta, o ktora prosilismy, i przypisalibysmy
    litery do cudzych etykiet.
    """
    if len(boxes) != len(chars):
        return 0
    if cfg is not None and glyphs:
        for b, ch in zip(boxes, chars):
            got = match_glyph(b.piece, glyphs, cfg, scale, box=b, allow_split=False)[0]
            if got != "?" and got != ch:
                return 0
    return sum(add_glyph(glyphs, b, c) for b, c in zip(boxes, chars))


def learned(glyphs):
    return {t["c"] for t in glyphs}


def retry_names(missing, glyphs, times=3):
    """Na kazdy brakujacy znak osobna nazwa: 'a9a9a9'.

    Rozdzielacz to litera juz nauczona, wiec runda sama sie sprawdza. Osobna
    nazwa na znak jest wazna: jeden znak, ktorego gra nie przyjmuje w nazwie,
    przewracal cala runde razem z pozostalymi i prosilo o nia w kolko.
    """
    known = learned(glyphs)
    sep = next((c for c in "aoetAOET" if c in known and c not in missing), "")
    return [(sep + ch) * times for ch in sorted(missing)]


def ask(msg):
    """Pytanie do gracza: linia z '> ' i czekanie na Enter. Okno (d2rgui)
    pokazuje wtedy przycisk i samo odsyla Enter."""
    print("> %s [Enter]" % msg, flush=True)
    if not sys.stdin.readline():
        print("Brak potwierdzenia - przerywam", file=sys.stderr)
        sys.exit(2)


def grab_game(win, note=True):
    """Pelna klatka okna, gdy gra jest na wierzchu. Po kliknieciu w okienku
    albo Enterze w terminalu gra jest przykryta, a zrzut przykrytego okna
    zlapalby to, co je przykrywa."""
    if not d2r_is_active(win):
        if note:
            print("    przelacz sie do gry", flush=True)
        wait_for(lambda: d2r_is_active(win), "czekam, az okno gry bedzie na wierzchu...")
        time.sleep(0.6)
    return grab(win)


def calibrate_lobby(win, cfg):
    print("Kalibracja lobby: zapamietuje, jak wyglada lobby na Twoim ekranie.", flush=True)
    steps = ("wejdz do lobby, na zakladke Create Game", "przelacz na zakladke Join Game")
    for _ in range(3):
        sets = []
        for i, text in enumerate(steps, 1):
            ask("[lobby %d/2] %s" % (i, text))
            frames = []
            for k in range(4):
                if k:
                    time.sleep(0.4)
                frames.append(thumb(grab_game(win, note=not k)))
            sets.append(frames)
        marks, switched = pick_marks(*sets)
        if not switched:
            print("    nie widze przelaczenia zakladki - jeszcze raz", flush=True)
            continue
        if not marks:
            print("    nie widze stalych elementow na ekranie - jeszcze raz", flush=True)
            continue
        c = load_calib()
        c["lobby"] = {"win": [win[3], win[4]], "marks": marks}
        save_calib(c)
        print("    lobby zapamietane (%d znaczniki)" % len(marks), flush=True)
        return True
    print("Kalibracja lobby nie wyszla - czy na pewno bylo lobby z zakladkami"
          " Create / Join?", file=sys.stderr)
    return False


def cmd_calibrate(args, cfg):
    win = need_window()
    if not calibrate_lobby(win, cfg):
        sys.exit(1)
    c = load_calib()
    c.pop("hud", None)       # linie 'Game:' czytnik znajdzie sam przy nastepnej grze
    save_calib(c)
    print("Gotowe. Lobby rozpoznane.")


def cmd_teach(args, cfg):
    win = need_window()
    full, fmeta = load_glyphs()
    # Uczymy zestaw dla tej wysokosci okna; zestawy innych rozdzielczosci
    # zostaja nietkniete.
    fonts, meta = for_window(full, fmeta, win[4], exact=True)
    if not fonts["hud"] and glyph_sets(full, fmeta):
        print("Nowa rozdzielczosc (%dp) - ucze sie jej od poczatku." % win[4], flush=True)

    def store():
        save_glyphs(merge_view(full, fmeta, fonts, win[4]), fmeta)

    meta["store"] = store
    if not args.lobby and not lobby_marks(win):
        # Rundy rozdziela lobby, wiec bez znacznika z tego ekranu nie ruszymy.
        if not calibrate_lobby(win, cfg):
            sys.exit(1)
    if args.lobby:
        teach_lobby(win, cfg, fonts, meta, args)
    else:
        teach_hud(win, cfg, fonts, meta, args)
    store()
    notify("D2R nauka", "gotowe")
    print("Gotowe. Sprawdz: d2rread.py once")


def teach_hud_round(win, cfg, glyphs, meta, name, samples=10):
    """Zbiera probki linii HUD, kazda przy kazdym progu maski.

    Ta sama litera wychodzi co klatke o piksel inna, a kazdy prog daje troche
    inna grubosc kreski - im wiecej wariantow w bazie, tym pewniejszy odczyt.
    """
    base = win_scale(win, meta)
    chars = list(HUD_PREFIX + name)
    new = rounds = 0
    seen = set()
    for i in range(samples):
        if i:
            time.sleep(0.4)
        img = grab(win, px=hud_rect(win, cfg))
        for level in cfg["hud_levels"]:
            boxes = hud_boxes(win, cfg, level, img=img)
            if boxes:
                seen.add(len(boxes))
            if len(boxes) == len(chars):
                rounds += 1
                new += learn_line(boxes, chars, glyphs, cfg, base)
        if rounds >= 8 and hud_game_name(win, cfg, glyphs, meta) == name:
            break                     # juz czyta te nazwe bezblednie
    return new, rounds, seen


def extra_rounds(done, glyphs, tries):
    """Dodatkowe gry na znaki, ktorych po serii dalej brakuje (najwyzej 2 razy)."""
    miss = ({c for n in done for c in n} | set(TEACH_EXTRA)) - learned(glyphs) - {" "}
    miss = {c for c in miss if tries[c] < 2}
    for c in miss:
        tries[c] += 1
    extra = retry_names(miss, glyphs) if miss else []
    if extra:
        print("  brakuje jeszcze: %s - tyle dodatkowych gier"
              % "".join(sorted(miss)), flush=True)
    return extra


def teach_hud(win, cfg, fonts, meta, args):
    glyphs = fonts["hud"]
    names = [args.text] if args.text else list(TEACH_NAMES)
    if args.again and not args.text:          # powtorka calej serii - z '_' wlacznie
        names += retry_names(set(TEACH_EXTRA), glyphs)
    print("Nauka czcionki HUD (nazwa gry w prawym gornym rogu).")
    print("Dla kazdej nazwy: wroc do lobby, zaloz gre o tej nazwie, wejdz do")
    print("niej, poczekaj na 'ok' i wyjdz (Exit Game).\n")
    todo, done, guard = list(names), [], 0
    tries = collections.Counter()
    while todo and guard < len(names) + 20:
        name = todo.pop(0)
        guard += 1
        if set(name) <= learned(glyphs) and not args.again:
            print("  pomijam %r - te znaki juz umiem" % name, flush=True)
            done.append(name)
            if not todo and not args.text:  # wszystko pominiete - braki i tak dograc
                todo += extra_rounds(done, glyphs, tries)
            continue          # nauke mozna wznowic bez powtarzania wszystkiego
        # Etapy rozdziela lobby, a nie znikniecie linii 'Game:' - ta znika sama
        # po chwili w grze, wiec braloby to za wyjscie i wyprzedzalo gracza.
        # Nazwe podajemy dopiero w lobby, zeby nie wyskakiwala w srodku gry.
        wait_for(lambda: lobby_visible(win, cfg), "czekam, az wrocisz do lobby...")
        # ile gier w sumie: zrobione + ta + kolejka + dokladka na znaki spoza serii
        pending = 0 if args.text else len(set(TEACH_EXTRA) - learned(glyphs)
                                          - set("".join(todo + [name])))
        print("  [%d/%d] zaloz gre o nazwie:  %s"
              % (len(done) + 1, len(done) + 1 + len(todo) + pending, name), flush=True)
        notify("D2R nauka (%d)" % (len(done) + 1), "zaloz gre o nazwie:\n%s" % name)
        # Linie 'Game:' szukamy w calym rogu po liczbie glifow - dziala przy
        # kazdej rozdzielczosci i proporcjach, takze zanim cokolwiek umiemy.
        expect = len(HUD_PREFIX + name)
        rect = wait_for(lambda: not lobby_visible(win, cfg)
                        and locate_hud(win, cfg, glyphs, expect),
                        "czekam, az wejdziesz do gry...")
        remember_hud(win, rect)
        if lobby_visible(win, cfg):
            print("    uwaga: znacznik lobby pasuje tez w grze - skalibruj lobby"
                  " jeszcze raz", file=sys.stderr, flush=True)
        new, rounds, seen = teach_hud_round(win, cfg, glyphs, meta, name)
        done.append(name)
        meta["store"]()
        if rounds:
            got = hud_game_name(win, cfg, glyphs, meta)
            check = "czyta poprawnie" if got == name else (
                "na razie czyta %r" % got if got else "jeszcze nie czyta calosci")
            print("    ok (%d czystych probek, %d nowych wzorcow, razem %d) - %s"
                  % (rounds, new, len(glyphs), check), flush=True)
        else:
            print("    zadna probka nie pasowala do nazwy %r (widzialem glifow:"
                  " %s, a znakow w nazwie jest %d) - czy gra przyjela cala"
                  " nazwe?" % (name, sorted(seen) or "-", len(HUD_PREFIX + name)),
                  file=sys.stderr, flush=True)
        notify("D2R nauka", "ok - wyjdz z gry (Exit Game)")
        print("    teraz wyjdz z gry (Exit Game)", flush=True)
        if not todo and not args.text:      # --text = jedna rzecz, bez dokladek
            todo += extra_rounds(done, glyphs, tries)
    miss = {c for n in done for c in n} - learned(glyphs) - {" "}
    if miss:
        print("  nie udalo sie nauczyc: %s" % "".join(sorted(miss)), file=sys.stderr)
        print("  jesli gra nie przyjmuje tych znakow w nazwie gry, to znaczy, ze"
              " nazwa nigdy ich nie zawiera - mozesz to zignorowac", file=sys.stderr)


def teach_lobby(win, cfg, fonts, meta, args):
    glyphs = fonts["lobby"]
    region = cfg["regions"]["create_name"]
    steps = [args.text] if args.text else TEACH_LOBBY
    print("Nauka czcionki lobby. Wejdz w lobby -> zakladka CREATE GAME.")
    print("Po kazdym kroku wyczysc pole (Ctrl+A, Backspace).\n")
    for i, want in enumerate(steps, 1):
        chars = [c for c in want if c != " "]
        print("  [%d/%d] wpisz w pole GAME NAME:  %s" % (i, len(steps), want), flush=True)
        notify("D2R nauka (%d/%d)" % (i, len(steps)), "wpisz w GAME NAME:\n%s" % want)
        prev, stable = None, 0
        while True:
            time.sleep(0.6)
            boxes = glyph_boxes(mask_lobby(grab(win, region), cfg))
            sig = [(b.x0, b.x1) for b in boxes]
            stable = stable + 1 if sig and sig == prev else 0
            prev = sig
            if stable >= 2:
                if len(boxes) != len(chars):
                    print("    widze %d glifow zamiast %d - popraw wpis"
                          % (len(boxes), len(chars)), flush=True)
                    stable = 0
                    continue
                learn_line(boxes, chars, glyphs, cfg, win_scale(win, meta))
                meta["store"]()
                print("    ok (razem %d wzorcow)" % len(glyphs), flush=True)
                notify("D2R nauka", "ok - wyczysc pole (Ctrl+A, Backspace)")
                break
        wait_for(lambda: not glyph_boxes(mask_lobby(grab(win, region), cfg)),
                 "czekam na wyczyszczenie pola...")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("once")
    n = sub.add_parser("now")
    n.add_argument("--discord", action="store_true", help="wyslij tez na kanal")
    w = sub.add_parser("watch"); w.add_argument("-v", "--verbose", action="store_true")
    w.add_argument("--presence", action="store_true",
                   help="pokazuj nazwe gry w statusie Discorda")
    w.add_argument("--discord", action="store_true",
                   help="wysylaj nazwe gry na kanal (webhook)")
    p = sub.add_parser("presence")
    p.add_argument("--id", help="Client ID aplikacji z Discord Developer Portal")
    p.add_argument("--test", nargs="?", const=True, default=False,
                   help="ustaw probny status (opcjonalnie wlasny tekst)")
    p.add_argument("--off", action="store_true", help="zdejmij status")
    dc = sub.add_parser("discord")
    dc.add_argument("--url", help="adres webhooka kanalu")
    dc.add_argument("--test", nargs="?", const=True, default=False,
                    help="wyslij probna wiadomosc (opcjonalnie wlasna nazwa)")
    dc.add_argument("--off", action="store_true", help="zapomnij webhook")
    sub.add_parser("check")
    h = sub.add_parser("hud", help="diagnostyka odczytu linii 'Game:'")
    h.add_argument("--wait", type=int, default=0, help="odczekaj tyle sekund przed zrzutem")
    h.add_argument("--shots", type=int, default=3, help="ile zrzutow po kolei")
    h.add_argument("--out", default="/tmp/d2r-hud.png", help="gdzie zapisac wycinki")
    r = sub.add_parser("regions"); r.add_argument("-o", "--out")
    sub.add_parser("calibrate", help="zapamietaj lobby na tym ekranie")
    t = sub.add_parser("teach")
    t.add_argument("--lobby", action="store_true", help="ucz czcionki lobby zamiast HUD")
    t.add_argument("--text", help="jeden ciag zamiast calej serii")
    t.add_argument("--again", action="store_true",
                   help="cala seria od nowa, takze znane znaki (doklada probki)")
    b = sub.add_parser("bump")
    b.add_argument("region")
    for f in ("dx", "dy", "dw", "dh"):
        b.add_argument("--" + f, type=int, default=0)
    args = ap.parse_args()
    cfg = load_config()
    {"once": cmd_once, "now": cmd_now, "watch": cmd_watch, "check": cmd_check, "hud": cmd_hud,
     "regions": cmd_regions, "teach": cmd_teach, "calibrate": cmd_calibrate, "bump": cmd_bump,
     "presence": cmd_presence, "discord": cmd_discord}[args.cmd](args, cfg)


if __name__ == "__main__":
    if sys.platform.startswith("linux"):
        try:                    # w btop 'd2r-reader' zamiast 'python3'
            import ctypes
            ctypes.CDLL(None).prctl(15, b"d2r-reader", 0, 0, 0)
        except (OSError, AttributeError):
            pass
    main()
