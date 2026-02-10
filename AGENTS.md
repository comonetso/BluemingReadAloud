# Yeogiaen STT Typer - AI 에이전트 거버넌스

## Project Context & Operations

### 비즈니스 목표
Google Cloud Speech-to-Text V2 및 Text-to-Speech를 활용한 Windows 데스크탑 음성 인식 타이핑 도구.
단축키로 음성 녹음 → 텍스트 변환 → 클립보드 자동 붙여넣기, 그리고 선택 텍스트 TTS 읽기를 제공한다.

### Tech Stack
- 언어: Python 3.13.5
- 플랫폼: Windows 데스크탑 (시스템 트레이 상주 앱)
- 음성인식: Google Cloud Speech-to-Text V2 API
- 음성합성: Google Cloud Text-to-Speech API (WaveNet)
- GUI: ttkbootstrap (tkinter 확장), pystray (시스템 트레이)
- 오디오: sounddevice, soundfile, numpy
- 입력: pynput (글로벌 핫키), pyperclip (클립보드)
- 빌드: PyInstaller
- 다국어: messages.py (한국어/영어)

### Operational Commands

개발 실행:
```bash
py whisperer.py
```
- 변경 후에는 실행 중인 프로세스를 수동 종료 후 재실행한다.
- Hot reload는 지원하지 않는다.

배포 빌드 (최종 마무리 시에만):
```bash
pyinstaller Yeogiaen_WhisperTyper.spec
```
또는 원파일 빌드:
```bash
pyinstaller --onefile --windowed --icon="favicon.ico" --add-data "messages.py;." --add-data "README.md;." --add-data "README.KR.md;." --add-data "favicon.ico;." --name "Yeogiaen_WhisperTyper" whisperer.py
```
- 빌드 결과물은 `dist/` 폴더에 생성된다.

의존성 설치:
```bash
py -m pip install -r requirements.txt
```

### 테스트
- 별도의 자동화 테스트 프레임워크(pytest 등)는 사용하지 않는다.
- 검증은 `py whisperer.py`로 실행하여 수동으로 확인한다.
- 테스트 목적의 임시 파일은 반드시 시스템 `/tmp` (Windows: `%TEMP%`)에 생성하고, 확인 후 삭제한다.

### 인증 및 민감 정보
- Google Cloud 서비스 계정 JSON 키: `google_credentials.json` (gitignore됨)
- 설정 파일: `whisperer_settings.json` (gitignore됨)
- 민감 파일은 절대 Git에 커밋하지 않는다.

---

## Golden Rules

### Immutable (절대 변경 불가)
- API 키, 서비스 계정 JSON 경로, 비밀번호를 코드에 하드코딩 금지.
- `google_credentials.json`, `whisperer_settings.json`, `openai_api_key.txt`는 절대 Git에 커밋하지 않는다.
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
- 다중 실행 방지 포트(51889)를 변경하지 않는다.
- `recordings/`, `logs/` 폴더의 사용자 데이터를 임의로 삭제하지 않는다.
- 빌드는 최종 마무리 시에만 수행하며, 개발 중에는 `py whisperer.py`로만 확인한다.

---

## Standards & References

### 코딩 컨벤션
- 파일 인코딩: UTF-8
- 코드 주석: 영어 또는 한국어 가능 (기존 스타일 유지)
- 함수/변수 네이밍: snake_case
- 전역 상태 변수: 파일 상단에서 `global` 선언 후 사용
- 로깅: `logging` 모듈 사용, `log_to_console()` 병행

### Git Operations Policy
- 원격 레포는 없으며, 로컬 Git으로만 관리한다.
- 기본 브랜치: `master`
- 중요한 작업(리팩토링, 대규모 수정) 시작 전 반드시 선(先) 커밋을 진행한다.
  - 커밋 전 반드시 사용자에게 커밋 메시지와 변경 범위를 제시하고 승인을 받는다.
