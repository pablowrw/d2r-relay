#!/usr/bin/env python3
"""
webhook - wysylanie nazwy gry na kanal Discorda.

Webhook to adres URL wystawiony przez kanal: POST z JSON-em i tyle, zadnego
bota ani procesu w tle. Nazwe i awatar nadawcy ustawiamy przy kazdej
wiadomosci, ale plakietki APP sie nie da zdjac - to celowe po stronie Discorda
i dlatego wlasnie nie podszywamy sie pod konto uzytkownika.

Adres webhooka jest poswiadczeniem: kto go ma, ten pisze na ten kanal. Stad
osobny plik z prawami 0600, a nie wspolny config.json.
"""
import json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import platformdirs_lite as dirs

CFG_DIR = dirs.config_dir()
HOOK_FILE = CFG_DIR / "webhook"
UA = "d2r-relay (https://github.com/pablowrw/d2r-relay, 1.0)"


class WebhookError(Exception):
    pass


def load_url():
    if not HOOK_FILE.exists():
        return ""
    return HOOK_FILE.read_text(encoding="utf-8").strip()


def save_url(url):
    url = url.strip()
    if not url.startswith("https://"):
        raise WebhookError("adres webhooka musi zaczynac sie od https://")
    if "/api/webhooks/" not in url:
        raise WebhookError("to nie wyglada na adres webhooka (brak /api/webhooks/)")
    dirs.secure_write(HOOK_FILE, url + "\n")    # adres = prawo pisania na kanal
    return url


def forget():
    if HOOK_FILE.exists():
        HOOK_FILE.unlink()
        return True
    return False


def post(url, content, username=None, avatar=None, timeout=10.0, retries=2):
    """Wysyla wiadomosc. Zwraca None albo rzuca WebhookError z czytelna przyczyna."""
    if not url:
        raise WebhookError("brak zapisanego webhooka")
    payload = {"content": content[:2000],
               # Zadnych pingow: nazwa gry z @everyone w srodku nie ma prawa
               # zawolac calego serwera.
               "allowed_mentions": {"parse": []}}
    if username:
        payload["username"] = username[:80]
    if avatar:
        payload["avatar_url"] = avatar
    data = json.dumps(payload).encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                r.read()
                return
        except urllib.error.HTTPError as e:
            body = e.read(500).decode("utf-8", "replace")
            if e.code == 429 and attempt < retries:
                # Discord sam mowi, ile czekac - sluchamy go zamiast dobijac.
                try:
                    wait = float(json.loads(body).get("retry_after", 1.0))
                except ValueError:
                    wait = 1.0
                time.sleep(min(wait, 15.0))
                continue
            if e.code in (401, 403, 404):
                raise WebhookError("webhook odrzucony (%d) - skasowany albo zly adres" % e.code)
            raise WebhookError("HTTP %d: %s" % (e.code, body.strip()[:200]))
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(1.5)
                continue
            raise WebhookError("brak polaczenia: %s" % e.reason)
    raise WebhookError("nie udalo sie wyslac po %d probach" % (retries + 1))


class Poster:
    """Opakowanie dla watch: nie rzuca, pamieta ostatni blad i nie powtarza
    tej samej nazwy w kolko, gdyby odczyt zamigotal."""

    def __init__(self, url, template="Gra: **{name}**", username="", avatar="", dedupe=90.0,
                 upper=False):
        self.url = url
        self.template = template
        self.username = username
        self.avatar = avatar
        self.dedupe = dedupe
        self.upper = upper
        self.sent = {}
        self.error = ""

    def send(self, name, force=False):
        now = time.time()
        if not force and now - self.sent.get(name, 0.0) < self.dedupe:
            return True                  # ta sama gra chwile temu - pomijamy
        try:
            shown = name.upper() if self.upper else name
            post(self.url, self.template.format(name=shown, time=time.strftime("%H:%M")),
                 self.username or None, self.avatar or None)
        except WebhookError as e:
            self.error = str(e)
            return False
        self.sent[name] = now
        self.error = ""
        return True
