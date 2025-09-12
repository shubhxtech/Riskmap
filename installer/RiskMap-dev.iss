; === RiskMap Installer (with IDP) ===
#define AppName "RiskMap"
#define AppVersion "2.0.0"
#define Publisher "Devansh Banga"
#define URL "https://github.com/Devansh-14971"
#define AppZip "https://github.com/Devansh-14971/RiskMap/releases/nightly/download/App.zip"
#define ModelsZipURL "https://github.com/Devansh-14971/RiskMap/releases/latest/download/models.zip"
#define AppTrigger "path/to/run_app.vbs"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL={#URL}
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=RiskMapInstaller
Compression=lzma
SolidCompression=yes
SetupLogging=yes
DisableFinishedPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; --- IDP Include ---
#pragma include __INCLUDE__ + ";tools\Inno Download Plugin"
#include "tools\Inno Download Plugin\idp.iss"

[Tasks]
; 1. Desktop shortcut
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

; 2. Preserve user data at uninstall
Name: "preserve"; Description: "Preserve .env, .ini, and user data"; Flags: unchecked

[Files]
; Local helper files
Source: "app.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: isreadme
Source: "EULA.txt"; DestDir: "{app}" ; Flags: isreadme
Source: "tools\7za.exe"; DestDir: "{tmp}";
Source: "tools\get-pip.py"; DestDir: "{tmp}"; Flags: dontcopy;
Source: "tools\python-3.10.9-embed-amd64.zip"; Destdir: "{tmp}";
; Source: "..\src\config_.ini"; DestDir: "{app}"; Flags: onlyifdoesntexist;
; Source: "..\src\index_map.json"; DestDir: "{app}"; Flags: onlyifdoesntexist;
; Source: "..\src\model_data.json"; DestDir: "{app}"; Flags: onlyifdoesntexist;
; Source: "..\src\cities.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist;

[Icons]
; Main app shortcut -> points to installed exe
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppTrigger}"

; Desktop shortcut (optional, controlled by user during install)
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppTrigger}"; Tasks: desktopicon

; Uninstall shortcut
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

[Code]
const
  MAX_EXTRACT_RETRIES = 2;
  MAX_CMD_RETRIES     = 3;
  CMD_RETRY_WAIT_MS   = 2000;
  
var
  LogFile: String;

procedure LogToFile(const Msg: String);
var
  F: TextFile;
begin
  Log(Msg);
  try
    AssignFile(F, LogFile);
    if FileExists(LogFile) then
      Append(F)
    else
      Rewrite(F);
    Writeln(F, FormatDateTime('yyyy-mm-dd hh:nn:ss', Now) + ' - ' + Msg);
    CloseFile(F);
  except
    { ignore logging errors }
  end;
end;

procedure InitializeWizard;
begin
  LogFile := ExpandConstant('{app}\install.log');
  LogToFile('Installer initialized.');
end;

function RunCommandWithRetries(const Program_, Params: string; Retries: Integer; ShowCmd: Integer): Boolean;
var
  i, ResultCode: Integer;
begin
  Result := False;
  for i := 1 to Retries do
  begin
    LogToFile(Format('Running (%d/%d): %s %s', [i, Retries, Program_, Params]));
    if Exec(Program_, Params, '', ShowCmd, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0) then
    begin
      Result := True;
      Exit;
    end;
    if i < Retries then
    begin
      LogToFile('Retrying after wait...');
      Sleep(CMD_RETRY_WAIT_MS);
    end;
  end;
end;

function VerifyZip(const ZipPath: string): Boolean;
var
  ResultCode: Integer;
  Cmd: String;
begin
  Result := False;
  if not FileExists(ZipPath) then Exit;
  Cmd := '"' + ExpandConstant('{tmp}\7za.exe') + '" t "' + ZipPath + '"';
  LogToFile('Verifying ZIP: ' + ZipPath);
  if Exec('cmd.exe', '/C ' + Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0) then
    Result := True
  else
    LogToFile('Zip verification failed: ' + ZipPath);
end;

