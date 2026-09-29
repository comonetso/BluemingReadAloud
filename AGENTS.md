# BluemingReadAloud - AI 에이전트 거버넌스

## Project Context & Operations

### 비즈니스 목표
Google Cloud Text-to-Speech를 활용한 Windows 데스크탑 **읽어주기(TTS) 전용** 도구.
어느 프로그램에서든 글을 선택하고 단축키를 누르거나, 선택 끝 옆에 뜨는 빨간 점을 누르면 선택한 글을 읽어 준다.
(옛 플로팅 아이콘은 2026-09-28 사용자 결정으로 없앴다 — 빨간 점이 대신한다.)
크롬 확장 `F:\workspace\EtcProject\ChromeExtentions\read-aloud-hrg` 처럼 동작하는 것이 목표다.
(옛 이름 "Yeogiaen STT Typer". 받아쓰기(STT) 기능은 걷어냈다.)

하단 재생 컨트롤러(`bottom_bar.py`)와 리더 창 형광펜(`reader_window.py`)은 c9627f4 에서 들어왔다.
2026-09-28 부터 형광펜은 **원문 위에 직접 칠하는 것**(`source_highlight.py`)이 먼저다. 리더 창은 원문 위에 칠할 수 없을 때만 띄운다.
Aside·웨일·크롬에는 크롬 확장이 있어서, 그 브라우저가 전경이면 이 앱은 쉰다(트레이 "브라우저에서 비활성화", 기본 켬).

### Tech Stack
- 언어: Python 3.13.5
- 플랫폼: Windows 데스크탑 (시스템 트레이 상주 앱)
- 음성합성: Google Cloud Text-to-Speech API v1 (기본 음성 `ko-KR-Chirp3-HD-Callirrhoe`)
- 인증: Google API 키 두 개 — TTS 키·Gemini 키(번역). 인증 창에 넣어 `whisperer_settings.json` 에 저장 (2026-09-29, 서비스 계정 JSON 에서 바꿈)
- 번역: Gemini API `gemini-3.5-flash-lite` — `translation.py` (한글이 없는 문장만 번역, 제한 3초)
- GUI: ttkbootstrap (tkinter 확장), pystray (시스템 트레이), Win32(ctypes) 빨간 점·하단 바·리더 창·원문 위 형광펜 막(포커스 안 뺏는 창)
- 원문 위 형광펜: UI Automation (comtypes) — `source_highlight.py` 전용 스레드에서만
- 오디오: sounddevice (`OutputStream` 연속 재생), numpy, winsound (비프음)
- 입력: pynput (글로벌 핫키, 전역 마우스 훅(빨간 점), Ctrl+C 입력), pyperclip (클립보드)
- 빌드: PyInstaller (`BluemingReadAloud.spec`)
- 다국어: messages.py (한국어/영어)

### Operational Commands

개발 실행:
```bash
python -u whisperer.py
```
- 콘솔 한글 깨짐을 피하려면 `PYTHONUTF8=1` 을 건다.
- 변경 후에는 실행 중인 프로세스를 수동 종료 후 재실행한다.
- Hot reload는 지원하지 않는다.

배포 빌드 (최종 마무리 시에만):
```bash
python -m PyInstaller BluemingReadAloud.spec --noconfirm
```
- `pyinstaller` 단독 명령은 이 PC의 PATH에 없다. 반드시 `python -m PyInstaller` 로 부른다.
- 빌드 결과물은 `dist/BluemingReadAloud.exe` 이다. `uac_admin=True` 라 실행 시 UAC 창이 뜬다.
- 빌드 성공은 종료 코드만 보지 말고 산출물 타임스탬프로도 확인한다.
- `*.spec` 은 `.gitignore` 대상이라 git에 없다. 옛 spec 3개(`Yeogiaen_*.spec`)는 정리 여부를 사용자가 정할 때까지 둔다.

의존성 설치:
```bash
python -m pip install -r requirements.txt
```

### 테스트
- 별도의 자동화 테스트 프레임워크(pytest 등)는 사용하지 않는다.
- 검증 순서: 수정 → `py_compile` → dev 실행(`python -u whisperer.py`) → 사용자 실사용 확인 → 빌드(사용자 통과 선언 후에만).
- 테스트 목적의 임시 파일은 반드시 시스템 `/tmp` (Windows: `%TEMP%`)에 생성하고, 확인 후 삭제한다.