- 커밋 메시지는 반드시 한글로, 목적이 드러나게 짧고 명확하게 작성한다.
  - 형식: `[타입] 작업 요약` (예: `[기능] TTS 음성 선택 기능 추가`)
  - 타입: `[기능]`, `[수정]`, `[리팩토링]`, `[문서]`, `[설정]`
- `.file_history/`가 생기면 `.gitignore`에 추가한다.

---

## Context Map (Action-Based Routing)

- **[메인 앱 로직](./whisperer.py)** -- 녹음, STT, TTS, 시스템 트레이, 설정 등 모든 핵심 로직. 약 3000줄의 단일 파일.
- **[다국어 메시지](./messages.py)** -- 한국어/영어 UI 메시지 사전. 새 메시지 추가 시 ko/en 동시 작업 필수.
- **[사용자 설정](./whisperer_settings.json)** -- 런타임 설정(언어, 단축키, TTS 음성 등). gitignore됨.
- **[의존성 목록](./requirements.txt)** -- pip 패키지 목록. 새 패키지 추가 시 여기에 반영.
- **[빌드 설정](./Yeogiaen_WhisperTyper.spec)** -- PyInstaller 빌드 스펙. 최종 배포 시에만 사용.
- **[한국어 사용자 문서](./README.KR.md)** -- 최종 사용자용 한국어 설명서.
- **[영어 사용자 문서](./README.md)** -- 최종 사용자용 영어 설명서.
- **[TTS 구현 계획](./TTS_IMPLEMENTATION_PLAN.md)** -- TTS 기능 추가 구현 로드맵.
- **[프로젝트 문서](./docs/)** -- 워크플로우 템플릿, 마스터 프롬프트 등 참조 문서.

---

## Architecture Quick Reference

### 파일 구조
```
Whisper Recoding/
  whisperer.py              # 메인 앱 (STT + TTS + 트레이 + 설정)
  messages.py               # 다국어 메시지 모듈
  whisperer_settings.json   # 런타임 설정 (gitignore)
  requirements.txt          # pip 의존성
  google_credentials.json   # Google Cloud 서비스 계정 키 (gitignore)
  favicon.ico               # 앱 아이콘
  open_console.bat          # 콘솔 로그 모니터링
  Yeogiaen_WhisperTyper.spec # PyInstaller 빌드 스펙
  README.md / README.KR.md  # 사용자 문서
  recordings/               # 녹음 파일 저장 (FLAC, gitignore)
  logs/                     # 앱 로그 (gitignore)
  build/ / dist/            # 빌드 산출물 (gitignore)
  docs/                     # 참조 문서
```

### 핵심 함수 맵 (whisperer.py)
- `main()` -- 앱 진입점, 모듈 로딩 및 초기화
- `load_modules_async()` / `load_modules()` -- 의존성 동적 로딩
- `setup_keyboard_listener()` -- 글로벌 핫키 등록 (on_press/on_release)
- `start_recording()` / `stop_recording()` -- 녹음 시작/종료 및 STT 처리
- `ensure_google_client()` -- Google STT 클라이언트 초기화
- `google_stt_streaming_thread()` -- 실시간 스트리밍 STT
- `speak_text()` / `stop_tts()` / `play_tts_file()` -- TTS 재생 관련
- `read_selected_text()` -- 선택 텍스트 읽기 (Ctrl+C 트릭)
- `process_address_format()` -- 주소 모드 후처리
- `setup_tray_icon()` -- 시스템 트레이 메뉴 구성
- `show_api_key_dialog()` -- Google 인증 파일 선택 UI
- `show_stt_settings_dialog()` / `show_tts_settings_dialog()` -- 설정 UI
- `save_settings()` / `load_settings()` -- JSON 설정 저장/로드

### 스레딩 구조
- 메인 스레드: tkinter GUI + 시스템 트레이
- 녹음 스레드: sounddevice 오디오 캡처
- STT 스레드: Google Cloud API 스트리밍 요청
- TTS 스레드: 음성 합성 및 재생
- GUI 큐: `gui_queue`를 통한 스레드 간 안전한 UI 업데이트
