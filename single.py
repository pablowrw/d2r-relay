"""
single - tylko jedna kopia programu naraz.

Blokada: na Windowsie nazwany mutex (ten sam sprawdza instalator - AppMutex,
zeby nie nadpisywal dzialajacego exe), na Linuksie flock na pliku. Druga kopia
laczy sie z pierwsza przez gniazdo na 127.0.0.1 (port w pliku obok), prosi
o pokazanie okna i konczy sie. Tylko petla zwrotna, wiec zapora nie pyta.
"""
import os
import socket
import sys
import threading

import platformdirs_lite as dirs

WINDOWS = sys.platform == "win32"
MUTEX = "d2r-relay-instance"
HELLO = b"d2r-relay\n"


class Instance:
    def __init__(self):
        self.dir = dirs.data_dir()
        self.port_file = self.dir / "instance.port"
        self._lock = None
        self._srv = None

    def acquire(self):
        """True - jestesmy jedyna kopia; False - inna juz dziala."""
        self.dir.mkdir(parents=True, exist_ok=True)
        if WINDOWS:
            import ctypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.restype = ctypes.c_void_p
            h = k32.CreateMutexW(None, False, MUTEX)
            if ctypes.get_last_error() == 183:          # ERROR_ALREADY_EXISTS
                k32.CloseHandle(ctypes.c_void_p(h))
                return False
            self._lock = h
            return True
        import fcntl
        f = open(self.dir / "instance.lock", "w")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return False
        self._lock = f
        return True

    def notify(self, cmd="show"):
        """Druga kopia: popros pierwsza o pokazanie okna."""
        if WINDOWS:
            try:            # oddajemy prawo wyciagniecia okna na wierzch
                import ctypes
                ctypes.windll.user32.AllowSetForegroundWindow(-1)   # ASFW_ANY
            except (OSError, AttributeError):
                pass
        try:
            port = int(self.port_file.read_text(encoding="utf-8"))
            with socket.create_connection(("127.0.0.1", port), timeout=2) as s:
                s.sendall(cmd.encode() + b"\n")
                return s.recv(64) == HELLO
        except (OSError, ValueError):
            return False

    def serve(self, on_show):
        """Pierwsza kopia: nasluch prosb od kolejnych uruchomien."""
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.bind(("127.0.0.1", 0))
            srv.listen(4)
            self.port_file.write_text(str(srv.getsockname()[1]), encoding="utf-8")
        except OSError:
            return                  # bez nasluchu blokada i tak dziala
        self._srv = srv

        def loop():
            while True:
                try:
                    conn, _ = srv.accept()
                except OSError:
                    return          # gniazdo zamkniete - koniec
                with conn:
                    try:
                        conn.settimeout(2)
                        cmd = conn.recv(64).strip()
                        conn.sendall(HELLO)
                    except OSError:
                        continue
                if cmd == b"show":
                    on_show()
        threading.Thread(target=loop, daemon=True).start()

    def release(self):
        """Zwolnienie przed ponownym uruchomieniem (zmiana jezyka)."""
        if self._srv:
            try:
                self._srv.shutdown(socket.SHUT_RDWR)    # budzi accept() w watku
            except OSError:
                pass
            try:
                self._srv.close()
            except OSError:
                pass
            self._srv = None
        if self._lock is None:
            return
        if WINDOWS:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self._lock))
        else:
            self._lock.close()
        self._lock = None