### 인증 및 민감 정보
- API 키 두 개(TTS 키·Gemini 키): 인증 창에 입력 → `whisperer_settings.json` 에 평문 저장. 키 하나로 둘 다는 안 된다
  (Gemini 키는 서비스 계정 바인딩이라 TTS 401, TTS 키는 Gemini 403 — 2026-09-29 실측). `.env` 는 앱이 읽지 않는다.
- 설정 파일: `whisperer_settings.json` (gitignore됨 — 키가 들어 있다. 콘솔 출력은 `_mask_keys` 로 가린다)
- `google_credentials.json`: 옛 서비스 계정 키. 더 이상 안 쓰지만 지우지 않았다(gitignore됨)
- 민감 파일은 절대 Git에 커밋하지 않는다.

---

## Golden Rules

### Immutable (절대 변경 불가)
- API 키, 서비스 계정 JSON 경로, 비밀번호를 코드에 하드코딩 금지.
- `google_credentials.json`, `whisperer_settings.json`, `openai_api_key.txt`, `.env`는 절대 Git에 커밋하지 않는다.
- 코드 수정 전 반드시 사용자에게 한글로 상세히 설명하고 동의를 받은 후에만 수정한다. 설명 없이 코드 수정은 **절대 금지**.

### Do's
- 모든 문서, Plan, Todo, 설명은 한글로 친절하게 작성한다.
- 대규모 수정 시 작은 단위로 나누어 단계별로 진행하고, 각 단계마다 동작 확인 후 Git 커밋한다.
- 사용자 대면 메시지를 추가/수정할 때는 반드시 `messages.py`의 `ko`와 `en` 양쪽에 동시 추가한다.
- 새 기능 추가 시 `whisperer_settings.json`의 `save_settings()`, `load_settings()` 양쪽을 동기화한다.
- 스레드 안전을 위해 GUI 업데이트는 반드시 `gui_queue`를 통한다.
- 오디오 리소스(스트림, 파일)는 사용 후 반드시 정리(close/cleanup)한다.

### Don'ts
- `whisperer.py`에 직접 한국어/영어 문자열을 하드코딩하지 않는다. `messages.py`를 사용한다.
- Windows 시스템 예약 단축키(Win+L, Ctrl+Alt+Del 등)를 핫키로 등록하지 않는다.
- 다중 실행 방지 포트(51888)를 변경하지 않는다.
- `recordings/`, `logs/` 폴더의 사용자 데이터를 임의로 삭제하지 않는다.
- 빌드는 최종 마무리 시에만 수행하며, 개발 중에는 `python -u whisperer.py`로만 확인한다.

### TTS·빨간 점 함정 규칙 (2026-06-07, 2026-07-27 세션 로그에서 옮김, 2026-09-28 플로팅 아이콘 제거로 갱신)
- 빨간 점 창(`selection_button.py`)은 절대 포커스를 뺏으면 안 된다(`WS_EX_NOACTIVATE|WS_EX_TOOLWINDOW`, 보일 때 `ShowWindow(SW_SHOWNOACTIVATE)`). 뺏으면 점을 누른 뒤의 Ctrl+C 가 글을 고른 앱이 아니라 점으로 가서 "선택 없음" 이 된다. Tk `attributes("-alpha"/"-transparentcolor")`·`deiconify()` 는 NOACTIVATE 를 지우거나 포커스를 가져가므로 쓰지 않는다.
- 마우스·키보드 훅 콜백은 가볍게: 판정(`SelectionGestureDetector`)·변수 바꾸기·`gui_queue.put` 만 한다. Tk 호출·파일 I/O·`log_to_console` 금지(윈도우가 느린 저수준 훅을 조용히 떼어 낸다 — `_make_selection_hook`).
- 빨간 점은 마우스 드래그·더블클릭으로 "선택했을 것" 을 추정해 띄운다(윈도우는 다른 앱의 선택 신호를 주지 않고, 점을 띄울지 판단하는 데에는 UI Automation 을 쓰지 않는다 — VS Code 를 얼린 전례). 한계: 창 제목 막대를 끌어도 뜬다(누르면 단축키처럼 그 창에 Ctrl+C 를 보낸다 — 전에 골라 둔 글이 남아 있으면 그 글을 읽고, 없으면 아무 일 없음), 키보드·Shift+클릭 선택엔 안 뜬다(단축키는 됨), 입력칸에서 고를 때도 뜬다.
- 선택 없이 단축키를 누르면: 읽는 중이면 멈춤, 아니면 아무것도 안 함(2026-09-28 사용자 결정). 빨간 점에서는 선택이 없어도 멈추지 않는다(확장 점은 읽기만 한다).
- 빨간 점 자리: 뗀 자리 오른쪽(+GAP), 모니터 작업 영역 안으로 끌어넣기. 끌어넣은 결과 점이 커서를 덮으면 커서 왼쪽(뗀 x − GAP − 점 크기)에 놓는다(2026-09-28 — 화면 오른쪽 끝 스크롤바를 끌고 놓은 뒤 다음 클릭이 점을 누르던 문제).
- **브라우저에서 비활성화**(2026-09-28 사용자 확정, 설정 키 `disable_in_browsers` 기본 true): 전경 창의 실행 파일이 `Aside.exe`·`whale.exe`·`chrome.exe`(대소문자 무시)면 빨간 점을 띄우지 않고 단축키로 새 읽기를 시작하지 않는다(Ctrl+C 도 안 보냄). 이 앱이 읽는 중이면 단축키는 멈춘다(막지 않음). `msedgewebview2.exe`(다른 앱 안의 웹 화면)는 브라우저가 아니다.
  판별(GetForegroundWindow → GetWindowThreadProcessId → OpenProcess(QUERY_LIMITED) → QueryFullProcessImageNameW)은 **Tk 메인에서만** 한다(`_handle_selection_button_msg`, `read_selected_text` 첫머리). 훅 콜백에서 하지 않는다.
