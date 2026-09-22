"""
i18n - jezyk okna: polski (zrodlowy) albo angielski.

Teksty w kodzie GUI sa po polsku i ida przez T(); slownik EN tlumaczy je 1:1,
wzorce z %s tlumaczy sie przed wstawieniem wartosci: T("Gra %s") % n.
Brak wpisu = tekst polski - lepszy niz pusty, a latwo go wylapac.

Jezyk czytany raz, przy starcie; zmiana dziala po ponownym uruchomieniu.
Linie CLI czytnika zostaja po polsku - GUI je rozpoznaje i tlumaczy u siebie.
"""
import locale
import os
import re

import d2rread

LANGS = (("pl", "Polski"), ("en", "English"))


def detect():
    """Wybor z configu; bez niego: stary config = polski (tak bylo dotad),
    nowa instalacja = jezyk systemu (polski albo angielski)."""
    lang = d2rread.load_config().get("language")
    if lang in dict(LANGS):
        return lang
    if d2rread.CONFIG.exists():
        return "pl"
    # Linux: zmienne srodowiska (locale procesu bywa C, gdy pl_PL nie jest
    # wygenerowane); Windows: ustawienia regionalne, np. 'Polish_Poland'
    sys_lang = next((os.environ[v] for v in ("LC_ALL", "LC_MESSAGES", "LANG")
                     if os.environ.get(v)), "")
    if not sys_lang:
        try:
            sys_lang = locale.getlocale()[0] or ""
        except ValueError:
            pass
    return "pl" if sys_lang.lower().startswith(("pl", "polish")) else "en"


LANG = detect()


def T(text):
    return EN.get(text, text) if LANG == "en" else text


# Domyslne teksty ustawien w obu jezykach. Wartosc rowna domyslnej z drugiego
# jezyka jest podmieniana przy starcie - wlasny tekst uzytkownika zostaje.
TEXT_DEFAULTS = {
    "presence_details_std": {"pl": "Gra: {name}", "en": "Game: {name}"},
    "discord_template": {"pl": "Gra: **{name}**", "en": "Game: **{name}**"},
}


def text_default(key):
    return TEXT_DEFAULTS[key][LANG]


def localize_defaults(cfg):
    """Zamienia domyslne teksty z drugiego jezyka na biezacy. True = cos zmienil."""
    changed = False
    for key, cfg_key in (("presence_details_std", "presence_details"),
                         ("discord_template", "discord_template")):
        vals = TEXT_DEFAULTS[key]
        if cfg.get(cfg_key) in vals.values() and cfg[cfg_key] != vals[LANG]:
            cfg[cfg_key] = vals[LANG]
            changed = True
    return changed


def TR(msg):
    """Jak T, ale dla gotowego tekstu z wstawionymi wartosciami (bledy z
    webhook.py, linie czytnika): dopasowuje wzorce z %s/%d."""
    if LANG != "en" or not msg:
        return msg
    if msg in EN:
        return EN[msg]
    for pl, en in EN.items():
        if "%" not in pl:
            continue
        rx = "^" + re.escape(pl).replace("%s", "(.*?)").replace("%d", "(\\d+)") + "$"
        m = re.match(rx, msg, re.S)
        if m:
            return en.replace("%d", "%s") % m.groups()
    return msg


