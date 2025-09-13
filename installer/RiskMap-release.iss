; === RiskMap Installer (with IDP) ===
#define AppName "RiskMap"
#define AppVersion "2.0.0"
#define Publisher "Devansh Banga"
#define URL "https://github.com/Devansh-14971"
#define AppExe "RiskMap.exe"
#define ExeURL "https://github.com/Devansh-14971/RiskMap/releases/latest/download/RiskMap.exe"
#define ModelsZipURL "https://github.com/Devansh-14971/RiskMap/releases/latest/download/models.zip"

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
UninstallDisplayIcon={app}\{#AppExe}
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
Source: "EULA.txt"; DestDir: "{app}"
Source: "tools\7za.exe"; DestDir: "{tmp}"; Flags: dontcopy;
Source: "tools\get-pip.py"; DestDir: "{tmp}"; Flags: dontcopy;
Source: "..\src\config_.ini"; DestDir: "{app}"; Flags: onlyifdoesntexist;
Source: "..\src\index_map.json"; DestDir: "{app}"; Flags: onlyifdoesntexist;
Source: "..\src\model_data.json"; DestDir: "{app}"; Flags: onlyifdoesntexist;
Source: "..\src\cities.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist;

[Icons]
; Main app shortcut -> points to installed exe
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"

; Desktop shortcut (optional, controlled by user during install)
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

; Uninstall shortcut
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

[Code]
const
  MAX_EXTRACT_RETRIES = 2;
  MAX_CMD_RETRIES     = 3;
  CMD_RETRY_WAIT_MS   = 2000;
  
var
  LogFile: String;

procedure LogToFile(const Msg: string);
var
  Timestamp: string;
begin
  Log(Msg); // setup log
  try
    Timestamp := GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':');
    SaveStringToFile(LogFile, Timestamp + ' - ' + Msg + #13#10, True);
  except
    { ignore logging errors }
  end;
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
  AppExePath, ModelsZip, PythonZip: string;
begin
  if CurStep = ssInstall then
  begin
  
    LogFile := ExpandConstant('{app}\install.log');
    LogToFile('Installer initialized.');
    
    LogToFile('== Installer main sequence (IDP only) ==');
    // Ensure helper binaries are extracted to {tmp} before usage
    try
      ExtractTemporaryFile('7za.exe');
      LogToFile('Extracted 7za.exe to {tmp}');
    except
      LogToFile('Failed to extract 7za.exe');
    end;

    
    // sanity checks
    if not FileExists(ExpandConstant('{tmp}\7za.exe')) then
    begin
      LogToFile('ERROR: 7za.exe missing from {tmp} after ExtractTemporaryFile');
      MsgBox('Critical installer error: 7za.exe not available in temp folder. Install aborted.', mbCriticalError, MB_OK);
      Abort;
    end;

    // Queue downloads
    idpClearFiles;
    idpAddFile('{#CodeExeURL}',   ExpandConstant('{tmp}\RiskMap.exe'));
    idpAddFile('{#ModelsZipURL}', ExpandConstant('{tmp}\models.zip'));

    idpDownloadAfter(wpInstalling);

    // 1) Move exe into app folder
    LogToFile(' Testing if App executable is present ');
    AppExePath := ExpandConstant('{tmp}\RiskMap.exe');
    if not FileExists(AppExePath) then
    begin
      MsgBox('Main application executable missing!', mbError, MB_OK);
      Abort;
    end;
    FileCopy(AppExePath, ExpandConstant('{app}\RiskMap.exe'), False);
    LogToFile('App executable has been downloaded successfully');

    // 2) Extract models
    ModelsZip := ExpandConstant('{tmp}\models.zip');
    if not VerifyZip(ModelsZip) then Abort;
    if not ExtractZipWithRetries(ModelsZip, ExpandConstant('{app}\models'), MAX_EXTRACT_RETRIES) then Abort;
    
    LogToFile('== Installer finished successfully ==');
  end;
end;

[UninstallDelete]
; Delete everything except preserved data if user checked "Preserve"
Type: filesandordirs; Name: "{app}\*"; Tasks: not preserve

; If user chose to preserve, leave .env/.ini/data; remove typical caches/logs
Type: files; Name: "{app}\*.exe";   Tasks: preserve
Type: files; Name: "{app}\*.log";   Tasks: preserve
Type: files; Name: "{app}\*.tmp";   Tasks: preserve
Type: files; Name: "{app}\*.cache"; Tasks: preserve