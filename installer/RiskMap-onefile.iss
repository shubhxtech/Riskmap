#define AppName "RiskMap"
#define AppVersion "2.0.0"
#define AppExe "RiskMap.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=RiskMapInstaller_Single
Compression=lzma2/ultra64
SolidCompression=yes
UninstallDisplayIcon={app}\{#AppExe}
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Single exe file
Source: "..\dist\RiskMap.exe"; DestDir: "{app}"; Flags: ignoreversion

; Config files (will be created on first run if missing)
Source: "..\src\config_.ini"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "..\src\index_map.json"; DestDir: "{app}"; Flags: onlyifdoesntexist  
Source: "..\src\model_data.json"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "..\src\cities.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