function ExtractZipWithRetries(const ZipPath, DestDir: string; Retries: Integer): Boolean;
var
  i, ResultCode: Integer;
  Cmd: String;
begin
  Result := False;
  for i := 1 to Retries do
  begin
    Cmd := '"' + ExpandConstant('{tmp}\7za.exe') + '" x -y "' + ZipPath + '" -o"' + DestDir + '"';
    LogToFile('Running command: ' + Cmd);
    if Exec('cmd.exe', '/C ' + Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0) then
    begin
      Result := True;
      Exit;
    end;
    if i < Retries then Sleep(CMD_RETRY_WAIT_MS);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppPath, ModelsZip, PythonZip, PipCmd: string;
begin
  if CurStep = ssInstall then
  begin
    LogToFile('== Installer main sequence (IDP only) ==');

    
    // sanity checks
    if not FileExists(ExpandConstant('{tmp}\7za.exe')) then
    begin
      LogToFile('ERROR: 7za.exe missing from {tmp} after ExtractTemporaryFile');
      MsgBox('Critical installer error: 7za.exe not available in temp folder. Install aborted.', mbCriticalError, MB_OK);
      Abort;
    end;

    // Queue downloads
    idpClearFiles;
    idpAddFile('{#AppZip}',   ExpandConstant('{tmp}\src\app.zip'));
    idpAddFile('{#ModelsZipURL}', ExpandConstant('{tmp}\models.zip'));

    idpDownloadAfter(wpInstalling);

    // 1) Extract app.zip
    AppZip := ExpandConstant('{tmp}\app.zip');
    if not VerifyZip(AppZip) then Abort;
    if not ExtractZipWithRetries(AppZip, ExpandConstant('{app}\src'), MAX_EXTRACT_RETRIES) then Abort;
    LogToFile('App source extracted.');

    LogToFile('App source code has been downloaded successfully');

    // 2) Extract models
    ModelsZip := ExpandConstant('{tmp}\models.zip');
    if not VerifyZip(ModelsZip) then Abort;
    if not ExtractZipWithRetries(ModelsZip, ExpandConstant('{app}\models'), MAX_EXTRACT_RETRIES) then Abort;

    // 3) Extract python
    PythonZip := ExpandConstant('{tmp}\python-3.10.9-embed-amd64.zip');
    if not VerifyZip(PythonZip) then Abort;
    if not ExtractZipWithRetries(PythonZip, ExpandConstant('{app}\python'), MAX_EXTRACT_RETRIES) then Abort;

    // 4) Ensure pip
    if not FileExists(ExpandConstant('{app}\python\Scripts\pip.exe')) then
    begin
      LogToFile('pip.exe not found, bootstrapping...');
      if not RunCommandWithRetries(
        ExpandConstant('{app}\python\python.exe'),
        '"' + ExpandConstant('{tmp}\get-pip.py') + '"',
        MAX_CMD_RETRIES, SW_SHOW) then Abort;
    end
    else
      LogToFile('pip already present.');

    // 5) Install requirements
    RequirementsFile := ExpandConstant('{app}\src\requirements.txt');
    PipCmd := '"' + ExpandConstant('{app}\python\python.exe') + '" -m pip install -r "' + RequirementsFile + '" --no-warn-script-location';

    if not RunCommandWithRetries('cmd.exe', '/C ' + PipCmd, MAX_CMD_RETRIES, SW_SHOW) then Abort;
    

    LogToFile('== Installer finished successfully ==');
  end;
end;

[UninstallDelete]
; Delete everything except preserved data if user checked "Preserve"
Type: filesandordirs; Name: "{app}\*"; Tasks: not preserve

; If user chose to preserve, leave .env/.ini/data; remove typical caches/logs
Type: files; Name: "{app}\*.py";    Tasks: preserve
Type: files; Name: "{app}\*.exe";   Tasks: preserve
Type: files; Name: "{app}\*.log";   Tasks: preserve
Type: files; Name: "{app}\*.tmp";   Tasks: preserve
Type: files; Name: "{app}\*.cache"; Tasks: preserve