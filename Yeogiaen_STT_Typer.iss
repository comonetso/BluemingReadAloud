; -- Yeogiaen_STT_Typer.iss --
; Inno Setup 스크립트 파일

[Setup]
AppId={{D1A3B4C5-E6F7-48G9-H0I1-J2K3L4M5N6O7}
AppName=Yeogiaen STT Typer
AppVersion=1.0
AppPublisher=Yeogiaen
DefaultDirName={pf}\Yeogiaen_STT_Typer
DefaultGroupName=Yeogiaen STT Typer
OutputDir=f:\workspace\Etc Project\Whisper Recoding\dist
OutputBaseFilename=Yeogiaen_STT_Typer_Setup
SetupIconFile=f:\workspace\Etc Project\Whisper Recoding\favicon.ico
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "f:\workspace\Etc Project\Whisper Recoding\dist\Yeogiaen_STT_Typer.exe"; DestDir: "{app}"; Flags: ignoreversion
; 필요한 설정 파일이나 아이콘이 있다면 추가
Source: "f:\workspace\Etc Project\Whisper Recoding\favicon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "f:\workspace\Etc Project\Whisper Recoding\README.KR.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Yeogiaen STT Typer"; Filename: "{app}\Yeogiaen_STT_Typer.exe"
Name: "{commondesktop}\Yeogiaen STT Typer"; Filename: "{app}\Yeogiaen_STT_Typer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Yeogiaen_STT_Typer.exe"; Description: "{cm:LaunchProgram,Yeogiaen STT Typer}"; Flags: nowait postinstall skipifsilent
