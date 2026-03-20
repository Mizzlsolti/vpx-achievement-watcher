; VPX Achievement Watcher - Inno Setup Script
; Builds a single installer: VPX-Achievement-Watcher-Setup.exe
; Run: iscc installer.iss   (or let the GitHub Action do it automatically)
;
; The installer collects the three required paths on a dedicated wizard
; page, pre-filled with sensible defaults (or existing config on upgrade).
; On completion it writes config.json into the installation directory so
; the user can launch Achievement_Watcher.exe directly.
; During silent/upgrade installs the paths page is skipped and any
; existing config.json is preserved.

#ifndef MyAppVersion
  #define MyAppVersion "2.6"
#endif

[Setup]
AppName=VPX Achievement Watcher
AppVersion={#MyAppVersion}
AppVerName=VPX Achievement Watcher
AppPublisher=Mizzlsolti
AppPublisherURL=https://github.com/Mizzlsolti/vpx-achievement-watcher
DefaultDirName=C:\vPinball\VPX Achievement Watcher
DefaultGroupName=VPX Achievement Watcher
OutputDir=installer-output
OutputBaseFilename=VPX-Achievement-Watcher-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=watcher.ico
UninstallDisplayIcon={app}\Achievement_Watcher.exe
CloseApplications=yes
RestartApplications=yes

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
; After interactive installation, offer to launch the main app
Filename: "{app}\Achievement_Watcher.exe"; Description: "Launch VPX Achievement Watcher"; Flags: nowait postinstall skipifsilent
; After silent/upgrade installation, always restart the app automatically
Filename: "{app}\Achievement_Watcher.exe"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallDelete]
; Remove everything in the installation directory on uninstall,
; including files created after install (config, logs, cache, etc.)
Type: filesandordirs; Name: "{app}"

[Code]
var
  PathsPage: TWizardPage;
  EdBase:   TEdit;
  EdTables: TEdit;
  EdNvram:  TEdit;

{ Read a string value from our simple JSON config file }
function GetJsonValue(const Json: string; const Key: string): string;
var
  SearchFor: string;
  P1, P2: Integer;
  Raw: string;
begin
  Result := '';
  SearchFor := '"' + Key + '": "';
  P1 := Pos(SearchFor, Json);
  if P1 = 0 then Exit;
  P1 := P1 + Length(SearchFor);
  Raw := Copy(Json, P1, Length(Json) - P1 + 1);
  P2 := Pos('"', Raw);
  if P2 = 0 then Exit;
  Raw := Copy(Raw, 1, P2 - 1);
  { Unescape JSON \\ -> \ }
  Result := StringChange(Raw, '\\', '\');
end;

{ Try to load existing paths from config.json into the edit fields.
  Returns True if the file was found and at least BASE was read. }
function LoadExistingConfig: Boolean;
var
  cfgPath, json: string;
  base, nvram, tables: string;
begin
  Result := False;
  cfgPath := ExpandConstant('{app}\config.json');
  if not FileExists(cfgPath) then Exit;
  if not LoadStringFromFile(cfgPath, json) then Exit;

  base   := GetJsonValue(json, 'BASE');
  nvram  := GetJsonValue(json, 'NVRAM_DIR');
  tables := GetJsonValue(json, 'TABLES_DIR');

  if base <> '' then
  begin
    EdBase.Text := base;
    Result := True;
  end;
  if nvram   <> '' then EdNvram.Text   := nvram;
  if tables  <> '' then EdTables.Text  := tables;
end;

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
  { On upgrade: pre-fill fields from existing config.json }
  LoadExistingConfig;
end;

{ Skip the paths page when running silently (auto-update) }
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (PathsPage <> nil) and (PageID = PathsPage.ID) then
    Result := WizardSilent;
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
    { In silent mode, preserve an existing config.json (upgrade path).
      If the file does not exist yet (first-time silent deploy) we fall
      through and write the defaults from the edit fields below. }
    if WizardSilent and FileExists(ExpandConstant('{app}\config.json')) then Exit;

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
