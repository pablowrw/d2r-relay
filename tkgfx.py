#!/usr/bin/env python3
"""
tkgfx - wygladzone obrazki dla Tk, bez zadnych zaleznosci.

Wbudowane motywy ttk rysuja pola wyboru, przyciski i kolka bez wygladzania i
bez zaokraglen, a kolorow ich obrysow nie da sie do konca opanowac. Zamiast
walczyc z motywem rysujemy te elementy sami: kazdy piksel probkowany jest
siatka NxN, wynik trafia do PNG z kanalem alfa, a PNG do PhotoImage. Tk 8.6
czyta PNG z przezroczystoscia na Linuksie i Windowsie tak samo, wiec ten sam
obrazek pasuje na kazde tlo.
"""
import base64
import struct
import tkinter as tk
import zlib


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _png(w, h, rows):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    raw = b"".join(b"\x00" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def paint(w, h, shade, ss=4):
    """shade(x, y) -> (r, g, b, alfa 0..1) albo None dla punktu (x, y)."""
    offs = [(i + 0.5) / ss for i in range(ss)]
    n = ss * ss
    rows = []
    for y in range(h):
        row = bytearray()
        for x in range(w):
            r = g = b = a = 0.0
            for oy in offs:
                for ox in offs:
                    c = shade(x + ox, y + oy)
                    if c:
                        r += c[0] * c[3]; g += c[1] * c[3]; b += c[2] * c[3]; a += c[3]
            if a:
                row += bytes((int(r / a), int(g / a), int(b / a), int(255 * a / n)))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return tk.PhotoImage(data=base64.b64encode(_png(w, h, rows)).decode())


# ---------- ksztalty ----------

def in_rrect(x, y, x0, y0, x1, y1, r):
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def in_circle(x, y, cx, cy, r):
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def near_seg(x, y, ax, ay, bx, by, hw):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    px, py = ax + t * dx - x, ay + t * dy - y
    return px * px + py * py <= hw * hw


def _c(h, a=1.0):
    return rgb(h) + (a,)


# ---------- gotowe elementy ----------

def button(fill, size=28, r=7):
    """Tlo przycisku do rozciagania (9-slice): rogi zostaja, srodek sie ciagnie."""
    f = _c(fill)
    return paint(size, size, lambda x, y: f if in_rrect(x, y, 0, 0, size, size, r) else None)


def checkbox(on, fill, edge, accent, mark, size=18, gap=8):
    f, e, a, m = _c(fill), _c(edge), _c(accent), _c(mark)
    k = size / 18.0

    def shade(x, y):
        if not in_rrect(x, y, 0.5, 0.5, size - 0.5, size - 0.5, 4.5 * k):
            return None
        if on:
            if (near_seg(x, y, 4.6 * k, 9.4 * k, 7.7 * k, 12.5 * k, 1.25 * k)
                    or near_seg(x, y, 7.7 * k, 12.5 * k, 13.6 * k, 5.8 * k, 1.25 * k)):
                return m
            return a
        if in_rrect(x, y, 2.0, 2.0, size - 2.0, size - 2.0, 3.2 * k):
            return f
        return e
    return paint(size + gap, size, shade)


def radio(on, fill, edge, accent, size=18, gap=8):
    f, e, a = _c(fill), _c(edge), _c(accent)
    c = size / 2.0

    def shade(x, y):
        if not in_circle(x, y, c, c, c - 0.5):
            return None
        if not in_circle(x, y, c, c, c - 2.0):
            return a if on else e
        if on and in_circle(x, y, c, c, c * 0.45):
            return a
        return f
    return paint(size + gap, size, shade)


def dot(color, halo=False, size=22):
    """Kropka stanu; z poswiata, gdy cos dziala."""
    core, glow = _c(color), _c(color, 0.22)
    c = size / 2.0

    def shade(x, y):
        if in_circle(x, y, c, c, size * 0.27):
            return core
        if halo and in_circle(x, y, c, c, c - 0.5):
            return glow
        return None
    return paint(size, size, shade)


def eye(shown, color, w=20, h=14):
    """Oko do pola z haslem: otwarte = pokaz, przekreslone = ukryj."""
    col = _c(color)
    cx, cy = w / 2.0, h / 2.0
    rx, ry = w / 2.0 - 1.0, h / 2.0 - 1.5

    def inside(x, y, sx, sy):
        return ((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2 <= 1.0

    def shade(x, y):
        if not shown and near_seg(x, y, 3.0, h - 1.5, w - 3.0, 1.5, 1.1):
            return col
        ring = inside(x, y, rx, ry) and not inside(x, y, rx - 1.5, ry - 1.5)
        return col if ring or in_circle(x, y, cx, cy, h * 0.2) else None
    return paint(w, h, shade)


def discord_avatar(size=18, blurple="#5865f2"):
    """Domyslny awatar webhooka: niebieskie kolko z bialym 'padem' i oczami."""
    b, w = _c(blurple), _c("#ffffff")
    k = size / 18.0
    c = size / 2.0

    def shade(x, y):
        if not in_circle(x, y, c, c, c - 0.3):
            return None
        pad = in_rrect(x, y, 4.2 * k, 5.6 * k, 13.8 * k, 12.6 * k, 2.6 * k)
        eye = in_circle(x, y, 7.2 * k, 9.0 * k, 1.1 * k) or in_circle(x, y, 10.8 * k, 9.0 * k, 1.1 * k)
        return w if pad and not eye else b
    return paint(size, size, shade)


def controller(color, w=16, h=12):
    """Pad jak przy grze na Discordzie: korpus z uchwytami, krzyzak i dwa przyciski."""
    col = _c(color)

    def shade(x, y):
        body = (in_rrect(x, y, 1.0, 1.5, w - 1.0, h - 3.5, 3.0)
                or in_circle(x, y, 3.6, h - 3.2, 2.4)
                or in_circle(x, y, w - 3.6, h - 3.2, 2.4))
        if not body:
            return None
        cross = ((abs(x - 4.6) <= 0.7 and abs(y - 5.2) <= 2.0)
                 or (abs(y - 5.2) <= 0.7 and abs(x - 4.6) <= 2.0))
        btn = in_circle(x, y, w - 5.4, 4.4, 0.95) or in_circle(x, y, w - 3.6, 6.2, 0.95)
        return None if cross or btn else col
    return paint(w, h, shade)


def user_avatar(size=32, status="#23a55a", face="#80848e"):
    """Zastepczy awatar uzytkownika z zielona kropka 'dostepny', wycieta w tle."""
    c = size / 2.0
    r_dot = size * 0.17
    dx = dy = size - r_dot - 0.5
    fill, dot_c = _c(face), _c(status)

    def shade(x, y):
        if in_circle(x, y, dx, dy, r_dot):
            return dot_c
        if in_circle(x, y, dx, dy, r_dot + size * 0.07):
            return None                     # przerwa miedzy kropka a awatarem
        if not in_circle(x, y, c, c, c - 0.3):
            return None
        head = in_circle(x, y, c, size * 0.38, size * 0.16)
        torso = in_circle(x, y, c, size * 0.92, size * 0.32)
        return _c("#ffffff", 0.85) if head or torso else fill
    return paint(size, size, shade)


def step_icon(state, done="#5fb87a", active="#d4a24a", idle="#5a606d", size=22):
    """Znacznik etapu: 'done' - zielone kolko z ptaszkiem, 'next' - zlota
    obwodka (to teraz), 'todo' - szara obwodka."""
    c = size / 2.0
    ring = size * 0.09

    def shade(x, y):
        if state == "done":
            if not in_circle(x, y, c, c, c - 0.5):
                return None
            tick = (near_seg(x, y, size * 0.28, size * 0.52, size * 0.44, size * 0.68, 1.1)
                    or near_seg(x, y, size * 0.44, size * 0.68, size * 0.73, size * 0.36, 1.1))
            return _c("#ffffff") if tick else _c(done)
        col = _c(active if state == "next" else idle)
        if in_circle(x, y, c, c, c - 0.5) and not in_circle(x, y, c, c, c - 0.5 - ring * 1.6):
            return col
        if state == "next" and in_circle(x, y, c, c, size * 0.18):
            return col
        return None
    return paint(size, size, shade)
