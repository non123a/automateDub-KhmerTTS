; Inno Setup installer template for AutomateDub Studio.
#define AppName "AutomateDub Studio"
#define AppVersion "0.1.0"
#define AppPublisher "AutomateDub"
#define AppExeName "AutomateDub Studio.exe"

[Setup]
AppId={{C4E3B33A-2C57-4E1C-B5E2-A4B3C08156C9}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\AutomateDub Studio
DefaultGroupName=AutomateDub Studio
OutputBaseFilename=AutomateDub-Studio-{#AppVersion}-windows-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "{#SourcePath}\..\..\dist\windows\AutomateDub Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AutomateDub Studio"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\AutomateDub Studio"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Registry]
Root: HKCR; Subkey: ".autodub"; ValueType: string; ValueName: ""; ValueData: "AutomateDubStudio.Project"; Flags: uninsdeletevalue
Root: HKCR; Subkey: "AutomateDubStudio.Project"; ValueType: string; ValueName: ""; ValueData: "AutomateDub Project"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AutomateDubStudio.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""
