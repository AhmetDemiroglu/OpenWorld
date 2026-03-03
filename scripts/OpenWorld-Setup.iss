; OpenWorld Setup Script for Inno Setup
; Bu script Inno Setup Compiler ile derlenir
; Sonuc: OpenWorld-Setup.exe

#define MyAppName "OpenWorld Local Agent"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Ahmet Demiroglu"
#define MyAppURL "https://github.com/AhmetDemiroglu/OpenWorld"
#define MyAppExeName "OpenWorld-Launcher.bat"

[Setup]
AppId={{B4A4C8F2-1234-5678-90AB-CDEF12345678}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\OpenWorld
DisableProgramGroupPage=no
LicenseFile=..\LICENSE
OutputDir=..\build
OutputBaseFilename=OpenWorld-Setup-v{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Ana proje dosyalari
Source: "..\*"; DestDir: "{app}"; Excludes: ".git,node_modules,.venv,*.gguf,*.log,build,dist"; Flags: ignoreversion recursesubdirs

; Launcher
Source: "..\OpenWorld-Launcher.bat"; DestDir: "{app}"; Flags: ignoreversion

; README ve dokumanlar
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

; Bos klasorler (olusturulmasi gerekenler)
Source: "..\data\*"; DestDir: "{app}\data"; Excludes: "sessions,logs,state.db"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Kullanici verileri icin bos klasorler
Name: "{app}\data\sessions"
Name: "{app}\data\logs"
Name: "{app}\data\planner"
Name: "{app}\data\mail\drafts"
Name: "{app}\data\reports"
Name: "{app}\models"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Kurulum sonrasi calistirilabilir
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Kurulum oncesi kontroller
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := true;
  
  // Windows surum kontrolu (Windows 10+)
  if not IsWindowsVersionOrHigher(10, 0, 0) then begin
    MsgBox('OpenWorld Windows 10 veya uzeri gerektirir.', mbCriticalError, MB_OK);
    Result := false;
    Exit;
  end;
  
  // Python kontrolu (bilgilendirme)
  if not Exec('cmd', '/c python --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then begin
    MsgBox('UYARI: Python bulunamadi!' + #13#10 + 
           'OpenWorld calismasi icin Python 3.11+ gerekli.' + #13#10 +
           'Lutfen https://python.org adresinden indirin.', mbInformation, MB_OK);
  end;
  
  // Node.js kontrolu (bilgilendirme)
  if not Exec('cmd', '/c node --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then begin
    MsgBox('UYARI: Node.js bulunamadi!' + #13#10 + 
           'OpenWorld calismasi icin Node.js 20+ gerekli.' + #13#10 +
           'Lutfin https://nodejs.org adresinden indirin.', mbInformation, MB_OK);
  end;
end;

// Kurulum sonrasi mesaj
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    // Kurulum tamamlandi, bilgilendirme
  end;
end;
