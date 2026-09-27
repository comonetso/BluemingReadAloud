; BluemingReadAloud 설치 파일 스크립트 (Inno Setup 6)
;
; 만드는 순서
;   1) python -m PyInstaller BluemingReadAloud.spec --noconfirm      → dist\BluemingReadAloud.exe (단일 exe)
;   2) "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\BluemingReadAloud.iss
;      → installer\Output\BluemingReadAloud_Setup_<버전>.exe
;
; 설치하는 것: exe 하나 + README 두 개 + favicon.ico. 시작 메뉴 바로가기, 바탕화면 바로가기(선택), 제거 프로그램.
; ⚠️ 인증 파일(google_credentials.json)·설정 파일(whisperer_settings.json)은 넣지 않는다 — 인증 파일은 비밀이라 설치 파일에
;    담으면 안 된다. 처음 실행하면 인증 창이 뜨고, 거기서 고른 파일을 앱이 설치 폴더에 복사해 둔다.
; ⚠️ 앱은 설정·로그를 "작업 폴더" 기준 상대 경로로 쓴다 → 바로가기와 설치 후 실행 모두 WorkingDir 을 설치 폴더로 둔다.
; ⚠️ exe 는 관리자 권한으로 실행된다(spec uac_admin=True — 전역 키보드 훅). 그래서 설치 폴더(Program Files)에 써도 된다.

#define MyAppName "BluemingReadAloud"
; 버전: 마지막 빌드가 v1.1.0(2026-05-25) — STT 를 걷어내고 이름을 바꾼 큰 개편이라 2.0.0 [임의 — 바꿔도 됨]
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Blueming"
#define MyAppExeName "BluemingReadAloud.exe"

[Setup]
; AppId 는 이 앱을 알아보는 고유 번호다. 한 번 정하면 바꾸지 말 것(바꾸면 업데이트 설치가 새 앱으로 따로 깔린다)
AppId={{7CC24D7A-3F3C-4292-A7B2-6B3EB0A97BB3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=Output
OutputBaseFilename=BluemingReadAloud_Setup_{#MyAppVersion}
SetupIconFile=..\favicon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 앱이 떠 있으면 설치 전에 닫는다(덮어쓰기 실패 방지). force = 정상 종료 요청에 응답하지 않으면 강제로 닫는다.
; ⚠️ yes 로 두면 멈춘다(2026-09-28 실측): 이 앱은 보이는 창 없이 트레이에만 떠 있어 윈도우의 "닫아 주세요"(Restart Manager)에
;    응답하지 못하고, 설치 창이 "응용 프로그램을 닫는 중…"에서 계속 기다렸다.
CloseApplications=force

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.KR.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\favicon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; runascurrentuser: 설치 프로그램(이미 관리자)이 직접 띄운다.
; ⚠️ 이 플래그가 없으면 Inno Setup 은 postinstall 을 "원래 사용자 권한" 보조 프로세스(spawn server)에 맡기는데, 이 exe 는
;    관리자 권한을 요구해서(requireAdministrator — spec uac_admin) 그 보조 프로세스가 못 띄우고
;    "내부 오류: CallSpawnServer: Unexpected response: $0" 가 났다(2026-09-28 실측 — 파일 설치는 끝난 뒤 마지막 실행만 실패).
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent runascurrentuser

; 제거할 때 앱이 만든 파일(설정·로그·인증 복사본)은 지우지 않는다 — 다시 설치해도 설정이 남게
