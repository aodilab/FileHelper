#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppId={{8E9B7D4C-4F18-4D90-9A1D-6C2A8E31F001}
AppName=文件传输助手 (FileHelper)
AppVersion={#MyAppVersion}
AppPublisher=aodilab
AppPublisherURL=https://github.com/aodilab/FileHelper
AppSupportURL=https://github.com/aodilab/FileHelper/issues
DefaultDirName={autopf}\FileHelper
DefaultGroupName=文件传输助手
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=FileHelper-Setup
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\FileHelper.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式（支持直接拖入文件到图标发送）"; GroupDescription: "附加选项:"
Name: "firewall"; Description: "自动添加 Windows 防火墙放行规则（局域网端口 8899）"; GroupDescription: "附加选项:"

[Files]
Source: "..\dist\FileHelper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\文件传输助手"; Filename: "{app}\FileHelper.exe"; IconFilename: "{app}\FileHelper.exe"
Name: "{group}\卸载 文件传输助手"; Filename: "{uninstallexe}"
Name: "{autodesktop}\文件传输助手"; Filename: "{app}\FileHelper.exe"; IconFilename: "{app}\FileHelper.exe"; Tasks: desktopicon

[Run]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""FileHelper (LAN 8899)"""; Flags: runhidden waituntilterminated; Tasks: firewall
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""FileHelper (LAN 8899)"" dir=in action=allow program=""{app}\FileHelper.exe"" enable=yes profile=any"; Flags: runhidden waituntilterminated; Tasks: firewall
Filename: "{app}\FileHelper.exe"; Description: "立即启动 文件传输助手"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""FileHelper (LAN 8899)"""; Flags: runhidden waituntilterminated
