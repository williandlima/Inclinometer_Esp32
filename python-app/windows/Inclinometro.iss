; Script do Inno Setup para gerar um instalador Windows (Setup.exe) do
; Inclinometro Avibras Aeroco a partir do executavel ja empacotado pelo
; PyInstaller (windows\build_exe.bat).
;
; Requer o Inno Setup instalado (https://jrsoftware.org/isinfo.php) e que
; "dist\Inclinometro\Inclinometro.exe" ja exista (rode build_exe.bat antes).
; Gerar com: windows\build_installer.bat

#define MyAppName "Inclinometro Avibras Aeroco"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Avibras Aeroco"
#define MyAppExeName "Inclinometro.exe"

[Setup]
AppId={{B4C6D9E1-7F2A-4B3C-9E1D-6A2F8C0D5E3B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Inclinometro
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Inclinometro-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
SetupIconFile=..\assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Area de Trabalho"; GroupDescription: "Atalhos adicionais:"

[Files]
Source: "..\dist\Inclinometro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} agora"; Flags: nowait postinstall skipifsilent
