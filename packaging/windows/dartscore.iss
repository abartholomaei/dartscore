; Inno Setup script for the Windows installer; built by packaging/build.py:
;   iscc /DAppVersion=0.1.0 /DBundleDir=build\dist\dartscore /DOutputDir=release
;        /DOutputName=dartscore-0.1.0-windows-x64-setup packaging\windows\dartscore.iss
; Installs per user (no admin rights), creates Start menu and desktop shortcuts that run
; `dartscore launch`. Settings and data live in %LOCALAPPDATA%\dartscore and are kept on
; uninstall.

#ifndef AppVersion
  #error AppVersion is not defined
#endif

[Setup]
AppId={{6B0E3C1A-8D55-4F1E-9C7B-2A4D5E6F7081}
AppName=dartscore
AppVersion={#AppVersion}
AppPublisher=Alexander Bartholomäi
AppPublisherURL=https://github.com/abartholomaei/dartscore
AppSupportURL=https://github.com/abartholomaei/dartscore/issues
AppUpdatesURL=https://github.com/abartholomaei/dartscore/releases
DefaultDirName={localappdata}\Programs\dartscore
DefaultGroupName=dartscore
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile=..\icons\dartscore.ico
UninstallDisplayIcon={app}\dartscore.exe
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[CustomMessages]
en.StartWithWindows=Start dartscore when I sign in to Windows
de.StartWithWindows=dartscore bei der Windows-Anmeldung starten
en.LaunchNow=Start dartscore now
de.LaunchNow=dartscore jetzt starten
en.OpenSettings=dartscore settings (config.toml)
de.OpenSettings=dartscore-Einstellungen (config.toml)

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:StartWithWindows}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Dirs]
Name: "{localappdata}\dartscore"; Flags: uninsneveruninstall

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\dartscore"; Filename: "{app}\dartscore.exe"; Parameters: "launch"; WorkingDir: "{app}"
Name: "{autoprograms}\{cm:OpenSettings}"; Filename: "{localappdata}\dartscore"
Name: "{autodesktop}\dartscore"; Filename: "{app}\dartscore.exe"; Parameters: "launch"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\dartscore"; Filename: "{app}\dartscore.exe"; Parameters: "launch --no-browser"; WorkingDir: "{app}"; Flags: runminimized; Tasks: autostart

[Run]
Filename: "{app}\dartscore.exe"; Parameters: "launch"; Description: "{cm:LaunchNow}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
