# BluemingReadAloud - AI 에이전트 거버넌스

## Project Context & Operations

### 비즈니스 목표
Google Cloud Text-to-Speech를 활용한 Windows 데스크탑 **읽어주기(TTS) 전용** 도구.
어느 프로그램에서든 글을 선택하고 단축키(또는 플로팅 아이콘)를 누르면 선택한 글을 읽어 준다.
크롬 확장 `F:\workspace\EtcProject\ChromeExtentions\read-aloud-hrg` 처럼 동작하는 것이 목표다.
(옛 이름 "Yeogiaen STT Typer". 받아쓰기(STT) 기능은 걷어냈다.)

개발 중(아직 없음): 형광펜(읽는 부분을 줄 단위로 칠하기 — 원문 위, 안 되면 리더 창), 하단 재생 컨트롤러.

### Tech Stack
- 언어: Python 3.13.5
- 플랫폼: Windows 데스크탑 (시스템 트레이 상주 앱)
- 음성합성: Google Cloud Text-to-Speech API v1 (기본 음성 `ko-KR-Chirp3-HD-Callirrhoe`)
- 인증: Google Cloud 서비스 계정 JSON (`google_credentials.json`)
- GUI: ttkbootstrap (tkinter 확장), pystray (시스템 트레이), Win32(ctypes) 플로팅 아이콘
- 오디오: sounddevice (`OutputStream` 연속 재생), numpy, winsound (비프음)
- 입력: pynput (글로벌 핫키, Ctrl+C 입력), pyperclip (클립보드)
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
- Google Cloud 서비스 계정 JSON 키: `google_credentials.json` (gitignore됨). 인증 창에서 고른 파일을 앱 폴더에 이 이름으로 복사한다.
- 설정 파일: `whisperer_settings.json` (gitignore됨)
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

### TTS·플로팅 함정 규칙 (2026-06-07, 2026-07-27 세션 로그에서 옮김)
- 플로팅 아이콘 표시/숨김은 반드시 `set_controller_visible()` 한 곳으로만 바꾼다. 직접 `withdraw`/`deiconify` 하면 트레이 라벨·설정 저장이 어긋난다.
- `update_state()`의 숨김 가드를 제거하지 않는다. 3초마다 도는 `lift()`가 숨긴 창을 되살린다.
- TTS 재생 중 판정은 `tts_playing`으로 한다. `is_speaking`은 죽은 변수다.
- `_speak`의 `finally`에서 `tts_stop_event.clear()`를 절대 추가하지 않는다(좀비 스레드 재발). clear는 다음 `_speak` 시작부에서 한다.
- 트레이 메뉴의 "플로팅 아이콘 보이기" 항목은 비상 복구 탈출구다. 제거 금지(숨김 상태가 영구 저장되기 때문).
- `sd.stop()`은 `sd.OutputStream`을 멈추지 못한다. `tts_output_stream.abort()`로 멈춘다.
- 전처리 노이즈 정규식에 U+2200~22FF 범위를 넣지 않는다(마이너스 부호 U+2212 손실).
- `read_selected_text()`의 "Ctrl+C 전에 클립보드 비우기"를 유지한다. 없으면 선택이 없을 때 직전 클립보드를 읽는다.
- `on_release`의 수정키(Ctrl/Shift/Alt) 눌림 해제 코드는 TTS 단축키에 필요하다. 지우면 Shift가 눌린 채로 굳는다.
- 플로팅 창은 `WS_EX_NOACTIVATE`라 포커스를 못 받는다. 팝업 메뉴는 `root`의 자식으로 만들고, 메뉴가 떠 있는 동안 `lift()`를 멈춘다(`menu_open`).

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

- **[메인 앱 로직](./whisperer.py)** -- TTS, 시스템 트레이, 플로팅 아이콘, 단축키, 설정 등 모든 핵심 로직. 단일 파일(파일명은 옛 이름 그대로).
- **[다국어 메시지](./messages.py)** -- 한국어/영어 UI 메시지 사전. 새 메시지 추가 시 ko/en 동시 작업 필수. 중첩 `ko`/`en` 블록은 지우지 않는다(`get_message`가 먼저 참조).
- **[사용자 설정](./whisperer_settings.json)** -- 런타임 설정(언어, 단축키, TTS 음성·속도, 플로팅 위치·숨김). gitignore됨.
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
  whisperer.py              # 메인 앱 (TTS + 트레이 + 플로팅 + 설정)
  messages.py               # 다국어 메시지 모듈
  whisperer_settings.json   # 런타임 설정 (gitignore)
  requirements.txt          # pip 의존성
  google_credentials.json   # Google Cloud 서비스 계정 키 (gitignore)
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
- `main()` -- 앱 진입점, 모듈 로딩·인증 확인·리스너·트레이·플로팅 초기화
- `load_modules()` -- 의존성 로딩
- `setup_keyboard_listener()` -- 글로벌 핫키 등록 (on_press/on_release)
- `read_selected_text()` -- 선택 텍스트 읽기 (클립보드 비우기 + Ctrl+C) 및 읽기/중지/플로팅 토글 3방향 분기
- `speak_text()` -- 전처리 → 청크 분할 → `_speak` 스레드 시작
- `_preprocess_for_tts()` / `_chunk_text_for_tts()` / `_synthesize_chunk()` -- 읽기용 정리, 청크 분할, 청크 합성
- `stop_tts()` / `stop_current_playback()` -- 재생 중지 (`tts_output_stream.abort()`)
- `setup_tray_icon()` -- 시스템 트레이 메뉴 구성, `check_gui_queue()` -- 스레드→GUI 통로(100ms 폴링)
- `setup_floating_controller()` / `set_controller_visible()` -- 플로팅 아이콘 생성 / 표시·숨김 단일 경로
- `show_api_key_dialog()` -- Google 인증 파일 선택 UI
- `show_tts_settings_dialog()` -- TTS 설정 UI (음성·미리듣기·속도·단축키)
- `save_settings()` / `load_settings()` -- JSON 설정 저장/로드

### 스레딩 구조
- 메인 스레드: tkinter GUI (`root` 숨김) + `check_gui_queue` 폴링
- 트레이 스레드: pystray
- 키보드 리스너 스레드: pynput (핸들러 안에서 I/O 금지, `root.after`로 넘김)
- TTS 스레드: `_speak` consumer(재생) + producer(선합성, `Queue(maxsize=2)`)
- GUI 큐: `gui_queue`를 통한 스레드 간 안전한 UI 업데이트
