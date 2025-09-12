#define AppName "RiskMap"
#define CodeExeURL "https://github.com/Devansh-14971/RiskMap/download/RiskMap.exe"
#define VersionURL "path/to/version.json"
#define Publisher "Devansh Banga"
#define PublisherURL "https://github.com/Devansh-14971"

[Setup]
AppName = {#AppName} Updater
AppVersion = 2.0
AppPublisher = {#Publisher}
AppPublisherURL = {#PublisherURL}
DefaultDirName = {app}
OutputDir = output
OutputBaseFilename = RiskMapUpdater
DisableProgramGroupPage = yes
Uninstallable = yes
SetupLogging = yes
PrivilegesRequired = lowest


[Code]
#include "tools\Inno Download Plugin\idp.iss"

procedure CheckIfNewVersion();
begin
 idpClearFiles;
 idpAddFile('{#VersionURL}', ExpandConstant('{tmp}\version_new.json'));
 idpDownloadFiles;
 
 if 

procedure CurStepChanged(CurStep: TSetupStep);
var 
  AppExe : String;
begin 
  if CurStep = ssInstall then
  begin
    