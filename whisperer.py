#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Powered by HRG

"""
STT Typer - 음성 인식 및 텍스트 변환 프로그램
Copyright (c) 2024 Yeogiaen

원래 OpenAI Whisper를 사용하였으나, Google Cloud STT V2로 변경됨
"""
import sys, os
import threading
import time
import datetime
import json
import tkinter as tk
from tkinter import messagebox
import logging
import socket
import winsound  # winsound import 추가 확인
import re # 정규식 모듈 임포트
import queue # 스트리밍용 큐 임포트

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def get_app_dir():
    """실행 파일 또는 스크립트가 있는 실제 디렉토리 경로를 반환합니다."""
    if getattr(sys, 'frozen', False):
        # PyInstaller로 패키징된 경우
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# 메시지 모듈 가져오기
from messages import messages, get_message

# 언어 설정 (기본값: 한국어)
current_language = "ko"  # "ko" 또는 "en"
auto_language_detection = False  # 언어 자동 감지 사용 여부
# API 키 단축키 변수
api_key_shortcut = False

# 전역 변수
recording = False
audio_data = []
stream = None
force_clipboard = False
ctrl_pressed = False
shift_pressed = False
alt_pressed = False
recording_started_with_combo = False
selected_device = None  # 선택된 마이크 장치
default_device = None   # 기본 마이크 장치
root = None             # Tk 창
status_label = None     # 상태 표시 레이블
tray_icon = None        # 트레이 아이콘
console_log_file = None # 콘솔 로그 파일
api_key = None          # OpenAI API 키
keyboard_listener = None # 키보드 리스너
pynput_initialized = False # Pynput 초기화 여부

# 성능 최적화 관련 변수
use_performance_mode = True   # 성능 최적화 모드 사용 여부
optimize_audio_quality = True  # 오디오 파일 최적화 여부
parallel_processing = True    # 병렬 처리 사용 여부
audio_preload_thread = None   # 오디오 사전 처리 스레드

# 중요 모듈들은 비동기적으로 나중에 로드
openai = None
openai_client = None
pyperclip = None
sd = None
np = None
soundfile = None
winsound = None
has_tray_support = False
has_pyaudio = False
pystray = None
Image = None
ImageDraw = None
Listener = None
Controller = None
Key = None
KeyCode = None

# Google Cloud STT 관련 변수
google_speech = None
google_stt_client = None
google_credentials_path = None  # 인증용 JSON 키 경로
google_project_id = None         # 구글 프로젝트 ID
google_stt_model = "long"  # 기본 모델
audio_queue = queue.Queue() # 실시간 스트리밍용 오디오 큐
is_streaming = False      # 스트리밍 활성화 플래그
streaming_transcript = "" # 실시간 인식 최종 확정 결과 저장용
latest_interim_transcript = "" # 실시간 인식 최신 중간 결과 저장용 (is_final 이전)
streaming_thread = None   # 실시간 STT 스레드 저장용

# Google Cloud TTS 관련 변수
google_tts = None
google_tts_client = None
tts_hotkey_modifiers = {"ctrl": True, "shift": False, "alt": True} # 기본 TTS 단축키: Ctrl+Alt+D
tts_hotkey_key = "D"
is_speaking = False       # TTS 재생 중 플래그
tts_voice_name = "ko-KR-Wavenet-A"  # 기본 음성 모델
tts_speaking_rate = 1.0   # 재생 속도 (0.25 ~ 4.0, 기본 1.0)
current_audio_stream = None  # 현재 재생 중인 오디오 스트림

# 사용 가능한 한국어 TTS 음성 목록 (이름, 성별, 유형, 설명)
KOREAN_VOICES = [
    ("ko-KR-Wavenet-A", "여성", "WaveNet", "밝고 친근한 여성 목소리"),
    ("ko-KR-Wavenet-B", "여성", "WaveNet", "부드럽고 차분한 여성 목소리"),
    ("ko-KR-Wavenet-C", "남성", "WaveNet", "신뢰감 있는 남성 목소리"),
    ("ko-KR-Wavenet-D", "남성", "WaveNet", "젊고 활기찬 남성 목소리"),
    ("ko-KR-Neural2-A", "여성", "Neural2", "자연스러운 여성 목소리"),
    ("ko-KR-Neural2-B", "여성", "Neural2", "편안한 여성 목소리"),
    ("ko-KR-Neural2-C", "남성", "Neural2", "전문적인 남성 목소리"),
    ("ko-KR-Standard-A", "여성", "Standard", "기본 여성 목소리 (저비용)"),
    ("ko-KR-Standard-B", "여성", "Standard", "표준 여성 목소리 (저비용)"),
    ("ko-KR-Standard-C", "남성", "Standard", "기본 남성 목소리 (저비용)"),
    ("ko-KR-Standard-D", "남성", "Standard", "표준 남성 목소리 (저비용)"),
]

# 단축키 전역 변수 추가 (파일 상단 전역 변수 섹션에 추가)
hotkey_modifiers = {"ctrl": True, "shift": True, "alt": True}  # 기본 단축키: Ctrl+Shift+Alt
hotkey_key = None  # 추가 키 없음

# 프로그램 다중 실행 방지
def prevent_multiple_instances():
    """프로그램의 다중 실행을 방지합니다"""
    try:
        # 소켓을 생성하여 특정 포트에 바인딩 시도
        global single_instance_socket
        single_instance_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # 테스트를 위해 다른 포트 사용 (원래 포트: 51888)
        test_port = 51889 # 테스트용 다른 포트 사용
        single_instance_socket.bind(('localhost', test_port))
        logging.info("프로그램 실행: 테스트 인스턴스 (포트 변경)")
        return True  # 첫 번째 인스턴스
    except socket.error:
        logging.warning("프로그램이 이미 실행 중입니다. 중복 실행을 방지합니다.")
        # 이미 실행 중인 프로그램이 있으면 메시지 표시 후 종료
        if not hasattr(sys, 'frozen'):  # 개발 모드에서는 경고만 표시
            print("프로그램이 이미 실행 중입니다.")
        else:  # 배포 버전에서는 GUI 메시지 표시
            try:
                root = tk.Tk()
                root.withdraw()
                messagebox.showwarning(
                    "Yeogiaen WhisperTyper",
                    "프로그램이 이미 실행 중입니다.\n시스템 트레이에서 프로그램 아이콘을 확인하세요."
                )
                root.destroy()
            except:
                pass
        return False  # 이미 다른 인스턴스가 실행 중

# 나중에 필요할 때 모듈 로딩
def load_modules_async():
    """필요한 모듈을 비동기적으로 로딩"""
    global openai, openai_client, pyperclip, sd, np, soundfile, winsound, pystray, Image, ImageDraw
    global Listener, Controller, Key, KeyCode, has_tray_support, has_pyaudio
    global api_session

    try:
        import openai
        logging.info("OpenAI 모듈 로딩 완료")

        # requests 모듈 로딩 및 세션 초기화 시도
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            # 최적화된 세션 설정
            api_session = requests.Session()

            # 재시도 전략 설정
            retry_strategy = Retry(
                total=3,                    # 최대 재시도 횟수
                backoff_factor=0.3,         # 재시도 간 대기 시간 증가 인자
                status_forcelist=[429, 500, 502, 503, 504],  # 재시도할 HTTP 상태 코드
                allowed_methods=["POST"]    # POST 요청에 대해서만 재시도
            )

            # 연결 풀 설정으로 세션 최적화
            adapter = HTTPAdapter(
                pool_connections=4,          # 영구적 연결 유지 수
                pool_maxsize=10,            # 최대 연결 수
                max_retries=retry_strategy  # 재시도 전략
            )

            # HTTPS 연결에 어댑터 설정
            api_session.mount('https://', adapter)
            logging.info("API 세션 최적화 설정 완료")

        except ImportError as e:
            logging.error(f"Requests 모듈 로딩 실패: {str(e)}")
            api_session = None
    except ImportError as e:
        logging.error(f"OpenAI 모듈 로딩 실패: {str(e)}")

    try:
        import pyperclip
        logging.info("Pyperclip 모듈 로딩 완료")
    except ImportError as e:
        logging.error(f"Pyperclip 모듈 로딩 실패: {str(e)}")

    try:
        import sounddevice as sd
        import numpy as np
        logging.info("Sounddevice 및 Numpy 모듈 로딩 완료")
    except ImportError as e:
        logging.error(f"Sounddevice 또는 Numpy 모듈 로딩 실패: {str(e)}")

    try:
        import soundfile
        logging.info("Soundfile 모듈 로딩 완료")
    except ImportError as e:
        logging.error(f"Soundfile 모듈 로딩 실패: {str(e)}")

    try:
        import winsound
        logging.info("Winsound 모듈 로딩 완료")
    except ImportError as e:
        logging.error(f"Winsound 모듈 로딩 실패: {str(e)}")

    try:
        import pystray
        from PIL import Image, ImageDraw
        has_tray_support = True
        logging.info("Pystray 및 PIL 모듈 로딩 완료")
    except ImportError as e:
        has_tray_support = False
        logging.error(f"Pystray 또는 PIL 모듈 로딩 실패: {str(e)}")

    try:
        from pynput.keyboard import Listener, Controller, Key, KeyCode
        logging.info("Pynput 모듈 로딩 완료")
    except ImportError as e:
        logging.error(f"Pynput 모듈 로딩 실패: {str(e)}")
        log_to_console("오류: 키보드 감지 모듈을 로드할 수 없습니다.")
        return False

    try:
        import pyaudio
        has_pyaudio = True
        logging.info("PyAudio 모듈 로딩 완료")
    except ImportError:
        has_pyaudio = False
        logging.info("PyAudio 모듈 없음, 기본 오디오 시스템 사용")

    # Google Cloud STT V2 모듈 로딩
    global google_speech, google_stt_client, google_credentials_path, google_project_id
    try:
        from google.cloud import speech_v2 as google_speech_module
        google_speech = google_speech_module
        logging.info("Google Cloud Speech V2 모듈 로딩 완료")

        # 인증 파일이 설정되어 있으면 클라이언트 초기화
        if google_credentials_path and os.path.exists(google_credentials_path):
            try:
                # JSON에서 project_id 추출
                with open(google_credentials_path, 'r', encoding='utf-8') as f:
                    creds_data = json.load(f)
                    google_project_id = creds_data.get('project_id')

                # 클라이언트 초기화
                google_stt_client = google_speech.SpeechClient.from_service_account_file(
                    google_credentials_path
                )

                # Google Cloud TTS 모듈 및 클라이언트 초기화
                global google_tts, google_tts_client
                try:
                    from google.cloud import texttospeech
                    google_tts = texttospeech
                    google_tts_client = google_tts.TextToSpeechClient.from_service_account_file(
                        google_credentials_path
                    )
                    logging.info("Google Cloud TTS 클라이언트 초기화 완료")
                    print("[TTS] Google Cloud TTS 클라이언트 초기화 성공!")
                except Exception as tts_e:
                    logging.error(f"Google Cloud TTS 초기화 실패: {tts_e}")
                    print(f"[TTS] Google Cloud TTS 초기화 실패: {tts_e}")

                # 클래스 참조 로드
                global StreamingRecognizeRequest, StreamingRecognitionConfig, RecognitionConfig
                global RecognitionFeatures, StreamingRecognitionFeatures, AutoDetectDecodingConfig, RecognizeRequest
                StreamingRecognizeRequest = google_speech.StreamingRecognizeRequest
                StreamingRecognitionConfig = google_speech.StreamingRecognitionConfig
                RecognitionConfig = google_speech.RecognitionConfig
                RecognitionFeatures = google_speech.RecognitionFeatures
                StreamingRecognitionFeatures = google_speech.StreamingRecognitionFeatures
                AutoDetectDecodingConfig = google_speech.AutoDetectDecodingConfig
                RecognizeRequest = google_speech.RecognizeRequest

                logging.info(f"Google Cloud STT 클라이언트 및 클래스 로드 완료 (프로젝트: {google_project_id})")
            except Exception as e:
                logging.error(f"Google Cloud STT 클라이언트 초기화 오류: {str(e)}")
    except ImportError as e:
        logging.warning(f"Google Cloud Speech 모듈 없음: {str(e)}")

# Tkinter 라벨 업데이트를 위한 안전한 함수
def set_status(text):
    """상태 라벨 업데이트를 스레드 안전하게 처리"""
    global status_label
    if status_label and status_label.winfo_exists():
        try:
            status_label.config(text=text)
            status_label.update()
        except Exception as e:
            logging.error(f"상태 업데이트 오류: {str(e)}")

