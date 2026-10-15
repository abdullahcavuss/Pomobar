; Inno Setup 6 script for Pomobar. Built by build.bat:
;   ISCC /DAppVersion=2.0.0 packaging\Pomobar.iss

#define AppName "Pomobar"
#ifndef AppVersion
  #define AppVersion "2.0.0"
#endif

[Setup]
AppId={{8F3C2A1E-5B7D-4C9A-9E21-6A4F0B3D7C55}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Abdullah ÇAVUŞ
AppPublisherURL=https://github.com/abdullahcavuss/Pomobar
AppSupportURL=https://github.com/abdullahcavuss/Pomobar/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Installs for the current user without admin rights (user can choose all users).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Pomobar-Setup-{#AppVersion}
SetupIconFile=pomobar.ico
UninstallDisplayIcon={app}\Pomobar.exe
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[CustomMessages]
english.StartupTask=Start Pomobar when Windows starts
turkish.StartupTask=Windows açılınca Pomobar'ı başlat
english.OptionsGroup=Options:
turkish.OptionsGroup=Seçenekler:

[Tasks]
Name: "startup"; Description: "{cm:StartupTask}"; GroupDescription: "{cm:OptionsGroup}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Pomobar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Pomobar.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Pomobar.exe"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\Pomobar.exe"; Tasks: startup

[Run]
Filename: "{app}\Pomobar.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Close a running Pomobar so its files can be removed.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Pomobar.exe"; Flags: runhidden; RunOnceId: "KillPomobar"