- **원문 위 형광펜 규칙**(2026-09-28 사용자 확정): 읽기 시작(`speak_text`) 때 `SourceHighlighter.begin(원문, 조각, on_result)`. `on_result(ok=True)` → 원문 위에 칠하고 리더 창은 안 띄움. `ok=False` → "리더 창 사용" 이 켜져 있으면 리더 창. **결과를 기다리는 동안은 리더 창을 띄우지 않는다.** 소리는 결과를 기다리지 않는다. 전체를 끄는 설정 키 `source_highlight_enabled`(기본 true)는 트레이·설정 창에 넣지 않는다(사용자가 트레이 목록을 정했다).
- **UI Automation 금지 호출**(2026-09-28 VS Code 를 얼린 사고: 창 전체 요소를 FindAll 로 훑고 요소마다 패턴·GetVisibleRanges 호출): `GetVisibleRanges`, `DocumentRange` 전체의 `GetText`/`GetBoundingRectangles`, 창·문서 단위 `FindAll(Descendants)`. 한 호출이 1초를 넘으면 그 읽기 동안 원문 위 칠하기를 멈춘다. UIA 는 `source_highlight.py` 의 전용 스레드 하나에서만 부르고, `whisperer.py` 는 UIA 를 직접 부르지 않는다.
- 실측(2026-09-28, VS Code 채팅): TextPattern 은 메시지·문단 요소엔 없고 4단계 위 **Document 요소**(ControlType 50030)에만 있다. `GetCurrentPattern(UIA_TextPatternId).QueryInterface(IUIAutomationTextPattern)` 는 되고 `GetCurrentPatternAs` 는 실패했다. `RangeFromPoint` → `ExpandToEnclosingUnit(TextUnit_Line)` → `GetBoundingRectangles()` 가 1~2ms.
- TTS 재생 중 판정은 `tts_playing`으로 한다. `is_speaking`은 죽은 변수다.
- 읽기 세션의 멈춤 신호(`TtsSession._stop_event`)를 재사용하거나 `clear()` 하지 않는다(좀비 스레드 재발). 읽기마다 새 `TtsSession` 을 만든다(tts_engine.py 머리말).
- `sd.stop()`은 `sd.OutputStream`을 멈추지 못한다. 엔진은 `TtsSession.stop()` 안에서 `stream.abort()`로 멈춘다.
- 전처리 노이즈 정규식에 U+2200~22FF 범위를 넣지 않는다(마이너스 부호 U+2212 손실).
- `read_selected_text()`의 "Ctrl+C 전에 클립보드 비우기"를 유지한다. 없으면 선택이 없을 때 직전 클립보드를 읽는다.
- `on_release`의 수정키(Ctrl/Shift/Alt) 눌림 해제 코드는 TTS 단축키에 필요하다. 지우면 Shift가 눌린 채로 굳는다.

---

## Standards & References

