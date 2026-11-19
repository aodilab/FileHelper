#ifndef MyAppVersion
  #define MyAppVersion "1.0.1"
#endif

[Setup]
AppId={{8E9B7D4C-4F18-4D90-9A1D-6C2A8E31F001}
AppName=文件传输助手
AppVersion={#MyAppVersion}
AppPublisher=aodilab
AppPublisherURL=https://github.com/aodilab/FileHelper
AppSupportURL=https://github.com/aodilab/FileHelper/issues
DefaultDirName={autopf}\FileHelper
DefaultGroupName=文件传输助手
DisableWelcomePage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
OutputDir=..\dist
OutputBaseFilename=FileHelper-Setup
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\FileHelper.exe
UninstallDisplayName=文件传输助手 (FileHelper)
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
CloseApplications=force
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl"

[Messages]
SetupWindowTitle=安装 - %1
ButtonBack=上一步(&B)
ButtonNext=下一步(&N)
ButtonInstall=立即安装(&I)
ButtonOK=确定
ButtonCancel=取消
ButtonFinish=完成(&F)
ButtonBrowse=浏览(&R)...
ClickNext=点击「下一步」继续，或点击「取消」退出安装。
WizardSelectDir=选择安装位置
SelectDirDesc=您想将 [name] 安装在哪里？
SelectDirLabel3=安装程序会将 [name] 安装到以下文件夹中。
SelectDirBrowseLabel=保持默认直接点击「下一步」即可；如需更改目录请点击「浏览」。
DiskSpaceMBLabel=至少需要 [mb] MB 可用磁盘空间。
WizardSelectTasks=快捷设置
SelectTasksDesc=请确认以下安装选项：
SelectTasksLabel2=建议保持以下两项勾选，然后点击「立即安装」。
WizardInstalling=正在安装
InstallingLabel=正在安装 [name]，请稍候...
FinishedHeadingLabel=[name] 安装完成
FinishedLabelNoIcons=已完成 [name] 的安装。
FinishedLabel=已完成 [name] 的安装，可通过桌面「文件传输助手」图标随时打开。
ClickFinish=点击「完成」退出安装向导。
ConfirmUninstall=确定要彻底卸载 %1 及其本地缓存数据吗？
UninstalledAll=%1 已从您的电脑彻底卸载。

[Tasks]
Name: "desktopicon"; Description: "创建桌面「文件传输助手」图标（支持把文件直接拖到图标上发送）"
Name: "firewall"; Description: "自动放行局域网防火墙规则（推荐，防止手机扫码连不上）"

[Files]
Source: "..\dist\FileHelper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\文件传输助手"; Filename: "{app}\FileHelper.exe"; IconFilename: "{app}\FileHelper.exe"
Name: "{group}\卸载 文件传输助手"; Filename: "{uninstallexe}"
Name: "{autodesktop}\文件传输助手"; Filename: "{app}\FileHelper.exe"; IconFilename: "{app}\FileHelper.exe"; Tasks: desktopicon

[Run]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""FileHelper (LAN 8899)"""; Flags: runhidden waituntilterminated; Tasks: firewall
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""FileHelper (LAN 8899)"" dir=in action=allow program=""{app}\FileHelper.exe"" enable=yes profile=any"; Flags: runhidden waituntilterminated; Tasks: firewall
Filename: "{app}\FileHelper.exe"; Description: "立即打开 文件传输助手"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM FileHelper.exe"; Flags: runhidden waituntilterminated; RunOnceId: "StopFileHelper"
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""FileHelper (LAN 8899)"""; Flags: runhidden waituntilterminated; RunOnceId: "DelFirewallRule"
Filename: "reg"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v FileHelper /f"; Flags: runhidden waituntilterminated; RunOnceId: "DelAutoStart"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\FileHelper"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM FileHelper.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;
