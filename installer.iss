; VPX Achievement Watcher - Inno Setup Script
; Builds a single installer: VPX-Achievement-Watcher-Setup.exe
; Run: iscc installer.iss   (or let the GitHub Action do it automatically)

[Setup]
AppName=VPX Achievement Watcher
AppVersion={#MyAppVersion}
AppPublisher=Mizzlsolti
AppPublisherURL=https://github.com/Mizzlsolti/vpx-achievement-watcher
DefaultDirName={autopf}\VPX Achievement Watcher
DefaultGroupName=VPX Achievement Watcher
OutputDir=installer-output
OutputBaseFilename=VPX-Achievement-Watcher-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=watcher.ico
UninstallDisplayIcon={app}\Achievement_Watcher.exe

[Files]
; Main application executable (built by PyInstaller)
Source: "dist\Achievement_Watcher.exe"; DestDir: "{app}"; Flags: ignoreversion
; First-run setup wizard (built by PyInstaller from aw_setup.py)
Source: "dist\AW_Setup.exe"; DestDir: "{app}"; Flags: ignoreversion
; Application icon
Source: "watcher.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\VPX Achievement Watcher"; Filename: "{app}\Achievement_Watcher.exe"; IconFilename: "{app}\watcher.ico"
Name: "{commondesktop}\VPX Achievement Watcher"; Filename: "{app}\Achievement_Watcher.exe"; IconFilename: "{app}\watcher.ico"
Name: "{group}\VPX Achievement Watcher Setup"; Filename: "{app}\AW_Setup.exe"; IconFilename: "{app}\watcher.ico"
Name: "{group}\Uninstall VPX Achievement Watcher"; Filename: "{uninstallexe}"

[Run]
; After installation, offer to run the first-run setup wizard
Filename: "{app}\AW_Setup.exe"; Description: "Run initial setup (configure paths)"; Flags: nowait postinstall skipifsilent