### 코딩 컨벤션
- 파일 인코딩: UTF-8
- 코드 주석: 영어 또는 한국어 가능 (기존 스타일 유지)
- 함수/변수 네이밍: snake_case
- 전역 상태 변수: 파일 상단에서 `global` 선언 후 사용
- 로깅: `logging` 모듈 사용, `log_to_console()` 병행

### Git Operations Policy
- 원격 레포: `origin` = `git@github.com:comonetso/BluemingReadAloud.git` (SSH). 기본 브랜치: `main`.
- 중요한 작업(리팩토링, 대규모 수정) 시작 전 반드시 선(先) 커밋을 진행한다.
  - 커밋 전 반드시 사용자에게 커밋 메시지와 변경 범위를 제시하고 승인을 받는다.
- 커밋 메시지는 반드시 한글로, 목적이 드러나게 짧고 명확하게 작성한다.
  - 형식: `[타입] 작업 요약` (예: `[기능] TTS 음성 선택 기능 추가`)
  - 타입: `[기능]`, `[수정]`, `[리팩토링]`, `[문서]`, `[설정]`
- `.file_history/`가 생기면 `.gitignore`에 추가한다.

---

## Context Map (Action-Based Routing)

- **[메인 앱 로직](./whisperer.py)** -- 시스템 트레이, 단축키, 빨간 점 연결(전역 마우스 훅), 브라우저 판별, 읽기 연결, 형광펜(원문 위/리더 창) 선택, 설정 등 핵심 로직(파일명은 옛 이름 그대로).
- **[빨간 점](./selection_button.py)** -- 글을 고르면 선택 끝 옆에 뜨는 읽기 버튼(확장 `js/selection-button.js` 이식). 드래그·더블클릭 판정기 + 점 창.
- **[원문 위 형광펜](./source_highlight.py)** -- UI Automation 으로 전경 앱의 원문 줄 사각형을 얻어 그 위에 반투명 노란 막을 칠한다. 없거나 실패하면 리더 창으로.
- **[다국어 메시지](./messages.py)** -- 한국어/영어 UI 메시지 사전. 새 메시지 추가 시 ko/en 동시 작업 필수. 중첩 `ko`/`en` 블록은 지우지 않는다(`get_message`가 먼저 참조).
- **[사용자 설정](./whisperer_settings.json)** -- 런타임 설정(언어, 단축키, TTS 음성·속도·볼륨, 리더 창, 하단 바 모니터, 빨간 점 켬/끔, `disable_in_browsers`, `source_highlight_enabled`). gitignore됨. 옛 플로팅 키(`controller_*`)는 읽지 않고 다음 저장 때 빠진다.
- **[의존성 목록](./requirements.txt)** -- pip 패키지 목록. 새 패키지 추가 시 여기에 반영.
- **[빌드 설정](./BluemingReadAloud.spec)** -- PyInstaller 빌드 스펙(git 미추적). 최종 배포 시에만 사용.
- **[한국어 사용자 문서](./README.KR.md)** -- 최종 사용자용 한국어 설명서.
- **[영어 사용자 문서](./README.md)** -- 최종 사용자용 영어 설명서.
- **[TTS 구현 계획](./TTS_IMPLEMENTATION_PLAN.md)** -- 2025-12 시점의 옛 TTS 구현 계획(참고용).
- **[프로젝트 문서](./docs/)** -- 워크플로우 템플릿, 마스터 프롬프트, 세션 로그(`docs/session_logs/`).

---

## Architecture Quick Reference

### 파일 구조
```
BluemingReadAloud/
  whisperer.py              # 메인 앱 (트레이 + 단축키 + 빨간 점 연결 + 설정)
  selection_button.py       # 빨간 점(선택 버튼) — 드래그·더블클릭 판정 + 점 창
  tts_engine.py             # 재생 엔진 (TtsSession: 선합성·연속 재생·이동·정지)
  readaloud_text.py         # 읽기용 조각 나누기 + 원문 위치 (확장 이식)
  bottom_bar.py             # 하단 재생 컨트롤러
  reader_window.py          # 리더 창 (원문 + 읽는 줄 형광펜) — 원문 위에 칠할 수 없을 때만
  source_highlight.py       # 원문 위 형광펜 (UI Automation 전용 스레드 + 클릭 통과 막 창)
  tests/                    # unittest (python -m unittest discover -s tests)
  messages.py               # 다국어 메시지 모듈
  whisperer_settings.json   # 런타임 설정 (gitignore)
  requirements.txt          # pip 의존성
  google_credentials.json   # 옛 서비스 계정 키 — 2026-09-29 부터 안 씀 (gitignore)
  favicon.ico               # 앱 아이콘
  open_console.bat          # 콘솔 로그 모니터링 (콘솔 열기 때마다 앱이 다시 씀)
  BluemingReadAloud.spec    # PyInstaller 빌드 스펙 (gitignore)
  README.md / README.KR.md  # 사용자 문서
  recordings/               # STT 시절 녹음 파일 (gitignore, 임의 삭제 금지)
  logs/                     # 앱 로그 (gitignore)
  build/ / dist/            # 빌드 산출물 (gitignore)
  docs/                     # 참조 문서, 세션 로그
```

