#!/usr/bin/env python3
"""
presence - Discord Rich Presence przez lokalne gniazdo klienta.

Status ustawia sie na Twoim profilu, Twoim imieniem, bez plakietki bota.
Dziala tylko wtedy, gdy klient Discorda chodzi na tej samej maszynie: gadamy
z nim po gniezdzie unix (discord-ipc-N), a nie po sieci. Zadnego tokenu konta
tu nie ma i nie moze byc - to jest ta legalna droga zamiast self-bota.

Protokol: naglowek <I opcode><I dlugosc>, potem JSON.
  op 0 = handshake, 1 = ramka (SET_ACTIVITY), 2 = zamkniecie, 3/4 = ping/pong.
"""
import json, os, socket, struct, sys, tempfile, time, uuid
from pathlib import Path

WINDOWS = sys.platform == "win32"

# Katalogi, w ktorych klient wystawia gniazdo. Flatpak i snap chowaja je
# glebiej, stad podkatalogi.
SOCK_DIRS = ("app/com.discordapp.Discord", "snap.discord", "app/com.discordapp.DiscordCanary", "")
OP_HANDSHAKE, OP_FRAME, OP_CLOSE, OP_PING, OP_PONG = 0, 1, 2, 3, 4


class _Pipe:
    """Windowsowy odpowiednik gniazda: Discord wystawia tam nazwany potok,
    ktory obsluguje sie zwyklym plikiem binarnym."""

    def __init__(self, path):
        self.f = open(path, "r+b", buffering=0)

    def sendall(self, b):
        self.f.write(b); self.f.flush()

    def recv(self, n):
        return self.f.read(n)

    def settimeout(self, t):
        pass                      # nazwany potok nie ma odpowiednika timeoutu

    def close(self):
        self.f.close()


def _open(path):
    if WINDOWS:
        return _Pipe(str(path))
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    return s


def socket_paths():
    if WINDOWS:
        return [r"\\.\pipe\discord-ipc-%d" % i for i in range(10)]
    bases = [os.environ.get("XDG_RUNTIME_DIR"), os.environ.get("TMPDIR"),
             os.environ.get("TMP"), os.environ.get("TEMP"), tempfile.gettempdir()]
    seen, out = set(), []
    for base in bases:
        if not base or base in seen:
            continue
        seen.add(base)
        for sub in SOCK_DIRS:
            for i in range(10):
                p = Path(base, sub, "discord-ipc-%d" % i)
                if p.exists():
                    out.append(p)
    return out


class PresenceError(Exception):
    pass


