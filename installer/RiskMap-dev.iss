; === RiskMap Installer (with IDP) ===
#define AppName "RiskMap"
#define AppVersion "2.0.0"
#define Publisher "Devansh Banga"
#define URL "https://github.com/Devansh-14971"
#define AppZip "https://github.com/Devansh-14971/RiskMap/releases/download/nightly/app.zip"
#define ModelsZipURL "https://github.com/Devansh-14971/RiskMap/releases/download/models-v1/models.zip"
#define RequirementsPath "https://github.com/Devansh-14971/RiskMap/releases/download/requirements/requirements.txt"

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
LicenseFile=LICENSE.txt
InfoBeforeFile=EULA.txt
DisableWelcomePage=false

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
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "EULA.txt"; DestDir: "{app}" ; Flags: isreadme
Source: "tools\7za.exe"; DestDir: "{tmp}"; Flags: dontcopy;
Source: "tools\get-pip.py"; DestDir: "{tmp}"; Flags: dontcopy;
Source: "tools\python-3.10.9-embed-amd64.zip"; Destdir: "{tmp}";
; Source: "..\src\config_.ini"; DestDir: "{app}"; Flags: onlyifdoesntexist;
; Source: "..\src\index_map.json"; DestDir: "{app}"; Flags: onlyifdoesntexist;
; Source: "..\src\model_data.json"; DestDir: "{app}"; Flags: onlyifdoesntexist;
; Source: "..\src\cities.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist;

[Icons]
; Main app shortcut -> points to installed exe
Name: "{group}\{#AppName}"; Filename: "{app}\src\run_app.vbs"; IconFilename: "{app}\app.ico"

; Desktop shortcut (optional, controlled by user during install)
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\src\run_app.vbs"; Tasks: desktopicon; IconFilename: "{app}\app.ico"

; Uninstall shortcut
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"; IconFilename: "{app}\app.ico"

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


procedure InitializeWizard;
begin
  idpClearFiles;
  idpAddFile('{#AppZip}', ExpandConstant('{tmp}\app.zip'));  // Installing to temp folder
  idpAddFile('{#ModelsZipURL}', ExpandConstant('{tmp}\models.zip'));
  idpAddFile('{#RequirementsPath}', ExpandConstant('{tmp}\requirements.txt'));
  idpDownloadAfter(wpReady);  
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
      LogToFile(Format('Exec returned code %d for %s %s', [ResultCode, Program_, Params]));
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
  if not FileExists(ZipPath) then 
    begin
      LogToFile('Path ' + ZipPath + ' does not exist');
      Exit;
    end;
  Cmd := ExpandConstant('{tmp}\7za.exe') + ' t "' + ZipPath + '"';
  LogToFile('Verifying ZIP: ' + ZipPath);
  LogToFile('Using command: ' + Cmd);
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
    Cmd := ExpandConstant('{tmp}\7za.exe') + ' x -y "' + ZipPath + '" -o"' + DestDir + '"';
    LogToFile('Running command: ' + Cmd);
    if Exec('cmd.exe', '/C ' + Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0) then
    begin
      LogToFile('Command was run successfully ' + Cmd);
      Result := True;
      Exit;
    end;
    if i < Retries then Sleep(CMD_RETRY_WAIT_MS);
  end;
  LogToFile('Command ' + Cmd + ' Was not run successfully');
end;

procedure EnableSitePackages(const FileName: string);
var
  Raw: AnsiString; // for loading/saving
  S: String;       // for modification
begin
  if LoadStringFromFile(FileName, Raw) then
  begin
    S := String(Raw);  // convert to String for StringChangeEx
    StringChangeEx(S, '#import site', 'import site', True);

    Raw := AnsiString(S); // convert back for saving
    if SaveStringToFile(FileName, Raw, False) then
      LogToFile('Patched ' + FileName + ' to enable site-packages')
    else
      LogToFile('Failed to write ' + FileName);
  end
  else
    LogToFile('Could not read ' + FileName);
end;


procedure CurStepChanged(CurStep: TSetupStep);
var
  AppZip, ModelsZip, PythonZip, PipCmd, RequirementsFile: string;
begin
  if CurStep = ssInstall then
  begin
    if not DirExists(ExpandConstant('{app}')) then
      ForceDirectories(ExpandConstant('{app}'));
      
    LogFile := ExpandConstant('{app}\install.log');
    LogToFile('Installer initialized at ' + LogFile);
    LogToFile('App will live in ' + ExpandConstant('{app}'));
    ExtractTemporaryFile('7za.exe');
    ExtractTemporaryFile('python-3.10.9-embed-amd64.zip');
    if FileCopy(ExpandConstant('{tmp}\requirements.txt'), ExpandConstant('{app}\requirements.txt'), True) then LogToFile('requirements.txt was copied from temp');
    LogToFile('== Installer main sequence ==');

    // sanity checks
    if not FileExists(ExpandConstant('{tmp}\7za.exe')) then
    begin
      LogToFile('ERROR: 7za.exe missing from {tmp} after ExtractTemporaryFile');
      MsgBox('Critical installer error: 7za.exe not available in temp folder. Install aborted.', mbCriticalError, MB_OK);
      Abort;
    end;
    
    // Remember to uncomment
    
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
    
    // Patch python310._pth to enable site-packages

    EnableSitePackages(ExpandConstant('{app}\python\python310._pth'));
     

    // 4) Ensure pip
    if not FileExists(ExpandConstant('{app}\python\Scripts\pip.exe')) then
    begin
      LogToFile('pip.exe not found, bootstrapping...');
      ExtractTemporaryFile('get-pip.py');
      if not RunCommandWithRetries(
        ExpandConstant('{app}\python\python.exe'),
        '"' + ExpandConstant('{tmp}\get-pip.py') + '"',
        MAX_CMD_RETRIES, SW_SHOW) then Abort;
    end
    else
      LogToFile('pip already present.');

    // 5) Install requirements
    RequirementsFile := ExpandConstant('{app}\requirements.txt');
    PipCmd := 'install -r "' + RequirementsFile + '" --no-warn-script-location';

    if not RunCommandWithRetries(ExpandConstant('{app}\python\Scripts\pip.exe') , PipCmd, MAX_CMD_RETRIES, SW_SHOW) then Abort;
    
    LogToFile('== Installer finished successfully ==');
  end;
end;

[UninstallDelete]
; Delete everything except preserved data if user checked "Preserve"
Type: filesandordirs; Name: "{app}\*"; Tasks: not preserve

; If user chose to preserve, leave .env/.ini/data; remove typical caches/logs
Type: files; Name: "{app}\*.txt";   Tasks: preserve
Type: files; Name: "{app}\*.py";    Tasks: preserve
Type: files; Name: "{app}\*.exe";   Tasks: preserve
Type: files; Name: "{app}\*.log";   Tasks: preserve
Type: files; Name: "{app}\*.tmp";   Tasks: preserve
Type: files; Name: "{app}\*.cache"; Tasks: preserve