# 마이크 초기화를 비동기적으로 수행
def init_microphone_async():
    """마이크 초기화를 비동기적으로 수행"""
    global sd, selected_device, default_device

    if not sd:
        logging.warning("Sounddevice 모듈이 로드되지 않아 마이크 초기화를 건너뜁니다.")
        return

    try:
        # 현재 자동 감지된 기본 장치
        default_device_idx = sd.default.device[0]  # 기본 입력 장치 인덱스

        # 사용 가능한 오디오 장치 목록 가져오기
        devices = sd.query_devices()
        logging.info(f"사용 가능한 오디오 장치: {len(devices)}개 감지됨")

        # 입력 장치 필터링 (마이크만)
        input_devices = []
        for idx, device in enumerate(devices):
            try:
                if device['max_input_channels'] > 0:
                    logging.info(f"입력 장치 #{idx}: {device['name']} (채널: {device['max_input_channels']})")
                    input_devices.append((idx, device))
            except KeyError:
                continue

        if not input_devices:
            logging.error("사용 가능한 입력 장치(마이크)가 없습니다.")
            return

        # 기본 입력 장치 정보 로깅
        try:
            default_device_info = sd.query_devices(kind='input')
            default_device = default_device_idx
            logging.info(f"기본 입력 장치: {default_device_info['name']} (장치 번호: {default_device})")

            # 첫 번째 실행 시 기본 장치를, 아니면 이전에 사용한 장치 계속 사용
            if selected_device is None:
                selected_device = default_device
                logging.info(f"기본 마이크로 선택됨: {default_device_info['name']}")

        except Exception as e:
            logging.error(f"기본 입력 장치 정보 가져오기 오류: {str(e)}")

            # 기본 장치가 없으면 첫 번째 이용 가능한 입력 장치 사용
            if input_devices:
                idx, device = input_devices[0]
                selected_device = idx
                logging.info(f"첫 번째 가용 마이크로 선택됨: {device['name']} (장치 번호: {idx})")

        # 마이크 작동 테스트 (짧은 스트림 생성해보기)
        try:
            if selected_device is not None:
                logging.info(f"마이크 연결 테스트 중 (장치 #{selected_device})...")
                test_stream = sd.InputStream(device=selected_device, channels=1, samplerate=16000)
                test_stream.start()
                time.sleep(0.1)  # 짧게 테스트
                test_stream.stop()
                test_stream.close()
                logging.info("마이크 연결 테스트 성공")
        except Exception as e:
            logging.error(f"마이크 연결 테스트 실패: {str(e)}")
            # 실패해도 계속 진행 (실제 녹음 시 다시 시도)

    except Exception as e:
        logging.error(f"마이크 초기화 오류: {str(e)}")
        log_to_console(f"마이크 초기화 오류: {str(e)}")
        # 실패해도 계속 진행

# 성능 최적화 기능 초기화 함수
def initialize_performance_optimization():
    """오디오 처리와 API 호출 가속화를 위한 성능 최적화 기능을 초기화합니다."""
    global openai, openai_client, api_key, use_performance_mode, optimize_audio_quality, parallel_processing

    if not openai or not api_key:
        logging.error("성능 최적화 시도 실패: OpenAI 모듈 또는 API 키가 없습니다.")
        log_to_console("성능 최적화 시도 실패: API 키가 없습니다.")
        return False

    try:
        # OpenAI 클라이언트 초기화
        openai_client = openai.OpenAI(api_key=api_key)
        log_to_console("=== 성능 최적화 기능 초기화 시작 ===")

        # 1. 오디오 처리 최적화 설정
        if np and soundfile:
            # 오디오 처리 관련 모듈이 있을 경우 최적화 적용
            optimize_audio_quality = True
            log_to_console("오디오 전처리 최적화 기능 활성화")
        else:
            # 필요한 모듈이 없을 경우 최적화 끄기
            optimize_audio_quality = False
            log_to_console("오디오 처리 모듈이 없어 오디오 최적화를 사용할 수 없습니다.")

        # 2. 병렬 처리 설정
        parallel_processing = True
        log_to_console("병렬 처리 기능 활성화")

        # 3. 오프라인 모듈 테스트 (whisper 오프라인 모듈 여부 확인)
        try:
            import pkg_resources
            whisper_offline_available = "whisper" in [pkg.key for pkg in pkg_resources.working_set]
            if whisper_offline_available:
                log_to_console("오프라인 Whisper 모듈 감지: 중복 처리 가능")
            else:
                log_to_console("오프라인 Whisper 모듈 없음: 온라인 API만 사용")
        except:
            # 확인이 실패해도 진행
            log_to_console("오프라인 모듈 확인 불가")

        # 4. OpenAI API 테스트
        try:
            # 간단한 API 테스트로 연결 확인
            test_response = openai_client.models.list()
            if test_response:
                log_to_console("OpenAI API 연결 테스트 성공")
        except Exception as api_e:
            log_to_console(f"OpenAI API 테스트 오류: {str(api_e)}")
            # 오류가 있어도 계속 진행

        # 성능 최적화 모드 활성화
        use_performance_mode = True

        # 5. 사전 워밍업 - 처음 호출 시 딜레이를 줄이기 위해 API를 미리 호출
        try:
            log_to_console("사전 워밍업: 초기 호출 지연 최소화")
            # 별도 스레드에서 비어있는 API 호출
            threading.Thread(target=lambda: preload_api(), daemon=True).start()
        except:
            # 실패해도 계속 진행
            pass

        log_to_console("=== 성능 최적화 기능 초기화 완료 ===")
        logging.info("성능 최적화 기능 활성화 - 응답 시간이 개선될 것입니다.")
        log_to_console("성능 최적화 모드가 활성화되었습니다. 응답 시간이 개선될 것입니다.")
        return True

    except Exception as e:
        logging.error(f"성능 최적화 초기화 중 오류: {str(e)}")
        log_to_console(f"성능 최적화 초기화 실패: {str(e)}")
        use_performance_mode = False
        return False

# API 사전 워밍업 함수
def preload_api():
    """처음 API 호출시 지연을 줄이기 위해 비어있는 API 호출을 수행합니다."""
    try:
        # API가 잠자기 모드에서 깨어나도록 가벽게 호출
        if openai_client:
            openai_client.models.list()
            logging.info("API 사전 워밍업 완료")
    except Exception as e:
        logging.error(f"API 사전 워밍업 중 오류: {str(e)}")
        # 오류가 있어도 무시 - 실패해도 되도록 하는 것일 뿐