class Presence:
    """Polaczenie z klientem. Kazda metoda moze rzucic PresenceError - wolajacy
    ma to potraktowac jak 'Discord chwilowo nieobecny', a nie jak blad krytyczny."""

    def __init__(self, client_id, timeout=5.0):
        self.client_id = str(client_id)
        self.timeout = timeout
        self.sock = None
        self.last = None        # ostatnio wyslana aktywnosc: nie powtarzamy jej

    # ---------- warstwa gniazda ----------

    def _send(self, op, payload):
        data = json.dumps(payload).encode()
        try:
            self.sock.sendall(struct.pack("<II", op, len(data)) + data)
        except OSError as e:
            raise PresenceError("zerwane polaczenie z Discordem: %s" % e)

    def _recv(self):
        head = self._read_exactly(8)
        op, ln = struct.unpack("<II", head)
        return op, json.loads(self._read_exactly(ln) or b"{}")

    def _read_exactly(self, n):
        buf = b""
        while len(buf) < n:
            try:
                chunk = self.sock.recv(n - len(buf))
            except OSError as e:
                raise PresenceError("brak odpowiedzi od Discorda: %s" % e)
            if not chunk:
                raise PresenceError("Discord zamknal polaczenie")
            buf += chunk
        return buf

    # ---------- polaczenie ----------

    def connect(self):
        paths = socket_paths()
        if not paths:
            raise PresenceError("nie widze gniazda discord-ipc-* - czy klient Discorda chodzi?")
        err = None
        for p in paths:
            try:
                s = _open(p)
                s.settimeout(self.timeout)
                if not WINDOWS:
                    s.connect(str(p))
            except OSError as e:
                err = e
                continue
            self.sock = s
            self.last = None
            try:
                self._send(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
                op, msg = self._recv()
            except PresenceError:
                self.close()
                continue
            if op == OP_CLOSE:
                # Najczestsza przyczyna: zle Client ID (aplikacja nie istnieje).
                self.close()
                raise PresenceError("Discord odrzucil polaczenie: %s"
                                    % msg.get("message", msg))
            return self
        raise PresenceError("nie udalo sie polaczyc z klientem Discorda: %s" % err)

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.last = None

    # ---------- aktywnosc ----------

    def set(self, details=None, state=None, start=None, force=False, name=None):
        """Ustawia status. details/state to dwie linie pod naglowkiem, a name
        nadpisuje sam naglowek (domyslnie idzie tam nazwa aplikacji spod
        client_id; ikona zostaje jej niezaleznie od nadpisania).
        start (epoch) wlacza licznik 'elapsed'. Bez argumentow czysci status."""
        act = None
        if details or state or name:
            act = {}
            if name:
                act["name"] = _fit(name)
            if details:
                act["details"] = _fit(details)
            if state:
                act["state"] = _fit(state)
            if start:
                act["timestamps"] = {"start": int(start)}
        if act == self.last and not force:
            return
        if not self.sock:
            raise PresenceError("brak polaczenia")
        nonce = str(uuid.uuid4())
        self._send(OP_FRAME, {"cmd": "SET_ACTIVITY", "nonce": nonce,
                              "args": {"pid": os.getpid(), "activity": act}})
        while True:
            op, msg = self._recv()
            if op == OP_PING:
                self._send(OP_PONG, msg)
                continue
            if op == OP_CLOSE:
                self.close()
                raise PresenceError("Discord rozlaczyl: %s" % msg.get("message", msg))
            if msg.get("nonce") == nonce:
                if msg.get("evt") == "ERROR":
                    raise PresenceError("Discord odrzucil status: %s"
                                        % msg.get("data", {}).get("message", msg))
                self.last = act
                return
            # DISPATCH/READY i inne zdarzenia po drodze - czytamy dalej.

    def clear(self):
        self.set()


def _fit(s):
    # Discord wymaga 2-128 znakow; jednoznakowa nazwa gry inaczej poleci bledem.
    s = str(s).strip()
    if len(s) == 1:
        s += " "
    return s[:128]


class Keeper:
    """Opakowanie dla dlugiego watch: samo sie laczy, samo wstaje po tym, jak
    Discord zniknie i wroci. Nigdy nie rzuca - tylko zwraca, czy sie udalo."""

    def __init__(self, client_id, retry=20.0):
        self.client_id = client_id
        self.retry = retry
        self.p = None
        self.next_try = 0.0
        self.error = ""

    def _ensure(self):
        if self.p and self.p.sock:
            return True
        now = time.time()
        if now < self.next_try:
            return False
        self.next_try = now + self.retry
        try:
            self.p = Presence(self.client_id).connect()
            self.error = ""
            return True
        except PresenceError as e:
            self.p = None
            self.error = str(e)
            return False

    def set(self, details=None, state=None, start=None, name=None):
        for attempt in (1, 2):        # druga proba: po zerwanym gniezdzie
            if not self._ensure():
                return False
            try:
                self.p.set(details, state, start, name=name)
                return True
            except PresenceError as e:
                self.error = str(e)
                if self.p:
                    self.p.close()
                self.p = None
                self.next_try = 0.0 if attempt == 1 else time.time() + self.retry
        return False

    def clear(self):
        return self.set()

    def close(self):
        if self.p:
            try:
                self.p.clear()
            except PresenceError:
                pass
            self.p.close()
        self.p = None
