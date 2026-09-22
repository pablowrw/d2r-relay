# D2R Relay

**English** | [Polski](README.pl.md)

Shows the name of the Diablo II: Resurrected game you are in on Discord, either
in your profile status or as a message in a channel.

- 🎮 Detects every game you join.
- 💬 Sends the game name to your Discord status, a channel, or both.
- 🖥️ Runs on Windows 10/11 and Linux (X11).
- 🌐 The interface is available in English and Polish.

## 🛡️ Safety

- D2R Relay only takes screenshots of the game window and recognises text on
  them. It does not read game memory, inject anything or modify game files. To
  Battle.net it is an ordinary screenshot.
- Everything stays on your computer. The only thing sent out is the channel
  message, and only if you turn it on.

## 📥 Installation

### Windows

1. Download **`D2R-Relay-setup.exe`** from the
   [latest release](https://github.com/pablowrw/d2r-relay/releases/latest).
2. Run the installer. No administrator rights are needed. The installer adds
   D2R Relay to the Start menu, optionally to the desktop, and to the list of
   installed apps.

The file is not digitally signed, so Windows SmartScreen may show a warning.
Click **More info → Run anyway**.

To run without installing, download `D2R-Relay-windows.zip`, extract it and run
`D2R-Relay.exe`.

In D2R, use **Windowed (Fullscreen)** or windowed mode. In exclusive fullscreen
the screenshot may come out black.

### Linux (X11)

You need `maim`, `xdotool`, `libnotify` and the Python packages
`pillow` and `numpy`. `pystray` is optional and adds a tray icon. On Arch Linux:

    sudo pacman -S maim xdotool libnotify python-pillow python-numpy python-pystray
    git clone https://github.com/pablowrw/d2r-relay.git
    cd d2r-relay
    ./d2rgui.py

To add an application menu entry:

    sed "s|@DIR@|$PWD|g" d2r-relay.desktop > ~/.local/share/applications/d2r-relay.desktop

Wayland is not supported.

## 🗺️ How it works

D2R shows the game name in the top-right corner of the screen **only while the
map is open** (Tab). D2R Relay reads the name from there, so open the map for a
moment after joining a game. The name is usually read within a few seconds.

## 🎯 First run

The **Calibration** tab walks you through setup. You need to do it once per
game resolution:

**Step 1: Lobby recognition**

1. Go to the lobby.
2. Confirm the screenshots with the button on the card.

**Step 2: Learning game names**

1. D2R Relay gives you a game name. Click **Copy**.
2. Create a game with that name (Ctrl+V in the game).
3. Join the game, open the map and wait for the confirmation.
4. Leave the game. D2R Relay gives you the next name.

Progress is saved, so you can stop and continue later.

## ▶️ Usage

The **Start** button turns reading on. The switches below it choose where the
game name goes: your profile status, a channel, or both. The **History** list
below shows the games read so far.

Settings save automatically. Both Discord tabs show a preview of what others
will see and have a test button.

### 👤 Profile status

The game name appears in your Discord status, under your name. No bot is
needed, only the Discord app running on the same computer. You can choose where
the game name appears:

- in the status title (recommended, because it also shows in the server member
  list),
- in the details line,
- in a custom layout.

### 📢 Channel messages

1. In Discord, open the channel settings and go to **Integrations → Webhooks →
   New Webhook → Copy Webhook URL**.
2. Paste the URL in the **Channel messages** tab and click **Try in channel**.

You can set the message text, sender name and avatar.

- Messages do not ping anyone.
- The same game is not sent again within a set time (90 s by default).
- The webhook URL is stored only on your computer. Treat it like a password,
  because anyone who has it can post in the channel.

### ⚙️ General

Here you can set:

- the interface language,
- starting with the system,
- turning reading on right after start,
- hiding to the tray instead of closing.

Only one copy of D2R Relay runs at a time. Launching it again brings up the
window of the running copy.

## ⚠️ Limitations

- The game window must be active. A covered window cannot be read, so the last
  name read stays.
- With the window at 720p or smaller, reading can be unreliable.
- The profile status is visible only while Discord is running. It disappears
  when reading stops.

## 🔧 Building from source (Windows)

You need:

- Python 3.10.1 or newer from python.org, installed with "Add python.exe to
  PATH" and "tcl/tk and IDLE",
- Inno Setup.

Then run:

    winget install JRSoftware.InnoSetup
    git clone https://github.com/pablowrw/d2r-relay.git
    cd d2r-relay
    windows\build.bat

The results go to `dist`: `D2R-Relay-setup.exe`, `D2R-Relay-windows.zip` and
the `D2R-Relay` folder. GitHub releases are built by
`.github/workflows/release.yml` when a `v*` tag is pushed.

## 📁 Settings and data

| System | Settings | Data |
| --- | --- | --- |
| Windows | `%APPDATA%\d2r-relay` | `%LOCALAPPDATA%\d2r-relay` |
| Linux | `~/.config/d2r-relay` | `~/.local/share/d2r-relay` |

Uninstalling keeps these folders. To remove your settings as well, delete them
manually.

## 📄 License

[MIT](LICENSE)
