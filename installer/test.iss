[Setup]
AppName=IDPTest
AppVersion=1.0
DefaultDirName={tmp}
OutputDir=.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

#pragma include __INCLUDE__ + ";tools\Inno Download Plugin"
#include "tools\Inno Download Plugin\idp.iss"

[Code]

procedure InitializeWizard;
begin
  MsgBox('wpInstalling = ' + IntToStr(wpInstalling), mbInformation, MB_OK);
end;