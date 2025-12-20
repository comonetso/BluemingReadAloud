**주식회사 엘마티 여기앤 서비스에서 2025년 03월17일에 개발자들이 Cursor AI 조금더 편리하게 사용하게 하기 위해 만들었습니다.**

# Yeogiaen STT Typer

Google Cloud Speech-to-Text V2 API를 사용하여 실시간으로 음성을 텍스트로 변환하는 가벼운 데스크톱 애플리케이션입니다. 빠른 음성 메모, 받아쓰기 및 접근성에 적합합니다.

## 주요 기능

- **간편한 음성 녹음**: 기본 단축키(Ctrl+Shift+Alt)를 누르면 녹음 시작, 아무 키나 떼면 녹음 중지
- **Google STT V2 통합**: 최신 Google Cloud 음성 인식 엔진을 사용하여 정확하고 빠른 변환 제공
- **대화 모드 설정**: 일반 대화 모드와 주소+POI 모드 등 상황에 맞는 최적의 인식 규칙 적용
- **인식 모델 선택**: long(긴 음성), short(짧은 명령어), telephony(전화) 등 최적화된 모델 선택 가능
- **클립보드 통합**: 변환된 텍스트를 자동으로 클립보드에 복사하고 붙여넣기
- **다국어 지원**: 한국어와 영어 인터페이스 제공 (메뉴 및 설정 포함)
- **사용자 정의 단축키**: 원하는 단축키로 변경 가능 (Windows 시스템 예약 단축키 제외)
- **시스템 트레이 통합**: 백그라운드에서 실행되며 시스템 트레이 아이콘으로 접근 가능
- **자동 녹음 저장**: 모든 녹음을 타임스탬프와 함께 FLAC 형식(16kHz)으로 저장

## 요구 사항

- Windows 운영 체제
- Google Cloud 서비스 계정 JSON 키 ([설정 가이드](https://cloud.google.com/speech-to-text/v2/docs/setup))
- API 액세스를 위한 인터넷 연결
- 마이크 장치 (기본 또는 선택 가능)

## 설치 방법

1. 릴리스 페이지에서 최신 버전을 다운로드
2. ZIP 파일을 원하는 위치에 압축 해제
3. `STT_Typer.exe` (또는 `whisperer.exe`) 실행
4. 메시지가 표시되면 Google Cloud 서비스 계정 JSON 파일을 선택 (최초 실행 시에만 필요)

## 사용 방법

1. 애플리케이션은 시스템 트레이 아이콘과 함께 백그라운드에서 실행됩니다
2. 설정된 단축키(기본: Ctrl+Shift+Alt)를 누르고 있으면 녹음이 시작됩니다
3. 마이크에 대고 명확하게 말하세요
4. 키 중 하나를 떼면 녹음이 중지되고 자동으로 텍스트로 변환됩니다
5. 변환된 텍스트는 자동으로 클립보드에 복사되고 현재 커서 위치에 붙여넣어집니다
6. 녹음된 파일은 'recordings' 폴더에 자동으로 저장됩니다

## 시스템 트레이 옵션

시스템 트레이 아이콘을 오른쪽 클릭하면 다음 옵션에 액세스할 수 있습니다:

- **녹음 파일 폴더 열기**: 모든 녹음된 오디오 파일이 있는 폴더를 엽니다
- **README 파일 열기**: 현재 언어에 맞는 도움말 문서를 엽니다
- **콘솔 창 열기**: 디버깅 및 로그 보기를 위한 콘솔 창을 엽니다
- **Google Cloud 인증 설정**: 서비스 계정 JSON 키 파일을 변경할 수 있습니다
- **대화 모드 설정**: 일반 대화 모드 또는 주소/POI 입력 모드 선택 (문장 부호 처리 등 차이)
- **인식 모델 설정**: Google STT 엔진 모델(long, short, telephony) 선택
- **단축키 설정**: 녹음 시작/종료 단축키를 변경할 수 있습니다
- **언어 변경**: 한국어와 영어 인터페이스 간 전환 (메뉴 전체가 해당 언어로 변경됨)
- **종료**: 애플리케이션 종료

## 참고 사항

- 애플리케이션은 Google Cloud STT V2 API를 사용하기 위해 인터넷 연결이 필요합니다
- 서비스 계정 JSON 키 파일은 프로그램 폴더로 복사되어 안전하게 관리됩니다
- 녹음은 `recordings` 폴더에 타임스탬프가 있는 파일 이름으로 FLAC 형식으로 저장됩니다
- 프로그램은 자동으로 중복 실행을 방지합니다
- 모든 로그는 'logs' 폴더에 저장되어 문제 해결에 도움을 줍니다

## 크레딧

이 애플리케이션은 다음을 사용합니다:
- Google Cloud Speech-to-Text V2 API (음성 인식)
- Python 라이브러리:
  - google-cloud-speech (Google STT 인증 및 호출)
  - sounddevice (오디오 녹음)
  - soundfile (오디오 파일 처리)
  - pynput (키보드 이벤트 처리)
  - pystray (시스템 트레이 아이콘)
  - tkinter (GUI 요소)

## 라이선스

이 프로젝트는 MIT 라이선스로 제공됩니다.




py whisperer.py

py -m PyInstaller Yeogiaen_WhisperTyper.spec --clean -y

py -m PyInstaller --onefile --windowed --icon=favicon.ico --add-data "favicon.ico;." --add-data "messages.py;." --add-data "README.md;." --add-data "README.KR.md;." --hidden-import "google.cloud.speech_v2" --hidden-import "grpc" --hidden-import "google.api_core" --name "Yeogiaen_STT_Typer" whisperer.py --clean -y