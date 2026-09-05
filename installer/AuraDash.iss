; AuraDash 安装包脚本（Inno Setup 6）
; 用法：用 Inno Setup 打开后用 [Run] 编译，产物：installer\AuraDash_Setup.exe
; 准备工作：先运行 build.ps1 生成 dist\AuraDash\AuraDash.exe

#define MyAppName "AuraDash"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "AuraDash Contributors"
#define MyAppExeName "AuraDash.exe"

[Setup]
AppId={{7A1D2F3C-4B5E-4C6D-9E8F-0A1B2C3D4E5F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\AuraDash
DefaultGroupName=AuraDash
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\installer
OutputBaseFilename=AuraDash_Setup_{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked
Name: "startmenu"; Description: "创建开始菜单快捷方式"; GroupDescription: "附加任务:"
Name: "autostart"; Description: "开机自启动"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source: "..\dist\AuraDash\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AuraDash"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenu
Name: "{autodesktop}\AuraDash"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "AuraDash"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 AuraDash"; Flags: nowait postinstall skipifsilent
