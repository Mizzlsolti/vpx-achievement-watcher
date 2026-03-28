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
AppId={{B8F4E3A1-7C2D-4A5F-9E6B-1D3C8F2A7E4B}
AppName=VPX Achievement Watcher
AppVersion={#MyAppVersion}
AppVerName=VPX Achievement Watcher
AppPublisher=Mizzlsolti
AppPublisherURL=https://github.com/Mizzlsolti/vpx-achievement-watcher
DefaultDirName=C:\vPinball\VPX Achievement Watcher
UsePreviousAppDir=yes
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

[Registry]
Root: HKCU; Subkey: "Software\VPX Achievement Watcher"; ValueType: string; ValueName: "EventsPath"; ValueData: "{code:GetEventsPath}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\VPX Achievement Watcher"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey

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
  StringChange(Raw, '\\', '\');
  Result := Raw;
end;

{ Try to load existing paths from config.json into the edit fields.
  Returns True if the file was found and at least BASE was read. }
function LoadExistingConfig: Boolean;
var
  cfgPath: string;
  json: AnsiString;
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
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (PathsPage <> nil) and (CurPageID = PathsPage.ID) then
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

{ Returns the custom_events folder path based on the wizard BASE value }
function GetEventsPath(Param: string): string;
begin
  Result := EdBase.Text + '\tools\AWeditor\custom_events\';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  cfgPath, json, oldVal: string;
  existingJson: AnsiString;
begin
  if CurStep = ssPostInstall then
  begin
    cfgPath := ExpandConstant('{app}\config.json');

    if FileExists(cfgPath) then
    begin
      { Silent upgrade: preserve existing config.json entirely. }
      if WizardSilent then Exit;

      { Interactive upgrade: preserve all settings (OVERLAY, cloud config,
        etc.) but update the three path values to whatever the user entered
        on the wizard page. }
      if LoadStringFromFile(cfgPath, existingJson) then
      begin
        json := existingJson;

        oldVal := GetJsonValue(json, 'BASE');
        StringChange(json, '"BASE": "' + EscapeJsonStr(oldVal) + '"',
                           '"BASE": "' + EscapeJsonStr(EdBase.Text) + '"');

        oldVal := GetJsonValue(json, 'NVRAM_DIR');
        StringChange(json, '"NVRAM_DIR": "' + EscapeJsonStr(oldVal) + '"',
                           '"NVRAM_DIR": "' + EscapeJsonStr(EdNvram.Text) + '"');

        oldVal := GetJsonValue(json, 'TABLES_DIR');
        StringChange(json, '"TABLES_DIR": "' + EscapeJsonStr(oldVal) + '"',
                           '"TABLES_DIR": "' + EscapeJsonStr(EdTables.Text) + '"');

        SaveStringToFile(cfgPath, json, False);
        Exit;
      end;
    end;

    { First-time install: write a minimal config.json with the wizard paths. }
    json :=
      '{' + #13#10 +
      '  "BASE": "'       + EscapeJsonStr(EdBase.Text)   + '",' + #13#10 +
      '  "NVRAM_DIR": "'  + EscapeJsonStr(EdNvram.Text)  + '",' + #13#10 +
      '  "TABLES_DIR": "' + EscapeJsonStr(EdTables.Text) + '",' + #13#10 +
      '  "FIRST_RUN": false' + #13#10 +
      '}';
    SaveStringToFile(cfgPath, json, False);
  end;
end;
