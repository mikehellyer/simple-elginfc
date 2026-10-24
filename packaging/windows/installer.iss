; Inno Setup script for Simple-ElginFC.
; Built with: iscc packaging\windows\installer.iss
; Expects dist\Simple-ElginFC\ (PyInstaller onedir output) to already
; exist, and the version passed in via /DAppVersion=x.y.z (the release
; workflow does this so the .iss file never has to be hand-edited per
; release).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Simple-ElginFC"
#define RepoRoot AddBackslash(SourcePath) + "..\.."

[Setup]
AppId={{21D7AEA4-D291-4C06-90EB-B6D4C0E25F51}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Mike Hellyer
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\Simple-ElginFC.exe
OutputDir={#RepoRoot}\dist
OutputBaseFilename=Simple-ElginFC-{#AppVersion}-Windows-Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#RepoRoot}\packaging\icons\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#RepoRoot}\dist\Simple-ElginFC\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Simple-ElginFC.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Simple-ElginFC.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Simple-ElginFC.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
