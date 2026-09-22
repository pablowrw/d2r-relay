# D2R Relay

[English](README.md) | **Polski**

Pokazuje na Discordzie nazwe gry Diablo II: Resurrected, w ktorej jestes: w
statusie na profilu albo jako wiadomosc na kanale.

- 🎮 Wykrywa kazda gre, do ktorej wejdziesz.
- 💬 Wysyla nazwe gry do statusu Discorda, na kanal albo w oba miejsca.
- 🖥️ Dziala na Windowsie 10/11 i Linuksie (X11).
- 🌐 Okno programu jest po polsku albo po angielsku.

## 🛡️ Bezpieczenstwo

- D2R Relay robi tylko zrzuty okna gry i rozpoznaje na nich tekst. Nie czyta
  pamieci gry, niczego nie wstrzykuje i nie zmienia plikow gry. Dla Battle.net
  to zwykly zrzut ekranu.
- Wszystko zostaje na Twoim komputerze. Na zewnatrz idzie tylko wiadomosc na
  kanal, i to tylko wtedy, gdy ja wlaczysz.

## 📥 Instalacja

### Windows

1. Pobierz **`D2R-Relay-setup.exe`** z
   [najnowszego wydania](https://github.com/pablowrw/d2r-relay/releases/latest).
2. Uruchom instalator. Uprawnienia administratora nie sa potrzebne. Instalator
   dodaje D2R Relay do menu Start, opcjonalnie na pulpit, i do listy
   zainstalowanych aplikacji.

Plik nie jest podpisany cyfrowo, wiec Windows SmartScreen moze pokazac
ostrzezenie. Kliknij **Wiecej informacji → Uruchom mimo to**.

Zeby uruchomic program bez instalacji, pobierz `D2R-Relay-windows.zip`,
rozpakuj go i uruchom `D2R-Relay.exe`.

W D2R ustaw tryb **Windowed (Fullscreen)** albo okno. W pelnym ekranie zrzut
moze wyjsc czarny.

### Linux (X11)

Potrzebne sa `maim`, `xdotool`, `libnotify` oraz pakiety Pythona
`pillow` i `numpy`. `pystray` jest opcjonalny i dodaje ikone w zasobniku. Na
Arch Linux:

    sudo pacman -S maim xdotool libnotify python-pillow python-numpy python-pystray
    git clone https://github.com/pablowrw/d2r-relay.git
    cd d2r-relay
    ./d2rgui.py

Zeby dodac skrot w menu aplikacji:

    sed "s|@DIR@|$PWD|g" d2r-relay.desktop > ~/.local/share/applications/d2r-relay.desktop

Wayland nie jest obslugiwany.

## 🗺️ Jak to dziala

D2R pokazuje nazwe gry w prawym gornym rogu ekranu **tylko przy otwartej
mapie** (Tab). D2R Relay odczytuje nazwe wlasnie stamtad, wiec po wejsciu do
gry otworz na chwile mape. Odczyt trwa zwykle kilka sekund.

## 🎯 Pierwsze uruchomienie

Zakladka **Kalibracja** prowadzi Cie krok po kroku. Wystarczy to zrobic raz dla
danej rozdzielczosci gry:

1. **Rozpoznawanie lobby.** Wejdz do lobby i potwierdzaj zrzuty przyciskiem na
   karcie.
2. **Nauka nazw gier.** D2R Relay podaje nazwe gry. Wtedy:
   1. zaloz gre o tej nazwie (przycisk **Kopiuj**, a w grze Ctrl+V),
   2. wejdz do niej, otworz mape i poczekaj na potwierdzenie,
   3. wyjdz z gry.

   Postep sie zapisuje, wiec mozesz przerwac i wrocic pozniej.

## ▶️ Uzycie

Przycisk **Start** wlacza odczyt. Przelaczniki pod nim decyduja, dokad trafia
nazwa gry: do statusu na profilu, na kanal albo w oba miejsca. Lista
**Historia** nizej pokazuje dotychczas odczytane gry.

Ustawienia zapisuja sie same. Obie zakladki Discorda pokazuja podglad tego, co
zobacza inni, i maja przycisk proby.

### 👤 Status na profilu

Nazwa gry pojawia sie w Twoim statusie Discorda, pod Twoim imieniem. Bot nie
jest potrzebny, wystarczy aplikacja Discord wlaczona na tym samym komputerze.
Mozesz wybrac, gdzie ma byc nazwa gry:

- w tytule statusu (zalecane, bo widac ja tez na liscie osob na serwerze),
- w opisie,
- we wlasnym ukladzie.

### 📢 Wiadomosci na kanal

1. Na Discordzie otworz ustawienia kanalu i wybierz **Integracje → Webhooki →
   Nowy webhook → Kopiuj adres webhooka**.
2. Wklej adres w zakladce **Wiadomosci na kanal** i kliknij **Wyprobuj na
   kanale**.

Mozesz ustawic tresc wiadomosci, nazwe nadawcy i awatar.

- Wiadomosci nikogo nie pinguja.
- Ta sama gra nie jest wysylana ponownie przez ustawiony czas (domyslnie 90 s).
- Adres webhooka jest zapisany tylko na Twoim komputerze. Traktuj go jak haslo,
  bo kazdy, kto go ma, moze pisac na kanal.

### ⚙️ Ogolne

Tutaj ustawisz:

- jezyk okna,
- uruchamianie razem z systemem,
- wlaczanie odczytu od razu po starcie,
- chowanie okna do zasobnika zamiast zamykania.

Naraz dziala tylko jedna kopia D2R Relay. Ponowne uruchomienie pokazuje okno
kopii, ktora juz dziala.

## ⚠️ Ograniczenia

- Okno gry musi byc aktywne. Zaslonietego okna nie da sie odczytac, wiec
  zostaje ostatnia odczytana nazwa.
- Przy oknie 720p i mniejszym odczyt moze byc zawodny.
- Status na profilu widac tylko wtedy, gdy Discord jest wlaczony. Znika po
  zatrzymaniu odczytu.

## 🔧 Budowanie ze zrodel (Windows)

Potrzebujesz:

- Pythona 3.10.1 lub nowszego z python.org, zainstalowanego z opcjami "Add
  python.exe to PATH" i "tcl/tk and IDLE",
- Inno Setup.

Nastepnie uruchom:

    winget install JRSoftware.InnoSetup
    git clone https://github.com/pablowrw/d2r-relay.git
    cd d2r-relay
    windows\build.bat

Wynik trafia do katalogu `dist`: `D2R-Relay-setup.exe`,
`D2R-Relay-windows.zip` i folder `D2R-Relay`. Wydania na GitHubie buduje
workflow `.github/workflows/release.yml` po wypchnieciu tagu `v*`.

## 📁 Ustawienia i dane

| System | Ustawienia | Dane |
| --- | --- | --- |
| Windows | `%APPDATA%\d2r-relay` | `%LOCALAPPDATA%\d2r-relay` |
| Linux | `~/.config/d2r-relay` | `~/.local/share/d2r-relay` |

Deinstalacja zostawia te katalogi. Zeby usunac tez ustawienia, skasuj je
recznie.

## 📄 Licencja

[MIT](LICENSE)