EN = {
    # --- naglowek ---
    "Pokazuj status na moim profilu": "Show status on my profile",
    "Wysylaj wiadomosc na kanal": "Post a message to a channel",
    "Zmiana zadziala po Stop i Start": "The change takes effect after Stop and Start",
    "Zmiany zadzialaja po Stop i Start": "Changes take effect after Stop and Start",
    "Wlaczony": "Running",
    "Wylaczony": "Stopped",
    "Oczekiwanie na wejscie do gry": "Waiting for you to join a game",
    "Kliknij Start, aby rozpoczac": "Click Start to begin",
    "Niedostepne podczas odczytu": "Unavailable while reading",
    "D2R Relay - odczyt wlaczony": "D2R Relay - reading on",
    "D2R Relay - odczyt wylaczony": "D2R Relay - reading off",
    "Start": "Start",
    "Stop": "Stop",
    # --- zakladki ---
    "Status na profilu": "Profile status",
    "Wiadomosci na kanal": "Channel messages",
    "Kalibracja": "Calibration",
    "Ogolne": "General",
    "Historia": "History",
    "Podglad": "Preview",
    # --- status na profilu ---
    "Lista uzytkownikow": "Member list",
    "Profil": "Profile",
    "Ty": "You",
    "Gra": "Game",
    "Tytul statusu": "Status title",
    "Nazwa gry (zalecane)": "Game name (recommended)",
    "Standardowy": "Standard",
    "Wlasny": "Custom",
    "Wyglad": "Appearance",
    "Nazwa gry duzymi literami": "Game name in capitals",
    "Tytul": "Title",
    "{name} wstawia nazwe gry. Puste - tytul z Application ID.":
        "{name} inserts the game name. Empty - title from the Application ID.",
    "Opis": "Details",
    "{name} wstawia nazwe gry. Puste - bez opisu.":
        "{name} inserts the game name. Empty - no details.",
    "W lobby": "In lobby",
    "Pokazywane zamiast nazwy gry, gdy jestes w lobby.":
        "Shown instead of the game name while you are in the lobby.",
    "Skad Discord bierze ikone i tytul. Domyslnie oficjalny wpis gry.":
        "Where Discord takes the icon and title from. Default: the official game entry.",
    "Przywroc oficjalne ID": "Restore official ID",
    "Tytul: nazwa gry. Opis: %s.": "Title: game name. Details: %s.",
    "Tytul: %s. Opis: nazwa gry.": "Title: %s. Details: game name.",
    "Wyprobuj na profilu": "Try on profile",
    "Zakoncz test (%d s)": "End test (%d s)",
    "Status testowy jest na Twoim profilu": "The test status is on your profile",
    # --- kanal ---
    "Wyprobuj na kanale": "Try in channel",
    "nazwa webhooka": "webhook name",
    "APL.": "APP",
    "Adres webhooka": "Webhook URL",
    "Edytuj kanal > Integracje > Webhooki > Kopiuj adres URL webhooka.\n"
    "Adres jest zapisywany tylko na tym komputerze.":
        "Edit Channel > Integrations > Webhooks > Copy Webhook URL.\n"
        "The URL is stored only on this computer.",
    "Nazwa nadawcy": "Sender name",
    "Puste - nazwa ustawiona przy webhooku.": "Empty - the name set on the webhook.",
    "Tresc": "Message",
    "{name} - nazwa gry, {time} - godzina, **tekst** - pogrubienie.":
        "{name} - game name, {time} - time, **text** - bold.",
    "Awatar": "Avatar",
    "Adres URL obrazka. Puste - awatar webhooka.": "Image URL. Empty - the webhook avatar.",
    "Blokada powtorzen": "Repeat block",
    "Sekundy, przez ktore ta sama gra nie zostanie wyslana ponownie.":
        "Seconds during which the same game will not be posted again.",
    "Przywroc domyslne": "Restore defaults",
    "Uzupelnij adres webhooka": "Enter the webhook URL",
    "Wiadomosc testowa wyslana": "Test message sent",
    "Nie udalo sie wyslac: %s": "Could not send: %s",
    "Blokada powtorzen: podaj liczbe sekund": "Repeat block: enter a number of seconds",
    "Nazwa nadawcy nie moze zawierac slow discord ani clyde":
        "The sender name cannot contain the words discord or clyde",
    # bledy z webhook.py
    "adres webhooka musi zaczynac sie od https://": "the webhook URL must start with https://",
    "to nie wyglada na adres webhooka (brak /api/webhooks/)":
        "this does not look like a webhook URL (no /api/webhooks/)",
    "brak zapisanego webhooka": "no webhook saved",
    "webhook odrzucony (%d) - skasowany albo zly adres":
        "webhook rejected (%d) - deleted or wrong URL",
    "brak polaczenia: %s": "no connection: %s",
    "nie udalo sie wyslac po %d probach": "could not send after %d attempts",
    # --- kalibracja ---
    "Rozpoznawanie lobby": "Lobby recognition",
    "Nauka nazw gier": "Learning game names",
    "Krok %d": "Step %d",
    "Zrob zrzut": "Take screenshot",
    "Kopiuj": "Copy",
    "Skopiowano": "Copied",
    "Gotowe": "Done",
    "Do zrobienia": "To do",
    "Gotowe (%s)": "Done (%s)",
    "%d z %d znakow": "%d of %d characters",
    "Przerwij": "Cancel",
    "Powtorz": "Repeat",
    "Kontynuuj": "Continue",
    "Rozpocznij": "Begin",
    "Zacznij od rozpoznania lobby": "Start with lobby recognition",
    "Wlacz gre i przejdz do lobby, potem kliknij Rozpocznij przy kroku 1.":
        "Launch the game and go to the lobby, then click Begin next to step 1.",
    "Teraz nauka nazw gier": "Next: learning game names",
    "Zalozysz kilka gier o podanych nazwach. Postep zapisuje sie po kazdej grze.":
        "You will create a few games with the given names. Progress is saved after each game.",
    "Wszystko gotowe": "All set",
    "Kliknij Start na gorze okna.": "Click Start at the top of the window.",
    "Najpierw zatrzymaj odczyt (Stop na gorze)": "Stop reading first (Stop at the top)",
    "Nauka nazw gier - cala seria": "Learning game names - full series",
    "Wejdz do lobby": "Go to the lobby",
    "Na ekran z zakladkami Create / Join.": "The screen with the Create / Join tabs.",
    "Start rozpoznawania lobby": "Lobby recognition started",
    "Program zapamieta, jak wyglada lobby na Twoim ekranie.":
        "The program will remember how the lobby looks on your screen.",
    "Nastepnie kliknij Zrob zrzut i wroc do okna gry.":
        "Then click Take screenshot and switch back to the game window.",
    "Zrzut zostanie wykonany, gdy okno gry bedzie na wierzchu.":
        "The screenshot will be taken when the game window is in front.",
    "Wroc do okna gry": "Switch back to the game window",
    "Nauka przerwana - dotychczasowy postep zostal zapisany":
        "Learning cancelled - progress so far has been saved",
    "Rozpoznawanie lobby przerwane": "Lobby recognition cancelled",
    "Przerwane": "Cancelled",
    "Postep zostal zapisany - mozesz kontynuowac w dowolnej chwili.":
        "Progress has been saved - you can continue at any time.",
    "Nauka przerwana bledem": "Learning stopped with an error",
    "Otworz w grze lobby na zakladce Create Game": "Open the lobby on the Create Game tab",
    "Przelacz lobby na zakladke Join Game": "Switch the lobby to the Join Game tab",
    "Rozpoznawanie lobby - ekran %s z %s": "Lobby recognition - screen %s of %s",
    "Ekran %s z %s: %s": "Screen %s of %s: %s",
    "Lobby zapamietane": "Lobby saved",
    "Nie wykryto zmiany zakladki - powtorz ten ekran":
        "No tab change detected - repeat this screen",
    "Nie wykryto lobby na ekranie - powtorz ten ekran":
        "Lobby not detected on screen - repeat this screen",
    "Nie udalo sie rozpoznac lobby": "Could not recognise the lobby",
    "Upewnij sie, ze w grze jest lobby z zakladkami Create / Join, i kliknij Rozpocznij "
    "przy kroku 1.":
        "Make sure the game shows the lobby with the Create / Join tabs, and click Begin "
        "next to step 1.",
    "Nowa rozdzielczosc%s - nauka liter od poczatku":
        "New resolution%s - learning letters from scratch",
    "Lobby rozpoznaje sie tez w grze - po nauce powtorz krok 1":
        "The lobby is also detected in game - repeat step 1 after learning",
    "Lobby rozpoznane": "Lobby recognised",
    "Gra %s": "Game %s",
    "Wpis %s": "Entry %s",
    " z %s": " of %s",
    "Zaloz gre o tej nazwie i wejdz do niej": "Create a game with this name and join it",
    "Wielkosc liter ma znaczenie.": "Letter case matters.",
    "Wpisz w pole Game Name": "Type it into the Game Name field",
    "Nie zakladaj gry - wystarczy sam wpis.": "Do not create the game - typing it is enough.",
    "Wroc do lobby": "Go back to the lobby",
    "Oczekiwanie na wejscie do gry...": "Waiting for you to join the game...",
    "Wyczysc pole Game Name": "Clear the Game Name field",
    "Ctrl+A, potem Backspace.": "Ctrl+A, then Backspace.",
    "Wyjdz z gry": "Leave the game",
    "Save and Exit, potem wroc do lobby.": "Save and Exit, then go back to the lobby.",
    "%s - zaliczona": "%s - passed",
    "%s - zaliczona, odczyt jeszcze niepewny": "%s - passed, reading not yet reliable",
    "Pominieta %s - znaki juz znane": "Skipped %s - characters already known",
    "Dodatkowa gra dla znakow: %s": "Extra game for characters: %s",
    "Wykryto %s znakow zamiast %s - popraw wpis":
        "Detected %s characters instead of %s - correct the entry",
    "Nie znaleziono okna gry": "Game window not found",
    "Wlacz Diablo II: Resurrected i sprobuj ponownie.":
        "Launch Diablo II: Resurrected and try again.",
    "Nauka zakonczona - program zna %d z %d znakow":
        "Learning finished - the program knows %d of %d characters",
    "Nauka zakonczona": "Learning finished",
    "%s - nie widac calej nazwy. Sprawdz, czy gra przyjela ja w calosci.":
        "%s - the full name is not visible. Check that the game accepted all of it.",
    "Nie udalo sie nauczyc znakow: %s - jesli gra nie przyjmuje ich w nazwie, mozna to "
    "pominac":
        "Could not learn characters: %s - if the game does not accept them in names, "
        "this can be ignored",
    # --- dziennik czytnika ---
    "Najpierw dokoncz albo przerwij kalibracje (zakladka Kalibracja)":
        "Finish or cancel calibration first (Calibration tab)",
    "Brak adresu webhooka - uzupelnij go w zakladce Wiadomosci na kanal":
        "No webhook URL - enter it in the Channel messages tab",
    "status na profilu": "profile status",
    "wiadomosci na kanal": "channel messages",
    "Wlaczono": "Started",
    "Wylaczono": "Stopped",
    "Odczyt sam sie wylaczyl": "Reading stopped unexpectedly",
    "Lobby": "Lobby",
    "Gra: %s": "Game: %s",
    "Nowa gra: %s": "New game: %s",
    "Powrot do lobby": "Back to the lobby",
    "Gra ma inna rozdzielczosc%s - powtorz krok 2 w zakladce Kalibracja":
        "The game uses a different resolution%s - repeat step 2 in the Calibration tab",
    "Lobby nierozpoznane - wykonaj krok 1 w zakladce Kalibracja":
        "Lobby not recognised - complete step 1 in the Calibration tab",
    "Nie udalo sie ustawic statusu: %s": "Could not set the status: %s",
    "Nie udalo sie wyslac na kanal: %s": "Could not post to the channel: %s",
    "Nie udalo sie odczytac ekranu: %s": "Could not read the screen: %s",
    "Program nie zna jeszcze czcionki gry - wykonaj krok 2 w zakladce Kalibracja":
        "The program does not know the game font yet - complete step 2 in the Calibration tab",
    "Brak Application ID - wybierz tryb albo wpisz ID w zakladce Status na profilu":
        "No Application ID - pick a mode or enter an ID in the Profile status tab",
    "Brak adresu webhooka - wklej go w zakladce Wiadomosci na kanal":
        "No webhook URL - paste it in the Channel messages tab",
    "Status testowy ustawiony - zerknij na swoj profil":
        "Test status set - take a look at your profile",
    "Status testowy zdjety": "Test status removed",
    "Status testowy nie wyszedl: %s": "Test status failed: %s",
    # --- ogolne ---
    "Jezyk": "Language",
    "Jezyk zmieni sie po ponownym uruchomieniu programu.":
        "The language changes after the program is restarted.",
    "Uruchom ponownie": "Restart now",
    "Uruchamianie": "Startup",
    "Uruchamiaj razem z systemem": "Start with the system",
    "Wlaczaj odczyt po uruchomieniu programu": "Start reading when the program opens",
    "Zasobnik systemowy": "System tray",
    "Zamykanie i minimalizacja chowaja okno do zasobnika":
        "Closing and minimising hide the window to the tray",
    "Program dziala dalej w tle. Menu ikony: Pokaz okno, Start/Stop, Zakoncz.":
        "The program keeps running in the background. Icon menu: Show window, Start/Stop, Quit.",
    "Wymaga pakietu pystray. Zainstaluj go w terminalu i uruchom program ponownie:":
        "Requires the pystray package. Install it in a terminal and restart the program:",
    "Nie udalo sie zmienic autostartu: %s": "Could not change autostart: %s",
    "Nie udalo sie dodac ikony do zasobnika: %s": "Could not add the tray icon: %s",
    "Pokaz okno": "Show window",
    "Zakoncz": "Quit",
    "Niezapisane zmiany": "Unsaved changes",
    "Czesci ustawien nie da sie zapisac (komunikat na dole okna). Zamknac mimo to?":
        "Some settings cannot be saved (see the message at the bottom). Close anyway?",
}