### 핵심 함수 맵 (whisperer.py)
- `main()` -- 앱 진입점, 모듈 로딩·인증 확인·키보드 훅·트레이·빨간 점(마우스 훅) 초기화
- `load_modules()` -- 의존성 로딩
- `setup_keyboard_listener()` -- 글로벌 핫키 등록 (on_press/on_release)
- `read_selected_text()` -- 선택 텍스트 읽기 (클립보드 비우기 + Ctrl+C) 및 읽기/중지/아무것도 안 함 3방향 분기
- `speak_text()` -- `readaloud_text.split_for_reading()`(줄 단위 조각 + 원문 위치) → 앞 읽기 정지 → `tts_engine.TtsSession` 시작
- `_handle_tts_event()` -- 엔진 알림(gui_queue 경유)을 받아 하단 바·형광펜(원문 위 또는 리더 창)을 움직인다
- `_begin_source_highlight()` / `_on_source_highlight_result()` / `_end_source_highlight()` -- 원문 위 형광펜 시작·결과(ok 면 원문 위, 아니면 리더 창)·끝
- `_foreground_disabled_browser()` / `toggle_disable_in_browsers()` -- 브라우저(Aside·웨일·크롬) 판별(Tk 메인 전용) / 트레이 켬·끔
- `stop_tts()` / `stop_current_playback()` -- 재생 중지 (`session.stop()` → 스트림 `abort()`)
- `setup_tray_icon()` -- 시스템 트레이 메뉴 구성(TTS 설정…·리더 창 사용·브라우저에서 비활성화·텍스트 선택 시 읽기 버튼·종료 다섯 개만), `check_gui_queue()` -- 스레드→GUI 통로(100ms 폴링)
- `setup_selection_button()` / `setup_mouse_listener()` / `toggle_selection_button()` -- 빨간 점 창·전역 마우스 훅 시작 / 트레이 켬·끔
- `_make_selection_hook()` -- 훅 스레드용 가벼운 판정(점 누름·우리 창 위 동작 거르기, gui_queue 로 보이기/숨기기)
- `show_api_key_dialog()` -- API 키 두 개(TTS·Gemini) 입력 UI. 저장 때 키마다 확인 요청 1회
- `show_tts_settings_dialog()` -- TTS 설정 UI (음성·미리듣기·속도·단축키 + 일반: 언어·인증 설정 버튼·콘솔 창 열기 버튼)
- `open_console_window()` / `_apply_language()` -- 콘솔 창 열기 / 언어 바꾸기(트레이 문구도 새 언어로)
- `save_settings()` / `load_settings()` -- JSON 설정 저장/로드

### 스레딩 구조
- 메인 스레드: tkinter GUI (`root` 숨김) + `check_gui_queue` 폴링
- 트레이 스레드: pystray
- 키보드 리스너 스레드: pynput (핸들러 안에서 I/O 금지, `root.after`로 넘김)
- 마우스 리스너 스레드: pynput (빨간 점 — 판정 후 `gui_queue.put` 만. 휠이면 `SourceHighlighter.notify_scroll()`(플래그만). 트레이에서 빨간 점을 끄면 내린다 → 그때는 휠 알림도 없다)
- 원문 위 형광펜 스레드: `source_highlight.py` 안의 UI Automation 전용 스레드 하나(결과는 `root.after` 로 Tk 메인에)
- TTS 스레드: 읽기마다 `tts-producer`(선합성, 최대 2조각 앞) + `tts-player`(재생) — `tts_engine.TtsSession`
- GUI 큐: `gui_queue`를 통한 스레드 간 안전한 UI 업데이트
