; === RiskMap Local Installer (Offline) ===
; This installer packages everything locally without downloading from internet
; Use this for development and for creating a complete offline installer

#define AppName "RiskMap"
#define AppVersion "2.0.0"
#define Publisher "Devansh Banga"
#define URL "https://github.com/Devansh-14971"
#define AppExe "RiskMap.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL={#URL}
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=RiskMapInstaller_Local
Compression=lzma2/ultra64
SolidCompression=yes
DiskSpanning=yes
DiskSliceSize=1500000000
UninstallDisplayIcon={app}\{#AppExe}
SetupLogging=yes
DisableWelcomePage=no
LicenseFile=LICENSE.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "preserve"; Description: "Preserve user data (.env, .ini) during uninstall"; Flags: unchecked

[Files]
; Main application folder from dist (onedir build)
Source: "..\dist\RiskMap\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Configuration files (if not already in the onedir bundle, but onedir usually includes them)
; We still include them just in case they are needed separately or for updates
Source: "..\src\config_.ini"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "..\src\index_map.json"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "..\src\model_data.json"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "..\src\cities.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist

; License files
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: isreadme
Source: "EULA.txt"; DestDir: "{app}"

; Models folder (include if present locally)
Source: "..\models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
; Start menu shortcut
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"

; Desktop shortcut (optional)
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

; Uninstall shortcut
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

[Run]
; Optionally launch app after installation
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Delete everything except preserved data if user checked "Preserve"
Type: filesandordirs; Name: "{app}\*"; Tasks: not preserve

; If user chose to preserve, only remove specific files
Type: files; Name: "{app}\*.exe"; Tasks: preserve
Type: files; Name: "{app}\*.log"; Tasks: preserve
Type: files; Name: "{app}\*.tmp"; Tasks: preserve
Type: files; Name: "{app}\*.cache"; Tasks: preserve

[Code]
var
  ProgressPage: TOutputProgressWizardPage;

procedure InitializeWizard;
begin
  // Create a progress page for extraction
  ProgressPage := CreateOutputProgressPage('Installing', 'Please wait while RiskMap is being installed on your computer.');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    ProgressPage.SetText('Copying files...', '');
    ProgressPage.Show;
  end
  else if CurStep = ssPostInstall then
  begin
    ProgressPage.SetText('Finalizing installation...', '');
  end;
end;

procedure DeinitializeSetup();
begin
  // Cleanup if needed
end;
