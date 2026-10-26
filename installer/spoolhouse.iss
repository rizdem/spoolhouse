; Spoolhouse for Windows - Inno Setup script. Built by build_windows.py, which passes:
;   /DAppVersion=2.4.0 /DSourceDir=...\dist\Spoolhouse /DIconFile=...\Spoolhouse.ico /DOutputDir=...\dist
;
; Installs for the current user only (no administrator prompt), into
; %LOCALAPPDATA%\Programs\Spoolhouse, with a Start menu shortcut and an uninstaller.
; Your data (%APPDATA%\Spoolhouse) is never touched by installing, updating or uninstalling.

#ifndef AppVersion
  #error Pass /DAppVersion=x.y.z
#endif

[Setup]
; never change AppId: it's how Windows knows a new version is an update of the same app
AppId={{6F3B0C52-8E1D-4A7B-9C55-2F1E7A0B5D31}
AppName=Spoolhouse
AppVersion={#AppVersion}
AppVerName=Spoolhouse {#AppVersion}
AppPublisher=Spoolhouse
AppPublisherURL=https://spoolhouse.app
AppSupportURL=https://github.com/rizdem/spoolhouse/issues
AppUpdatesURL=https://spoolhouse.app
DefaultDirName={autopf}\Spoolhouse
DefaultGroupName=Spoolhouse
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Spoolhouse-{#AppVersion}-windows-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\Spoolhouse.exe
UninstallDisplayName=Spoolhouse
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Spoolhouse holds this while running: setup asks you to close it first (it may be in the system tray)
AppMutex=Local\Spoolhouse
CloseApplications=yes
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Spoolhouse setup

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; a new version replaces the old program files completely (never your data, which lives elsewhere)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Spoolhouse"; Filename: "{app}\Spoolhouse.exe"
Name: "{autodesktop}\Spoolhouse"; Filename: "{app}\Spoolhouse.exe"; Tasks: desktopicon

[Registry]
; "Start with Windows" is switched on from inside the app; uninstalling removes it
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Spoolhouse"; ValueType: none; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Spoolhouse.exe"; Description: "{cm:LaunchProgram,Spoolhouse}"; Flags: nowait postinstall skipifsilent
