@echo off
rem Buduje dist\D2R-Relay\D2R-Relay.exe. Wymaga Pythona 3.10.1+ z python.org
rem (zaznacz "Add python.exe to PATH" albo uzyj launchera py).
setlocal
cd /d "%~dp0\.."
rem dzialajacy exe z dist trzyma swoje pliki - PyInstaller nie nadpisze folderu
tasklist /fi "imagename eq D2R-Relay.exe" 2>nul | find /i "D2R-Relay.exe" >nul && goto :running
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist .venv-build %PY% -m venv .venv-build || goto :err
rem 3.10.0 ma blad w module dis - PyInstaller konczy sie IndexError: tuple index out of range
.venv-build\Scripts\python -c "import sys; sys.exit(sys.version_info < (3, 10, 1))" || goto :oldpy
rem bez tkinter PyInstaller buduje exe bez okna (No module named 'tkinter')
.venv-build\Scripts\python -c "import tkinter; tkinter.Tcl()" 2>nul || goto :notk
.venv-build\Scripts\python -m pip install --upgrade pip || goto :err
.venv-build\Scripts\python -m pip install -r windows\requirements.txt || goto :err
.venv-build\Scripts\pyinstaller --noconfirm --distpath dist --workpath build windows\d2r-relay.spec || goto :err
rem PyInstaller po cichu pomija tkinter, gdy uzna Tcl/Tk za zepsute
if not exist dist\D2R-Relay\_internal\_tkinter.pyd goto :notkexe
powershell -NoProfile -Command "Compress-Archive -Force dist\D2R-Relay dist\D2R-Relay-windows.zip"
echo.
echo Gotowe: dist\D2R-Relay\D2R-Relay.exe  (paczka: dist\D2R-Relay-windows.zip)
rem instalator (skroty w menu Start i na pulpicie, deinstalacja) - gdy jest Inno Setup
set ISCC=
rem PATH, potem kazda wersja Inno Setup w typowych miejscach (winget, instalator)
for /f "delims=" %%p in ('where iscc 2^>nul') do set ISCC="%%p"
for /d %%d in ("%ProgramFiles(x86)%\Inno Setup*" "%ProgramFiles%\Inno Setup*" "%LOCALAPPDATA%\Programs\Inno Setup*") do if exist "%%~d\ISCC.exe" set ISCC="%%~d\ISCC.exe"
if not defined ISCC goto :noinno
rem ISCC_DEFS - np. /DAppVersion=1.2.0 (ustawia workflow wydania)
%ISCC% /Q %ISCC_DEFS% windows\installer.iss || goto :err
echo.
echo Instalator: dist\D2R-Relay-setup.exe  - uruchom go, zeby dodac skroty
exit /b 0
:noinno
echo.
echo UWAGA: instalator pominiety - nie znaleziono Inno Setup (ISCC.exe).
echo Bez instalatora nie ma skrotow w menu Start. Zeby go miec:
echo   winget install JRSoftware.InnoSetup
echo a potem build.bat jeszcze raz.
exit /b 0
:oldpy
echo Python 3.10.0 ma blad, przez ktory PyInstaller sie wywraca.
echo Zainstaluj nowszego Pythona (np. 3.13) z python.org i uruchom build.bat ponownie.
rmdir /s /q .venv-build
exit /b 1
:notk
echo Tcl/Tk w tym Pythonie nie dziala - bez niego program nie ma okna.
echo Sprawdz: python -c "import tkinter; tkinter.Tcl()"
echo Napraw: instalator Pythona - Repair (z "tcl/tk and IDLE"), albo nowszy Python;
echo ustawiona zmienna TCL_LIBRARY tez potrafi to psuc. Potem build.bat ponownie.
rmdir /s /q .venv-build
exit /b 1
:notkexe
echo Exe zbudowany bez tkinter - PyInstaller pominal Tcl/Tk.
echo Szczegoly: build\d2r-relay\warn-d2r-relay.txt i linie WARNING wyzej.
exit /b 1
:running
echo D2R Relay jest uruchomiony - zamknij go (ikona w zasobniku - Zakoncz)
echo albo: taskkill /im D2R-Relay.exe /f   i uruchom build.bat ponownie.
exit /b 1
:err
echo Budowanie nie powiodlo sie.
exit /b 1
