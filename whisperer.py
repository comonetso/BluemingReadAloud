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
google_credentials_path = None
google_project_id = None
google_stt_model = "long"  # 기본 모델

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
                logging.info(f"Google Cloud STT 클라이언트 초기화 완료 (프로젝트: {google_project_id})")
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
        level=logging.INFO,
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
        global google_stt_client, google_project_id
        if google_credentials_path and os.path.exists(google_credentials_path):
            try:
                # 클라이언트가 아직 초기화 안 됐으면 초기화
                if not google_stt_client and google_speech:
                    with open(google_credentials_path, 'r', encoding='utf-8') as f:
                        creds_data = json.load(f)
                        google_project_id = creds_data.get('project_id')
                    google_stt_client = google_speech.SpeechClient.from_service_account_file(google_credentials_path)
                    log_to_console(f"Google Cloud STT 클라이언트 초기화 완료 (프로젝트: {google_project_id})")
                elif google_stt_client:
                    log_to_console("Google Cloud 인증 로드 완료")
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

            logging.debug(f"현재 키 상태: Ctrl={ctrl_pressed}, Shift={shift_pressed}, Alt={alt_pressed}")
            logging.debug(f"설정된 단축키: 수정자={hotkey_modifiers}, 키={hotkey_key}")

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
                    if isinstance(key, KeyCode) and key.char:
                        key_char = key.char
                        # If ctrl is pressed and key_char is a control character, convert it to its corresponding letter
                        if ctrl_pressed and len(key_char) == 1 and ord(key_char) < 32:
                            key_char = chr(ord(key_char) + 64)
                        key_match = key_char.upper() == hotkey_key.upper()
                        logging.debug("키 비교: {} vs {} = {}".format(key_char.upper(), hotkey_key.upper(), key_match))
                    elif key:
                        key_str = str(key).replace('Key.', '')
                        key_match = key_str.upper() == hotkey_key.upper()
                        logging.debug("특수키 비교: {} vs {} = {}".format(key_str.upper(), hotkey_key.upper(), key_match))
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

                # Google Cloud 인증 파일 경로 로드
                if "google_credentials_path" in settings:
                    google_credentials_path = settings["google_credentials_path"]

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
            show_hotkey_dialog()
            log_to_console(get_msg("hotkey_updated", "단축키가 업데이트되었습니다."))

        def update_tray_menu():
            # 트레이 아이콘 메뉴 업데이트
            tray_icon.menu = pystray.Menu(
                pystray.MenuItem(get_msg("open_recordings_folder"), open_recordings_folder),
                pystray.MenuItem(get_msg("open_readme"), open_readme_file),
                pystray.MenuItem(get_msg("open_console"), open_console),
                pystray.MenuItem(get_msg("google_credential_setting"), set_google_credentials),
                pystray.MenuItem(get_msg("set_hotkey"), set_hotkey),
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
            dest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), dest_filename)

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
def show_hotkey_dialog():
    """단축키 변경 대화 상자를 표시합니다."""
    global hotkey_modifiers, hotkey_key, Listener, Key, KeyCode

    # 현재 단축키 문자열 생성
    def get_hotkey_string():
        parts = []
        if hotkey_modifiers.get("ctrl", False):
            parts.append("Ctrl")
        if hotkey_modifiers.get("shift", False):
            parts.append("Shift")
        if hotkey_modifiers.get("alt", False):
            parts.append("Alt")
        if hotkey_key:
            parts.append(str(hotkey_key).upper())
        return "+".join(parts)

    # 완전히 독립적인 모달 대화 상자 생성
    dialog = tk.Toplevel()
    dialog.title(get_msg("set_hotkey_title", "단축키 설정"))
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
    ctrl_var = tk.BooleanVar(value=hotkey_modifiers.get("ctrl", True))
    ctrl_cb = tk.Checkbutton(modifiers_frame, text="Ctrl", variable=ctrl_var, font=("Segoe UI", 10))
    ctrl_cb.pack(side=tk.LEFT, padx=10)

    # Shift 체크박스
    shift_var = tk.BooleanVar(value=hotkey_modifiers.get("shift", True))
    shift_cb = tk.Checkbutton(modifiers_frame, text="Shift", variable=shift_var, font=("Segoe UI", 10))
    shift_cb.pack(side=tk.LEFT, padx=10)

    # Alt 체크박스
    alt_var = tk.BooleanVar(value=hotkey_modifiers.get("alt", True))
    alt_cb = tk.Checkbutton(modifiers_frame, text="Alt", variable=alt_var, font=("Segoe UI", 10))
    alt_cb.pack(side=tk.LEFT, padx=10)

    # 키 추가 프레임
    key_frame = tk.Frame(frame)
    key_frame.pack(fill=tk.X, pady=10)

    # 추가 키 라벨
    tk.Label(key_frame, text=get_msg("additional_key", "추가 키(선택사항):"),
             font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 10))

    # 추가 키 입력 필드 (읽기 전용)
    key_var = tk.StringVar(value=str(hotkey_key) if hotkey_key else "")
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

    current_hotkey_label = tk.Label(current_hotkey_frame, text=get_hotkey_string(),
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
        global hotkey_modifiers, hotkey_key

        # 최소한 하나의 수정자 키 필요
        if not (ctrl_var.get() or shift_var.get() or alt_var.get()):
            result_label.config(text=get_msg("need_modifier", "최소 하나의 수정자 키(Ctrl, Shift, Alt)가 필요합니다."),
                               fg="red")
            return

        # 수정자 키 저장
        hotkey_modifiers = {
            "ctrl": ctrl_var.get(),
            "shift": shift_var.get(),
            "alt": alt_var.get()
        }

        # 추가 키 저장
        key_text = key_var.get().strip()
        hotkey_key = key_text if key_text else None

        # 저장된 값 로깅
        logging.info(f"저장되는 단축키 값: 수정자={hotkey_modifiers}, 키={hotkey_key}")
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
        current_hotkey_label.config(text=get_hotkey_string())

        # 단축키 변경 로그 출력
        hotkey_str = get_hotkey_string()
        log_msg = f"단축키가 변경되었습니다: {hotkey_str}"
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
    global recording, audio_data, sd, np, stream, selected_device, winsound # winsound 전역 변수 사용 명시

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
        recording = True

        # 녹음 콜백 함수
        def audio_callback(indata, frames, time, status):
            if status:
                logging.warning(f"녹음 상태 문제: {status}")
            if recording:
                try:
                    if indata.shape[1] == channels:  # 채널 수 확인
                        audio_data.append(indata.copy())
                    else:
                        # 채널 수가 맞지 않으면 로그만 남기고 계속 진행
                        logging.warning(f"채널 수 불일치: 예상 {channels}, 실제 {indata.shape[1]}")
                except Exception as cb_e:
                    logging.error(f"오디오 콜백 오류: {str(cb_e)}")

        # 스트림 시작
        try:
            device_id = selected_device if selected_device is not None else None
            stream = sd.InputStream(
                device=device_id,
                samplerate=samplerate,
                channels=channels,
                callback=audio_callback
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
        log_to_console("녹음 중... (단축키를 떼면 종료)") # 메시지 수정

    except Exception as e:
        error_msg = f"녹음 시작 오류: {str(e)}"
        logging.error(error_msg)
        log_to_console(error_msg)
        recording = False
        # GUI 오류 메시지 표시 (메인 스레드에서)
        if root:
            root.after(10, lambda: messagebox.showerror("녹음 오류", error_msg))

def stop_recording():
    """녹음 중지 및 오디오 처리 함수"""
    global recording, audio_data, stream, openai, openai_client, api_key, pyperclip
    global google_speech, google_stt_client, google_credentials_path, google_project_id

    if not recording:
        logging.info("녹음 중이 아닙니다.")
        return

    try:
        # 녹음 중지
        recording = False
        log_to_console("녹음 종료 중...")

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
            log_to_console(get_msg("saving_audio_file", filename))
            soundfile.write(filename, audio, 16000)

            # Google Cloud 인증 확인 및 자동 복구 (강화된 버전)
            if not google_stt_client:
                if google_credentials_path and os.path.exists(google_credentials_path):
                    try:
                        log_to_console("Google Cloud STT 클라이언트 초기화 시도...")

                        # 전역 모듈이 없으면 여기서 임포트
                        global google_speech
                        if google_speech is None:
                            try:
                                from google.cloud import speech_v2 as google_speech_module
                                google_speech = google_speech_module
                            except ImportError:
                                log_to_console("[오류] google-cloud-speech 패키지가 설치되지 않았습니다.")
                                raise ImportError("google-cloud-speech package missing")

                        # JSON에서 project_id 추출
                        with open(google_credentials_path, 'r', encoding='utf-8') as f:
                            creds_data = json.load(f)
                            global google_project_id
                            google_project_id = creds_data.get('project_id')

                        if google_speech and google_project_id:
                            google_stt_client = google_speech.SpeechClient.from_service_account_file(google_credentials_path)
                            log_to_console(f"클라이언트 초기화 성공: {google_project_id}")
                        else:
                            log_to_console(f"[오류] 정보 부족 - Speech: {google_speech is not None}, Project: {google_project_id is not None}")
                    except Exception as e:
                        logging.error(f"초기화 실패: {str(e)}")
                        log_to_console(f"[오류] 초기화 실패: {str(e)}")

            # 최종 체크
            if not google_stt_client:
                log_to_console(f"[오류] 인증 정보 미설정 (Client: {google_stt_client is not None}, Path: {google_credentials_path is not None})")
                log_to_console(get_msg("no_api_key_set"))
                # 메인 스레드에서 API 키 설정 창 표시
                if root:
                    root.after(100, lambda: show_api_key_dialog(required=True))
                return

            # Google Cloud STT V2로 음성 인식
            if google_stt_client and google_project_id:
                log_to_console("Google Cloud STT로 음성 데이터 전송 중...")

                try:
                    # API 호출 시간 측정 시작
                    api_start_time = time.time()

                    # 언어 코드 설정
                    if auto_language_detection:
                        lang_codes = ["ko-KR", "en-US"]  # 자동 감지용 다중 언어
                        log_to_console("언어 자동 감지 모드 사용 중...")
                    else:
                        if current_language == "ko":
                            lang_codes = ["ko-KR"]
                            log_to_console("언어 설정: 한국어")
                        elif current_language == "en":
                            lang_codes = ["en-US"]
                            log_to_console("언어 설정: English")
                        else:
                            lang_codes = ["ko-KR"]
                            log_to_console("언어 설정: 한국어(기본값)")

                    # 오디오 파일 읽기
                    with open(filename, "rb") as audio_file:
                        audio_content = audio_file.read()

                    # Google STT V2 설정
                    from google.cloud.speech_v2 import RecognizeRequest, RecognitionConfig, RecognitionFeatures, AutoDetectDecodingConfig

                    config = RecognitionConfig(
                        auto_decoding_config=AutoDetectDecodingConfig(),
                        language_codes=lang_codes,
                        model=google_stt_model,
                        features=RecognitionFeatures(
                            enable_automatic_punctuation=(active_mode != "address_poi"),
                        ),
                    )

                    request = RecognizeRequest(
                        recognizer=f"projects/{google_project_id}/locations/global/recognizers/_",
                        config=config,
                        content=audio_content,
                    )

                    # Google STT API 호출
                    response = google_stt_client.recognize(request=request)

                    # 결과 추출
                    transcript_text = ""
                    for result in response.results:
                        if len(result.alternatives) > 0:
                            transcript_text += result.alternatives[0].transcript + " "

                    transcript_text = transcript_text.strip()

                    # API 호출 시간 측정 종료 및 레이턴시 계산
                    api_end_time = time.time()
                    api_latency = (api_end_time - api_start_time) * 1000

                    original_text = transcript_text

                    # 원본 텍스트 로그 추가
                    log_to_console("====== " + get_msg("recognition_result") + " ======")
                    # 현재 사용 중인 대화 모드 표시
                    mode_names = {
                        "general": "일반 대화",
                        "address": "주소",
                        "poi": "장소",
                        "address_poi": "주소+장소"
                    }
                    mode_display_name = mode_names.get(active_mode, active_mode)
                    log_to_console(f"대화 모드: {mode_display_name}")
                    log_to_console(get_msg("api_response_time", api_latency))
                    log_to_console("[원본] " + get_msg("recognized_text", original_text))
                    log_to_console(get_msg("text_length", len(original_text)))

                    # 텍스트 후처리 - 주소 형식 변환 (주소+POI 모드에서만 실행)
                    if active_mode == "address_poi":
                        text = original_text
                        # text = process_address_format(original_text)
                    else:
                        text = original_text

                    # 변환된 텍스트가 원본과 다르면 변환 결과 표시
                    if text != original_text:
                        log_to_console("[변환] " + get_msg("recognized_text", text))
                        log_to_console(get_msg("text_length", len(text)))

                    log_to_console("=========================")
                    logging.info(f"[인식결과] 원본 텍스트: {original_text}")
                    logging.info(f"[인식결과] 변환 텍스트: {text}")

                    # 텍스트 처리
                    if text:

                        # 1. "개행" 또는 "엔터" 및 주변 공백을 줄바꿈 문자로 변환 (정규식 사용)
                        original_text_before_newline = text
                        text = re.sub(r'\s*(개행|엔터)\s*', '\\n', text) # Regex replace

                        # 변환 로그 (이전과 유사)
                        if text != original_text_before_newline:
                            log_to_console("특정 단어('개행', '엔터') 및 주변 공백을 줄바꿈 문자로 변환했습니다.")
                            logging.info(f"[텍스트 변환] 완료. 변환된 텍스트: {text}")
                        else:
                            logging.info("[텍스트 변환] 변환할 단어('개행', '엔터') 없음")

                        # 2. 전체 텍스트 앞뒤 공백/개행 제거 및 시작/끝 마침표 제거
                        cleaned_text = text.strip()
                        initial_cleaned_text = cleaned_text # 비교용
                        if cleaned_text.startswith('.'):
                            cleaned_text = cleaned_text[1:]
                        if cleaned_text.endswith('.'):
                            cleaned_text = cleaned_text[:-1]
                        cleaned_text = cleaned_text.strip() # 마침표 제거 후 남을 수 있는 공백 재제거

                        # 3. 줄 단위 추가 정리: 각 줄 시작의 '.' 및 공백 제거
                        lines = cleaned_text.split('\\n')
                        cleaned_lines = []
                        text_changed_in_loop = False # 줄 단위 변경 추적

                        for line in lines:
                            processed_line = line.strip() # 각 줄의 앞뒤 공백 제거
                            original_processed_line = processed_line
                            if processed_line.startswith('.'):
                                # 맨 앞 '.' 제거 및 뒤따르는 공백 제거
                                processed_line = processed_line[1:].lstrip()

                            cleaned_lines.append(processed_line)
                            if processed_line != original_processed_line:
                                text_changed_in_loop = True

                        # 4. 최종 텍스트 재구성
                        final_cleaned_text = "\\n".join(cleaned_lines)

                        # 최종 변경 로그 및 결과 할당
                        if final_cleaned_text != initial_cleaned_text or text_changed_in_loop:
                             log_to_console("텍스트 앞/뒤 및 각 줄 시작의 불필요한 공백/마침표를 최종 정리했습니다.")
                             log_to_console(f"최종 정리된 텍스트: {final_cleaned_text}")
                             logging.info(f"[텍스트 최종 정리] 완료. 최종 텍스트: {final_cleaned_text}")
                             text = final_cleaned_text # 최종 결과 사용
                        elif cleaned_text != text.strip(): # Regex 변환 후 첫 strip에서만 변경된 경우
                             log_to_console("텍스트 앞/뒤 공백/개행을 제거했습니다.")
                             log_to_console(f"정리된 텍스트: {cleaned_text}")
                             logging.info(f"[텍스트 정리] 앞/뒤 공백 제거 완료. 텍스트: {cleaned_text}")
                             text = cleaned_text # 중간 결과 사용
                        # else: 로그 불필요

                        # 클립보드/붙여넣기 (최종 text 사용)
                        clipboard_success = False
                        if pyperclip:
                            try:
                                pyperclip.copy(text) # 최종 정리된 text 사용
                                clipboard_success = True
                                log_to_console(get_msg("text_copied"))
                            except Exception as clip_e:
                                logging.error(f"클립보드 복사 오류: {str(clip_e)}")
                                log_to_console(get_msg("copy_error", str(clip_e)))

                        # 붙여넣기 방법 1: 컨트롤러로 붙여넣기
                        paste_success = False
                        if Controller:
                            try:
                                time.sleep(0.2)
                                keyboard = Controller()
                                log_to_console(get_msg("attempting_paste"))

                                keyboard.press(Key.ctrl)
                                keyboard.press('v')
                                keyboard.release('v')
                                keyboard.release(Key.ctrl)
                                paste_success = True
                                log_to_console(get_msg("paste_complete"))

                            except Exception as paste_e:
                                logging.error(f"붙여넣기 오류: {str(paste_e)}")
                                log_to_console(get_msg("paste_error", str(paste_e)))

                                # 붙여넣기 실패 시 대체 방법으로 직접 텍스트 입력 시도
                                try:
                                    log_to_console(get_msg("attempting_direct_input"))
                                    time.sleep(0.2)

                                    # 각 문자를 하나씩 입력 시도
                                    for char in text: # 최종 정리된 text 사용
                                        try:
                                            keyboard.type(char)
                                            time.sleep(0.01)  # 약간의 지연
                                        except:
                                            pass

                                    log_to_console(get_msg("direct_input_complete"))
                                except Exception as direct_e:
                                    logging.error(f"직접 텍스트 입력 오류: {str(direct_e)}")
                                    log_to_console(get_msg("direct_input_error", str(direct_e)))

                        # 최종 상태 보고
                        if clipboard_success:
                            log_to_console(get_msg("clipboard_success"))

                        if not paste_success and not clipboard_success:
                            log_to_console(get_msg("all_input_failed"))
                            log_to_console(get_msg("manual_copy"))
                            log_to_console(text)
                    else:
                        log_to_console(get_msg("no_text_recognized"))

                except Exception as e:
                    logging.error(f"Google STT API 오류: {str(e)}")
                    log_to_console(get_msg("recognition_error", str(e)))

                    # API 키 오류인지 확인
                    error_msg = str(e).lower()
                    if "api key" in error_msg or "apikey" in error_msg or "authentication" in error_msg or "인증" in error_msg:
                        error_message = get_msg("api_key_invalid_long")
                        log_to_console(error_message)

                        # 바로 API 키 설정 창 표시 (메인 스레드에서 실행)
                        if root:
                            def show_error_and_settings():
                                messagebox.showerror(get_msg("api_key_error"), error_message)
                                show_api_key_dialog(required=True)

                            root.after(100, show_error_and_settings)

            else:
                log_to_console(get_msg("openai_api_not_set"))
                # Google Cloud 인증이 설정되지 않은 경우 설정 창 표시
                if not google_stt_client and root:
                    root.after(100, lambda: show_api_key_dialog(required=True))

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

    # 개별 한글 숫자 변환은 제거함 - '사랑해요'가 '4랑해요'로 변환되는 문제를 방지
    # 연속된 숫자 발음만 처리하도록 수정
    # for word, number in number_words.items():
    #    text = re.sub(r'\b' + word + r'\b', number, text)

    # 3. 연속된 한글 숫자 발음 패턴 처리
    # 예: 사사오이에사사 -> 445244
    # 최소 두 개 이상의 숫자 발음이 연속될 때만 변환하도록 수정 (예: '사랑해요'의 '사'는 변환하지 않음)
    han_num_pattern = r'(일|이|삼|사|오|육|륙|칠|팔|구|영|하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉)(일|이|삼|사|오|육|륙|칠|팔|구|영|하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉)+'

    # 한글 숫자 발음의 연속된 패턴을 찾아서 처리
    han_num_matches = re.finditer(han_num_pattern, text)
    for match in han_num_matches:
        han_nums = match.group(0)
        # 각 발음을 숫자로 변환
        nums = ''
        for i in range(0, len(han_nums), 1):
            if i < len(han_nums):
                char = han_nums[i]
                if char in number_words:
                    nums += number_words[char]

        # 원본 한글 숫자 발음을 변환된 숫자로 교체
        if nums:
            text = text.replace(han_nums, nums, 1)

    # 주소 구분자를 하이픈(-)으로 변환
    address_separators = ['의', '에', '다시', '데시', '데쉬', '대시', '대쉬']

    # 각 구분자에 대해 정규표현식 생성 및 적용
    for separator in address_separators:
        # 구분자 앞에 공백이 없는 경우
        text = re.sub(r'(\d+)' + separator + r'\s*(\d+)', r'\1-\2', text)
        # 구분자 앞에 공백이 있는 경우
        text = re.sub(r'(\d+)\s+' + separator + r'\s*(\d+)', r'\1-\2', text)
        # 구분자 앞에 공백이 있고 뒤에도 공백이 있는 경우
        text = re.sub(r'(\d+)\s+' + separator + r'\s+(\d+)', r'\1-\2', text)

    # 연속된 숫자 사이의 공백 제거 (예: 1 9 5 4 -> 1954)
    text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)

    # 숫자 사이의 콤마 제거 (예: 4, 4, 5, 2, 4, 4 -> 445244)
    text = re.sub(r'(\d),\s*(\d)', r'\1\2', text)

    # 추가 정리: 주소 형식에서 자주 사용되는 패턴 처리
    text = re.sub(r'(\d+)\s*번\s*지', r'\1번지', text)  # 예: 123 번 지 -> 123번지

    # 로그 추가
    logging.info(f"주소 형식 변환 결과: {text}")

    return text

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
