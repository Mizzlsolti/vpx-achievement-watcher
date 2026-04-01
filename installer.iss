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
AppVerName=VPX Achievement Watcher
AppPublisher=Solters
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

[Code]
var
  PathsPage:   TWizardPage;
  EdBase:      TEdit;
  EdTables:    TEdit;
  EdNvram:     TEdit;
  SavedConfig: AnsiString;

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

{ Before installation begins: silently remove any existing installation so
  only one Control Panel entry exists after the upgrade. The existing
  config.json is saved in memory and restored afterwards. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  UninstallString: string;
  cfgPath: string;
  ResultCode: Integer;
begin
  Result := '';
  NeedsRestart := False;

  { Save existing config.json so we can restore it after the uninstaller
    removes the installation directory. }
  SavedConfig := '';
  cfgPath := ExpandConstant('{app}\config.json');
  if FileExists(cfgPath) then
    LoadStringFromFile(cfgPath, SavedConfig);

  { Look for an existing uninstall entry – check HKLM first, then HKCU. }
  UninstallString := '';
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
      '{B8F4E3A1-7C2D-4A5F-9E6B-1D3C8F2A7E4B}_is1',
      'UninstallString', UninstallString) then
    RegQueryStringValue(HKEY_CURRENT_USER,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
      '{B8F4E3A1-7C2D-4A5F-9E6B-1D3C8F2A7E4B}_is1',
      'UninstallString', UninstallString);

  { Run the old uninstaller silently so its Control Panel entry is removed.
    If the uninstaller cannot be launched we continue anyway; the duplicate
    entry may remain but the new installation itself is not affected. }
  if UninstallString <> '' then
    if not Exec(UninstallString, '/SILENT', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      { Ignore: proceed with installation even if the old uninstaller failed. };
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
  cfgPath, json, oldVal, basePath: string;
  existingJson: AnsiString;
begin
  if CurStep = ssPostInstall then
  begin
    cfgPath := ExpandConstant('{app}\config.json');
    basePath := EdBase.Text;

    { If the old uninstaller deleted config.json, restore the saved copy so
      the upgrade logic below can preserve all existing settings. }
    if (not FileExists(cfgPath)) and (SavedConfig <> '') then
      if not SaveStringToFile(cfgPath, SavedConfig, False) then
        if not WizardSilent then
          MsgBox('Warning: could not restore the previous configuration file.' +
                 #13#10 + 'You may need to re-enter your paths.',
                 mbInformation, MB_OK);

    if FileExists(cfgPath) then
    begin
      if WizardSilent then
      begin
        { Silent upgrade: preserve existing config.json entirely.
          Read BASE from config for the registry entry. }
        if LoadStringFromFile(cfgPath, existingJson) then
          basePath := GetJsonValue(existingJson, 'BASE');
      end
      else
      begin
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
        end;
      end;
    end
    else
    begin
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

    { Write registry entries (only when we have a valid base path) }
    if basePath <> '' then
    begin
      RegWriteStringValue(HKEY_CURRENT_USER,
        'Software\VPX Achievement Watcher',
        'EventsPath',
        basePath + '\tools\AWeditor\custom_events\');
      RegWriteStringValue(HKEY_CURRENT_USER,
        'Software\VPX Achievement Watcher',
        'Version',
        '{#MyAppVersion}');
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\VPX Achievement Watcher');
end;
