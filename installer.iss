; VPX Achievement Watcher - Inno Setup Script
; Builds a single installer: VPX-Achievement-Watcher-Setup.exe
; Run: iscc installer.iss   (or let the GitHub Action do it automatically)
;
; The installer collects the three required paths on a dedicated wizard
; page, pre-filled with sensible defaults.  On completion it writes
; config.json into the installation directory so the user can launch
; Achievement_Watcher.exe directly — no separate setup step needed.

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
; Application icon
Source: "watcher.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\VPX Achievement Watcher"; Filename: "{app}\Achievement_Watcher.exe"; IconFilename: "{app}\watcher.ico"
Name: "{commondesktop}\VPX Achievement Watcher"; Filename: "{app}\Achievement_Watcher.exe"; IconFilename: "{app}\watcher.ico"
Name: "{group}\Uninstall VPX Achievement Watcher"; Filename: "{uninstallexe}"

[Run]
; After installation, offer to launch the main app directly
Filename: "{app}\Achievement_Watcher.exe"; Description: "Launch VPX Achievement Watcher"; Flags: nowait postinstall skipifsilent

[Code]
var
  PathsPage: TWizardPage;
  EdBase:   TEdit;
  EdTables: TEdit;
  EdNvram:  TEdit;

procedure CreatePathsPage;
var
  lbl: TLabel;
  top: Integer;
begin
  PathsPage := CreateCustomPage(
    wpSelectDir,
    'Configure Paths',
    'Set the folders used by VPX Achievement Watcher. You can edit these later in the app.'
  );

  top := 8;

  lbl := TLabel.Create(PathsPage);
  lbl.Caption := 'Base folder (achievements data):';
  lbl.Parent  := PathsPage.Surface;
  lbl.SetBounds(0, top, PathsPage.SurfaceWidth, 16);
  top := top + 20;

  EdBase := TEdit.Create(PathsPage);
  EdBase.Parent := PathsPage.Surface;
  EdBase.SetBounds(0, top, PathsPage.SurfaceWidth, 22);
  EdBase.Text := 'C:\vPinball\VPX Achievement Watcher';
  top := top + 36;

  lbl := TLabel.Create(PathsPage);
  lbl.Caption := 'Tables folder (.vpx files):';
  lbl.Parent  := PathsPage.Surface;
  lbl.SetBounds(0, top, PathsPage.SurfaceWidth, 16);
  top := top + 20;

  EdTables := TEdit.Create(PathsPage);
  EdTables.Parent := PathsPage.Surface;
  EdTables.SetBounds(0, top, PathsPage.SurfaceWidth, 22);
  EdTables.Text := 'C:\vPinball\VisualPinball\Tables';
  top := top + 36;

  lbl := TLabel.Create(PathsPage);
  lbl.Caption := 'NVRAM folder (VPinMAME .nv files):';
  lbl.Parent  := PathsPage.Surface;
  lbl.SetBounds(0, top, PathsPage.SurfaceWidth, 16);
  top := top + 20;

  EdNvram := TEdit.Create(PathsPage);
  EdNvram.Parent := PathsPage.Surface;
  EdNvram.SetBounds(0, top, PathsPage.SurfaceWidth, 22);
  EdNvram.Text := 'C:\vPinball\VisualPinball\VPinMAME\nvram';
end;

procedure InitializeWizard;
begin
  CreatePathsPage;
end;

function EscapeJsonStr(const S: string): string;
var
  i: Integer;
begin
  Result := '';
  for i := 1 to Length(S) do
  begin
    if S[i] = '\' then
      Result := Result + '\\'
    else if S[i] = '"' then
      Result := Result + '\"'
    else
      Result := Result + S[i];
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  cfgPath, json: string;
begin
  if CurStep = ssPostInstall then
  begin
    json :=
      '{' + #13#10 +
      '  "BASE": "'       + EscapeJsonStr(EdBase.Text)   + '",' + #13#10 +
      '  "NVRAM_DIR": "'  + EscapeJsonStr(EdNvram.Text)  + '",' + #13#10 +
      '  "TABLES_DIR": "' + EscapeJsonStr(EdTables.Text) + '",' + #13#10 +
      '  "FIRST_RUN": false' + #13#10 +
      '}';
    cfgPath := ExpandConstant('{app}\config.json');
    SaveStringToFile(cfgPath, json, False);
  end;
end;
