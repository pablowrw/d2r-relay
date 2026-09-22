; Instalator Windows (Inno Setup 6). Budowanie: windows\build.bat, ktory
; wywola ISCC, jesli Inno Setup jest zainstalowany (winget install JRSoftware.InnoSetup).
; Instalacja dla biezacego uzytkownika, bez uprawnien administratora.

#define AppName "D2R Relay"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppExe "D2R-Relay.exe"
#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"
; wersja sprzed zmiany nazwy (D2R Status) - usuwana przy instalacji
#define OldUninstKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\{96EDCF42-1FCF-4509-BCD4-47052DA79125}_is1"

[Setup]
AppId={{989FB58C-230A-410F-8C5F-6195EBBD711A}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher=pablowrw
AppPublisherURL=https://github.com/pablowrw/d2r-relay
AppSupportURL=https://github.com/pablowrw/d2r-relay/issues
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=D2R-Relay-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; ten sam mutex trzyma dzialajacy program (single.py) - instalator i
; deinstalator poprosza o jego zamkniecie; drugi to mutex dawnej wersji
AppMutex=d2r-relay-instance,d2r-gamereader-instance

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; pliki starszej wersji - nowa moze miec inny zestaw bibliotek
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\D2R-Relay\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// Dawna wersja (D2R Status) jest odinstalowywana po cichu; jej ustawienia
// przenosi sam program (platformdirs_lite), a wlaczony autostart zapisujemy
// od razu pod nowa nazwa i sciezka.
procedure CurStepChanged(CurStep: TSetupStep);
var
  Uninst: String;
  Code: Integer;
  HadAutostart: Boolean;
begin
  if CurStep = ssInstall then
  begin
    if RegQueryStringValue(HKEY_CURRENT_USER, '{#OldUninstKey}', 'UninstallString', Uninst) then
    begin
      HadAutostart := RegValueExists(HKEY_CURRENT_USER, '{#RunKey}', 'd2r-gamereader');
      Exec(RemoveQuotes(Uninst), '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '',
           SW_HIDE, ewWaitUntilTerminated, Code);
      if HadAutostart then
        RegWriteStringValue(HKEY_CURRENT_USER, '{#RunKey}', 'd2r-relay',
                            '"' + ExpandConstant('{app}\{#AppExe}') + '" --autostart');
    end;
  end;
end;

// autostart (autostart.py) zapisuje wpis w HKCU\...\Run - usuwamy go razem z programem;
// ustawienia w %APPDATA%\d2r-relay zostaja
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKEY_CURRENT_USER, '{#RunKey}', 'd2r-relay');
    RegDeleteValue(HKEY_CURRENT_USER, '{#RunKey}', 'd2r-gamereader');
  end;
end;