# 기본 로깅 설정
def setup_logging():
    """로깅 설정"""
    global console_log_file

    # 로그 파일 이름 설정
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    # 로그 디렉토리 확인
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 로그 파일 경로
    log_file = os.path.join(log_dir, f"whisperer_{timestamp}.log")
    console_log_file = "whisperer_console.log"

    # 로그 포맷 설정
    log_format = '%(asctime)s - %(levelname)s - %(message)s'

    # 기본 로거 설정
    logging.basicConfig(
        level=logging.DEBUG, # DEBUG로 변경하여 모든 로그 확인
        format=log_format,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    # 콘솔 로그 초기화
    try:
        with open(console_log_file, 'w', encoding='utf-8') as f:
            f.write(f"=== Whisperer 로그 시작: {timestamp} ===\n\n")

        # 시작 로그 기록
        log_to_console("=== Yeogiaen WhisperTyper 콘솔 ===")
        log_to_console("이 창을 닫아도 프로그램은 계속 실행됩니다.")
        log_to_console("\n로그 출력을 시작합니다...\n")

        logging.info("로깅 시스템 초기화 완료")
    except Exception as e:
        logging.error(f"로그 파일 초기화 오류: {str(e)}")

# 콘솔 로그 기록 함수
def log_to_console(message):
    """콘솔 로그 파일에 메시지 기록"""
    global console_log_file

    # 콘솔에 출력
    print(message)

    # 파일에 기록
    if console_log_file:
        try:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            with open(console_log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            print(f"로그 기록 오류: {str(e)}")

def main():
    # README 파일 추출
    extract_readme_files()

    # 현재 언어 설정 표시
    lang_name = "English" if current_language == 'en' else "한국어"
    print(f"Current language: {lang_name}")

    try:
        print("프로그램 시작 중...")
        print("============================")
        print("= Yeogiaen STT Typer =")
        print("============================")

        # 로깅 설정
        setup_logging()
        logging.info("애플리케이션 시작")
        log_to_console("로깅 시스템 초기화 완료")

        # Tkinter 루트 창 생성 (숨김)
        global root
        root = tk.Tk()
        root.withdraw()  # 창 숨기기
        root.title("Yeogiaen STT Typer")

        # 모듈 로딩
        print("주요 모듈 로딩 중...")
        load_modules()
        log_to_console("모듈 로딩 완료")

        # 마이크 초기화 (명시적 호출)
        print("마이크 초기화 중...")
        log_to_console("마이크 초기화 중...")
        init_microphone_async()

        # 설정 로드 (언어, 단축키 등)
        load_settings()
        logging.info(f"현재 언어: {current_language}")
        # 현재 언어 설정을 콘솔에 표시
        language_name = "한국어" if current_language == "ko" else "English"
        log_to_console(f"현재 언어 설정: {language_name} ({current_language})")

        # 현재 단축키 설정 로그
        hotkey_str = []
        if hotkey_modifiers.get("ctrl", False):
            hotkey_str.append("Ctrl")
        if hotkey_modifiers.get("shift", False):
            hotkey_str.append("Shift")
        if hotkey_modifiers.get("alt", False):
            hotkey_str.append("Alt")
        if hotkey_key:
            hotkey_str.append(hotkey_key)

        hotkey_display = "+".join(hotkey_str)
        log_to_console(f"현재 단축키 설정: {hotkey_display}")

        # 녹음 폴더 생성
        recordings_dir = "recordings"
        if not os.path.exists(recordings_dir):
            os.makedirs(recordings_dir)
            log_to_console(f"녹음 폴더 생성됨: {recordings_dir}")

        # Google Cloud 인증 확인 및 설정
        print("Google Cloud 인증 확인 중...")
        log_to_console("Google Cloud 인증 확인 중...")

        # 설정에서 경로를 이미 로드했으므로, 클라이언트 초기화 시도
        global google_stt_client, google_project_id, google_tts, google_tts_client
        if google_credentials_path and os.path.exists(google_credentials_path):
            try:
                # 클라이언트가 아직 초기화 안 됐으면 초기화
                if not google_stt_client and google_speech:
                    with open(google_credentials_path, 'r', encoding='utf-8') as f:
                        creds_data = json.load(f)
                        google_project_id = creds_data.get('project_id')
                    google_stt_client = google_speech.SpeechClient.from_service_account_file(google_credentials_path)
                    log_to_console(f"Google Cloud STT 클라이언트 초기화 완료 (프로젝트: {google_project_id})")

                    # TTS 클라이언트도 초기화
                    log_to_console("[TTS] TTS 클라이언트 초기화 시도 중...")
                    try:
                        from google.cloud import texttospeech
                        google_tts = texttospeech
                        google_tts_client = google_tts.TextToSpeechClient.from_service_account_file(google_credentials_path)
                        log_to_console("[TTS] Google Cloud TTS 클라이언트 초기화 성공!")
                        logging.info("Google Cloud TTS 클라이언트 초기화 완료")
                    except Exception as tts_err:
                        log_to_console(f"[TTS] TTS 클라이언트 초기화 실패: {tts_err}")
                        logging.error(f"TTS 클라이언트 초기화 실패: {tts_err}")
                elif google_stt_client:
                    log_to_console("Google Cloud 인증 로드 완료")
                    # STT는 있는데 TTS가 없으면 TTS만 초기화
                    if not google_tts_client:
                        log_to_console("[TTS] TTS 클라이언트 초기화 시도 중...")
                        try:
                            from google.cloud import texttospeech
                            google_tts = texttospeech
                            google_tts_client = google_tts.TextToSpeechClient.from_service_account_file(google_credentials_path)
                            log_to_console("[TTS] Google Cloud TTS 클라이언트 초기화 성공!")
                            logging.info("Google Cloud TTS 클라이언트 초기화 완료")
                        except Exception as tts_err:
                            log_to_console(f"[TTS] TTS 클라이언트 초기화 실패: {tts_err}")
                            logging.error(f"TTS 클라이언트 초기화 실패: {tts_err}")
            except Exception as e:
                logging.error(f"Google Cloud 인증 오류: {str(e)}")
                log_to_console(f"Google Cloud 인증 오류: {str(e)}")
                show_api_key_dialog(required=True)
        else:
            logging.warning("Google Cloud 인증 파일이 없습니다.")
            log_to_console("Google Cloud 인증 파일이 없습니다. 설정 창을 표시합니다.")
            show_api_key_dialog(required=True)

        # 키보드 리스너 설정
        print("키보드 리스너 설정 중...")
        log_to_console("키보드 리스너 설정 중...")
        setup_keyboard_listener()

        # 시스템 트레이 아이콘 설정
        print("시스템 트레이 아이콘 설정 중...")
        log_to_console("시스템 트레이 아이콘 설정 중...")
        setup_tray_icon()

        # 초기화 완료
        logging.info("초기화 완료")
        print("\n프로그램이 시스템 트레이에서 실행 중입니다.")
        log_to_console("===================================")
        log_to_console("프로그램이 실행 중입니다.")
        log_to_console("시스템 트레이에서 아이콘을 확인하세요.")
        log_to_console("단축키: Ctrl+Shift+Alt (눌렀다 떼면 녹음 시작/종료)")
        log_to_console("===================================")

        # 메인 이벤트 루프 실행
        root.mainloop()

    except Exception as e:
        logging.error(f"메인 함수 오류: {str(e)}")
        print(f"심각한 오류 발생: {str(e)}")
        log_to_console(f"심각한 오류 발생: {str(e)}")
        try:
            import tkinter.messagebox as mbox
            mbox.showerror("오류", f"프로그램 실행 중 오류가 발생했습니다: {str(e)}")
        except:
            pass

# 모든 모듈을 즉시 로드하는 함수
def load_modules():
    """필요한 모듈을 동기적으로 로딩"""
    global openai, openai_client, pyperclip, sd, np, soundfile, winsound, pystray, Image, ImageDraw
    global Listener, Controller, Key, KeyCode, has_tray_support, has_pyaudio

    try:
        import openai
        print("OpenAI 모듈 로딩 완료")
    except ImportError as e:
        print(f"OpenAI 모듈 로딩 실패: {str(e)}")

    try:
        import pyperclip
        print("Pyperclip 모듈 로딩 완료")
    except ImportError as e:
        print(f"Pyperclip 모듈 로딩 실패: {str(e)}")

    try:
        import sounddevice as sd
        import numpy as np
        print("Sounddevice 및 Numpy 모듈 로딩 완료")
    except ImportError as e:
        print(f"Sounddevice 또는 Numpy 모듈 로딩 실패: {str(e)}")

    try:
        import soundfile
        print("Soundfile 모듈 로딩 완료")
    except ImportError as e:
        print(f"Soundfile 모듈 로딩 실패: {str(e)}")

    try:
        import winsound
        print("Winsound 모듈 로딩 완료")
    except ImportError as e:
        print(f"Winsound 모듈 로딩 실패: {str(e)}")

    try:
        import pystray
        from PIL import Image, ImageDraw
        has_tray_support = True
        print("Pystray 및 PIL 모듈 로딩 완료")
    except ImportError as e:
        has_tray_support = False
        print(f"Pystray 또는 PIL 모듈 로딩 실패: {str(e)}")

    try:
        from pynput.keyboard import Listener, Controller, Key, KeyCode
        print("Pynput 모듈 로딩 완료")
    except ImportError as e:
        print(f"Pynput 모듈 로딩 실패: {str(e)}")

    try:
        import pyaudio
        has_pyaudio = True
        print("PyAudio 모듈 로딩 완료")
    except ImportError:
        has_pyaudio = False
        print("PyAudio 모듈 없음, 기본 오디오 시스템 사용")

    # Google Cloud STT V2 모듈 로딩
    global google_speech, google_stt_client, google_credentials_path, google_project_id
    global google_tts, google_tts_client
    global StreamingRecognizeRequest, StreamingRecognitionConfig, RecognitionConfig
    global RecognitionFeatures, StreamingRecognitionFeatures, AutoDetectDecodingConfig, RecognizeRequest
    try:
        from google.cloud import speech_v2 as google_speech_module
        google_speech = google_speech_module

        # 클래스 참조들도 로드
        if google_speech:
            StreamingRecognizeRequest = google_speech.StreamingRecognizeRequest
            StreamingRecognitionConfig = google_speech.StreamingRecognitionConfig
            RecognitionConfig = google_speech.RecognitionConfig
            RecognitionFeatures = google_speech.RecognitionFeatures
            StreamingRecognitionFeatures = google_speech.StreamingRecognitionFeatures
            AutoDetectDecodingConfig = google_speech.AutoDetectDecodingConfig
            RecognizeRequest = google_speech.RecognizeRequest
            print("Google Cloud Speech 클래스 참조 로드 완료")

        print("Google Cloud Speech V2 모듈 로딩 완료")
        logging.info("Google Cloud Speech V2 모듈 로딩 완료")
    except ImportError as e:
        print(f"Google Cloud Speech 모듈 로딩 실패: {str(e)}")
        logging.warning(f"Google Cloud Speech 모듈 없음: {str(e)}")

# 키보드 리스너 설정
def setup_keyboard_listener():
    """키보드 리스너 설정"""
    global Listener, Key, Controller, KeyCode, pynput_initialized
    load_settings()  # added to ensure hotkey settings from whisperer_settings.json are reloaded

    if Listener is None:
        try:
            from pynput.keyboard import Listener, Key, Controller, KeyCode
            pynput_initialized = True
            logging.info("Pynput 모듈 로드됨")
        except ImportError as e:
            logging.error(f"Pynput 모듈 로드 실패: {str(e)}")
            log_to_console("오류: 키보드 감지 모듈을 로드할 수 없습니다.")
            return False

    def on_press(key):
        """키 누름 이벤트 핸들러"""
        global ctrl_pressed, shift_pressed, alt_pressed, recording, recording_started_with_combo

        try:
            logging.debug(f"키 누름: {key}")

            # 키 상태 업데이트
            if key == Key.ctrl_l or key == Key.ctrl_r:
                ctrl_pressed = True
                logging.debug("Ctrl 키 눌림")
            elif key == Key.shift_l or key == Key.shift_r:
                shift_pressed = True
                logging.debug("Shift 키 눌림")
            elif key == Key.alt_l or key == Key.alt_r:
                alt_pressed = True
                logging.debug("Alt 키 눌림")

            # 특정 키 조합 로그 (콘솔에도 출력하여 확인 유도)
            if ctrl_pressed or alt_pressed:
                logging.info(f"조합 키 입력 감지: {key} (Ctrl={ctrl_pressed}, Alt={alt_pressed}, Shift={shift_pressed})")

            logging.debug(f"현재 키 상태: Ctrl={ctrl_pressed}, Shift={shift_pressed}, Alt={alt_pressed}")
            logging.debug(f"설정된 STT 단축키: 수정자={hotkey_modifiers}, 키={hotkey_key}")
            logging.debug(f"설정된 TTS 단축키: 수정자={tts_hotkey_modifiers}, 키={tts_hotkey_key}")

            if not recording:
                # If no 사용자 정의 단축키가 설정되어 있으면 기본 단축키 (Ctrl+Shift+Alt) 사용
                if hotkey_key is None and ctrl_pressed and shift_pressed and alt_pressed:
                    logging.info("기본 녹음 단축키 감지됨 (Ctrl+Shift+Alt)")
                    log_to_console("녹음 시작 단축키 감지...")
                    if root:
                        root.after(10, start_recording)
                    else:
                        start_recording()
                    recording_started_with_combo = True
                    return True

                # 사용자 정의 단축키 조합 확인
                modifier_match = (
                    (not hotkey_modifiers.get("ctrl", False) or ctrl_pressed) and
                    (not hotkey_modifiers.get("shift", False) or shift_pressed) and
                    (not hotkey_modifiers.get("alt", False) or alt_pressed)
                )

                key_match = False
                if hotkey_key:
                    if isinstance(key, KeyCode):
                        # pynput KeyCode handling (char might be control char)
                        key_char = key.char
                        if key_char:
                            # Ctrl+Key 처리
                            if ctrl_pressed and len(key_char) == 1 and ord(key_char) < 32:
                                key_char = chr(ord(key_char) + 64)
                            key_match = key_char.upper() == hotkey_key.upper()
                        elif key.vk is not None:
                            # VK 코드로 문자 키 확인 (D=68, S=83 등)
                            try:
                                # A-Z는 VK 65-90
                                if 65 <= key.vk <= 90:
                                    key_match = chr(key.vk).upper() == hotkey_key.upper()
                            except:
                                pass
                    elif key:
                        key_str = str(key).replace('Key.', '')
                        key_match = key_str.upper() == hotkey_key.upper()
                else:
                    key_match = True

                if modifier_match and key_match:
                    logging.info(f"사용자 정의 녹음 단축키 감지됨: 수정자={hotkey_modifiers}, 키={hotkey_key}")
                    log_to_console("사용자 정의 녹음 단축키 감지...")
                    if root:
                        root.after(10, start_recording)
                    else:
                        start_recording()
                    recording_started_with_combo = True
                    return True

            # TTS 단축키 확인 (녹음 중이 아닐 때만)
            if not recording and not is_speaking:
                tts_modifier_match = (
                    (not tts_hotkey_modifiers.get("ctrl", False) or ctrl_pressed) and
                    (not tts_hotkey_modifiers.get("shift", False) or shift_pressed) and
                    (not tts_hotkey_modifiers.get("alt", False) or alt_pressed)
                )

                tts_key_match = False
                if tts_hotkey_key:
                    if isinstance(key, KeyCode):
                        key_char = key.char
                        if key_char:
                            if ctrl_pressed and len(key_char) == 1 and ord(key_char) < 32:
                                key_char = chr(ord(key_char) + 64)
                            tts_key_match = key_char.upper() == tts_hotkey_key.upper()
                        elif key.vk is not None:
                            try:
                                if 65 <= key.vk <= 90:
                                    tts_key_match = chr(key.vk).upper() == tts_hotkey_key.upper()
                            except:
                                pass
                    elif key:
                        key_str = str(key).replace('Key.', '')
                        tts_key_match = key_str.upper() == tts_hotkey_key.upper()

                if tts_modifier_match and tts_key_match:
                    logging.info("TTS 읽기 단축키 감지됨")
                    if root:
                        root.after(10, read_selected_text)
                    else:
                        read_selected_text()
                    return True

        except Exception as e:
            logging.error(f"키 누름 처리 중 오류: {str(e)}")
            return False

    def on_release(key):
        """키 뗌 이벤트 핸들러"""
        global ctrl_pressed, shift_pressed, alt_pressed, recording, recording_started_with_combo

        try:
            # 현재 키 로깅
            logging.debug(f"키 뗌: {key}")

            # 키 상태 업데이트
            if key == Key.ctrl_l or key == Key.ctrl_r:
                ctrl_pressed = False
                logging.debug("Ctrl 키 뗌")
            elif key == Key.shift_l or key == Key.shift_r:
                shift_pressed = False
                logging.debug("Shift 키 뗌")
            elif key == Key.alt_l or key == Key.alt_r:
                alt_pressed = False
                logging.debug("Alt 키 뗌")

            # 녹음 중이고 단축키로 시작했을 때만 처리
            if recording and recording_started_with_combo:
                # 수정자 키(Ctrl, Shift, Alt)가 떼어졌는지 확인
                if (key == Key.ctrl_l or key == Key.ctrl_r or
                    key == Key.shift_l or key == Key.shift_r or
                    key == Key.alt_l or key == Key.alt_r):

                    logging.info("녹음 종료 단축키 감지 (수정자 키 뗌)")
                    log_to_console("녹음 종료 단축키 감지...")

                    # 녹음 종료 (메인 스레드에서 실행)
                    if root:
                        root.after(10, stop_recording)
                    else:
                        stop_recording()
                    recording_started_with_combo = False
                    return True

        except Exception as e:
            logging.error(f"키 뗌 처리 중 오류: {str(e)}")
            return False

        # 기존에 리스너 재시작하는 코드 블록 제거
        return True

    # 리스너 시작
    try:
        # 기존 리스너가 있으면 중지
        global keyboard_listener
        if 'keyboard_listener' in globals() and keyboard_listener is not None:
            try:
                keyboard_listener.stop()
                logging.info("기존 키보드 리스너 중지됨")
            except:
                pass

        # 새 리스너 생성 및 시작
        keyboard_listener = Listener(on_press=on_press, on_release=on_release)
        keyboard_listener.daemon = True  # 데몬 스레드로 설정
        keyboard_listener.start()
        logging.info("키보드 리스너 시작됨")
        log_to_console("키보드 리스너가 시작되었습니다. (단축키 설정: 녹음)")
        return True

    except Exception as e:
        logging.error(f"키보드 리스너 시작 실패: {str(e)}")
        log_to_console(f"오류: 키보드 리스너 시작 실패: {str(e)}")
        return False

# 언어 설정 저장/로드 함수 수정
def save_settings():
    try:
        # whisper_settings는 로드만 하고 저장하지 않음
        settings = {
            "language": current_language,
            "auto_detection": auto_language_detection,
            "google_credentials_path": google_credentials_path,
            "hotkey": {
                "modifiers": hotkey_modifiers,
                "key": hotkey_key
            },
            "tts_hotkey": {
                "modifiers": tts_hotkey_modifiers,
                "key": tts_hotkey_key
            }
        }
        print(f"저장할 설정: {settings}")
        with open('whisperer_settings.json', 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
            # 파일 강제 쓰기
            f.flush()
            os.fsync(f.fileno())
        logging.info("설정 저장 완료")
        print("설정 파일 저장됨: whisperer_settings.json")
    except Exception as e:
        logging.error(f"설정 저장 오류: {str(e)}")
        print(f"설정 저장 오류: {str(e)}")

# Whisper API 설정을 위한 전역 변수 추가 (Google STT로 전환됨)
whisper_prompt = None
active_mode = "general"  # 기본값은 일반 대화 모드

def load_settings():
    global current_language, hotkey_modifiers, hotkey_key, auto_language_detection, whisper_prompt, active_mode, google_credentials_path, google_stt_model
    try:
        if os.path.exists('whisperer_settings.json'):
            with open('whisperer_settings.json', 'r', encoding='utf-8') as f:
                settings = json.load(f)
                print(f"로드된 설정: {settings}")
                if "language" in settings:
                    current_language = settings["language"]
                if "auto_detection" in settings:
                    auto_language_detection = settings["auto_detection"]
                if "hotkey" in settings:
                    if "modifiers" in settings["hotkey"]:
                        hotkey_modifiers = settings["hotkey"]["modifiers"]
                    if "key" in settings["hotkey"]:
                        hotkey_key = settings["hotkey"]["key"]

                # TTS 단축키 로드
                if "tts_hotkey" in settings:
                    if "modifiers" in settings["tts_hotkey"]:
                        tts_hotkey_modifiers = settings["tts_hotkey"]["modifiers"]
                    if "key" in settings["tts_hotkey"]:
                        tts_hotkey_key = settings["tts_hotkey"]["key"]

                # Google Cloud 인증 파일 경로 로드
                if "google_credentials_path" in settings:
                    google_credentials_path = settings["google_credentials_path"]

                # 경로가 유효하지 않으면 앱 디렉토리 내의 기본 파일 확인 (백업/이동 대응)
                if not google_credentials_path or not os.path.exists(google_credentials_path):
                    default_path = os.path.join(get_app_dir(), "google_credentials.json")
                    if os.path.exists(default_path):
                        google_credentials_path = default_path
                        logging.info(f"기본 위치에서 인증 파일 발견: {google_credentials_path}")

                # Google STT 설정 로드
                if "google_settings" in settings:
                    if "model" in settings["google_settings"]:
                        google_stt_model = settings["google_settings"]["model"]

                # Whisper API 설정 로드 (기존 호환성 및 대화 모드 유지)
                if "whisper_settings" in settings:

                    # 대화 모드 로드
                    if "active_mode" in settings["whisper_settings"]:
                        active_mode = settings["whisper_settings"]["active_mode"]

                    # prompts 객체가 있는 경우
                    if "prompts" in settings["whisper_settings"]:
                        prompts = settings["whisper_settings"]["prompts"]

                        # 대화 모드에 따라 프롬프트 생성
                        if active_mode == "address_poi":
                            whisper_prompt = prompts.get("address_poi_rules", "")
                        elif active_mode == "general":
                            whisper_prompt = prompts.get("general_rules", "")

            logging.info(f"설정 로드 완료: 언어={current_language}, 단축키 수정자={hotkey_modifiers}, 단축키={hotkey_key}")
            print(f"설정 로드 완료: 언어={current_language}, 단축키 수정자={hotkey_modifiers}, 단축키={hotkey_key}")
        # 설정 파일이 없는 경우는 무시하고 기본값 사용
    except Exception as e:
        logging.error(f"설정 로드 오류: {str(e)}")
        print(f"설정 로드 오류: {str(e)}")

# 단일 설정 함수들 (이전 코드와의 호환성)
def save_language_setting():
    save_settings()

def load_language_setting():
    load_settings()

# 메시지 가져오기 함수 래퍼
def get_msg(key, *args):
    global current_language
    return get_message(key, *args, language=current_language)

# 시스템 트레이 아이콘 이미지 생성 및 설정 함수
def create_image():
    """시스템 트레이 아이콘 이미지 생성"""
    global Image, ImageDraw

    try:
        # 모듈이 로드되었는지 확인
        if Image is None or ImageDraw is None:
            from PIL import Image, ImageDraw
            logging.info("PIL 모듈 로딩 완료")

        # 리소스 파일 경로 계산 (패키지 내부 또는 현재 디렉토리)
        favicon_paths = []

        # PyInstaller 리소스 경로 (_MEIPASS) 추가
        favicon_paths.append(resource_path("favicon.ico"))

        # 실행 파일 경로 기준 (PyInstaller로 패키징된 경우)
        base_path = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
        favicon_paths.append(os.path.join(base_path, "favicon.ico"))

        # 현재 작업 디렉토리 기준
        favicon_paths.append(os.path.abspath("favicon.ico"))

        # 현재 스크립트 디렉토리 기준
        script_dir = os.path.dirname(os.path.abspath(__file__))
        favicon_paths.append(os.path.join(script_dir, "favicon.ico"))

        # 모든 가능한 경로 로깅
        logging.info(f"favicon.ico 파일 가능한 경로들: {favicon_paths}")

        # 각 경로 시도
        favicon_loaded = False
        for favicon_path in favicon_paths:
            logging.info(f"favicon.ico 파일 경로 시도: {favicon_path}")

            if os.path.exists(favicon_path):
                try:
                    # 이미지 로드
                    img = Image.open(favicon_path)
                    logging.info(f"이미지 로드됨: {favicon_path}, 크기 {img.size}, 포맷 {img.format}, 모드 {img.mode}")

                    # 16x16 크기로 조정 (트레이 아이콘에 최적)
                    if img.size != (16, 16):
                        img = img.resize((16, 16), Image.LANCZOS)
                        logging.info("이미지 크기 16x16으로 조정됨")

                    favicon_loaded = True
                    return img
                except Exception as e:
                    logging.error(f"이미지 로드 오류: {favicon_path}: {str(e)}")
                    import traceback
                    logging.error(traceback.format_exc())

        if not favicon_loaded:
            logging.error("모든 favicon.ico 파일 경로 시도 실패")
            log_to_console("favicon.ico 파일을 찾을 수 없습니다.")

            # 배포 버전이 아닌 경우에만 기본 아이콘 생성 (개발 모드)
            if not hasattr(sys, 'frozen'):
                try:
                    logging.info("기본 아이콘 생성 중...")
                    image = Image.new('RGB', (16, 16), color=(73, 109, 137))
                    d = ImageDraw.Draw(image)
                    d.text((4, 4), "W", fill=(255, 255, 0))
                    logging.info("기본 아이콘 생성됨")
                    return image
                except Exception as e:
                    logging.error(f"기본 아이콘 생성 오류: {str(e)}")

    except Exception as e:
        logging.error(f"아이콘 생성 준비 중 오류: {str(e)}")
        log_to_console(f"아이콘 생성 오류: {str(e)}")

    return None

def setup_tray_icon():
    """시스템 트레이 아이콘 설정"""
    global tray_icon, pystray, Image, ImageDraw

    try:
        # 필요한 모듈이 로드되었는지 확인
        if pystray is None:
            logging.info("pystray 모듈 로딩 중...")
            import pystray
            logging.info("pystray 모듈 로딩 완료")

        if Image is None or ImageDraw is None:
            logging.info("PIL 모듈 로딩 중...")
            from PIL import Image, ImageDraw
            logging.info("PIL 모듈 로딩 완료")
    except ImportError as e:
        logging.error(f"트레이 아이콘 설정 실패 - 모듈 로딩 오류: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"트레이 아이콘 설정 중 예상치 못한 오류: {str(e)}")
        return None

    try:
        # 아이콘 이미지 생성
        logging.info("트레이 아이콘 이미지 생성 중...")
        icon_image = create_image()
        logging.info("트레이 아이콘 이미지 생성 완료")

        if icon_image is None:
            logging.error("트레이 아이콘 이미지 생성 실패")
            if root:
                root.after(10, lambda: messagebox.showerror("아이콘 오류", "트레이 아이콘 이미지를 생성할 수 없습니다.\nfavicon.ico 파일이 존재하는지 확인하세요."))
            return None

        # 메뉴 항목 정의
        def exit_action(icon, item):
            icon.stop()
            os._exit(0)

        # 녹음 파일 폴더 열기 함수
        def open_recordings_folder(icon, item):
            try:
                recordings_dir = os.path.abspath("recordings")
                if not os.path.exists(recordings_dir):
                    os.makedirs(recordings_dir)
                # Windows에서 폴더 열기
                os.startfile(recordings_dir)
                log_to_console(f"녹음 파일 폴더 열기: {recordings_dir}")
            except Exception as e:
                log_to_console(f"녹음 파일 폴더 열기 오류: {str(e)}")

        # README 파일 열기 함수
        def open_readme_file(icon, item):
            try:
                # 현재 언어 설정에 따라 README 파일 선택
                readme_file = "README.KR.md" if current_language == "ko" else "README.md"
                readme_path = os.path.abspath(readme_file)

                if os.path.exists(readme_path):
                    # Windows에서 기본 앱으로 파일 열기
                    os.startfile(readme_path)
                    log_to_console(f"README 파일 열기: {readme_path}")
                else:
                    log_to_console(f"README 파일을 찾을 수 없습니다: {readme_path}")
            except Exception as e:
                log_to_console(f"README 파일 열기 오류: {str(e)}")

        # Google Cloud 인증 설정 함수
        def set_google_credentials(icon, item):
            show_api_key_dialog(required=False)
            log_to_console(get_msg("google_credential_updated"))
            if openai is not None:
                openai_client = openai.OpenAI(api_key=api_key)

        # 마이크 정보 표시 및 재설정 함수
        def check_microphone(icon, item):
            global selected_device, default_device, sd

            try:
                if sd:
                    # 현재 선택된 마이크 정보
                    current_info = ""
                    try:
                        if selected_device is not None:
                            device_info = sd.query_devices(selected_device)
                            current_info = f"현재 마이크: {device_info['name']} (장치 #{selected_device})"
                            log_to_console(current_info)
                        else:
                            current_info = "선택된 마이크 없음"
                            log_to_console(current_info)
                    except Exception as e:
                        log_to_console(f"마이크 정보 확인 오류: {str(e)}")

                    # 사용 가능한 마이크 다시 검색
                    log_to_console("마이크 초기화 중...")
                    init_microphone_async()
                    log_to_console("마이크 초기화 완료")

                    # 새로 설정된 마이크 정보
                    if selected_device is not None:
                        try:
                            device_info = sd.query_devices(selected_device)
                            log_to_console(f"설정된 마이크: {device_info['name']} (장치 #{selected_device})")
                        except Exception as e:
                            log_to_console(f"마이크 정보 확인 오류: {str(e)}")
                else:
                    log_to_console("오디오 모듈이 로드되지 않았습니다.")
            except Exception as e:
                log_to_console(f"마이크 확인 오류: {str(e)}")

        # 콘솔 창 열기 함수
        def open_console(icon, item):
            try:
                import subprocess

                # 콘솔 창 열기 배치 파일 생성
                with open('open_console.bat', 'w', encoding='utf-8') as f:
                    f.write('@echo off\n')
                    f.write(f'title {get_msg("whisper_console")}\n')
                    f.write('chcp 65001\n')  # UTF-8 인코딩 설정
                    f.write(f'echo {get_msg("console_title")}\n')
                    f.write(f'echo {get_msg("console_info")}\n')
                    f.write('echo.\n')
                    f.write(f'echo {get_msg("log_start")}\n')
                    f.write('echo.\n')
                    # 로그 파일 생성 및 실시간 모니터링
                    f.write('echo > whisperer_console.log\n')
                    f.write(f'echo {get_msg("key_monitoring")}\n')
                    f.write('echo.\n')
                    # 로그 파일 실시간 모니터링 (PowerShell 사용)
                    f.write('powershell -command "Get-Content -Path whisperer_console.log -Wait -Encoding UTF8"\n')

                # 새 콘솔 창에서 배치 파일 실행
                subprocess.Popen(['start', 'open_console.bat'],
                               shell=True,
                               creationflags=subprocess.CREATE_NEW_CONSOLE)

                log_to_console("콘솔 창이 열렸습니다.")

                # 콘솔 로그 파일 경로 설정
                global console_log_file
                console_log_file = os.path.abspath("whisperer_console.log")

                # 콘솔 창이 열렸음을 로그에 기록
                log_to_console(get_msg("console_opened"))
                log_to_console(get_msg("program_status"))
                log_to_console(get_msg("recordings_folder", os.path.abspath("recordings")))

            except Exception as e:
                log_to_console(get_msg("console_open_error", str(e)))

        # 한국어로 변경 함수
        def set_korean_language(icon, item):
            global current_language, auto_language_detection
            current_language = "ko"
            auto_language_detection = False
            save_settings()
            log_to_console(get_msg("language_changed", "한국어"))
            # 트레이 아이콘 메뉴 업데이트
            update_tray_menu()

        # 영어로 변경 함수
        def set_english_language(icon, item):
            global current_language, auto_language_detection
            current_language = "en"
            auto_language_detection = False
            save_settings()
            log_to_console(get_msg("language_changed", "English"))
            # 트레이 아이콘 메뉴 업데이트
            update_tray_menu()

        # 자동 감지 토글 함수
        def toggle_auto_detection(icon, item):
            global auto_language_detection
            auto_language_detection = not auto_language_detection
            save_settings()
            if auto_language_detection:
                log_to_console(get_msg("auto_detection_enabled"))
            else:
                log_to_console(get_msg("auto_detection_disabled"))
            # 트레이 아이콘 메뉴 업데이트
            update_tray_menu()

        # Google STT 모델 설정 변수
        global google_stt_model
        google_stt_model = "long" # 기본값

        # Google STT 모델 설정 함수
        def set_stt_model(model_name):
            def _set_model(icon, item):
                global google_stt_model
                google_stt_model = model_name

                # 설정 파일에 저장
                try:
                    settings = {}
                    if os.path.exists('whisperer_settings.json'):
                        with open('whisperer_settings.json', 'r', encoding='utf-8') as f:
                            settings = json.load(f)

                    if "google_settings" not in settings:
                        settings["google_settings"] = {}
                    settings["google_settings"]["model"] = model_name

                    with open('whisperer_settings.json', 'w', encoding='utf-8') as f:
                        json.dump(settings, f, ensure_ascii=False, indent=2)

                    log_to_console(f"인식 모델이 '{model_name}'으로 설정되었습니다.")
                except Exception as e:
                    log_to_console(f"모델 설정 저장 오류: {str(e)}")

                update_tray_menu()
            return _set_model

        # 대화 모드 설정 함수
        def set_conversation_mode(mode):
            def _set_mode(icon, item):
                global active_mode
                active_mode = mode
                # 설정 파일에 모드 저장
                settings = {}
                try:
                    if os.path.exists('whisperer_settings.json'):
                        with open('whisperer_settings.json', 'r', encoding='utf-8') as f:
                            settings = json.load(f)
                except Exception as e:
                    log_to_console(f"설정 파일 읽기 오류: {str(e)}")

                if "whisper_settings" not in settings:
                    settings["whisper_settings"] = {}
                settings["whisper_settings"]["active_mode"] = mode

                try:
                    with open('whisperer_settings.json', 'w', encoding='utf-8') as f:
                        json.dump(settings, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    log_to_console(f"설정 파일 저장 오류: {str(e)}")

                # 로그 출력
                mode_names = {
                    "address_poi": get_msg("address_poi_mode"),
                    "general": get_msg("general_mode")
                }
                log_to_console(get_msg("conversation_mode") + f": {mode_names.get(mode, mode)}")

                # 프롬프트 다시 로드
                load_settings()

                # 트레이 아이콘 메뉴 업데이트
                update_tray_menu()
            return _set_mode

        # 언어 변경 메뉴 항목 (기존 호환성 유지용)
        def change_language(icon, item):
            global current_language
            # 언어 전환 (한국어 <-> 영어)
            current_language = "en" if current_language == "ko" else "ko"
            auto_language_detection = False
            save_settings()
            log_to_console(get_msg("language_changed", current_language))
            # 트레이 아이콘 메뉴 업데이트
            update_tray_menu()

        # 단축키 설정 함수 추가 (언어 변경 함수 아래에 추가)
        def set_hotkey(icon, item):
            show_hotkey_dialog(mode="stt")
            log_to_console(get_msg("hotkey_updated", "단축키가 업데이트되었습니다."))

        def set_tts_hotkey(icon, item):
            show_hotkey_dialog(mode="tts")
            log_to_console(get_msg("tts_hotkey_updated", "읽어주기 단축키가 업데이트되었습니다."))

        def update_tray_menu():
            # 트레이 아이콘 메뉴 업데이트
            tray_icon.menu = pystray.Menu(
                pystray.MenuItem(get_msg("open_recordings_folder"), open_recordings_folder),
                pystray.MenuItem(get_msg("open_readme"), open_readme_file),
                pystray.MenuItem(get_msg("open_console"), open_console),
                pystray.MenuItem(get_msg("google_credential_setting"), set_google_credentials),
                pystray.MenuItem(get_msg("set_hotkey", "녹음 단축키 설정"), set_hotkey),
                pystray.MenuItem(get_msg("set_tts_hotkey", "읽어주기 단축키 설정"), set_tts_hotkey),
                # 언어 설정 하위 메뉴 추가
                pystray.MenuItem(
                    get_msg("language_menu"),
                    pystray.Menu(
                        pystray.MenuItem(
                            get_msg("korean_language"),
                            set_korean_language,
                            checked=lambda item: current_language == "ko" and not auto_language_detection
                        ),
                        pystray.MenuItem(
                            get_msg("english_language"),
                            set_english_language,
                            checked=lambda item: current_language == "en" and not auto_language_detection
                        ),
                        pystray.MenuItem(
                            get_msg("auto_detection"),
                            toggle_auto_detection,
                            checked=lambda item: auto_language_detection
                        ),
                    )
                ),
                # 대화 모드 설정 하위 메뉴 추가
                pystray.MenuItem(
                    get_msg("conversation_mode"),
                    pystray.Menu(
                        pystray.MenuItem(
                            get_msg("general_mode"),
                            set_conversation_mode("general"),
                            checked=lambda item: active_mode == "general"
                        ),
                        pystray.MenuItem(
                            get_msg("address_poi_mode"),
                            set_conversation_mode("address_poi"),
                            checked=lambda item: active_mode == "address_poi"
                        )
                    )
                ),
                # 인식 모델 설정 하위 메뉴
                pystray.MenuItem(
                    get_msg("recognition_model_setting"),
                    pystray.Menu(
                        pystray.MenuItem(
                            get_msg("model_long"),
                            set_stt_model("long"),
                            checked=lambda item: google_stt_model == "long"
                        ),
                        pystray.MenuItem(
                            get_msg("model_short"),
                            set_stt_model("short"),
                            checked=lambda item: google_stt_model == "short"
                        ),
                        pystray.MenuItem(
                            get_msg("model_telephony"),
                            set_stt_model("telephony"),
                            checked=lambda item: google_stt_model == "telephony"
                        )
                    )
                ),
                pystray.MenuItem(get_msg("exit"), exit_action)
            )

        # 초기 메뉴 설정 (update_tray_menu를 호출하여 중복 제거)
        tray_icon = pystray.Icon("whisperer")
        tray_icon.icon = icon_image
        tray_icon.title = "Yeogiaen STT Typer"
        update_tray_menu()

        # 백그라운드 스레드에서 트레이 아이콘 실행
        logging.info("트레이 아이콘 실행 준비 완료")
        # 트레이 아이콘을 별도 스레드로 실행
        icon_thread = threading.Thread(target=tray_icon.run, daemon=True)
        icon_thread.start()
        logging.info("트레이 아이콘 스레드 시작됨")

        return tray_icon
    except Exception as e:
        logging.error(f"트레이 아이콘 설정 중 오류 발생: {str(e)}")
        return None

# API 키 설정 대화 상자 표시 함수
def show_api_key_dialog(required=False):
    """Google Cloud 인증 파일 선택 대화 상자를 표시합니다."""
    global google_credentials_path, google_stt_client, google_project_id

    from tkinter import filedialog
    import shutil

    # 완전히 독립적인 모달 대화 상자 생성
    dialog = tk.Toplevel()
    dialog.title("Google Cloud 인증 설정")
    dialog.geometry("550x280")
    dialog.resizable(False, False)

    # 모달 설정
    dialog.transient()
    dialog.grab_set()
    dialog.focus_set()
    dialog.attributes("-topmost", True)

    # 메인 프레임
    frame = tk.Frame(dialog, padx=25, pady=20)
    frame.pack(fill=tk.BOTH, expand=True)

    # 설명 라벨
    if current_language == "ko":
        label_text = "Google Cloud Service Account JSON 파일을 선택해 주세요\n\n파일은 Google Cloud Console에서 다운로드할 수 있습니다:\nhttps://console.cloud.google.com/iam-admin/serviceaccounts"
    else:
        label_text = "Select your Google Cloud Service Account JSON file\n\nYou can download the file from Google Cloud Console:\nhttps://console.cloud.google.com/iam-admin/serviceaccounts"

    tk.Label(frame, text=label_text, font=("Segoe UI", 11), justify=tk.LEFT).pack(anchor="w", pady=(0, 15))

    # 파일 경로 표시 프레임
    path_frame = tk.Frame(frame)
    path_frame.pack(fill=tk.X, pady=8)

    # 현재 설정된 경로 표시
    current_path = google_credentials_path if google_credentials_path else ""
    path_var = tk.StringVar(value=current_path)

    path_entry = tk.Entry(path_frame, textvariable=path_var, font=("Courier New", 10), width=50, state="readonly")
    path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # 파일 선택 함수
    def browse_file():
        filename = filedialog.askopenfilename(
            title="Google Service Account JSON 파일 선택",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            parent=dialog
        )
        if filename:
            path_var.set(filename)
            result_label.config(text="", fg="black")

    # 찾아보기 버튼
    browse_btn = tk.Button(path_frame, text="...", command=browse_file, width=3, font=("Segoe UI", 10))
    browse_btn.pack(side=tk.RIGHT, padx=(5, 0))

    # 결과 메시지 라벨
    result_label = tk.Label(frame, text="", font=("Segoe UI", 10))
    result_label.pack(pady=10)

    # 버튼 프레임
    btn_frame = tk.Frame(frame)
    btn_frame.pack(pady=10)

    # 결과 변수
    result = [None]

    # 저장 함수
    def save_credentials():
        global google_credentials_path, google_stt_client, google_project_id, google_speech

        selected_path = path_var.get().strip()

        if required and not selected_path:
            result_label.config(text="인증 파일을 선택해 주세요.", fg="red")
            return

        if not os.path.exists(selected_path):
            result_label.config(text="파일이 존재하지 않습니다.", fg="red")
            return

        try:
            # 앱 폴더에 복사할 파일명
            dest_filename = "google_credentials.json"
            dest_path = os.path.join(get_app_dir(), dest_filename)

            # 파일 복사 (이미 같은 위치가 아니면)
            if os.path.abspath(selected_path) != os.path.abspath(dest_path):
                shutil.copy2(selected_path, dest_path)
                log_to_console(f"인증 파일이 복사되었습니다: {dest_path}")

            # 전역 변수에 설정
            google_credentials_path = dest_path

            # JSON에서 project_id 추출
            with open(dest_path, 'r', encoding='utf-8') as f:
                creds_data = json.load(f)
                google_project_id = creds_data.get('project_id')

            # Google STT 클라이언트 초기화
            if google_speech:
                google_stt_client = google_speech.SpeechClient.from_service_account_file(dest_path)
                log_to_console(f"Google Cloud STT 클라이언트 초기화 완료 (프로젝트: {google_project_id})")

            # 설정 저장
            save_settings()

            # 성공 메시지
            result_label.config(text="✓ Google Cloud 인증 설정이 완료되었습니다.", fg="green")
            logging.info(f"Google Cloud 인증 파일 설정됨: {dest_path}")
            log_to_console(f"Google Cloud 인증 파일 설정됨: {dest_path}")

            result[0] = dest_path

            # 성공 후 창 닫기
            dialog.after(1500, dialog.destroy)

        except Exception as e:
            result_label.config(text=f"오류: {str(e)}", fg="red")
            logging.error(f"인증 파일 설정 오류: {str(e)}")

    # 취소 함수
    def cancel():
        if required and not google_stt_client:
            result_label.config(text="인증 파일을 선택해 주세요.", fg="red")
            return
        dialog.destroy()

    # 저장 버튼
    save_btn = tk.Button(btn_frame, text="설정" if current_language == "ko" else "Save", command=save_credentials,
                         width=12, height=1, bg="#4CAF50", fg="white", font=("Segoe UI", 10, "bold"))
    save_btn.pack(side=tk.LEFT, padx=10)

    # 취소 버튼
    cancel_btn = tk.Button(btn_frame, text="취소" if current_language == "ko" else "Cancel", command=cancel,
                          width=12, height=1, bg="#f44336", fg="white", font=("Segoe UI", 10, "bold"))
    cancel_btn.pack(side=tk.LEFT, padx=10)

    # 이벤트 바인딩
    dialog.bind("<Return>", lambda event: save_credentials())
    dialog.bind("<Escape>", lambda event: cancel())
    dialog.protocol("WM_DELETE_WINDOW", cancel)

    # 창 위치 설정 (화면 중앙)
    dialog.update_idletasks()
    width = dialog.winfo_width()
    height = dialog.winfo_height()
    x = (dialog.winfo_screenwidth() // 2) - (width // 2)
    y = (dialog.winfo_screenheight() // 2) - (height // 2)
    dialog.geometry(f"+{x}+{y}")

    # 모달 대화 상자 실행
    dialog.wait_window()

    return result[0] or google_credentials_path

# API 키 오류 대화 상자
def show_api_key_error_dialog(error_message):
    """API 키 오류 대화 상자를 표시합니다."""
    dialog = tk.Toplevel()
    dialog.title(get_msg("error"))
    dialog.geometry("450x200")
    dialog.resizable(False, False)

    # 모달 설정
    dialog.transient()
    dialog.grab_set()
    dialog.focus_set()
    dialog.attributes("-topmost", True)

    # 메인 프레임
    frame = tk.Frame(dialog, padx=20, pady=15)
    frame.pack(fill=tk.BOTH, expand=True)

    # 오류 아이콘
    try:
        error_label = tk.Label(frame, text="⚠️", font=("Segoe UI", 24), fg="red")
        error_label.pack(pady=(0, 10))
    except:
        pass  # 이모지 표시 오류가 나면 무시

    # 오류 메시지
    message_label = tk.Label(frame, text=error_message, font=("Segoe UI", 10), wraplength=400)
    message_label.pack(pady=10)

    # 버튼 프레임
    btn_frame = tk.Frame(frame)
    btn_frame.pack(pady=10)

    # API 키 설정 버튼
    def open_api_key_dialog():
        dialog.destroy()
        show_api_key_dialog(required=False)

    setup_btn = tk.Button(btn_frame, text=get_msg("set_openai_api_key"), command=open_api_key_dialog,
                         width=15, bg="#4CAF50", fg="white", font=("Segoe UI", 9, "bold"))
    setup_btn.pack(side=tk.LEFT, padx=10)

    # 닫기 버튼
    close_btn = tk.Button(btn_frame, text=get_msg("cancel"), command=dialog.destroy,
                         width=10, bg="#f44336", fg="white", font=("Segoe UI", 9, "bold"))
    close_btn.pack(side=tk.LEFT, padx=10)

    # 키보드 이벤트
    dialog.bind("<Return>", lambda event: open_api_key_dialog())
    dialog.bind("<Escape>", lambda event: dialog.destroy())

    # 창 위치 설정 (화면 중앙)
    dialog.update_idletasks()
    width = dialog.winfo_width()
    height = dialog.winfo_height()
    x = (dialog.winfo_screenwidth() // 2) - (width // 2)
    y = (dialog.winfo_screenheight() // 2) - (height // 2)
    dialog.geometry(f"+{x}+{y}")

    # 대화 상자 표시
    dialog.wait_window()

# 단축키 설정 대화상자 함수 추가 (API 키 대화 상자 다음에 추가)
def show_hotkey_dialog(mode="stt"):
    """단축키 변경 대화 상자를 표시합니다."""
    global hotkey_modifiers, hotkey_key, tts_hotkey_modifiers, tts_hotkey_key, Listener, Key, KeyCode

    # 현재 설정할 변수 참조 설정
    if mode == "stt":
        current_modifiers = hotkey_modifiers
        current_key = hotkey_key
        title = get_msg("set_hotkey_title", "녹음 단축키 설정")
    else:
        current_modifiers = tts_hotkey_modifiers
        current_key = tts_hotkey_key
        title = get_msg("set_tts_hotkey_title", "읽어주기 단축키 설정")

    # 현재 단축키 문자열 생성
    def get_hotkey_string_local(modifiers, key_val):
        parts = []
        if modifiers.get("ctrl", False):
            parts.append("Ctrl")
        if modifiers.get("shift", False):
            parts.append("Shift")
        if modifiers.get("alt", False):
            parts.append("Alt")
        if key_val:
            parts.append(str(key_val).upper())
        return "+".join(parts)

    # 완전히 독립적인 모달 대화 상자 생성
    dialog = tk.Toplevel()
    dialog.title(title)
    dialog.geometry("450x300")
    dialog.resizable(False, False)

    # 모달 설정 (부모 창 비활성화)
    dialog.transient()
    dialog.grab_set()
    dialog.focus_set()

    # 항상 위에 표시
    dialog.attributes("-topmost", True)

    # 메인 프레임
    frame = tk.Frame(dialog, padx=25, pady=20)
    frame.pack(fill=tk.BOTH, expand=True)

    # 설명 라벨
    tk.Label(frame, text=get_msg("hotkey_instruction", "단축키를 설정하세요. 체크박스로 수정자 키를 선택하세요."),
             font=("Segoe UI", 11), justify=tk.LEFT).pack(anchor="w", pady=(0, 15))

    # 수정자 키 체크박스
    modifiers_frame = tk.Frame(frame)
    modifiers_frame.pack(fill=tk.X, pady=5)

    # Ctrl 체크박스
    ctrl_var = tk.BooleanVar(value=current_modifiers.get("ctrl", True))
    ctrl_cb = tk.Checkbutton(modifiers_frame, text="Ctrl", variable=ctrl_var, font=("Segoe UI", 10))
    ctrl_cb.pack(side=tk.LEFT, padx=10)

    # Shift 체크박스
    shift_var = tk.BooleanVar(value=current_modifiers.get("shift", True))
    shift_cb = tk.Checkbutton(modifiers_frame, text="Shift", variable=shift_var, font=("Segoe UI", 10))
    shift_cb.pack(side=tk.LEFT, padx=10)

    # Alt 체크박스
    alt_var = tk.BooleanVar(value=current_modifiers.get("alt", True))
    alt_cb = tk.Checkbutton(modifiers_frame, text="Alt", variable=alt_var, font=("Segoe UI", 10))
    alt_cb.pack(side=tk.LEFT, padx=10)

    # 키 추가 프레임
    key_frame = tk.Frame(frame)
    key_frame.pack(fill=tk.X, pady=10)

    # 추가 키 라벨
    tk.Label(key_frame, text=get_msg("additional_key", "추가 키(선택사항):"),
             font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 10))

    # 추가 키 입력 필드 (읽기 전용)
    key_var = tk.StringVar(value=str(current_key) if current_key else "")
    key_entry = tk.Entry(key_frame, textvariable=key_var, width=10, font=("Segoe UI", 10),
                         state="readonly", bg="white")
    key_entry.pack(side=tk.LEFT)

    # 키 리스닝 상태
    listening = [False]

    # 리스닝 시작 버튼
    def start_listening():
        if listening[0]:
            return

        listening[0] = True
        listen_btn.config(text=get_msg("press_key", "키를 누르세요..."), bg="red")
        key_var.set("")

        # 입력된 키 값을 저장할 변수
        key_value = None

        # 키 눌림 이벤트 핸들러
        def on_key_press(key):
            if not listening[0]:
                return True

            try:
                nonlocal key_value
                # 수정자 키는 무시
                if key == Key.ctrl_l or key == Key.ctrl_r or \
                    key == Key.shift_l or key == Key.shift_r or \
                    key == Key.alt_l or key == Key.alt_r:
                    return True

                # 다른 키는 저장
                if isinstance(key, KeyCode):
                    key_name = key.char
                    if key_name:
                        key_var.set(key_name.upper())
                        key_value = key_name.upper()
                else:
                    # 특수 키는 이름 사용
                    key_name = str(key).replace('Key.', '')
                    key_var.set(key_name.upper())
                    key_value = key_name.upper()

                # 리스닝 종료
                listening[0] = False
                listen_btn.config(text=get_msg("set_key", "키 설정"), bg="#4CAF50")

                # 키 입력이 끝나면 리스너 중지
                return False
            except Exception as e:
                logging.error(f"키 리스닝 오류: {str(e)}")
                return False

        # 임시 리스너 설정
        temp_listener = Listener(on_press=on_key_press)
        temp_listener.start()

        # 5초 후 자동 타임아웃
        def timeout():
            nonlocal key_value
            if listening[0]:
                listening[0] = False
                listen_btn.config(text=get_msg("set_key", "키 설정"), bg="#4CAF50")
                temp_listener.stop()

            # 키 값이 입력되었다면 저장
            if key_value:
                key_var.set(key_value)

        dialog.after(5000, timeout)

    # 리스닝 버튼
    listen_btn = tk.Button(key_frame, text=get_msg("set_key", "키 설정"),
                         command=start_listening, bg="#4CAF50", fg="white",
                         font=("Segoe UI", 9))
    listen_btn.pack(side=tk.LEFT, padx=10)

    # 키 지우기 버튼
    def clear_key():
        key_var.set("")

    clear_btn = tk.Button(key_frame, text=get_msg("clear_key", "지우기"),
                         command=clear_key, bg="#f44336", fg="white",
                         font=("Segoe UI", 9))
    clear_btn.pack(side=tk.LEFT)

    # 현재 단축키 표시
    current_hotkey_frame = tk.Frame(frame)
    current_hotkey_frame.pack(fill=tk.X, pady=15)

    tk.Label(current_hotkey_frame, text=get_msg("current_hotkey", "현재 단축키:"),
             font=("Segoe UI", 10)).pack(side=tk.LEFT)

    current_hotkey_label = tk.Label(current_hotkey_frame, text=get_hotkey_string_local(current_modifiers, current_key),
                                   font=("Segoe UI", 10, "bold"))
    current_hotkey_label.pack(side=tk.LEFT, padx=10)

    # 결과 메시지 라벨
    result_label = tk.Label(frame, text="", font=("Segoe UI", 10))
    result_label.pack(pady=10)

    # 버튼 프레임
    btn_frame = tk.Frame(frame)
    btn_frame.pack(pady=10)

    # 저장 함수
    def save_hotkey():
        global hotkey_modifiers, hotkey_key, tts_hotkey_modifiers, tts_hotkey_key

        # 최소한 하나의 수정자 키 필요
        if not (ctrl_var.get() or shift_var.get() or alt_var.get()):
            result_label.config(text=get_msg("need_modifier", "최소 하나의 수정자 키(Ctrl, Shift, Alt)가 필요합니다."),
                               fg="red")
            return

        # 설정값 준비
        new_modifiers = {
            "ctrl": ctrl_var.get(),
            "shift": shift_var.get(),
            "alt": alt_var.get()
        }
        key_text = key_var.get().strip()
        new_key = key_text if key_text else None

        # 모드에 따라 전역 변수 업데이트
        if mode == "stt":
            hotkey_modifiers = new_modifiers
            hotkey_key = new_key
        else:
            tts_hotkey_modifiers = new_modifiers
            tts_hotkey_key = new_key

        # 저장된 값 로깅
        logging.info(f"저장되는 {mode} 단축키 값: 수정자={new_modifiers}, 키={new_key}")
        print(f"=== 단축키 저장 시작 ===")
        print(f"저장할 단축키: 수정자={hotkey_modifiers}, 키={hotkey_key}")

        # 설정 파일에 저장
        try:
            save_settings()
            print("설정 파일에 단축키 저장 완료")
            logging.info("단축키 설정 저장 완료")
        except Exception as e:
            err_msg = f"설정 파일 저장 오류: {str(e)}"
            print(err_msg)
            logging.error(err_msg)
            result_label.config(text=err_msg, fg="red")
            return

        # 성공 메시지
        result_label.config(text=get_msg("hotkey_saved", "단축키가 저장되었습니다."), fg="green")

        # 현재 단축키 표시 업데이트
        current_hotkey_label.config(text=get_hotkey_string_local(new_modifiers, new_key))

        # 단축키 변경 로그 출력
        hotkey_str = get_hotkey_string_local(new_modifiers, new_key)
        log_msg = f"{'녹음' if mode == 'stt' else '읽어주기'} 단축키가 변경되었습니다: {hotkey_str}"
        logging.info(log_msg)
        log_to_console(log_msg)
        print(log_msg)

        # 키보드 리스너 재설정 - 새로운 단축키 적용을 위해
        print("키보드 리스너 재설정 중...")
        setup_keyboard_listener()
        print("키보드 리스너 재설정 완료")

        # 1초 후 창 닫기
        dialog.after(1000, dialog.destroy)

    # 취소 함수
    def cancel():
        dialog.destroy()

    # 저장 버튼
    save_btn = tk.Button(btn_frame, text=get_msg("save", "저장"), command=save_hotkey,
                         width=12, height=1, bg="#4CAF50", fg="white", font=("Segoe UI", 10, "bold"))
    save_btn.pack(side=tk.LEFT, padx=10)

    # 취소 버튼
    cancel_btn = tk.Button(btn_frame, text=get_msg("cancel", "취소"), command=cancel,
                          width=12, height=1, bg="#f44336", fg="white", font=("Segoe UI", 10, "bold"))
    cancel_btn.pack(side=tk.LEFT, padx=10)

    # 이벤트 바인딩
    dialog.bind("<Escape>", lambda event: cancel())

    # 창 위치 설정 (화면 중앙)
    dialog.update_idletasks()
    width = dialog.winfo_width()
    height = dialog.winfo_height()
    x = (dialog.winfo_screenwidth() // 2) - (width // 2)
    y = (dialog.winfo_screenheight() // 2) - (height // 2)
    dialog.geometry(f"+{x}+{y}")

    # 대화 상자 표시
    dialog.wait_window()

# 녹음 관련 함수
def start_recording():
    """녹음 시작 함수"""
    global recording, audio_data, sd, np, stream, selected_device, winsound, streaming_thread

    if recording:
        logging.info("이미 녹음 중입니다.")
        return

    # sounddevice 모듈이 로드되었는지 확인
    if sd is None or np is None:
        error_msg = "녹음에 필요한 모듈이 로드되지 않았습니다."
        logging.error(error_msg)
        log_to_console(f"오류: {error_msg}")
        # GUI 오류 메시지 표시 (메인 스레드에서)
        if root:
            root.after(10, lambda: messagebox.showerror("녹음 오류", error_msg))
        return

    try:
        # 녹음 시작
        logging.info("녹음 시작")
        log_to_console("녹음 시작 중...")

        # 마이크 정보 확인
        try:
            # 사용 가능한 장치 확인
            devices = sd.query_devices()
            logging.info(f"사용 가능한 오디오 장치: {len(devices)}개")

            # 입력 장치 선택 (선택된 장치가 없으면 기본 장치 사용)
            device_info = None
            if selected_device is not None:
                device_info = sd.query_devices(selected_device)
                logging.info(f"선택된 마이크 사용: {device_info['name']}")
            else:
                device_info = sd.query_devices(kind='input')
                logging.info(f"기본 마이크 사용: {device_info['name']}")

            # 로그에 디바이스 정보 기록
            log_to_console(f"마이크: {device_info['name']}")
        except Exception as e:
            logging.error(f"마이크 정보 확인 오류: {str(e)}")
            log_to_console(f"마이크 정보 확인 오류: {str(e)}")
            # 계속 진행 (기본 설정으로 시도)

        # 샘플링 설정
        samplerate = 16000  # OpenAI Whisper에 적합한 샘플링 레이트
        channels = 1        # 모노 녹음

        # 오디오 데이터 초기화
        audio_data = []

        # 스트리밍 초기화
        while not audio_queue.empty():
            try: audio_queue.get_nowait()
            except: pass

        global is_streaming
        is_streaming = True
        streaming_thread = threading.Thread(target=google_stt_streaming_thread, daemon=True)
        streaming_thread.start()

        recording = True

        # 녹음 콜백 함수
        def audio_callback(indata, frames, time, status):
            if status:
                logging.warning(f"녹음 상태 문제: {status}")
            if recording:
                try:
                    if indata.shape[1] == channels:  # 채널 수 확인
                        # 기존 방식: 오디오 파일 저장용으로 리스트에도 보관
                        audio_data.append(indata.copy())

                        # 스트리밍 방식: 실시간 큐에 데이터 주입
                        # float32 데이터를 int16 PCM 데이터로 변환
                        pcm_data = (indata.copy() * 32767).astype(np.int16).tobytes()
                        audio_queue.put(pcm_data)
                    else:
                        logging.warning(f"채널 수 불일치: 예상 {channels}, 실제 {indata.shape[1]}")
                except Exception as cb_e:
                    logging.error(f"오디오 콜백 오류: {str(cb_e)}")

        # 스트림 시작
        try:
            device_id = selected_device if selected_device is not None else None
            # blocksize를 8000 (16000Hz 기준 500ms)으로 설정하여 더 여유롭고 효율적으로 처리
            stream = sd.InputStream(
                device=device_id,
                samplerate=samplerate,
                channels=channels,
                callback=audio_callback,
                blocksize=8000
            )
            stream.start()
            logging.info("오디오 스트림 시작됨")

            # 녹음 시작 비프음 추가 (Windows 환경)
            if winsound:
                try:
                    winsound.Beep(600, 200) # 600Hz, 200ms 비프음
                except Exception as beep_e:
                    logging.warning(f"녹음 시작 비프음 재생 오류: {str(beep_e)}")

        except Exception as stream_e:
            error_msg = f"오디오 스트림 시작 오류: {str(stream_e)}"
            logging.error(error_msg)
            log_to_console(error_msg)
            recording = False
            # GUI 오류 메시지 표시 (메인 스레드에서)
            if root:
                root.after(10, lambda: messagebox.showerror("녹음 오류", f"마이크를 시작할 수 없습니다: {str(stream_e)}"))
            return

        # 녹음 시작 알림

    except Exception as e:
        error_msg = f"녹음 시작 오류: {str(e)}"
        logging.error(error_msg)
        log_to_console(error_msg)
        recording = False
        # GUI 오류 메시지 표시 (메인 스레드에서)
        if root:
            root.after(10, lambda: messagebox.showerror("녹음 오류", error_msg))

def ensure_google_client():
    """Google Cloud STT 클라이언트를 초기화하고 유효성을 확인합니다."""
    global google_stt_client, google_project_id, google_speech, google_credentials_path
    global StreamingRecognizeRequest, StreamingRecognitionConfig, RecognitionConfig
    global RecognitionFeatures, StreamingRecognitionFeatures, AutoDetectDecodingConfig, RecognizeRequest

    if google_stt_client and google_project_id and StreamingRecognizeRequest:
        return True

    if google_credentials_path and os.path.exists(google_credentials_path):
        try:
            # 전역 모듈이 없으면 여기서 임포트
            if google_speech is None:
                from google.cloud import speech_v2
                google_speech = speech_v2

            # JSON에서 project_id 추출
            with open(google_credentials_path, 'r', encoding='utf-8') as f:
                creds_data = json.load(f)
                google_project_id = creds_data.get('project_id')

            if google_speech and google_project_id:
                google_stt_client = google_speech.SpeechClient.from_service_account_file(google_credentials_path)

                # 클래스 참조 로드
                StreamingRecognizeRequest = google_speech.StreamingRecognizeRequest
                StreamingRecognitionConfig = google_speech.StreamingRecognitionConfig
                RecognitionConfig = google_speech.RecognitionConfig
                RecognitionFeatures = google_speech.RecognitionFeatures
                StreamingRecognitionFeatures = google_speech.StreamingRecognitionFeatures
                AutoDetectDecodingConfig = google_speech.AutoDetectDecodingConfig
                ExplicitDecodingConfig = google_speech.ExplicitDecodingConfig # 추가
                RecognizeRequest = google_speech.RecognizeRequest
                return True
        except Exception as e:
            logging.error(f"Google client initialization failed: {e}")
    return False

class AudioGenerator:
    """오디오 큐에서 데이터를 조각내어 반환하는 생성기 클래스"""
    def __init__(self, audio_queue, is_streaming_flag_func):
        self.audio_queue = audio_queue
        self.is_streaming_flag_func = is_streaming_flag_func

    def __iter__(self):
        while True:
            try:
                # 큐에서 데이터를 기다림 (약간의 타임아웃)
                chunk = self.audio_queue.get(timeout=0.5)
                if chunk is None: # 종료 센티넬 확인
                    return
                yield chunk
            except queue.Empty:
                if not self.is_streaming_flag_func():
                    return
                continue
            except Exception as e:
                logging.error(f"AudioGenerator error: {e}")
                break

def google_stt_streaming_thread():
    """별도 스레드에서 구글 STT 스트리밍을 처리하고 결과를 실시간으로 파싱합니다."""
    global is_streaming, google_stt_client, google_project_id, google_stt_model
    global streaming_transcript, latest_interim_transcript
    global active_mode, auto_language_detection, current_language, google_speech

    try:
        # 클라이언트 초기화 보장
        if not ensure_google_client():
            is_streaming = False
            return

        global google_speech


        # 1. 스트리밍 설정 구성 (Raw PCM이므로 Explicit 감지 사용)
        lang_codes = ["ko-KR"]
        if not auto_language_detection:
            if current_language == "en": lang_codes = ["en-US"]
        else:
            lang_codes = ["ko-KR", "en-US"]

        config = google_speech.RecognitionConfig(
            explicit_decoding_config=google_speech.ExplicitDecodingConfig(
                encoding=google_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                audio_channel_count=1,
            ),
            language_codes=lang_codes,
            model=google_stt_model,
            features=google_speech.RecognitionFeatures(
                enable_automatic_punctuation=(active_mode != "address_poi"),
            ),
        )

        streaming_config = google_speech.StreamingRecognitionConfig(
            config=config,
            streaming_features=google_speech.StreamingRecognitionFeatures(
                interim_results=True  # 중간 결과 활성화
            )
        )

        # 2. 스트리밍 요청 제너레이터 정의
        def request_generator():
            try:
                # 첫 번째 요청: 설정 정보 전송
                yield google_speech.StreamingRecognizeRequest(
                    recognizer=f"projects/{google_project_id}/locations/global/recognizers/_",
                    streaming_config=streaming_config
                )

                # 이후 요청: 오디오 데이터 조각들 전송
                audio_gen = AudioGenerator(audio_queue, lambda: is_streaming)
                for chunk in audio_gen:
                    if chunk is not None:
                        yield google_speech.StreamingRecognizeRequest(audio=chunk)
            except Exception as e:
                logging.error(f"Streaming generator error: {e}")

        # 3. 비동기 스트리밍 호출 및 응답 루프
        responses = google_stt_client.streaming_recognize(requests=request_generator())

        streaming_transcript = ""
        latest_interim_transcript = ""
        for response in responses:
            # 모든 결과 블록을 조합하여 전체 중간 결과를 생성
            temp_interim = ""
            for result in response.results:
                if len(result.alternatives) > 0:
                    transcript = result.alternatives[0].transcript
                    if result.is_final:
                        streaming_transcript += transcript + " "
                    else:
                        temp_interim += transcript

            # 현재 응답의 모든 중간 결과를 합쳐서 업데이트
            current_interim = temp_interim.strip()
            # 텍스트가 이전과 달라졌을 때만 로그 출력 (리소스 절약)
            if current_interim and current_interim != latest_interim_transcript:
                latest_interim_transcript = current_interim
            elif not current_interim:
                latest_interim_transcript = ""

    except Exception as e:
        error_msg = f"스트리밍 스레드 치명적 오류: {str(e)}"
        logging.error(error_msg)
        log_to_console(error_msg)
        is_streaming = False

def stop_recording():
    """녹음 중지 및 오디오 처리 함수"""
    global recording, audio_data, stream, openai, openai_client, api_key, pyperclip
    global google_speech, google_stt_client, google_credentials_path, google_project_id, streaming_thread

    if not recording:
        logging.info("녹음 중이 아닙니다.")
        return

    try:
        # 녹음 중지
        recording = False

        # 스트림 종료
        if stream:
            stream.stop()
            stream.close()

        # 소리로 녹음 종료 알림 (Windows 환경)
        if winsound:
            try:
                winsound.Beep(800, 200)  # 800Hz, 200ms
            except:
                pass

        # 녹음된 데이터가 없으면 종료
        if not audio_data:
            logging.warning("녹음된 데이터가 없습니다.")
            log_to_console(get_msg("no_audio_data"))
            return

        log_to_console(get_msg("processing_audio"))

        # 오디오 데이터 합치기
        try:
            audio = np.concatenate(audio_data, axis=0)

            # 녹음 폴더 확인
            recordings_dir = "recordings"
            if not os.path.exists(recordings_dir):
                os.makedirs(recordings_dir)

            # 현재 시간을 파일명으로 사용
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(recordings_dir, f"recording_{timestamp}.flac")

            # FLAC 파일로 저장 (Whisper API에 최적)
            soundfile.write(filename, audio, 16000)

            # Google Cloud 인증 확인
            if not ensure_google_client():
                log_to_console(get_msg("no_api_key_set"))
                if root:
                    root.after(100, lambda: show_api_key_dialog(required=True))
                return

            # 스트리밍 종료 신호 및 대기
            global is_streaming, streaming_transcript, latest_interim_transcript
            is_streaming = False
            audio_queue.put(None) # 종료 알림

            # 스트리밍 결과 마무리 대기 (큐가 비었더라도 서버 응답을 받을 시간 확보)
            wait_start = time.time()
            # 1.5초 정도로 약간 더 기다리면서 중간 결과가 확정으로 바뀌거나 마지막 데이터가 오길 대기
            while time.time() - wait_start < 1.5:
                time.sleep(0.1)
                # 만약 streaming_thread가 끝났다면 더 기다리지 않음
                if not streaming_thread.is_alive():
                    break

            # 2. 결과 조합 (확정 결과 + 마지막 중간 결과)
            # 만약 중간 결과의 시작이 확정 결과의 끝과 겹친다면 중복 제거
            final_part = streaming_transcript.strip()
            interim_part = latest_interim_transcript.strip()

            if final_part and interim_part:
                # 간단한 중복 체크: interim_part가 final_part에 이미 포함되어 있는지 확인
                if interim_part in final_part:
                    transcript_text = final_part
                else:
                    transcript_text = final_part + " " + interim_part
            else:
                transcript_text = final_part or interim_part

            transcript_text = transcript_text.strip()
            original_text = transcript_text

            # 3. 결과가 없을 경우에만 일반 인식(Unary)으로 백업 시도
            if not transcript_text and ensure_google_client():
                try:
                    log_to_console("실시간 결과 없음 - 일반 인식으로 전환 중...")
                    with open(filename, "rb") as audio_file:
                        audio_content = audio_file.read()

                    config = google_speech.RecognitionConfig(
                        auto_decoding_config=google_speech.AutoDetectDecodingConfig(),
                        language_codes=["ko-KR", "en-US"] if auto_language_detection else ([ "en-US"] if current_language == "en" else ["ko-KR"]),
                        model=google_stt_model,
                        features=google_speech.RecognitionFeatures(enable_automatic_punctuation=(active_mode != "address_poi")),
                    )
                    request = google_speech.RecognizeRequest(
                        recognizer=f"projects/{google_project_id}/locations/global/recognizers/_",
                        config=config,
                        content=audio_content,
                    )
                    response = google_stt_client.recognize(request=request)
                    for result in response.results:
                        if len(result.alternatives) > 0:
                            transcript_text += result.alternatives[0].transcript + " "
                    transcript_text = transcript_text.strip()
                except Exception as backup_e:
                    logging.error(f"Backup recognition failed: {backup_e}")
                    log_to_console(f"백업 인식 실패: {backup_e}")

            # --- 결과 처리 및 출력 ---
            if transcript_text:
                log_to_console("====== " + get_msg("recognition_result") + " ======")
                # 현재 사용 중인 대화 모드 표시
                mode_names = {"general": "일반 대화", "address": "주소", "poi": "장소", "address_poi": "주소+장소"}
                mode_display_name = mode_names.get(active_mode, active_mode)
                log_to_console(f"대화 모드: {mode_display_name}")
                log_to_console("[원본] " + get_msg("recognized_text", transcript_text))

                # 텍스트 정리 (줄바꿈, 공백, 마침표)
                text = transcript_text
                # '엔터' 또는 '개행'을 실제 줄바꿈으로 변경
                text = re.sub(r'\s*(개행|엔터)\s*', '\\n', text)

                # 각 줄에 대해 앞뒤 공백 및 마침표(.) 제거
                # 구글 STT가 문장 끝에 자동으로 찍는 마침표가 줄바꿈과 겹칠 때 지저분해지는 문제 해결
                text = text.strip().strip('.').strip()
                lines = text.split('\\n')
                text = "\\n".join([line.strip().strip('.').strip() for line in lines])

                log_to_console("=========================")
                logging.info(f"[최종인식결과] {text}")

                # 클립보드 복사
                if pyperclip:
                    try:
                        pyperclip.copy(text)
                        log_to_console(get_msg("text_copied"))
                    except Exception as clip_e:
                        logging.error(f"Clipboard error: {clip_e}")

                # 자동 붙여넣기
                if Controller:
                    try:
                        time.sleep(0.1)
                        keyboard = Controller()
                        log_to_console(get_msg("attempting_paste"))
                        keyboard.press(Key.ctrl)
                        keyboard.press('v')
                        keyboard.release('v')
                        keyboard.release(Key.ctrl)
                        log_to_console(get_msg("paste_complete"))
                    except Exception as paste_e:
                        logging.error(f"Paste error: {paste_e}")
            else:
                # 결과가 없고 인증도 안 된 경우 설정창 표시
                if not ensure_google_client() and root:
                    root.after(100, lambda: show_api_key_dialog(required=True))
                else:
                    log_to_console(get_msg("no_text_recognized"))

        except Exception as e:
            logging.error(f"오디오 처리 오류: {str(e)}")
            log_to_console(get_msg("audio_processing_error", str(e)))

    except Exception as e:
        logging.error(f"녹음 종료 오류: {str(e)}")
        log_to_console(get_msg("recording_stop_error", str(e)))

    finally:
        # 상태 초기화
        recording = False
        audio_data = []
        stream = None

def process_address_format(text):
    """주소 형식을 변환: 숫자 발음을 실제 숫자로 변환하고 '의' 등을 주소형식인 하이픈(-)으로 변환"""
    if not text:
        return ""

    # 숫자 발음을 실제 숫자로 변환하는 사전
    number_words = {
        '영': '0', '제로': '0',
        '일': '1', '하나': '1', '원': '1',
        '이': '2', '둘': '2', '투': '2',
        '삼': '3', '셋': '3', '스리': '3', '쓰리': '3',
        '사': '4', '넷': '4', '포': '4',
        '오': '5', '다섯': '5', '파이브': '5',
        '육': '6', '여섯': '6', '식스': '6',
        '륙': '6',
        '칠': '7', '일곱': '7', '세븐': '7',
        '팔': '8', '여덟': '8', '에잇': '8',
        '구': '9', '아홉': '9', '나인': '9'
    }

    # 한글 숫자 패턴 정의
    korean_number_pattern = r'(일|이|삼|사|오|육|륙|칠|팔|구)?(천)?(\s*)?(일|이|삼|사|오|육|륙|칠|팔|구)?(백)?(\s*)?(일|이|삼|사|오|육|륙|칠|팔|구)?(십)?(\s*)?(일|이|삼|사|오|육|륙|칠|팔|구)?'

    matches = re.finditer(korean_number_pattern, text)
    for match in matches:
        full_match = match.group(0)

        # 각 자리수 수집
        thousand_prefix = match.group(1)  # 천 앞의 수
        has_thousand = match.group(2)     # 천 여부
        hundred_prefix = match.group(4)   # 백 앞의 수
        has_hundred = match.group(5)      # 백 여부
        ten_prefix = match.group(7)       # 십 앞의 수
        has_ten = match.group(8)          # 십 여부
        ones = match.group(10)            # 일의 자리

        # 값 초기화
        total_value = 0

        # 천 단위 처리
        if has_thousand:
            if thousand_prefix and thousand_prefix in number_words:
                total_value += int(number_words[thousand_prefix]) * 1000
            else:
                total_value += 1000

        # 백 단위 처리
        if has_hundred:
            if hundred_prefix and hundred_prefix in number_words:
                total_value += int(number_words[hundred_prefix]) * 100
            else:
                total_value += 100

        # 십 단위 처리
        if has_ten:
            if ten_prefix and ten_prefix in number_words:
                total_value += int(number_words[ten_prefix]) * 10
            else:
                total_value += 10

        # 일의 자리 처리
        if ones and ones in number_words:
            total_value += int(number_words[ones])

        # 값이 0보다 클 경우에만 교체
        if total_value > 0 and len(full_match) > 0:
            text = text.replace(full_match, str(total_value), 1)

    # 3. 연속된 한글 숫자 발음 패턴 처리 (예: 사사오이에사사 -> 445244)
    han_num_pattern = r'(일|이|삼|사|오|육|륙|칠|팔|구|영|하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉)(일|이|삼|사|오|육|륙|칠|팔|구|영|하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉)+'

    han_num_matches = re.finditer(han_num_pattern, text)
    for match in han_num_matches:
        han_nums = match.group(0)
        nums = ''
        for char in han_nums:
            if char in number_words:
                nums += number_words[char]
        if nums:
            text = text.replace(han_nums, nums, 1)

    # 주소 구분자를 하이픈(-)으로 변환
    address_separators = ['의', '에', '다시', '데시', '데쉬', '대시', '대쉬']

    for separator in address_separators:
        text = re.sub(r'(\d+)' + separator + r'\s*(\d+)', r'\1-\2', text)
        text = re.sub(r'(\d+)\s+' + separator + r'\s*(\d+)', r'\1-\2', text)
        text = re.sub(r'(\d+)\s+' + separator + r'\s+(\d+)', r'\1-\2', text)

    # 연속된 숫자 사이의 공백 제거 (예: 1 9 5 4 -> 1954)
    text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)

    # 숫자 사이의 콤마 제거
    text = re.sub(r'(\d),\s*(\d)', r'\1\2', text)

    # 주소 형식에서 자주 사용되는 패턴 처리
    text = re.sub(r'(\d+)\s*번\s*지', r'\1번지', text)

    logging.info(f"주소 형식 변환 결과: {text}")
    return text

def speak_text(text):
    """텍스트를 음성으로 변환하여 재생합니다."""
    global google_tts, google_tts_client, is_speaking

    log_to_console(f"[TTS] speak_text 호출됨 (텍스트 길이: {len(text) if text else 0})")

    if not text:
        log_to_console("[TTS] 오류: 텍스트가 비어있습니다.")
        return

    if not google_tts_client:
        log_to_console("[TTS] 오류: TTS 클라이언트가 초기화되지 않았습니다.")
        logging.error("TTS 클라이언트가 초기화되지 않음")
        return

    if not google_tts:
        log_to_console("[TTS] 오류: TTS 모듈이 로드되지 않았습니다.")
        logging.error("TTS 모듈이 로드되지 않음")
        return

    def _speak():
        global is_speaking
        try:
            is_speaking = True

            # 비프음으로 TTS 시작 알림
            try:
                import winsound
                winsound.Beep(800, 150)  # 800Hz, 150ms
                log_to_console("[TTS] 비프음 재생 완료")
            except Exception as beep_err:
                logging.warning(f"비프음 재생 실패: {beep_err}")

            log_to_console(f"[TTS] 음성 합성 시작: '{text[:50]}...'")

            # 입력 텍스트 설정
            log_to_console("[TTS] SynthesisInput 생성 중...")
            synthesis_input = google_tts.SynthesisInput(text=text)

            # 보이스 설정 (한국어 고품질 WaveNet)
            log_to_console("[TTS] VoiceSelectionParams 설정 중...")
            voice = google_tts.VoiceSelectionParams(
                language_code="ko-KR",
                name="ko-KR-Wavenet-A"
            )

            log_to_console("[TTS] AudioConfig 설정 중...")
            audio_config = google_tts.AudioConfig(
                audio_encoding=google_tts.AudioEncoding.LINEAR16,
                sample_rate_hertz=24000
            )

            log_to_console("[TTS] Google TTS API 호출 중...")
            response = google_tts_client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )

            audio_content = response.audio_content
            log_to_console(f"[TTS] 오디오 데이터 수신 완료 ({len(audio_content)} bytes)")

            if len(audio_content) <= 44:
                log_to_console("[TTS] 오류: 오디오 데이터가 너무 작습니다.")
                return

            import numpy as np
            import sounddevice as sd

            # WAV 헤더(44바이트)를 제외하고 numpy 배열로 변환
            audio_data = np.frombuffer(audio_content[44:], dtype=np.int16)
            log_to_console(f"[TTS] 오디오 재생 시작 (샘플 수: {len(audio_data)})")

            sd.play(audio_data, 24000)
            sd.wait()

            log_to_console("[TTS] 음성 재생 완료")

        except Exception as e:
            import traceback
            error_msg = f"TTS 재생 오류: {e}"
            logging.error(error_msg)
            logging.error(traceback.format_exc())
            log_to_console(f"[TTS] {error_msg}")
        finally:
            is_speaking = False
            log_to_console("[TTS] speak_text 종료")

    threading.Thread(target=_speak, daemon=True).start()

def read_selected_text():
    """선택된 텍스트를 읽어옵니다. (Ctrl+C 트릭 사용)"""
    global Controller, Key, pyperclip, ctrl_pressed, alt_pressed, shift_pressed

    if not Controller:
        try:
            from pynput.keyboard import Controller, Key
        except:
            log_to_console("pynput 모듈을 로드할 수 없습니다.")
            return

    try:
        keyboard = Controller()

        # 먼저 현재 눌린 수정자 키들을 해제 (Ctrl+Alt+D 상태에서 호출되므로)
        keyboard.release(Key.ctrl)
        keyboard.release(Key.alt)
        keyboard.release(Key.shift)

        # 키 해제 후 잠시 대기
        time.sleep(0.1)

        # 현재 클립보드 백업
        old_clipboard = ""
        try:
            old_clipboard = pyperclip.paste()
        except:
            pass

        logging.info(f"이전 클립보드: '{old_clipboard[:50]}...' (길이: {len(old_clipboard)})")

        # Ctrl+C 실행 (깨끗한 상태에서)
        keyboard.press(Key.ctrl)
        time.sleep(0.05)
        keyboard.press('c')
        time.sleep(0.05)
        keyboard.release('c')
        time.sleep(0.05)
        keyboard.release(Key.ctrl)

        # 클립보드 업데이트 대기 (충분히)
        time.sleep(0.5)

        # 새로운 클립보드 내용 확인
        new_text = ""
        try:
            new_text = pyperclip.paste()
        except Exception as e:
            logging.error(f"클립보드 읽기 오류: {e}")
            log_to_console(f"클립보드 읽기 오류: {str(e)}")
            return

        logging.info(f"새 클립보드: '{new_text[:50] if new_text else ''}...' (길이: {len(new_text) if new_text else 0})")

        # 새로운 텍스트가 있고, 이전과 다르면 읽기
        if new_text and len(new_text.strip()) > 0:
            if new_text != old_clipboard:
                log_to_console(f"선택된 텍스트 감지: {new_text[:30]}...")
                speak_text(new_text)
            else:
                # 같은 텍스트라도 선택된 것이 있으면 읽기
                if len(new_text.strip()) > 0:
                    log_to_console(f"동일 텍스트 다시 읽기: {new_text[:30]}...")
                    speak_text(new_text)
                else:
                    log_to_console("읽을 텍스트가 선택되지 않았습니다.")
        else:
            log_to_console("읽을 텍스트가 선택되지 않았거나 복사에 실패했습니다.")

    except Exception as e:
        logging.error(f"선택 영역 읽기 오류: {e}")
        log_to_console(f"선택 영역 읽기 오류: {str(e)}")

def extract_readme_files():
    """README 파일을 실행 파일이 있는 디렉토리에 추출합니다."""
    try:
        import os
        import sys

        # 실행 파일 경로 찾기
        if getattr(sys, 'frozen', False):
            # PyInstaller로 패키징된 경우
            base_path = sys._MEIPASS
            exe_dir = os.path.dirname(sys.executable)

            # README 파일 경로
            readme_files = ["README.md", "README.KR.md"]

            for readme_file in readme_files:
                src_path = os.path.join(base_path, readme_file)
                dst_path = os.path.join(exe_dir, readme_file)

                # 파일이 존재하고 대상 경로에 없는 경우에만 복사
                if os.path.exists(src_path) and not os.path.exists(dst_path):
                    import shutil
                    shutil.copy2(src_path, dst_path)
                    print(f"Extracted {readme_file} to {exe_dir}")
    except Exception as e:
        print(f"Error extracting README files: {e}")

# 메인 함수 실행
if __name__ == "__main__":
    print("\n============================================")
    print("     Yeogiaen STT Typer 시작      ")
    print("============================================\n")

    try:
        # 프로그램 다중 실행 체크 - 실행 중이면 종료
        if not prevent_multiple_instances():
            print("이미 프로그램이 실행 중입니다. 중복 실행을 방지합니다.")
            sys.exit(0)

        # 시작 시간 기록
        start_time = datetime.datetime.now()
        print(f"프로그램 시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # 메인 함수 실행
        main()

        # 메인 스레드가 여기에 도달하면 루트 윈도우 메인 루프 실행
        if root:
            root.mainloop()
    except KeyboardInterrupt:
        print("\n사용자에 의해 프로그램이 종료되었습니다.")
    except ImportError as ie:
        logging.error(f"필수 모듈 가져오기 실패: {str(ie)}")
        print(f"오류: 필요한 라이브러리가 설치되지 않았습니다. {str(ie)}")
        print("pip install -r requirements.txt 명령으로 필요한 라이브러리를 설치하세요.")
    except Exception as e:
        logging.error(f"예상치 못한 오류로 프로그램이 종료됩니다: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        print(f"오류: {str(e)}")
    finally:
        # 종료 시간 기록
        end_time = datetime.datetime.now()
        print(f"\n프로그램 종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # 종료 시 clean-up
        if tray_icon:
            try:
                tray_icon.stop()
            except:
                pass
        print("프로그램이 종료됩니다.")
        sys.exit(0)
