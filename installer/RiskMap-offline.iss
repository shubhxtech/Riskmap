; === RiskMap Installer (Offline) ===
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
OutputBaseFilename=RiskMapInstaller_Offline
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\{#AppExe}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; 1. Desktop shortcut
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

; 2. Preserve user data at uninstall
Name: "preserve"; Description: "Preserve .env, .ini, and user data"; Flags: unchecked

[Files]
; Local helper files
Source: "..\app.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: isreadme
Source: "EULA.txt"; DestDir: "{app}"

; Bundling the main executable from local dist folder (Offline mode)
Source: "..\dist\RiskMap.exe"; DestDir: "{app}"; Flags: ignoreversion

; Config files
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

[UninstallDelete]
; Delete everything except preserved data if user checked "Preserve"
Type: filesandordirs; Name: "{app}\*"; Tasks: not preserve

; If user chose to preserve, leave .env/.ini/data; remove typical caches/logs
Type: files; Name: "{app}\*.exe";   Tasks: preserve
Type: files; Name: "{app}\*.log";   Tasks: preserve
Type: files; Name: "{app}\*.tmp";   Tasks: preserve
Type: files; Name: "{app}\*.cache"; Tasks: preserve
