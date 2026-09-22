# D2R Relay

Przekazuje nazwe gry Diablo II: Resurrected, w ktorej wlasnie jestes, na
Discorda: do statusu na Twoim profilu albo jako wiadomosc na kanale, np. zeby
znajomi mogli od razu dolaczyc.

- Program sam wykrywa wejscie do gry, Twojej albo cudzej.
- Nazwa gry pokazuje sie w statusie Discorda, na kanale albo w obu miejscach naraz, i trafia tez do schowka.
- Dziala na Windowsie 10/11 i Linuksie (X11).
- Okno programu jest po polsku albo po angielsku.

## Bezpieczenstwo

- Program **tylko robi zrzut okna gry** i rozpoznaje na nim tekst. Nie czyta
  pamieci gry, niczego nie wstrzykuje i nie zmienia plikow gry. Dla Battle.net
  to zwykly zrzut ekranu.
- **Hasla gry nie odczytuje.** Linia `Password:` jest pomijana.
- Wszystko zostaje na Twoim komputerze. Na zewnatrz idzie tylko wiadomosc na
  kanal, jesli ja wlaczysz.
- Nie pisze z Twojego konta Discord. Wiadomosci wysyla webhook kanalu, bo
  automatyczne wiadomosci z konta uzytkownika lamia regulamin Discorda.

## Instalacja

### Windows

1. Pobierz **`D2R-Relay-setup.exe`** z
   [najnowszego wydania](https://github.com/pablowrw/d2r-relay/releases/latest).
2. Uruchom instalator. Uprawnienia administratora nie sa potrzebne. Program
   pojawi sie w menu Start (opcjonalnie tez na pulpicie) i na liscie aplikacji
   do odinstalowania.

Plik nie jest podpisany cyfrowo, wiec Windows SmartScreen moze pokazac
ostrzezenie. Wybierz wtedy **Wiecej informacji -> Uruchom mimo to**.

Wersja bez instalacji: pobierz `D2R-Relay-windows.zip`, rozpakuj go i uruchom
`D2R-Relay.exe`.

W D2R ustaw tryb **Windowed (Fullscreen)** albo okno. W pelnym ekranie zrzut
bywa czarny.

### Linux (X11)

Potrzebne sa `maim`, `xdotool`, `xclip` i `libnotify` oraz pakiety Pythona
`pillow` i `numpy`. Pakiet `pystray` jest opcjonalny i daje ikone w zasobniku.
Przyklad dla Arch Linux:

    sudo pacman -S maim xdotool xclip libnotify python-pillow python-numpy python-pystray
    git clone https://github.com/pablowrw/d2r-relay.git
    cd d2r-relay
    ./d2rgui.py

Skrot w menu aplikacji:

    sed "s|@DIR@|$PWD|g" d2r-relay.desktop > ~/.local/share/applications/d2r-relay.desktop

Wayland nie jest obslugiwany.

## Pierwsze uruchomienie

Zakladka **Kalibracja** prowadzi krok po kroku. Wystarczy to zrobic raz dla
danej rozdzielczosci:

1. **Rozpoznawanie lobby.** Wejdz do lobby i potwierdzaj zrzuty przyciskiem na
   karcie.
2. **Nauka nazw gier.** Program podaje nazwe gry, a Ty:
   1. zakladasz gre o tej nazwie (przycisk **Kopiuj**, w grze Ctrl+V),
   2. wchodzisz do niej i czekasz na potwierdzenie,
   3. wychodzisz.

   Postep sie zapisuje, wiec mozesz przerwac i wrocic pozniej.

## Uzycie

Przycisk **Start** wlacza odczyt. Przelaczniki pod nim decyduja, dokad trafia
nazwa gry: do statusu na profilu, na kanal albo w oba miejsca. Nizej widac
historie odczytanych gier.

Ustawienia zapisuja sie same. Obie zakladki Discorda maja podglad tego, co
zobacza inni, i przycisk proby.

### Status na profilu

Nazwa gry pokazuje sie w Twoim statusie Discorda, pod Twoim imieniem. Nie
trzeba zakladac bota, wystarczy wlaczony Discord na tym samym komputerze. Do
wyboru jest miejsce nazwy gry:

- w tytule statusu (zalecane, bo wtedy widac ja na liscie osob na serwerze),
- w opisie,
- we wlasnym ukladzie.

### Wiadomosci na kanal

1. Na kanale Discorda wybierz **Edytuj kanal -> Integracje -> Webhooki -> Nowy
   webhook -> Kopiuj adres webhooka**.
2. Wklej adres w zakladce **Wiadomosci na kanal** i kliknij **Wyprobuj na
   kanale**.

Mozesz ustawic tresc wiadomosci, nazwe nadawcy i awatar.

- Wiadomosci nikogo nie pinguja.
- Ta sama gra nie jest wysylana ponownie przez ustawiony czas (domyslnie 90 s).
- Adres webhooka jest zapisany tylko na Twoim komputerze. Traktuj go jak haslo:
  kto go ma, moze pisac na kanal.

### Ogolne

W tej zakladce ustawisz:

- jezyk okna,
- uruchamianie razem z systemem,
- wlaczanie odczytu od razu po starcie,
- chowanie okna do zasobnika zamiast zamykania.

Naraz dziala tylko jedna kopia programu. Ponowne uruchomienie pokazuje okno juz
dzialajacej kopii.

## Ograniczenia

- Okno gry musi byc aktywne. Zasloniete okno nie da sie odczytac, wtedy
  zostaje ostatnia odczytana nazwa.
- Nazwa gry jest w rogu ekranu tylko przez chwile po wejsciu do gry. Program
  lapie ja zwykle w kilka sekund.
- Przy oknie 720p i mniejszym odczyt bywa zawodny.
- Status na profilu widac tylko wtedy, gdy Discord jest wlaczony. Znika po
  zatrzymaniu odczytu.

## Budowanie ze zrodel (Windows)

Potrzebny jest Python 3.10.1 lub nowszy z python.org, zainstalowany z opcjami
"Add python.exe to PATH" i "tcl/tk and IDLE", oraz Inno Setup:

    winget install JRSoftware.InnoSetup
    git clone https://github.com/pablowrw/d2r-relay.git
    cd d2r-relay
    windows\build.bat

Wynik trafia do katalogu `dist`: `D2R-Relay-setup.exe`,
`D2R-Relay-windows.zip` i folder `D2R-Relay`. Wydania na GitHubie buduje
workflow `.github/workflows/release.yml` po wypchnieciu tagu `v*`.

## Ustawienia i dane

| System | Ustawienia | Dane |
| --- | --- | --- |
| Windows | `%APPDATA%\d2r-relay` | `%LOCALAPPDATA%\d2r-relay` |
| Linux | `~/.config/d2r-relay` | `~/.local/share/d2r-relay` |

Deinstalacja zostawia te katalogi. Jesli chcesz usunac tez ustawienia, skasuj
je recznie.
