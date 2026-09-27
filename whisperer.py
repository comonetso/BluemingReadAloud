#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Powered by HRG

"""
BluemingReadAloud - 선택한 글을 읽어주는 TTS 프로그램 (Google Cloud Text-to-Speech)
Copyright (c) 2024 Yeogiaen

과거 STT(받아쓰기)+TTS 겸용 앱이었으나 STT를 걷어내고 TTS 전용으로 전환됨

■ 한눈에 보는 흐름
  단축키(기본 Ctrl+Alt+D) 또는 플로팅 아이콘 클릭
    → read_selected_text : Ctrl+C 를 흉내 내 선택한 글을 클립보드로 가져온다
    → speak_text         : readaloud_text.split_for_reading 으로 줄 단위 조각을 만들고
                           tts_engine.TtsSession(합성 스레드 + 재생 스레드)을 시작한다
    → 엔진 알림          : 재생 스레드 → gui_queue → check_gui_queue(Tk 메인) → _handle_tts_event
                           → 하단 바(bottom_bar.py)·리더 창 형광펜(reader_window.py)

■ 스레드 지도 (⚠️ tkinter 는 스레드 안전하지 않다 — Tk 창은 Tk 메인 스레드에서만 만진다)
  - Tk 메인        : root.mainloop. 모든 창(플로팅 아이콘·하단 바·리더 창·설정 창)과 speak_text
  - pynput 스레드  : 전역 키보드 훅(setup_keyboard_listener). 여기서는 root.after 로 Tk 메인에 넘기기만 한다
  - pystray 스레드 : 트레이 아이콘·메뉴(setup_tray_icon). Tk 일은 gui_queue 에 문자열을 넣어 넘긴다
  - tts-producer / tts-player : 읽기 한 번마다 새로 뜨는 합성·재생 스레드(tts_engine.py). UI 는 gui_queue 로만
  - watchdog       : 30초마다 키보드 훅이 살아 있는지 확인

■ 이 파일에서 절대 깨면 안 되는 약속 (근거: docs/session_logs/2026-06-07 §4, 2026-07-27 §4·§10)
  - 재생 중 판정은 tts_playing 으로 한다(is_speaking 은 죽은 변수라 지웠다)
  - 플로팅 아이콘 보이기/숨기기는 set_controller_visible() 한 곳으로만(트레이 라벨·설정 저장이 함께 움직인다)
  - update_state() 의 숨김 가드를 지우지 말 것(3초마다 하는 lift 가 숨긴 창을 되살린다)
  - 트레이의 "플로팅 보이기" 항목은 비상 복구 통로 — 지우지 말 것
  - 재생 정지는 출력 스트림 abort 로(sd.stop() 은 OutputStream 을 못 멈춘다).
    재생 쪽 finally 에서 멈춤 신호를 clear() 하지 말 것(좀비 스레드 재발)
  - Ctrl+C 전에 클립보드를 비우는 동작을 유지할 것(안 비우면 "선택 없음" 을 판별할 수 없다)
  - 인증은 서비스 계정 JSON(google_credentials.json). .env 방식은 재시도 금지(06-07 세션에서 폐기)
"""
__version__ = "1.1.0"
import sys, os
import threading
import time
import datetime
import json
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import logging
import socket
import winsound  # winsound import 추가 확인
import re # 정규식 모듈 임포트
import queue # GUI 스레드 전달·TTS 선합성용 큐 임포트
# 다른 스레드(트레이·재생 엔진)가 "Tk 메인에서 해 줘" 할 일을 넣는 통로. check_gui_queue 가 100ms 마다 꺼내 처리한다.
# 넣는 것: 문자열 명령("show_tts_settings" 등) 또는 ("tts_event", 세션, 종류, 데이터) 튜플.
gui_queue = queue.Queue()

def resource_path(relative_path):
    """exe 안에 함께 묶은 파일(README·favicon.ico·data\\english-words.js 등)의 실제 경로를 돌려준다.

    PyInstaller 로 만든 exe 는 실행할 때 묶은 파일을 임시 폴더(sys._MEIPASS)에 풀어 놓는다 → 거기를 본다.
    개발 중(python whisperer.py)에는 _MEIPASS 가 없으므로 "지금 작업 폴더" 기준이다.
    ⚠️ 개발 실행 때 작업 폴더가 앱 폴더가 아니면 못 찾을 수 있다 → 앱 폴더를 함께 보는 곳은 get_app_dir() 를 쓴다.
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def get_app_dir():
    """실행 파일 또는 스크립트가 있는 실제 디렉토리 경로를 반환합니다.

    resource_path 와 다른 점: exe 로 실행하면 임시 폴더(_MEIPASS)가 아니라 exe 가 놓인 폴더다.
    사용자가 고치거나 남아야 하는 파일(google_credentials.json 복사본 등)은 여기에 둔다
    (_MEIPASS 는 프로그램이 끝나면 지워진다).
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller로 패키징된 경우
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _favicon_path():
    """favicon.ico 의 절대 경로. 못 찾으면 None.

    옛 설정 창은 iconbitmap("favicon.ico") 상대 경로라 "지금 폴더" 기준으로 찾았다 → exe 로 실행하면
    (dist\\ 에는 exe 옆에 favicon.ico 가 없음) 조용히 건너뛰었다(1차 보고 아이콘_교체.md ④).
    exe 는 spec datas 로 _MEIPASS 에 넣으므로 resource_path 를 먼저, 개발 실행은 앱 폴더를 본다.
    """
    for path in (resource_path("favicon.ico"), os.path.join(get_app_dir(), "favicon.ico")):
        if os.path.exists(path):
            return path
    return None

def _apply_default_window_icon(win):
    """루트 창에 favicon.ico 를 "모든 창의 기본 아이콘"으로 건다 (Tk: wm iconbitmap -default).

    iconbitmap 을 따로 부르지 않는 창(인증 창, 메시지 상자 등)도 이 아이콘을 쓰게 된다.
    """
    path = _favicon_path()
    if not path:
        logging.warning("favicon.ico 를 찾지 못해 창 기본 아이콘을 걸지 않았습니다")
        return
    try:
        win.iconbitmap(default=path)
    except Exception as e:
        logging.warning(f"창 기본 아이콘 설정 실패: {e}")

# 메시지 모듈 가져오기
from messages import messages, get_message

# 읽기용 텍스트 로직(확장 read-aloud-hrg 이식)과 재생 엔진 — 둘 다 모듈 로딩 시점엔 표준 라이브러리만 쓴다
# (numpy·sounddevice·google 은 엔진 안에서 필요할 때 불러온다)
import readaloud_text
import tts_engine

# 하단 컨트롤 바·리더 창(형광펜) — 다른 파일(bottom_bar.py, reader_window.py)에 있다.
# ⚠️ 이 둘은 없어도(파일 없음·문법 오류·import 오류) 앱이 죽으면 안 된다 → 실패하면 None 으로 두고
#    화면 없이 "읽기만" 한다. 무슨 오류였는지는 main() 에서 로그로 남긴다(여기선 로깅 준비 전이라).
try:
    from bottom_bar import BottomBar
    _bottom_bar_import_error = None
except Exception as _e:
    BottomBar = None
    _bottom_bar_import_error = _e
try:
    from reader_window import ReaderWindow
    _reader_window_import_error = None
except Exception as _e:
    ReaderWindow = None
    _reader_window_import_error = _e

# 언어 설정 (기본값: 한국어)
current_language = "ko"  # "ko" 또는 "en"

# 전역 변수
# 수정자 키(Ctrl/Shift/Alt)가 지금 눌려 있는가 — pynput 훅(on_press/on_release)이 직접 켜고 끈다.
# 단축키 판정(on_press)이 이 셋을 본다. on_release 에서 반드시 False 로 돌려놔야 한다(안 그러면 굳는다).
ctrl_pressed = False
shift_pressed = False
alt_pressed = False
root = None             # Tk 창
tray_icon = None        # 트레이 아이콘
tray_menu_updater = None # 트레이 메뉴 갱신 함수 참조 (setup_tray_icon 내부 함수를 외부에서 호출하기 위함)
console_log_file = None # 콘솔 로그 파일
keyboard_listener = None # 키보드 리스너
pynput_initialized = False # Pynput 초기화 여부
floating_controller = None   # 플로팅 컨트롤러 창
controller_canvas = None     # 컨트롤러 캔버스
controller_position = None   # 컨트롤러 위치 {"x": int, "y": int}
# (구 controller_mode 'stt'/'tts' 분기는 TTS 전용 전환으로 제거됨 — 플로팅 버튼은 항상 TTS 동작)
controller_hidden = False    # 컨트롤러 숨김 여부 (우클릭 메뉴로 숨김 / 트레이 메뉴로 복원)

# 중요 모듈들은 load_modules()에서 로드
# (sd = TTS 재생 출력, pyperclip·Controller/Key = 선택 글 Ctrl+C 복사에 사용 — 녹음 전용 아님)
# 처음엔 None 이고 load_modules() 가 채운다. 모듈이 없으면(설치 안 됨) None 으로 남으므로
# 쓰는 곳은 try 로 감싸거나 None 인지 본다.
# ※ winsound 는 위에서 import 했지만 여기서 None 으로 덮고 load_modules() 가 다시 채운다(옛 구조 그대로).
#   그래서 load_modules() 전에 winsound 를 쓰면 안 된다(함수 안에서 필요하면 그 자리에서 import 한다).
pyperclip = None
sd = None
np = None
winsound = None
has_tray_support = False
pystray = None
Image = None
ImageDraw = None
Listener = None
Controller = None
Key = None
KeyCode = None

# Google Cloud 인증 관련 변수 (TTS 클라이언트가 사용)
google_credentials_path = None  # 인증용 서비스 계정 JSON 키 경로
google_project_id = None         # 구글 프로젝트 ID (로그 표시용)

# Google Cloud TTS 관련 변수
google_tts = None          # google.cloud.texttospeech 모듈 (요청 객체를 만들 때 씀). init_tts_client 가 채운다
google_tts_client = None   # TextToSpeechClient. None 이면 "인증 안 됨" — speak_text 가 읽지 않고 돌아간다
tts_hotkey_modifiers = {"ctrl": True, "shift": False, "alt": True} # 기본 TTS 단축키: Ctrl+Alt+D
tts_hotkey_key = "D"
tts_voice_name = "ko-KR-Chirp3-HD-Callirrhoe"  # 기본 음성 모델
tts_speaking_rate = 1.0   # 재생 속도 (0.25 ~ 4.0, 기본 1.0). 합성 때 tts_engine.clamp_rate 로 이 범위에 잘린다
tts_volume = 1.0          # 재생 볼륨 0~1 (하단 바 설정에서 바꾼다. 확장처럼 저장해서 다음 읽기에도 쓴다 — 확장 defaults.js:36 기본 1.0)
# ※ TTS 재생 중 판정은 tts_playing(아래 TTS 재생 상태 변수)으로 한다

# 하단 바·리더 창 설정 (whisperer_settings.json 에 저장)
reader_window_enabled = True     # 트레이 "리더 창" 체크. 켜면 읽는 동안 원문을 보여 주고 읽는 줄을 형광펜으로 칠한다
reader_window_geometry = None    # 사용자가 옮기거나 크기를 바꾼 리더 창 위치 "WxH+X+Y" (None 이면 기본 위치)
bottom_bar_monitor = "foreground"  # 하단 바를 띄울 모니터: "foreground"(읽기 시작 순간 전경 창의 모니터) | "primary"(주 모니터)

# 하단 바·리더 창 객체 (Tk 메인 스레드에서만 만들고 부른다). 만들지 못하면 None — 읽기는 그대로 된다
bottom_bar = None
reader_window = None
_reading_work_area = None        # 이번 읽기에서 하단 바를 붙일 모니터 작업 영역 (left, top, right, bottom)
_reading_segment_idx = None      # 지금 형광펜을 칠한 조각 번호 (리더 창을 읽는 도중에 켤 때 다시 칠하려고)
_english_words = None            # 영어 단어 목록(data/english-words.js). 처음 읽을 때 한 번 불러온다
_english_words_loaded = False

# 사용 가능한 한국어 TTS 음성 목록 (이름, 성별, 유형, 설명)
KOREAN_VOICES = [
    ("ko-KR-Chirp3-HD-Callirrhoe", "여성", "Chirp3-HD", "고품질 한/영 자연스러운 여성 목소리 (추천)"),
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

# 프로그램 다중 실행 방지
def prevent_multiple_instances():
    """프로그램의 다중 실행을 방지합니다 (소켓 + Windows Mutex 이중 방어)

    두 개가 동시에 뜨면 전역 단축키 훅·트레이 아이콘이 둘이 되어 한 번 눌렀는데 두 번 읽는다.
    반환: True = 내가 첫 번째(계속 실행) / False = 이미 실행 중(호출부가 종료한다).
    - 1차 Mutex 이름 "YeogiaenSTTTyper_SingleInstance" 는 옛 앱 이름 그대로다. 바꾸면 옛 exe 와 새 exe 가
      동시에 뜰 수 있으니 이름을 바꿀 때는 그 점을 알고 바꿀 것.
    - 2차 소켓은 UDP 51888 포트를 붙잡아 두는 방식(Mutex 생성이 실패했을 때의 백업).
      (CLAUDE.md 의 "51889 test port" 설명은 옛 문서다 — 코드는 51888)
    - 이 함수는 로깅 준비(setup_logging) 전에 불린다 → logging 호출은 기본 설정으로 나간다.
    """
    # 1차: Windows Named Mutex 방식 (가장 확실)
    # _instance_mutex 를 전역에 붙잡아 둬야 프로그램이 도는 동안 Mutex 가 유지된다(지역 변수면 사라질 수 있음)
    global _instance_mutex
    try:
        import ctypes
        _instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "YeogiaenSTTTyper_SingleInstance")
        last_error = ctypes.windll.kernel32.GetLastError()
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            logging.warning("Mutex: 프로그램이 이미 실행 중입니다.")
            if hasattr(sys, 'frozen'):
                try:
                    import tkinter as tk
                    from tkinter import messagebox
                    root = tk.Tk()
                    root.withdraw()
                    messagebox.showwarning(
                        "BluemingReadAloud",
                        "프로그램이 이미 실행 중입니다.\n시스템 트레이에서 프로그램 아이콘을 확인하세요."
                    )
                    root.destroy()
                except:
                    pass
            else:
                print("프로그램이 이미 실행 중입니다.")
            return False
    except Exception as e:
        logging.warning(f"Mutex 생성 실패, 소켓 방식으로 대체: {e}")

    # 2차: 소켓 포트 바인딩 방식 (백업)
    try:
        global single_instance_socket
        single_instance_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        single_instance_socket.bind(('localhost', 51888))
        logging.info("프로그램 단일 인스턴스 확인 완료")
    except socket.error:
        logging.warning("소켓: 프로그램이 이미 실행 중입니다.")
        if not hasattr(sys, 'frozen'):
            print("프로그램이 이미 실행 중입니다.")
        return False

    return True  # 첫 번째 인스턴스

# 기본 로깅 설정
def setup_logging():
    """로깅 설정 — 파일 두 종류를 만든다.

    - logs\\whisperer_YYYYMMDD_HHMMSS.log : logging 모듈 기록(실행마다 새 파일, DEBUG 까지)
    - whisperer_console.log              : log_to_console() 기록. 트레이 "콘솔 열기" 창이 이 파일을 실시간으로 보여 준다
    ⚠️ 두 경로 모두 "지금 작업 폴더" 기준 상대 경로다(exe 는 보통 exe 폴더에서 실행되므로 거기에 생긴다).
    exe(console=False)는 sys.stdout 이 None 이라 화면 출력 핸들러를 붙이지 않는다(붙이면 쓰기 오류).
    """
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
    # PyInstaller console=False에서는 sys.stdout이 None이므로 방어 처리
    log_handlers = [logging.FileHandler(log_file, encoding='utf-8')]
    if sys.stdout is not None:
        log_handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        handlers=log_handlers
    )

    # 콘솔 로그 초기화
    try:
        with open(console_log_file, 'w', encoding='utf-8') as f:
            f.write(f"=== BluemingReadAloud 로그 시작: {timestamp} ===\n\n")

        # 시작 로그 기록
        log_to_console(f"=== BluemingReadAloud v{__version__} 콘솔 ===")
        log_to_console("이 창을 닫아도 프로그램은 계속 실행됩니다.")
        log_to_console("\n로그 출력을 시작합니다...\n")

        logging.info("로깅 시스템 초기화 완료")
    except Exception as e:
        logging.error(f"로그 파일 초기화 오류: {str(e)}")

# 콘솔 로그 기록 함수
def log_to_console(message):
    """콘솔 로그 파일에 메시지 기록 (사용자가 트레이 "콘솔 열기" 로 보는 로그).

    어느 스레드에서 불러도 된다(재생 엔진·트레이·키보드 훅 모두 부른다). 절대 예외를 밖으로 내지 않는다 —
    로그 때문에 재생이나 훅이 죽으면 안 되기 때문이다. 대신 쓰기가 실패하면 조용히 버린다.
    ⚠️ 키보드 훅 콜백(on_press/on_release) 안에서는 부르지 말 것(파일 I/O 가 훅 시간 제한을 넘길 수 있다).
    """
    global console_log_file

    # 콘솔에 출력 (sys.stdout이 None이 아닐 때만)
    if sys.stdout is not None:
        try:
            print(message)
        except Exception:
            pass

    # 파일에 기록
    if console_log_file:
        try:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            with open(console_log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception:
            pass

def _format_hotkey(modifiers, key):
    """단축키 설정을 'Ctrl+Alt+D' 형태 문자열로 만든다 (로그 표시용)."""
    # main() 초기화 도중(리스너·트레이 설정 전)에 불리므로, 여기서 예외가 나면 main 전체가 중단된다.
    # 설정 파일이 손상돼 modifiers가 dict가 아니어도 로그 표시 때문에 앱이 멈추지 않게 한다.
    if not isinstance(modifiers, dict):
        modifiers = {}
    parts = []
    if modifiers.get("ctrl", False):
        parts.append("Ctrl")
    if modifiers.get("shift", False):
        parts.append("Shift")
    if modifiers.get("alt", False):
        parts.append("Alt")
    if key:
        parts.append(str(key))
    return "+".join(parts) if parts else "(없음)"

def init_tts_client(credentials_path):
    """서비스 계정 JSON으로 Google Cloud TTS 클라이언트를 초기화한다.

    STT와 완전히 독립이다 (과거에는 STT 초기화 분기 안에서만 TTS를 만들었다).
    반환:
      True  — google_tts / google_tts_client 준비 완료
      False — google-cloud-texttospeech 모듈을 불러올 수 없어 건너뜀 (로그만 남김)
    인증 파일이 잘못돼 JSON 읽기나 클라이언트 생성이 실패하면 예외를 그대로 올린다
    (호출부가 인증 창을 띄우거나 오류를 표시한다).

    부르는 곳 두 군데:
      - main() 시작 때: 설정에 저장된 경로(또는 앱 폴더의 google_credentials.json)로 시도. 예외면 필수 인증 창.
      - show_api_key_dialog 의 "설정" 버튼: 사용자가 고른 파일을 앱 폴더로 복사한 뒤 시도.
    왜 서비스 계정 JSON 인가: 2026-06-07 에 .env(API 키) 방식을 시도했다가 STT v2 의 IAM 제약 때문에 폐기했다.
      STT 는 걷어냈지만 인증 방식은 사용자 결정으로 JSON 을 유지한다(재시도 금지 — 06-07 로그 §10).
    전역 google_tts / google_tts_client 는 성공했을 때만 바꾼다 → 실패해도 앞에서 만든 클라이언트는 그대로 남는다.
    """
    global google_tts, google_tts_client, google_project_id

    # JSON에서 project_id 추출 (잘못된 JSON이면 여기서 예외)
    with open(credentials_path, 'r', encoding='utf-8') as f:
        creds_data = json.load(f)
    google_project_id = creds_data.get('project_id')

    # ⚠️ ImportError만 잡으면 안 된다. protobuf 버전 충돌(TypeError) 같은 import 시점 오류가
    #    "인증 파일 오류"로 올라가면, 필수 인증 창이 저장해도 계속 실패 + 취소 불가 → 영영 못 닫힌다.
    #    (옛 코드도 TTS import 오류는 except Exception으로 로그만 남겼다)
    try:
        from google.cloud import texttospeech
    except Exception as e:
        logging.error(f"Google Cloud TTS 모듈 로딩 실패: {e}")
        log_to_console(f"[TTS] TTS 모듈(google-cloud-texttospeech)을 불러올 수 없습니다: {e}")
        return False

    client = texttospeech.TextToSpeechClient.from_service_account_file(credentials_path)
    google_tts = texttospeech
    google_tts_client = client
    log_to_console(f"[TTS] Google Cloud TTS 클라이언트 초기화 성공! (프로젝트: {google_project_id})")
    logging.info(f"Google Cloud TTS 클라이언트 초기화 완료 (프로젝트: {google_project_id})")
    return True

def main():
    """앱 초기화 순서를 한곳에 모은 함수. 순서가 곧 의존 관계라 함부로 바꾸지 말 것.

    1) README 추출 → 2) 로깅 → 3) 숨긴 Tk 루트(모든 창의 부모, 기본 아이콘) → 4) 모듈 로딩(load_modules)
    → 5) 설정 로딩(load_settings) → 6) 인증(TTS 클라이언트, 실패하면 필수 인증 창)
    → 7) 키보드 훅 → 8) 트레이(여기서 gui_queue 확인 루프도 시작) → 9) 플로팅 아이콘 → 10) root.mainloop()
    - 키보드 훅(7)보다 설정(5)이 먼저여야 저장된 단축키로 훅이 뜬다.
    - 플로팅 아이콘(9)은 설정의 controller_hidden·controller_position 을 쓰므로 설정 뒤.
    - 하단 바·리더 창은 여기서 만들지 않는다. 첫 읽기 때 _ensure_reading_ui() 가 만든다(안 쓰면 안 만든다).
    - 여기서 예외가 나면 오류 상자를 띄우고 함수가 끝난다. 그 뒤 아래 __main__ 블록이 root 가 있으면
      mainloop 를 한 번 더 돈다(옛 구조 그대로 — 초기화가 중간에 끊겨도 트레이가 떠 있으면 앱이 남는다).
    """
    # README 파일 추출
    extract_readme_files()

    # 현재 언어 설정 표시
    lang_name = "English" if current_language == 'en' else "한국어"
    print(f"Current language: {lang_name}")

    try:
        print("프로그램 시작 중...")
        print("============================")
        print("= BluemingReadAloud =")
        print("============================")

        # 로깅 설정
        setup_logging()
        logging.info("애플리케이션 시작")
        log_to_console("로깅 시스템 초기화 완료")


        # Tkinter 루트 창 생성 (숨김)
        global root
        # 모던한 테마 적용 (cosmo 테마 사용)
        # iconphoto=None: ttkbootstrap 은 기본값('')이면 자기 아이콘을 "모든 창의 기본 아이콘"으로 건다
        # (ttkbootstrap window.py Window.__init__ 의 iconphoto(True, ...)). 그러면 iconbitmap 을 따로 안 부르는
        # 인증 창 같은 곳에 ttkbootstrap 아이콘이 뜬다 → 끄고 아래에서 favicon.ico 를 기본 아이콘으로 건다.
        root = ttk.Window(themename="cosmo", iconphoto=None)
        root.withdraw()  # 창 숨기기
        root.title("BluemingReadAloud")
        _apply_default_window_icon(root)

        # 하단 바·리더 창 모듈을 못 불러왔으면 여기서 알린다(없어도 읽기는 된다)
        if _bottom_bar_import_error is not None:
            logging.warning(f"하단 바 모듈(bottom_bar) 로딩 실패 — 바 없이 읽기만 합니다: {_bottom_bar_import_error}")
            log_to_console(f"[UI] 하단 바를 불러오지 못했습니다(바 없이 읽기만 합니다): {_bottom_bar_import_error}")
        if _reader_window_import_error is not None:
            logging.warning(f"리더 창 모듈(reader_window) 로딩 실패 — 형광펜 없이 읽기만 합니다: {_reader_window_import_error}")
            log_to_console(f"[UI] 리더 창을 불러오지 못했습니다(형광펜 없이 읽기만 합니다): {_reader_window_import_error}")

        # 모듈 로딩
        print("주요 모듈 로딩 중...")
        load_modules()
        log_to_console("모듈 로딩 완료")

        # 설정 로드 (언어, 단축키 등)
        load_settings()
        logging.info(f"현재 언어: {current_language}")
        # 현재 언어 설정을 콘솔에 표시
        language_name = "한국어" if current_language == "ko" else "English"
        log_to_console(f"현재 언어 설정: {language_name} ({current_language})")

        # 현재 읽어주기(TTS) 단축키 설정 로그
        log_to_console(f"현재 읽어주기 단축키 설정: {_format_hotkey(tts_hotkey_modifiers, tts_hotkey_key)}")

        # Google Cloud 인증 확인 및 설정
        print("Google Cloud 인증 확인 중...")
        log_to_console("Google Cloud 인증 확인 중...")

        # 설정에서 경로를 이미 로드했으므로, TTS 클라이언트 초기화 시도
        # (STT와 무관하게 인증 경로만 유효하면 TextToSpeechClient를 만든다)
        if google_credentials_path and os.path.exists(google_credentials_path):
            try:
                log_to_console("[TTS] TTS 클라이언트 초기화 시도 중...")
                init_tts_client(google_credentials_path)
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

        # 플로팅 미니 컨트롤러 설정
        print("플로팅 컨트롤러 설정 중...")
        log_to_console("플로팅 컨트롤러 설정 중...")
        setup_floating_controller()

        # 초기화 완료
        logging.info("초기화 완료")
        print("\n프로그램이 시스템 트레이에서 실행 중입니다.")
        log_to_console("===================================")
        log_to_console("프로그램이 실행 중입니다.")
        log_to_console("시스템 트레이에서 아이콘을 확인하세요.")
        log_to_console(f"읽어주기 단축키: {_format_hotkey(tts_hotkey_modifiers, tts_hotkey_key)} (글을 선택하고 누르면 읽기 시작)")
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
    """필요한 모듈을 동기적으로 로딩 — 결과는 같은 이름의 전역 변수(pyperclip, sd, np, ...)에 들어간다.

    왜 파일 맨 위에서 import 하지 않나: 옛 구조가 "무거운 모듈을 나중에, 없으면 없는 대로" 였다.
    하나가 없어도(ImportError) 앱 전체가 죽지 않고 그 기능만 빠진다(예: pystray 가 없으면 트레이 없이).
    ⚠️ 함수 안 import 가 전역을 채우는 건 위 global 선언 덕분이다. global 목록에서 이름을 빼면
       그 모듈은 이 함수 안에서만 살고 전역은 None 으로 남는다.
    """
    global pyperclip, sd, np, winsound, pystray, Image, ImageDraw
    global Listener, Controller, Key, KeyCode, has_tray_support

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

    # Google Cloud TTS 모듈·클라이언트는 main()의 인증 확인 단계에서 init_tts_client()로 초기화한다

# 키보드 리스너 설정
def setup_keyboard_listener():
    """전역 키보드 훅(pynput Listener)을 띄워 읽기 단축키를 감시한다. 반환: 성공 True / 실패 False.

    동작 요약
      - on_press  : 수정자 키 상태를 기록하고, "설정된 수정자 + 설정된 글자" 가 맞으면 read_selected_text 를
                    Tk 메인으로 넘긴다(root.after). 읽기/중지/아이콘 토글 3방향 분기는 read_selected_text 가 한다.
      - on_release: 수정자 키 상태를 되돌린다.
      - watchdog  : 30초마다 훅 스레드가 죽었는지 보고 죽었으면 새로 띄운다(윈도우가 느린 훅을 떼어 내는 일이 있어서).
    ⚠️ 훅 콜백(on_press/on_release)은 윈도우가 시간 제한을 둔다. 여기서 파일 I/O·로그·오래 걸리는 일을 하면
       윈도우가 훅을 조용히 떼어 내 단축키가 먹통이 된다 → 콜백은 변수만 바꾸고 일은 root.after 로 넘긴다.
    ⚠️ 이 함수는 다시 불려도 된다(단축키를 바꾼 뒤 등). 기존 리스너를 멈추고 새로 띄운다.
       다만 watchdog 스레드는 부를 때마다 하나씩 더 생긴다(옛 구조 그대로 — 지금은 main 에서 한 번만 부른다).
    """
    global Listener, Key, Controller, KeyCode, pynput_initialized
    # 설정 파일의 단축키(tts_hotkey)를 다시 읽는다 — on_press 는 전역 tts_hotkey_modifiers/tts_hotkey_key 를 본다
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
        """키 누름 이벤트 핸들러 — Windows 훅 타임아웃 방지를 위해 I/O 금지

        pynput 스레드에서 불린다(Tk 메인 아님). 단축키가 맞으면 root.after 로 Tk 메인에 일을 넘긴다.
        (root.after 는 다른 스레드에서 불러도 tkinter 가 Tk 메인으로 전달해 준다 — 옛날부터 이렇게 동작해 왔다.
         단 Tk 창을 직접 만지는 호출은 여기서 하면 안 된다.
         ⚠️ 알려진 한계: 이 전달은 Tk 메인이 이벤트를 처리할 때까지 기다린다. read_selected_text 가 Tk 메인을
         약 0.8초 잡고 있는 동안 단축키를 또 누르면 이 콜백도 그만큼 멈춘다 → 윈도우 훅 시간 제한에 걸릴 수 있다.
         gui_queue.put 으로 바꾸면 안 기다리지만 반응이 최대 100ms 늦어진다 — 바꿀지는 사용자 결정으로 남겼다)
        key 는 두 종류다: KeyCode(글자 키, .char/.vk 가 있음) / Key(특수 키, Key.ctrl_l 같은 것).
        """
        global ctrl_pressed, shift_pressed, alt_pressed

        try:
            # 키 상태 업데이트 (I/O 없이 빠르게 처리)
            if key == Key.ctrl_l or key == Key.ctrl_r:
                ctrl_pressed = True
            elif key == Key.shift_l or key == Key.shift_r:
                shift_pressed = True
            elif key == Key.alt_l or key == Key.alt_r:
                alt_pressed = True

            # TTS 단축키 확인
            # (재생 중에도 통과시켜야 한다 — 선택 없이 누르면 read_selected_text가 "중지"로 분기한다.
            #  옛 가드(녹음 여부 + 죽은 재생 플래그 검사)는 사실상 항상 참이었으므로 제거해도 동작 동일.
            #  재생 중 판정이 필요하면 tts_playing을 쓸 것)
            tts_modifier_match = (
                (not tts_hotkey_modifiers.get("ctrl", False) or ctrl_pressed) and
                (not tts_hotkey_modifiers.get("shift", False) or shift_pressed) and
                (not tts_hotkey_modifiers.get("alt", False) or alt_pressed)
            )

            # 눌린 키가 설정된 단축키 글자(tts_hotkey_key, 예 "D")인지
            tts_key_match = False
            if tts_hotkey_key:
                if isinstance(key, KeyCode):
                    key_char = key.char
                    if key_char:
                        # Ctrl 을 누른 채 글자를 치면 pynput 이 제어 문자(Ctrl+D → '\x04')를 준다.
                        # 32 미만 제어 문자는 +64 하면 원래 대문자('\x04'+64 = 'D')로 돌아온다.
                        if ctrl_pressed and len(key_char) == 1 and ord(key_char) < 32:
                            key_char = chr(ord(key_char) + 64)
                        tts_key_match = key_char.upper() == tts_hotkey_key.upper()
                    elif key.vk is not None:
                        # Ctrl+Alt 조합 등에서는 char 가 None 으로 올 때가 있다 → 가상 키 코드(A~Z = 65~90)로 판정
                        try:
                            if 65 <= key.vk <= 90:
                                tts_key_match = chr(key.vk).upper() == tts_hotkey_key.upper()
                        except:
                            pass
                elif key:
                    # 특수 키(F1 등)를 단축키로 쓴 경우: "Key.f1" → "f1" 로 비교
                    key_str = str(key).replace('Key.', '')
                    tts_key_match = key_str.upper() == tts_hotkey_key.upper()

            if tts_modifier_match and tts_key_match:
                # 10ms 뒤 Tk 메인에서 실행 — 훅 콜백은 곧바로 돌아가야 한다(위 docstring).
                # read_selected_text 가 선택 있음=읽기 / 선택 없음+재생 중=중지 / 선택 없음+대기=아이콘 토글 로 가른다.
                if root:
                    root.after(10, read_selected_text)
                else:
                    read_selected_text()
                return True

        except Exception:
            pass  # 훅 콜백에서 예외 로깅도 타임아웃 유발 가능

    def on_release(key):
        """키 뗌 이벤트 핸들러 — Windows 훅 타임아웃 방지를 위해 I/O 금지

        수정자 키를 떼면 눌림 상태를 False 로 되돌린다. 항상 True 를 돌려준다(False 면 pynput 이 리스너를 멈춘다).
        """
        global ctrl_pressed, shift_pressed, alt_pressed

        try:
            # 키 상태 업데이트 (I/O 없이 빠르게 처리)
            # ⚠️ 이 해제 블록은 절대 지우지 말 것 — 없으면 수정키가 눌린 상태로 굳어
            #    (예: 단축키 Shift+X) Shift를 한 번 누른 뒤로는 X만 쳐도 읽기가 시작된다.
            if key == Key.ctrl_l or key == Key.ctrl_r:
                ctrl_pressed = False
            elif key == Key.shift_l or key == Key.shift_r:
                shift_pressed = False
            elif key == Key.alt_l or key == Key.alt_r:
                alt_pressed = False

        except Exception:
            pass  # 훅 콜백에서 예외 로깅도 타임아웃 유발 가능

        return True

    # 리스너 시작
    try:
        global keyboard_listener
        if 'keyboard_listener' in globals() and keyboard_listener is not None:
            try:
                keyboard_listener.stop()
            except:
                pass

        keyboard_listener = Listener(on_press=on_press, on_release=on_release)
        keyboard_listener.daemon = True
        keyboard_listener.start()
        log_to_console("키보드 리스너가 시작되었습니다. (단축키 설정: 읽어주기)")

        # 키보드 리스너 watchdog 시작 (30초마다 리스너 생존 확인, 죽으면 재시작)
        def keyboard_watchdog():
            """(별도 데몬 스레드) 훅 스레드가 죽었으면 같은 콜백으로 새로 띄운다. 앱이 끝날 때까지 돈다.

            수정자 키 상태(ctrl_pressed 등)는 되돌리지 않는다(옛 구조 그대로). 그래서 훅이 죽어 있던 사이에 뗀
            수정자 키는 그 키를 다시 눌렀다 뗄 때까지 "눌림" 으로 남을 수 있다(드묾 — 알려진 한계).
            """
            global keyboard_listener
            while True:
                try:
                    import time as _time
                    _time.sleep(30)
                    if keyboard_listener and not keyboard_listener.is_alive():
                        log_to_console("[Watchdog] 키보드 리스너 재시작 중...")
                        keyboard_listener = Listener(on_press=on_press, on_release=on_release)
                        keyboard_listener.daemon = True
                        keyboard_listener.start()
                        log_to_console("[Watchdog] 키보드 리스너 재시작 완료")
                except Exception:
                    pass

        watchdog_thread = threading.Thread(target=keyboard_watchdog, daemon=True)
        watchdog_thread.start()

        return True

    except Exception as e:
        log_to_console(f"오류: 키보드 리스너 시작 실패: {str(e)}")
        return False

# 언어 설정 저장/로드 함수 수정
def save_settings():
    """지금 전역 설정값을 whisperer_settings.json 에 통째로 쓴다(부분 갱신 아님).

    어느 스레드에서 불려도 되지만(트레이 스레드의 언어 변경 등) 동시에 두 곳에서 쓰는 경우는 막지 않는다
    (옛 구조 그대로 — 설정 저장은 사람 손으로 드물게 일어난다).
    ⚠️ 파일은 "지금 작업 폴더" 기준 상대 경로다. 사용자 데이터이므로 키 이름을 바꾸면 옛 설정을 못 읽는다
       → 키를 바꿀 땐 load_settings 에 옛 키 읽기를 남길 것.
    키 목록: language, google_credentials_path, tts_hotkey{modifiers,key}, tts_settings{voice_name,speaking_rate,volume},
            controller_position, controller_hidden, reader_window_enabled, reader_window_geometry, bottom_bar_monitor
    """
    try:
        # ※ 설정 파일 전체를 이 dict로 덮어쓴다. 옛 STT 키(stt_enabled, hotkey, auto_detection,
        #   google_settings, whisper_settings)는 로드 시 무시되고, 첫 저장 때 파일에서 빠진다.
        settings = {
            "language": current_language,
            "google_credentials_path": google_credentials_path,
            "tts_hotkey": {
                "modifiers": tts_hotkey_modifiers,
                "key": tts_hotkey_key
            },
            "tts_settings": {
                "voice_name": tts_voice_name,
                "speaking_rate": tts_speaking_rate,
                "volume": tts_volume
            },
            "controller_position": controller_position,
            "controller_hidden": controller_hidden,
            # 하단 바·리더 창 (2026-09-28 추가)
            "reader_window_enabled": reader_window_enabled,
            "reader_window_geometry": reader_window_geometry,
            "bottom_bar_monitor": bottom_bar_monitor
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

def load_settings():
    """whisperer_settings.json 을 읽어 전역 설정값을 채운다. 파일이 없거나 키가 없으면 기본값을 그대로 둔다.

    부르는 곳: main() 시작 때, setup_keyboard_listener() 안(단축키를 다시 읽으려고).
    - 파일이 깨졌으면(JSON 오류) 로그만 남기고 기본값으로 계속 간다 — 설정 때문에 앱이 안 뜨면 안 된다.
    - 새 키(reader_window_*, bottom_bar_monitor, tts_settings.volume)는 값 모양이 이상하면 무시한다.
    - 인증 파일 경로가 없거나 가리키는 파일이 사라졌으면 앱 폴더의 google_credentials.json 을 대신 찾는다
      (인증 창이 "설정" 할 때 거기로 복사해 두므로, 앱 폴더를 통째로 옮겨도 인증이 살아 있다).
    ⚠️ 여기서 읽은 tts_speaking_rate 는 범위를 자르지 않는다 — 합성할 때 tts_engine.clamp_rate 가 자른다.
    """
    global current_language, google_credentials_path
    global tts_hotkey_modifiers, tts_hotkey_key, tts_voice_name, tts_speaking_rate, tts_volume
    global controller_position, controller_hidden
    global reader_window_enabled, reader_window_geometry, bottom_bar_monitor
    try:
        if os.path.exists('whisperer_settings.json'):
            with open('whisperer_settings.json', 'r', encoding='utf-8') as f:
                settings = json.load(f)
                print(f"로드된 설정: {settings}")
                if "language" in settings:
                    current_language = settings["language"]
                # 옛 STT 키(stt_enabled, hotkey, auto_detection, google_settings, whisper_settings)는
                # 남아 있어도 읽지 않는다 — stt_enabled=true가 저장돼 있어도 TTS 전용으로 동작

                # TTS 단축키 로드
                if "tts_hotkey" in settings:
                    if "modifiers" in settings["tts_hotkey"]:
                        tts_hotkey_modifiers = settings["tts_hotkey"]["modifiers"]
                    if "key" in settings["tts_hotkey"]:
                        tts_hotkey_key = settings["tts_hotkey"]["key"]

                # TTS 설정 로드
                if "tts_settings" in settings:
                    if "voice_name" in settings["tts_settings"]:
                        tts_voice_name = settings["tts_settings"]["voice_name"]
                    if "speaking_rate" in settings["tts_settings"]:
                        tts_speaking_rate = settings["tts_settings"]["speaking_rate"]
                    if "volume" in settings["tts_settings"]:
                        tts_volume = tts_engine.clamp_volume(settings["tts_settings"]["volume"])

                # 하단 바·리더 창 설정 (없으면 기본값 유지). 값이 이상하면 무시한다
                if isinstance(settings.get("reader_window_enabled"), bool):
                    reader_window_enabled = settings["reader_window_enabled"]
                if "reader_window_geometry" in settings:
                    geom = settings["reader_window_geometry"]
                    reader_window_geometry = geom if isinstance(geom, str) and geom else None
                if settings.get("bottom_bar_monitor") in ("foreground", "primary"):
                    bottom_bar_monitor = settings["bottom_bar_monitor"]

                # Google Cloud 인증 파일 경로 로드
                if "google_credentials_path" in settings:
                    google_credentials_path = settings["google_credentials_path"]

                # 경로가 유효하지 않으면 앱 디렉토리 내의 기본 파일 확인 (백업/이동 대응)
                if not google_credentials_path or not os.path.exists(google_credentials_path):
                    default_path = os.path.join(get_app_dir(), "google_credentials.json")
                    if os.path.exists(default_path):
                        google_credentials_path = default_path
                        logging.info(f"기본 위치에서 인증 파일 발견: {google_credentials_path}")

                # 컨트롤러 위치 로드
                if "controller_position" in settings:
                    controller_position = settings["controller_position"]

                # 컨트롤러 숨김 상태 로드 (숨긴 채 종료했으면 다음 실행도 숨김 유지)
                if "controller_hidden" in settings:
                    controller_hidden = bool(settings["controller_hidden"])

            logging.info(f"설정 로드 완료: 언어={current_language}, 읽어주기 단축키 수정자={tts_hotkey_modifiers}, 단축키={tts_hotkey_key}")
            print(f"설정 로드 완료: 언어={current_language}, 읽어주기 단축키 수정자={tts_hotkey_modifiers}, 단축키={tts_hotkey_key}")
        # 설정 파일이 없는 경우는 무시하고 기본값 사용
    except Exception as e:
        logging.error(f"설정 로드 오류: {str(e)}")
        print(f"설정 로드 오류: {str(e)}")

# 단일 설정 함수들 (이전 코드와의 호환성)
# (지금은 부르는 곳이 없다. 옛 코드가 부르던 이름이라 남겨 둔 껍데기 — 전체 저장/로드와 같다)
def save_language_setting():
    save_settings()

def load_language_setting():
    load_settings()

# 메시지 가져오기 함수 래퍼
def get_msg(key, *args):
    """messages.py 의 문구를 지금 언어(current_language)로 가져온다. args 는 문구 안 {} 자리에 들어간다.

    하단 바·리더 창에도 이 함수를 넘긴다(get_msg 인자). 없는 키면 "[Missing message: 키]" 가 온다.
    """
    global current_language
    return get_message(key, *args, language=current_language)

# 시스템 트레이 아이콘 이미지 생성 및 설정 함수
def create_image():
    """시스템 트레이 아이콘 이미지 생성 — favicon.ico 의 16x16 프레임(PIL Image)을 돌려준다. 못 만들면 None.

    찾는 순서: exe 임시 폴더(_MEIPASS) → exe/스크립트 폴더 → 작업 폴더 → 스크립트 폴더. 처음 찾은 파일을 쓴다.
    파일을 못 찾으면: 개발 실행에서만 임시 그림(파란 네모에 노란 "W" — 옛 WhisperTyper 시절 그대로)을 만들고,
    exe 에서는 None(호출부가 오류 상자를 띄운다).
    """
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

                    # favicon.ico 에는 16px 전용 도안(음파 한 줄)이 따로 들어 있다(1차 아이콘 교체, 7개 크기).
                    # Pillow 는 ICO 를 열면 가장 큰 프레임(256)을 고르므로, 그대로 16 으로 줄이면 음파 두 줄이
                    # 뭉개진 그림이 된다 → ICO 의 16x16 프레임을 직접 고른다(Pillow: img.size 에 넣으면 그 프레임).
                    if img.format == "ICO" and (16, 16) in (img.info.get("sizes") or ()):
                        img.size = (16, 16)
                        img.load()
                        logging.info("ICO 의 16x16 프레임을 직접 사용")

                    # 16x16 크기로 조정 (트레이 아이콘에 최적) — 16 프레임이 없는 파일일 때만 줄인다
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
    """시스템 트레이 아이콘과 메뉴를 만들고, 트레이를 별도 스레드에서 돌린다. 반환: tray_icon 또는 None.

    ⚠️ 스레드 규칙: 트레이 메뉴 콜백(아래 안쪽 함수들)은 pystray 스레드에서 불린다.
       Tk 창을 만지는 일(설정 창 열기·플로팅 아이콘 보이기/숨기기·리더 창 켬/끔)은 직접 하지 말고
       gui_queue 에 문자열을 넣어 Tk 메인(check_gui_queue)에 넘긴다(07-27 로그 §4-5).
       Tk 를 안 만지는 일(재생 정지·README 열기·콘솔 열기·언어 저장)은 그 자리에서 한다.
    ⚠️ update_tray_menu 는 위 global 선언 덕분에 "전역 함수" 가 된다(안쪽에서 def 해도 전역에 묶임).
       다른 곳(speak_text 등)이 update_tray_menu() 를 부를 수 있는 이유다. 트레이 설정이 실패하면 정의되지 않으므로
       부르는 쪽은 항상 try 로 감싼다.
    check_gui_queue(100ms 주기 루프)도 여기서 시작한다 — 트레이 설정이 초반에 실패하면 이 루프도 안 돈다(옛 구조).
    """
    global tray_icon, pystray, Image, ImageDraw, update_tray_menu

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
        # (exit_action 은 지금 메뉴에 걸려 있지 않다 — 메뉴의 "종료" 는 아래 exit_program. 옛 코드의 남은 껍데기)
        def exit_action(icon, item):
            icon.stop()
            os._exit(0)

        # README 파일 열기 함수
        def open_readme_file(icon, item):
            """(트레이 스레드) 지금 언어의 README 를 윈도우 기본 앱으로 연다. 작업 폴더 기준 경로
            (exe 는 extract_readme_files 가 exe 폴더에 풀어 둔 것을 연다)."""
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
            """(트레이 스레드) 인증 창은 Tk 창이라 직접 못 연다 → gui_queue 로 Tk 메인에 넘긴다."""
            gui_queue.put("show_api_key_dialog")

        # 콘솔 창 열기 함수
        def open_console(icon, item):
            """(트레이 스레드) 새 cmd 창을 열어 whisperer_console.log 를 실시간으로 보여 준다(PowerShell Get-Content -Wait).

            작업 폴더에 open_console.bat 을 만들어 실행한다. ⚠️ bat 안의 "echo > whisperer_console.log" 가
            로그 파일을 한 번 비운다(옛 동작 그대로).
            """
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

            except Exception as e:
                log_to_console(get_msg("console_open_error", str(e)))

        # 언어 변경 메뉴 항목 (기존 호환성 유지용)
        def change_language(icon, item):
            """(트레이 스레드) 한국어 ↔ 영어 전환 후 저장하고 메뉴 문구를 새 언어로 다시 만든다.

            하단 바·리더 창은 문구를 그릴 때마다 get_msg 를 새로 부르므로 따로 알릴 필요가 없다.
            """
            global current_language
            # 언어 전환 (한국어 <-> 영어)
            current_language = "en" if current_language == "ko" else "ko"
            save_settings()
            log_to_console(get_msg("language_changed", current_language))
            # 트레이 아이콘 메뉴 업데이트
            update_tray_menu()

        # 설정 함수들
        def open_tts_settings(icon, item):
            """(트레이 스레드) TTS 설정 창도 Tk 창이라 gui_queue 로 Tk 메인에 넘긴다."""
            # 큐를 통해 메인 스레드로 전달
            gui_queue.put("show_tts_settings")

        def exit_program(icon, item):
            """프로그램 종료 함수 (트레이 "종료").

            트레이 스레드에서 불린다. tray_icon.stop() → root.quit()(Tk 메인 루프 끝내기) → sys.exit.
            sys.exit 는 이 스레드만 끝내므로(SystemExit 는 except: 에 잡혀) 결국 os._exit(0) 로 프로세스를 끝낸다.
            읽는 중이면 재생 스레드들은 데몬이라 함께 사라진다(출력 스트림도 프로세스와 함께 닫힘).
            """
            try:
                tray_icon.stop()
                root.quit()
                sys.exit(0)
            except:
                os._exit(0)

        def update_tray_menu():
            """트레이 메뉴를 지금 상태(언어·재생 중·플로팅 숨김·리더 창 켬)에 맞게 새로 만들어 끼운다.

            pystray 메뉴는 문구가 고정이라 상태가 바뀔 때마다 이 함수로 통째로 다시 만든다.
            어느 스레드에서 불러도 된다(pystray 메뉴 교체는 Tk 와 무관). 부르는 곳: 읽기 시작/끝, 언어 변경,
            set_controller_visible, toggle_reader_window, 트레이 TTS 토글.
            """
            global tray_icon, tts_playing, tts_paused, tts_current_file, current_language

            if not tray_icon: return

            def toggle_tts():
                """TTS 토글: 중지/처음부터 재생

                (트레이 스레드) 읽는 중이면 stop_current_playback() 으로 멈춘다(어느 스레드에서 불러도 되는 함수).
                "처음부터 재생" 쪽은 tts_current_file 을 채우는 곳이 없어 지금은 도달하지 않는다(play_tts_file 은 죽은 코드).
                그래서 메뉴 항목은 읽는 중일 때만 켜지고 사실상 "TTS 중지" 버튼으로만 쓰인다.
                """
                global tts_paused, tts_playing, tts_current_file

                if tts_playing:
                    # 재생 중이면 중지
                    stop_current_playback()
                    log_to_console("[TTS] 재생 중지")
                elif tts_current_file and os.path.exists(tts_current_file):
                    # 재생 중이 아니고 마지막 파일이 있으면 처음부터 재생
                    log_to_console("[TTS] 마지막 파일 다시 재생")
                    threading.Thread(target=play_tts_file, args=(tts_current_file,), daemon=True).start()
                else:
                    log_to_console("[TTS] 재생할 파일이 없습니다.")

                # 상태 변경 후 메뉴 갱신
                update_tray_menu()

            # 토글 메뉴 라벨 결정
            if tts_playing:
                tts_toggle_label = "⏹ TTS 중지"
            else:
                tts_toggle_label = "▶ TTS 재생"

            # 토글 메뉴 활성화 여부 (파일이 없으면 비활성화)
            tts_enabled = tts_playing or (tts_current_file is not None and os.path.exists(tts_current_file) if tts_current_file else False)

            # 현재 언어 표시를 위한 라벨
            lang_label = get_msg("current_language_ko") if current_language == "ko" else get_msg("current_language_en")

            # 플로팅 컨트롤러 표시/숨김 토글 라벨 (현재 상태의 반대 동작을 표시)
            controller_toggle_label = get_msg("menu_show_controller") if controller_hidden else get_msg("menu_hide_controller")

            base_items = [
                pystray.MenuItem(get_msg("open_console"), open_console),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(get_msg("menu_tts_settings"), open_tts_settings),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(get_msg("google_credential_setting"), set_google_credentials),
                pystray.MenuItem(f"{get_msg('menu_language')} ({lang_label})", change_language),
                pystray.MenuItem(get_msg("open_readme"), open_readme_file),
                pystray.Menu.SEPARATOR,
                # TTS 토글 메뉴 (종료 바로 위)
                pystray.MenuItem(tts_toggle_label, lambda icon, item: toggle_tts(), enabled=tts_enabled),
                # 플로팅 컨트롤러 표시/숨김 (tkinter 조작이므로 큐를 통해 메인 스레드로 전달)
                pystray.MenuItem(controller_toggle_label, lambda icon, item: gui_queue.put("toggle_controller")),
                # 리더 창(원문 + 읽는 줄 형광펜) 켬/끔 체크 — 역시 tkinter 조작이라 큐로 메인 스레드에 넘긴다.
                # 체크 표시는 pystray 가 메뉴를 그릴 때 checked 함수를 불러 정한다(전역값을 그대로 읽음)
                pystray.MenuItem(get_msg("menu_reader_window"),
                                 lambda icon, item: gui_queue.put("toggle_reader_window"),
                                 checked=lambda item: reader_window_enabled),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(get_msg("exit"), exit_program)
            ]

            tray_icon.menu = pystray.Menu(*base_items)

        # 메뉴 갱신 함수를 전역에 노출 (플로팅 컨트롤러 우클릭 등 외부 경로에서 라벨 갱신용)
        global tray_menu_updater
        tray_menu_updater = update_tray_menu

        # 아이콘 객체 생성
        tray_icon = pystray.Icon("whisperer")
        tray_icon.icon = icon_image
        tray_icon.title = "BluemingReadAloud"
        # 좌클릭 시 메뉴가 나오도록 activate 콜백 제거

        update_tray_menu()

        def check_gui_queue():
            """다른 스레드(트레이·재생 엔진)가 넣은 일을 Tk 메인 스레드에서 처리한다 (100ms 주기).

            ⚠️ 하나가 예외를 내도 이 루프는 계속 돌아야 한다. 예외가 밖으로 새면 아래 root.after 가
               다시 걸리지 않아 트레이 메뉴·하단 바·형광펜이 전부 영영 멈춘다 → 항목마다 잡는다.
            """
            try:
                while True:
                    msg = gui_queue.get_nowait()
                    try:
                        if msg == "show_tts_settings":
                            show_tts_settings_dialog()
                        elif msg == "show_api_key_dialog":
                            show_api_key_dialog(required=False)
                        elif msg == "toggle_controller":
                            # 숨김 상태면 보이게, 보이는 상태면 숨기게
                            # (메뉴 라벨 갱신은 set_controller_visible이 직접 처리)
                            set_controller_visible(controller_hidden)
                        elif msg == "toggle_reader_window":
                            toggle_reader_window()
                        elif isinstance(msg, tuple) and msg and msg[0] == "tts_event":
                            # 재생 엔진 알림 (session, kind, data) → 하단 바·리더 창
                            _handle_tts_event(*msg[1:])
                    except Exception as e:
                        logging.error(f"GUI 큐 처리 오류 ({msg if isinstance(msg, str) else msg[:3]}): {e}")
                        import traceback
                        logging.error(traceback.format_exc())
            except queue.Empty:
                pass
            if root:
                root.after(100, check_gui_queue)

        # GUI 큐 확인 시작
        if root:
            root.after(100, check_gui_queue)

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

def set_controller_visible(visible):
    """플로팅 컨트롤러를 표시/숨김 전환합니다.

    ⚠️ 반드시 메인(GUI) 스레드에서만 호출할 것.
       트레이 아이콘은 별도 스레드에서 돌기 때문에 거기서 직접 부르면 안 되고,
       gui_queue에 "toggle_controller"를 넣어 메인 스레드로 넘겨야 한다.
    """
    global controller_hidden

    controller_hidden = not visible
    save_settings()

    if not floating_controller:
        return

    try:
        if visible:
            floating_controller.deiconify()
            # withdraw 동안 창 관리자가 topmost를 잊는 경우가 있어 복원 시 재적용
            floating_controller.attributes('-topmost', True)
            floating_controller.lift()
            log_to_console(get_msg("controller_shown_log"))
        else:
            floating_controller.withdraw()
            log_to_console(get_msg("controller_hidden_log"))
    except Exception as e:
        logging.warning(f"컨트롤러 표시 전환 실패: {e}")

    # 어느 경로로 상태가 바뀌든 트레이 메뉴 라벨을 항상 동기화
    # (플로팅 우클릭 → 숨김 시에도 트레이가 "보이기"로 뒤집혀야 함)
    if tray_menu_updater:
        try:
            tray_menu_updater()
        except Exception as e:
            logging.warning(f"트레이 메뉴 갱신 실패: {e}")


# 플로팅 미니 컨트롤러 (읽어주기 버튼)
def setup_floating_controller():
    """항상 위에 떠있는 미니 읽어주기 컨트롤러를 생성합니다.

    28px 동그란 버튼 하나. 왼쪽 클릭 = 읽는 중이면 중지, 아니면 선택한 글 읽기 / 끌기 = 옮기기(위치 저장) /
    오른쪽 클릭 = "숨기기" 메뉴. 색: 파랑(대기, 흰 동그라미) ↔ 주황(읽는 중, 흰 네모) — update_state 가 0.5초마다 칠한다.
    ⚠️ 핵심 함정 (07-27 로그 §4-3·4-4)
      - WS_EX_NOACTIVATE: 눌러도 포커스를 뺏지 않는다. 뺏으면 read_selected_text 의 Ctrl+C 가 사용자가 글을
        선택한 창이 아니라 이 버튼으로 가서 "선택 없음" 이 된다. 하단 바·리더 창도 같은 처리를 한다.
      - 이 창은 포커스를 못 받으므로 오른쪽 클릭 메뉴는 root 의 자식으로 만들어야 바깥 클릭에 닫힌다.
      - 3초마다 topmost+lift 로 다시 올린다(다른 항상-위 창에 묻히는 것 방지). 숨김 상태에서는 건너뛰어야 한다
        (update_state 의 숨김 가드 — 지우면 숨긴 창이 되살아난다). 메뉴가 떠 있을 때도 건너뛴다(menu_open).
      - 보이기/숨기기는 반드시 set_controller_visible() 로(트레이 라벨·설정 저장이 함께 움직임).
    """
    import tkinter as tk
    import ctypes
    global floating_controller, controller_canvas, controller_position

    if not root:
        return

    SIZE = 28  # 작고 깔끔한 크기
    ICON_COLOR = 'white'
    TTS_COLOR = '#1565C0'        # TTS 대기: 파란색
    TTS_OUTLINE = '#42A5F5'
    TTS_PLAY_COLOR = '#E65100'   # TTS 재생 중: 주황색
    TTS_PLAY_OUTLINE = '#FF8A65'

    # Toplevel 창 생성
    ctrl_win = tk.Toplevel(root)
    ctrl_win.overrideredirect(True)      # 타이틀바 제거
    ctrl_win.attributes('-topmost', True) # 항상 위
    ctrl_win.configure(bg=TTS_COLOR)      # 배경 = 버튼색 (사각 모서리 최소화)

    # 저장된 위치 복원 또는 기본 위치 (화면 우하단)
    screen_w = ctrl_win.winfo_screenwidth()
    screen_h = ctrl_win.winfo_screenheight()
    if controller_position and isinstance(controller_position, dict):
        x = controller_position.get('x', screen_w - 120)
        y = controller_position.get('y', screen_h - 120)
        # 저장된 위치가 현재 화면 범위 밖이면 기본 위치로 폴백
        if y >= screen_h or y < -SIZE or x >= screen_w * 2 or x < -screen_w:
            x = screen_w - 120
            y = screen_h - 120
            log_to_console(f"[컨트롤러] 저장 위치 화면 밖 → 기본 위치로 복원 ({x},{y})")
    else:
        x = screen_w - 120
        y = screen_h - 120

    log_to_console(f"[컨트롤러] 생성 위치: ({x}, {y}), 화면: {screen_w}x{screen_h}")
    ctrl_win.geometry(f"{SIZE}x{SIZE}+{x}+{y}")

    # ── Win32: 소유자 분리 + 포커스 탈취 방지 + TOPMOST 확정 ──
    # root.withdraw()와 독립시켜 사라짐을 근본 방지
    ctrl_win.update_idletasks()
    try:
        hwnd = ctypes.windll.user32.GetParent(ctrl_win.winfo_id())

        # 1) 소유자 창(root) 연결 해제 → root 상태와 무관하게 독립 생존
        GWLP_HWNDPARENT = -8
        try:
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, 0)
        except AttributeError:
            ctypes.windll.user32.SetWindowLongW(hwnd, GWLP_HWNDPARENT, 0)

        # 2) 포커스 탈취 방지 + 작업표시줄 제외
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        style = style & ~WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

        # 3) SetWindowPos로 TOPMOST 확정 (스타일 변경 반영)
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_FRAMECHANGED = 0x0020
        ctypes.windll.user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED
        )

        # 4) 원형 모양으로 창 클리핑 (네모 모서리 제거)
        region = ctypes.windll.gdi32.CreateEllipticRgn(0, 0, SIZE + 1, SIZE + 1)
        ctypes.windll.user32.SetWindowRgn(hwnd, region, True)

        logging.info("컨트롤러 Win32 설정 완료 (소유자 분리 + 포커스 방지 + TOPMOST)")
    except Exception as e:
        logging.warning(f"컨트롤러 Win32 설정 실패 (기능에 영향 없음): {e}")

    # 캔버스 생성 (배경 = 버튼색)
    canvas = tk.Canvas(ctrl_win, width=SIZE, height=SIZE,
                       highlightthickness=0, bd=0, bg=TTS_COLOR)
    canvas.pack(fill='both', expand=True)

    # 둥근 버튼 그리기
    PAD = 2
    canvas.create_oval(PAD, PAD, SIZE - PAD, SIZE - PAD,
                       fill=TTS_COLOR, outline=TTS_OUTLINE, width=2,
                       tags='btn_circle')
    # 내부 아이콘: 흰색 원 (대기 심볼, 재생 중에는 update_state가 정지 사각형으로 바꿈)
    icon_r = SIZE // 5
    cx, cy = SIZE // 2, SIZE // 2
    canvas.create_oval(cx - icon_r, cy - icon_r, cx + icon_r, cy + icon_r,
                       fill=ICON_COLOR, outline='', width=0,
                       tags='btn_icon')

    floating_controller = ctrl_win
    controller_canvas = canvas

    # ── 드래그 & 클릭 판정 로직 ──
    # 누른 자리에서 5px 넘게 움직이면 "끌기", 아니면 뗄 때 "클릭" 으로 본다.
    drag_data = {'start_x': 0, 'start_y': 0, 'dragging': False}

    def on_press(event):
        """(Tk 메인) 왼쪽 버튼 누름: 시작 위치만 기억한다. 클릭인지 끌기인지는 움직임을 보고 정한다."""
        drag_data['start_x'] = event.x_root
        drag_data['start_y'] = event.y_root
        drag_data['dragging'] = False

    def on_drag(event):
        """(Tk 메인) 누른 채 움직임: 5px 를 넘으면 끌기로 보고 창을 따라 옮긴다."""
        dx = event.x_root - drag_data['start_x']
        dy = event.y_root - drag_data['start_y']
        if abs(dx) > 5 or abs(dy) > 5:
            drag_data['dragging'] = True
        if drag_data['dragging']:
            new_x = ctrl_win.winfo_x() + (event.x_root - drag_data['start_x'])
            new_y = ctrl_win.winfo_y() + (event.y_root - drag_data['start_y'])
            ctrl_win.geometry(f"+{new_x}+{new_y}")
            drag_data['start_x'] = event.x_root
            drag_data['start_y'] = event.y_root

    def on_release(event):
        """(Tk 메인) 버튼 뗌: 끌기였으면 위치 저장, 클릭이었으면 읽기/중지.

        클릭 판정은 tts_playing 으로 한다(is_speaking 아님). 단축키와 달리 "선택 없음 → 아이콘 숨김" 분기는 없다.
        root.after(10) 로 한 번 미루는 건 이 이벤트 처리를 먼저 끝내려는 것(옛 구조 그대로).
        """
        if drag_data['dragging']:
            # 드래그 종료 → 위치 저장
            _save_controller_position()
        else:
            # 클릭: 재생 중이면 중지, 아니면 선택 텍스트 읽기 시작
            log_to_console(f"[컨트롤러] TTS 버튼 클릭 — tts_playing={tts_playing}")
            if tts_playing:
                root.after(10, stop_tts)
            else:
                root.after(10, read_selected_text)

    def _save_controller_position():
        """(Tk 메인) 지금 창 위치를 controller_position 에 넣고 설정 파일에 저장한다(다음 실행 때 그 자리에 뜬다)."""
        global controller_position
        controller_position = {
            'x': ctrl_win.winfo_x(),
            'y': ctrl_win.winfo_y()
        }
        save_settings()
        logging.debug(f"컨트롤러 위치 저장: {controller_position}")

    # ── 우클릭 컨텍스트 메뉴 (숨기기) ──
    # ctrl_win은 WS_EX_NOACTIVATE라 포커스를 받지 못한다.
    # 메뉴를 ctrl_win이 아닌 root의 자식으로 만들어야 바깥 클릭 시 정상적으로 닫힌다.
    ctrl_menu = tk.Menu(root, tearoff=0)
    ctrl_menu.add_command(label=get_msg("ctrl_menu_hide"),
                          command=lambda: set_controller_visible(False))

    menu_open = [False]   # 메뉴가 떠 있는 동안 keep-alive lift를 멈추기 위한 플래그

    def on_right_click(event):
        """(Tk 메인) 오른쪽 클릭: "숨기기" 메뉴를 띄운다. 메뉴가 떠 있는 동안은 keep-alive lift 를 멈춘다(menu_open)."""
        menu_open[0] = True
        try:
            # 언어가 바뀌었을 수 있으므로 팝업 직전 라벨 갱신
            ctrl_menu.entryconfigure(0, label=get_msg("ctrl_menu_hide"))
            ctrl_menu.tk_popup(event.x_root, event.y_root)
        except Exception as e:
            # 팝업이 실패하면 우클릭이 먹통이 되므로 즉시 숨김으로 폴백
            logging.warning(f"컨트롤러 우클릭 메뉴 실패 → 즉시 숨김 폴백: {e}")
            set_controller_visible(False)
        finally:
            ctrl_menu.grab_release()
            # tk_popup은 메뉴가 닫히기 전에 반환될 수 있어 지연 해제
            ctrl_win.after(300, lambda: menu_open.__setitem__(0, False))

    canvas.bind('<ButtonPress-1>', on_press)
    canvas.bind('<B1-Motion>', on_drag)
    canvas.bind('<ButtonRelease-1>', on_release)
    canvas.bind('<Button-3>', on_right_click)

    # ── 상태 업데이트 + 사라짐 방지 루프 (500ms 주기) ──
    keep_alive_counter = [0]

    def update_state():
        """(Tk 메인, 0.5초마다 스스로 다시 예약) 재생 상태에 맞춰 색·아이콘을 칠하고, 3초마다 맨 위로 다시 올린다.

        tts_playing 은 재생 스레드(끝 알림)와 Tk 메인(읽기 시작·정지)이 바꾸는 값이라 여기서는 읽기만 한다
        (최대 0.5초 늦게 색이 바뀐다).
        ⚠️ winfo_exists() 는 withdraw 뒤에도 True 라서 이 루프는 숨긴 동안에도 돈다 → 아래 숨김 가드가 꼭 필요하다.
        """
        if not ctrl_win.winfo_exists():
            return
        # 숨김 상태면 그리기와 keep-alive lift를 모두 건너뛴다.
        # (아래 lift/topmost가 살아 있으면 withdraw한 창이 되살아날 수 있음)
        if controller_hidden:
            ctrl_win.after(500, update_state)
            return
        try:
            # 파란색 대기 (재생 중이면 주황색 + 정지 아이콘) — 재생 판정은 tts_playing
            if tts_playing:
                color = TTS_PLAY_COLOR
                outline = TTS_PLAY_OUTLINE
            else:
                color = TTS_COLOR
                outline = TTS_OUTLINE
            canvas.itemconfig('btn_circle', fill=color, outline=outline)
            canvas.configure(bg=color)
            ctrl_win.configure(bg=color)
            canvas.delete('btn_icon')
            if tts_playing:
                sq_r = SIZE // 6
                canvas.create_rectangle(cx - sq_r, cy - sq_r, cx + sq_r, cy + sq_r,
                                        fill=ICON_COLOR, outline='', width=0, tags='btn_icon')
            else:
                canvas.create_oval(cx - icon_r, cy - icon_r, cx + icon_r, cy + icon_r,
                                   fill=ICON_COLOR, outline='', width=0, tags='btn_icon')

            # 3초마다 topmost 재적용 (사라짐 방지)
            # 단, 우클릭 메뉴가 떠 있는 동안은 lift가 메뉴를 가리므로 건너뛴다
            keep_alive_counter[0] += 1
            if keep_alive_counter[0] >= 6 and not menu_open[0]:  # 500ms * 6 = 3초
                keep_alive_counter[0] = 0
                ctrl_win.attributes('-topmost', True)
                ctrl_win.lift()

        except Exception:
            pass
        ctrl_win.after(500, update_state)

    # 저장된 숨김 상태 복원 (숨긴 채로 종료했으면 숨긴 채로 시작)
    if controller_hidden:
        ctrl_win.withdraw()
        log_to_console("[컨트롤러] 숨김 상태로 시작 — 트레이 메뉴에서 다시 표시할 수 있습니다.")

    update_state()

    logging.info("플로팅 컨트롤러 생성 완료")
    if not controller_hidden:
        log_to_console(get_msg("controller_created"))

# API 키 설정 대화 상자 표시 함수
def show_api_key_dialog(required=False):
    """Google Cloud 인증 파일 선택 대화 상자를 표시합니다.

    저장하면 TTS 클라이언트를 초기화하고, 필수 모드(required=True)의 취소·닫기는
    TTS 클라이언트(google_tts_client)가 준비됐을 때만 허용한다.

    ⚠️ Tk 메인 스레드에서만 부른다(main 의 인증 확인 / 트레이 → gui_queue "show_api_key_dialog").
    흐름: "..." 로 JSON 고르기 → "설정" → 앱 폴더에 google_credentials.json 으로 복사 → init_tts_client →
          설정 저장 → 1.5초 뒤 창 닫힘. 실패하면 창에 빨간 글씨로 이유를 보이고 창은 열어 둔다.
    필수 모드(시작할 때 인증이 없거나 깨졌을 때): 클라이언트가 준비될 때까지 취소·X·Esc 로 닫을 수 없다.
      그래서 init_tts_client 는 "모듈 import 오류" 를 예외로 올리지 않고 False 를 돌려준다
      (예외로 올리면 저장이 계속 실패하고 취소도 안 돼 창을 영영 못 닫는다 — 그 함수의 ⚠️ 설명).
    wait_window() 로 창이 닫힐 때까지 이 함수가 돌아오지 않는다(그동안에도 Tk 이벤트는 돈다).
    반환: 새로 설정한 경로, 없으면 기존 경로.
    """
    global google_credentials_path

    from tkinter import filedialog
    import shutil

    # 완전히 독립적인 모달 대화 상자 생성
    # (부모를 안 주면 기본 루트가 부모가 된다. 창 아이콘은 main 이 건 "기본 아이콘"(favicon.ico)을 따른다)
    dialog = ttk.Toplevel()
    dialog.title("Google Cloud 인증 설정")
    dialog.geometry("550x350")
    dialog.resizable(False, False)

    # 모달 설정
    dialog.transient()
    dialog.grab_set()
    dialog.focus_set()
    dialog.attributes("-topmost", True)

    # 메인 프레임
    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill=tk.BOTH, expand=True)

    # 설명 라벨
    if current_language == "ko":
        label_text = "Google Cloud Service Account JSON 파일을 선택해 주세요\n\n파일은 Google Cloud Console에서 다운로드할 수 있습니다:\nhttps://console.cloud.google.com/iam-admin/serviceaccounts"
    else:
        label_text = "Select your Google Cloud Service Account JSON file\n\nYou can download the file from Google Cloud Console:\nhttps://console.cloud.google.com/iam-admin/serviceaccounts"

    ttk.Label(frame, text=label_text, justify=tk.LEFT).pack(anchor="w", pady=(0, 15))

    # 파일 경로 표시 프레임
    path_frame = ttk.Frame(frame)
    path_frame.pack(fill=tk.X, pady=8)

    # 현재 설정된 경로 표시
    current_path = google_credentials_path if google_credentials_path else ""
    path_var = tk.StringVar(value=current_path)

    path_entry = ttk.Entry(path_frame, textvariable=path_var, width=50, state="readonly")
    path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # 파일 선택 함수
    def browse_file():
        """"..." 버튼: 파일 선택 창으로 JSON 을 고르면 경로 칸에 넣는다(아직 저장·검사 안 함 — "설정" 때 한다)."""
        filename = filedialog.askopenfilename(
            title="Google Service Account JSON 파일 선택",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            parent=dialog
        )
        if filename:
            path_var.set(filename)
            # 초기화 (기본 스타일로)
            result_label.config(text="", bootstyle="default")

    # 찾아보기 버튼
    browse_btn = ttk.Button(path_frame, text="...", command=browse_file, width=3, bootstyle="info-outline")
    browse_btn.pack(side=tk.RIGHT, padx=(5, 0))

    # 결과 메시지 라벨 (bootstyle 활용)
    result_label = ttk.Label(frame, text="")
    result_label.pack(pady=10)

    # 버튼 프레임
    btn_frame = ttk.Frame(frame)
    btn_frame.pack(pady=10)

    # 결과 변수
    result = [None]

    # 저장 함수
    def save_credentials():
        """"설정" 버튼(또는 Enter): 고른 파일을 앱 폴더로 복사하고 TTS 클라이언트를 만든다.

        ⚠️ 복사가 먼저라, 잘못된 파일을 고르면 앱 폴더의 google_credentials.json 이 그 파일로 덮인다
           (init_tts_client 가 실패해도 되돌리지 않는다 — 옛 동작 그대로). 전역 경로도 복사본으로 바뀐 채 남는다.
        """
        global google_credentials_path

        selected_path = path_var.get().strip()

        if required and not selected_path:
            result_label.config(text="인증 파일을 선택해 주세요.", bootstyle="danger")
            return

        if not os.path.exists(selected_path):
            result_label.config(text="파일이 존재하지 않습니다.", bootstyle="danger")
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

            # Google Cloud TTS 클라이언트 초기화 (project_id 추출 포함)
            # - 인증 파일이 잘못됐으면 예외 → 아래 except에서 오류 표시, 창은 열어 둔다
            # - texttospeech 모듈이 없으면 False(로그만) — 옛 STT 때 모듈이 없으면 건너뛰던 것처럼 저장은 진행
            init_tts_client(dest_path)

            # 설정 저장
            save_settings()

            # 성공 메시지
            result_label.config(text="✓ Google Cloud 인증 설정이 완료되었습니다.", bootstyle="success")
            logging.info(f"Google Cloud 인증 파일 설정됨: {dest_path}")
            log_to_console(f"Google Cloud 인증 파일 설정됨: {dest_path}")

            result[0] = dest_path

            # 성공 후 창 닫기
            dialog.after(1500, dialog.destroy)

        except Exception as e:
            result_label.config(text=f"오류: {str(e)}", bootstyle="danger")
            logging.error(f"인증 파일 설정 오류: {str(e)}")

    # 취소 함수
    def cancel():
        """"취소"·Esc·X 모두 여기로 온다. 필수 모드에서 클라이언트가 없으면 닫지 않고 안내만 한다."""
        # 필수 모드에서는 TTS 클라이언트가 준비된 뒤에만 닫을 수 있다
        if required and not google_tts_client:
            result_label.config(text="인증 파일을 선택해 주세요.", bootstyle="danger")
            return
        dialog.destroy()

    # 저장 버튼
    save_btn = ttk.Button(btn_frame, text="설정" if current_language == "ko" else "Save", command=save_credentials, width=12, bootstyle="success")
    save_btn.pack(side=tk.LEFT, padx=10)

    # 취소 버튼
    cancel_btn = ttk.Button(btn_frame, text="취소" if current_language == "ko" else "Cancel", command=cancel, width=12, bootstyle="secondary")
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


# TTS 설정 대화상자
def show_tts_settings_dialog():
    """TTS 설정 대화상자를 표시합니다.

    ⚠️ Tk 메인 스레드에서만 부른다(트레이 → gui_queue "show_tts_settings").
    이미 열려 있으면 새로 만들지 않고 앞으로 올린다(함수 속성 .dialog 에 창을 기억).
    고칠 수 있는 것: 음성(KOREAN_VOICES), 속도(0.25~4.0), 단축키(Ctrl/Shift/Alt + 글자).
    저장하면 전역값을 바꾸고 파일에 쓴다. 읽는 중인 세션에는 적용되지 않고 다음 읽기부터 쓰인다
    (읽는 중 속도는 하단 바 설정 패널이 바꾼다).
    ⚠️ 단축키를 바꿔도 키보드 훅은 전역값을 매번 읽으므로 곧바로 새 단축키가 먹는다(훅을 다시 띄울 필요 없음).
    """
    global root, tts_hotkey_modifiers, tts_hotkey_key, tts_voice_name, tts_speaking_rate

    if hasattr(show_tts_settings_dialog, 'dialog') and show_tts_settings_dialog.dialog and show_tts_settings_dialog.dialog.winfo_exists():
        show_tts_settings_dialog.dialog.lift()
        return

    dialog = ttk.Toplevel(root)
    dialog.title(get_msg("dialog_tts_title"))
    dialog.geometry("650x550")
    dialog.resizable(False, False)
    show_tts_settings_dialog.dialog = dialog

    try:
        # 상대 경로("favicon.ico")는 exe 실행 때 못 찾았다 → 앱 폴더 기준 절대 경로 (_favicon_path)
        icon_path = _favicon_path()
        if icon_path:
            dialog.iconbitmap(icon_path)
    except Exception:
        pass

    padding = {'padx': 20, 'pady': 10}

    # 1. 음성 모델 설정 (+ 미리듣기 버튼을 여기로 이동)
    voice_frame = ttk.Labelframe(dialog, text=get_msg("label_voice_model"), padding=15)
    voice_frame.pack(fill="x", **padding)

    voice_options = []
    voice_map = {}

    current_voice_display = ""

    for v_id, v_gender, v_type, v_desc in KOREAN_VOICES:
        display_str = f"{v_id} ({v_gender}, {v_type}) - {v_desc}"
        voice_options.append(display_str)
        voice_map[display_str] = v_id
        if v_id == tts_voice_name:
            current_voice_display = display_str

    if not current_voice_display and voice_options:
        current_voice_display = voice_options[0]

    voice_var = tk.StringVar(value=current_voice_display)

    # 상단: 콤보박스와 미리듣기 버튼을 가로로 배치
    voice_selection_row = ttk.Frame(voice_frame)
    voice_selection_row.pack(fill="x", pady=5)

    voice_combo = ttk.Combobox(voice_selection_row, textvariable=voice_var, values=voice_options, state="readonly")
    voice_combo.pack(side="left", fill="x", expand=True, padx=(0, 10))

    # 미리듣기 기능 (클로저)
    def preview_tts():
        """"미리듣기" 버튼: 고른 음성·속도로 정해진 문장을 합성해 별도 스레드에서 들려준다.

        읽기 엔진(TtsSession)을 쓰지 않고 sd.play 로 한 번 튼다 → 하단 바·형광펜 없음.
        멈춤은 stop_current_playback 의 sd.stop() 이 맡는다(sd.play 에는 sd.stop 이 듣는다).
        ⚠️ 읽는 중에 누르면 두 소리가 겹쳐 난다(옛 동작 그대로).
        """
        selected_disp = voice_var.get()
        sel_voice_id = voice_map.get(selected_disp, "ko-KR-Wavenet-A")
        # 현재 화면의 속도값 가져오기 (rate_var가 아직 정의 전이거나 아래에 있으므로 주의. 함수 호출 시점엔 정의됨)
        sel_rate = rate_var.get()

        text = "안녕하세요. TTS 목소리 미리듣기입니다."

        def _preview():
            # (별도 스레드) 네트워크 요청이 Tk 메인을 멈추지 않게 따로 돈다. 여기서는 Tk 를 만지지 않는다.
            # 속도는 슬라이더 값 그대로(0.25~4.0 — 슬라이더 범위가 곧 제한), 언어 코드는 ko-KR 고정(한국어 음성 목록뿐).
            try:
                if not google_tts_client:
                    log_to_console("TTS 클라이언트 미초기화")
                    return

                synthesis_input = google_tts.SynthesisInput(text=text)
                voice = google_tts.VoiceSelectionParams(language_code="ko-KR", name=sel_voice_id)
                audio_config = google_tts.AudioConfig(audio_encoding=google_tts.AudioEncoding.LINEAR16, sample_rate_hertz=24000, speaking_rate=sel_rate)

                response = google_tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)

                import numpy as np
                import sounddevice as sd
                audio_data = np.frombuffer(response.audio_content[44:], dtype=np.int16)
                sd.play(audio_data, 24000)
                sd.wait()
            except Exception as e:
                log_to_console(f"미리듣기 실패: {e}")

        threading.Thread(target=_preview, daemon=True).start()

    # 미리듣기 버튼을 콤보박스 옆에 배치
    ttk.Button(voice_selection_row, text=get_msg("btn_preview"), command=preview_tts, bootstyle="info-outline").pack(side="right")


    # 2. 재생 속도 설정
    rate_frame = ttk.Labelframe(dialog, text=get_msg("label_speaking_rate"), padding=15)
    rate_frame.pack(fill="x", **padding)

    rate_var = tk.DoubleVar(value=tts_speaking_rate)

    rate_container = ttk.Frame(rate_frame)
    rate_container.pack(fill="x", pady=5)

    rate_label = ttk.Label(rate_container, text=f"{tts_speaking_rate:.1f}x", bootstyle="primary")
    rate_label.pack(side="right", padx=10)

    def update_rate_label(val):
        rate_label.config(text=f"{float(val):.1f}x")

    # ttk.Scale은 command 인자 지원이 tk와 다를 수 있음. 보통 command=func 인데, 값 변경시 호출됨.
    rate_scale = ttk.Scale(rate_container, from_=0.25, to=4.0, variable=rate_var, command=update_rate_label, bootstyle="success")
    rate_scale.pack(side="left", fill="x", expand=True, padx=10)

    # 3. 단축키 설정
    hotkey_frame = ttk.Labelframe(dialog, text=get_msg("group_hotkey"), padding=15)
    hotkey_frame.pack(fill="x", **padding)

    current_modifiers = tts_hotkey_modifiers.copy()
    current_key = tts_hotkey_key

    ctrl_var = tk.BooleanVar(value=current_modifiers.get("ctrl", False))
    shift_var = tk.BooleanVar(value=current_modifiers.get("shift", False))
    alt_var = tk.BooleanVar(value=current_modifiers.get("alt", False))
    key_var = tk.StringVar(value=current_key if current_key else "")

    check_frame = ttk.Frame(hotkey_frame)
    check_frame.pack(fill="x", pady=5)

    ttk.Checkbutton(check_frame, text="Ctrl", variable=ctrl_var).pack(side="left", padx=5)
    ttk.Checkbutton(check_frame, text="Shift", variable=shift_var).pack(side="left", padx=5)
    ttk.Checkbutton(check_frame, text="Alt", variable=alt_var).pack(side="left", padx=5)

    key_frame = ttk.Frame(hotkey_frame)
    key_frame.pack(fill="x", pady=5)

    ttk.Label(key_frame, text="Key:").pack(side="left", padx=5)
    key_entry = ttk.Entry(key_frame, textvariable=key_var, width=10)
    key_entry.pack(side="left", padx=5)

    # 4. 저장 버튼 (미리듣기는 위로 이동함)
    button_frame = ttk.Frame(dialog)
    button_frame.pack(side="bottom", fill="x", pady=20)

    # (미리듣기 버튼 제거됨)

    def save_tts_settings_action():
        """"저장" 버튼: 창의 값을 전역 설정에 넣고 파일에 저장한 뒤 창을 닫는다.

        글자 칸이 비면 단축키 글자를 None 으로 둔다(→ 단축키가 꺼진다). 음성을 못 찾으면 ko-KR-Wavenet-A(옛 기본값).
        """
        global tts_hotkey_modifiers, tts_hotkey_key, tts_voice_name, tts_speaking_rate

        tts_hotkey_modifiers["ctrl"] = ctrl_var.get()
        tts_hotkey_modifiers["shift"] = shift_var.get()
        tts_hotkey_modifiers["alt"] = alt_var.get()
        k = key_var.get().strip().upper()
        tts_hotkey_key = k if k else None

        selected_disp = voice_var.get()
        tts_voice_name = voice_map.get(selected_disp, "ko-KR-Wavenet-A")
        tts_speaking_rate = rate_var.get()

        save_settings()

        log_to_console(get_msg("tts_hotkey_updated"))
        # 토스트 알림 (messagebox 대신)
        try:
            from ttkbootstrap.toast import ToastNotification
            ToastNotification(title="설정 저장", message="TTS 설정이 저장되었습니다.", duration=2000, bootstyle="success").show_toast()
        except: pass
        dialog.destroy()

    ttk.Button(button_frame, text=get_msg("save"), command=save_tts_settings_action, width=10, bootstyle="success").pack(side="right", padx=20)
    ttk.Button(button_frame, text=get_msg("cancel"), command=dialog.destroy, width=10, bootstyle="secondary").pack(side="right", padx=10)

    # 창 크기 자동 조절 및 강제 업데이트 (렌더링 문제 해결)
    dialog.update()


# ════════════════════════════════════════════════════════════════════
# TTS 재생 — 엔진은 tts_engine.py(TtsSession), 조각 나누기는 readaloud_text.py(split_for_reading)
#   옛 _preprocess_for_tts / _chunk_text_for_tts / _speak(producer·consumer) / _synthesize_chunk 는
#   2026-09-28 에 tts_engine.py·readaloud_text.py 로 옮기거나 대체했다.
# ════════════════════════════════════════════════════════════════════

# TTS 재생 관련 상태 변수
tts_playing = False   # 읽는 중인가 — 플로팅 아이콘 색·단축키 3방향 분기·트레이 메뉴가 이것으로 판정한다(is_speaking 아님)
tts_paused = False    # 지금 읽기가 일시정지인가 — 엔진 state 알림으로 갱신한다(하단 바 ⏯ 로 실제 일시정지된다)
tts_stop_event = threading.Event()  # 옛 파일 재생(play_tts_file) 전용. 읽기 엔진은 세션마다 자기 멈춤 신호를 쓴다
tts_current_file = None  # 현재 재생 파일 경로 (play_tts_file 전용 — 지금은 채우는 곳이 없다)
tts_session = None    # 지금 읽고 있는 tts_engine.TtsSession (없으면 None). Tk 메인 스레드에서만 바꾼다
# tts_session·tts_playing·tts_paused 를 "확인하고 고치기" 한 덩어리로 묶는 락.
# 왜 필요한가: 옛 읽기의 재생 스레드가 끝 알림(_make_tts_event_handler)에서 "내가 지금 세션이면 tts_playing=False"
#   를 하는 사이에, Tk 메인의 speak_text 가 새 세션을 넣고 tts_playing=True 로 만들면 → 옛 스레드가 뒤늦게 False 로
#   덮어써서 새 읽기가 재생 중인데도 플로팅 아이콘이 파랑·단축키가 "중지" 대신 "아이콘 숨김" 으로 갔다
#   (2026-09-28 깨 보기, 확인과 대입 사이에 새 읽기를 끼워 넣어 재현 — tests/test_tts_engine.py TestWhispererGlue).
# ⚠️ 이 락을 쥔 채로 엔진 메서드(session.stop 등)나 UI 를 부르지 마라. 값만 읽고 쓰고 바로 놓는다.
_tts_state_lock = threading.Lock()

def stop_current_playback():
    """현재 재생 중인 오디오를 강제 중지합니다. 어느 스레드에서 불러도 된다(트레이 스레드에서도 불림).

    읽기는 session.stop() 이 세션 안에서 출력 스트림을 abort 한다(sd.stop() 은 OutputStream 을 못 멈춘다 — 06-07 §4).
    하단 바·리더 창 정리는 엔진이 보내는 session_end 알림을 Tk 메인 스레드가 받아서 한다(_handle_tts_event).
    ⚠️ 여기서 tts_stop_event 를 clear 하지 않는다. 읽기 엔진은 이 전역 신호를 쓰지 않는다(좀비 함정 — tts_engine.py 설명).

    세션을 꺼내는 일과 tts_playing=False 를 락 안에서 한 번에 한다(_tts_state_lock 설명 참고).
    트레이 스레드의 "TTS 중지" 와 Tk 메인의 새 읽기가 동시에 와도, 둘 중 먼저 락을 잡은 쪽 순서대로 일관되게 끝난다
    (중지가 먼저 → 새 읽기가 True 로 만든다 / 새 읽기가 먼저 → 중지가 새 세션을 멈추고 False).
    session.stop() 은 락 밖에서 부른다(엔진 락과 겹쳐 잡지 않으려고).
    """
    global tts_playing, tts_paused

    tts_stop_event.set()
    with _tts_state_lock:
        session = tts_session
        tts_playing = False
        tts_paused = False
    if session is not None:
        try:
            session.stop()
        except Exception as e:
            logging.warning(f"읽기 세션 정지 오류: {e}")
    try:
        sd.stop()   # TTS 설정 창 미리듣기(sd.play) 멈춤
    except Exception:
        pass
    try:
        import winsound
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass
    # (옛 코드는 여기 끝에서 tts_playing=False 를 한 번 더 했다. 락 밖이라 그 사이 다른 스레드가 시작한 새 읽기를
    #  False 로 덮을 수 있어 뺐다 — 위 락 안에서 이미 False 로 만들었다)

def play_tts_file(filepath):
    """저장된 WAV 파일을 재생합니다.

    ⚠️ 죽은 코드: 부르는 곳은 트레이 toggle_tts 의 "마지막 파일 다시 재생" 뿐인데, tts_current_file 을
       채우는 곳이 없어 도달하지 않는다. 지우는 건 사용자 결정이라 남겨 두었다.
    ⚠️ 이 함수를 되살리지 말 것 — 아래 finally 가 tts_stop_event.clear() 와 tts_playing=False 를 한다.
       읽기 엔진이 도는 중에 이게 돌면 엔진의 tts_playing 을 False 로 덮어쓴다(엔진은 tts_stop_event 를 안 써서
       좀비 스레드는 안 생기지만, "finally 에서 clear 금지" 규칙(06-07 §4)과도 어긋나는 모양이다).
    """
    global tts_playing, tts_paused, tts_stop_event, tts_current_file

    # 기존 재생 중지
    stop_current_playback()
    import time
    time.sleep(0.1)

    tts_playing = True
    tts_paused = False
    tts_stop_event.clear()
    tts_current_file = filepath

    try:
        update_tray_menu()
    except: pass

    log_to_console(f"[TTS] 파일 재생 시작: {os.path.basename(filepath)}")

    try:
        import winsound
        # 비동기 재생
        winsound.PlaySound(filepath, winsound.SND_FILENAME | winsound.SND_ASYNC)

        # 파일 길이 계산하여 대기
        try:
            import soundfile as sf
            data, samplerate = sf.read(filepath)
            duration = len(data) / samplerate
        except:
            duration = 10  # 기본 10초

        # 재생 시간 동안 대기하면서 중지 이벤트 체크
        start_time = time.time()
        while time.time() - start_time < duration:
            if tts_stop_event.is_set():
                winsound.PlaySound(None, winsound.SND_PURGE)
                log_to_console("[TTS] 재생 중지됨")
                break
            time.sleep(0.1)

    except Exception as e:
        log_to_console(f"[TTS] 재생 오류: {e}")
    finally:
        tts_playing = False
        tts_paused = False
        tts_stop_event.clear()
        log_to_console("[TTS] 재생 종료")
        try:
            update_tray_menu()
        except: pass

def _get_english_words():
    """영어 단어 목록(확장 js/english-words.js 복사본, data/english-words.js)을 처음 한 번만 읽어 둔다.

    readaloud_text 가 README → "read me" 처럼 영어 단어를 풀어 읽을 때 쓴다(확장 spoken-text.js 와 같다).
    못 읽으면 None — 읽기는 되고 영어 단어 규칙만 꺼진다. exe 에서는 spec datas 로 _MEIPASS\\data 에 들어간다.
    """
    global _english_words, _english_words_loaded
    if _english_words_loaded:
        return _english_words
    _english_words_loaded = True
    rel = os.path.join("data", "english-words.js")
    for path in (resource_path(rel), os.path.join(get_app_dir(), rel)):
        if not os.path.exists(path):
            continue
        try:
            _english_words = readaloud_text.load_english_words(path)
            log_to_console(f"[TTS] 영어 단어 목록 {len(_english_words)}개를 불러왔습니다")
            break
        except Exception as e:
            log_to_console(f"[TTS] 영어 단어 목록 읽기 실패({path}): {e}")
    if _english_words is None:
        log_to_console("[TTS] 영어 단어 목록이 없어 영어 단어 읽기 규칙을 끕니다")
    return _english_words

def _current_work_area():
    """(Tk 메인) 하단 바를 붙일 모니터의 작업 영역(작업표시줄 제외) (left, top, right, bottom) 화면 좌표.

    bottom_bar_monitor 설정:
      "foreground" (기본) — 읽기를 시작한 순간 전경 창(GetForegroundWindow)이 있는 모니터
                            (읽던 창과 같은 화면에 바가 뜨게. 플로팅 아이콘은 WS_EX_NOACTIVATE 라 전경을 뺏지 않는다)
      "primary"           — 주 모니터
    Win32: GetForegroundWindow → MonitorFromWindow(가까운 모니터) → GetMonitorInfoW 의 rcWork.
    ⚠️ ctypes.windll.user32 의 함수에 argtypes 를 걸면 앱 전체(플로팅 아이콘 코드 등)에 영향이 가므로
       따로 불러온 WinDLL 객체에만 건다. 64비트에서 핸들이 잘리지 않게 restype 을 꼭 지정한다.
    실패하면 주 화면 전체(Tk 가 아는 화면 크기)로 대신한다.
    """
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        user32 = getattr(_current_work_area, "_user32", None)
        if user32 is None:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetForegroundWindow.argtypes = []
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
            user32.MonitorFromWindow.restype = wintypes.HMONITOR
            user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            user32.MonitorFromPoint.restype = wintypes.HMONITOR
            _current_work_area._user32 = user32

        MONITOR_DEFAULTTOPRIMARY = 1
        MONITOR_DEFAULTTONEAREST = 2
        hmon = None
        if bottom_bar_monitor != "primary":
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if not hmon:
            hmon = user32.MonitorFromPoint(wintypes.POINT(0, 0), MONITOR_DEFAULTTOPRIMARY)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if hmon and user32.GetMonitorInfoW(wintypes.HMONITOR(hmon), ctypes.byref(info)):
            r = info.rcWork
            return (r.left, r.top, r.right, r.bottom)
    except Exception as e:
        logging.warning(f"모니터 작업 영역 조회 실패 → 주 화면 전체로 대신: {e}")
    try:
        return (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
    except Exception:
        return (0, 0, 1920, 1080)

def _make_tts_event_handler(box):
    """엔진 알림 받기 함수를 만든다. box["session"] 에 이 알림을 보내는 세션이 들어 있다.

    ⚠️ 이 함수는 재생 스레드(tts-player)에서 불린다. Tk 는 스레드 안전하지 않으므로 UI 는 절대 만지지 않고
       gui_queue 로 Tk 메인 스레드에 넘긴다(check_gui_queue → _handle_tts_event, 100ms 주기).
       빨리 돌아와야 한다 — 엔진이 이 호출을 기다리는 동안 다음 블록을 못 쓴다.
    tts_playing/tts_paused 는 여기서 바로 고친다(단순 대입이라 안전). 큐 지연(최대 100ms) 동안 "끝났는데 재생 중"
    으로 보이는 틈을 줄이려는 것. 단 이미 새 읽기로 바뀌었으면(옛 세션의 늦은 알림) 건드리지 않는다.
    """
    def on_event(kind, data):
        global tts_playing, tts_paused
        session = box.get("session")
        # "지금 세션인가" 확인과 대입을 락 하나로 묶는다. 락 없이 하면 확인 직후 Tk 메인이 새 읽기를 시작해
        # tts_playing=True 로 만든 것을 이 옛 세션 알림이 False 로 덮어쓴다(_tts_state_lock 설명).
        with _tts_state_lock:
            if session is not None and session is tts_session:
                if kind == "state" and isinstance(data, dict):
                    tts_paused = data.get("state") == "PAUSED"
                elif kind == "session_end":
                    tts_playing = False
                    tts_paused = False
        gui_queue.put(("tts_event", session, kind, data))
    return on_event

def speak_text(text):
    """선택한 글을 읽기 시작한다. ⚠️ Tk 메인 스레드에서만 부른다(read_selected_text 가 root.after 로 부름).

    1) readaloud_text.split_for_reading — 확장 드래그 읽기와 같은 규칙으로 줄 단위 조각 + 원문 위치를 만든다.
       lang/voice_lang 은 음성 이름 앞 두 덩어리(ko-KR). 영어 단어 목록은 data/english-words.js.
    2) 앞 읽기를 멈추고(세션 abort), 하단 바를 붙일 모니터를 지금(전경 창 기준) 정한다.
    3) 새 TtsSession 을 만들어 시작한다. 합성은 Google Cloud TTS(make_google_synthesize), 출력은 sounddevice.
       새 세션은 앞 세션의 재생 스레드가 스트림을 닫을 때까지 기다린 뒤 비프음 → 재생한다(previous=).
    4) 엔진 알림 → gui_queue → _handle_tts_event 가 하단 바·리더 창을 움직인다.
    """
    global tts_session, tts_playing, tts_paused, _reading_work_area, _reading_segment_idx

    log_to_console(f"[TTS] speak_text 호출됨 (원본 길이: {len(text) if text else 0})")

    if not text or not text.strip():
        log_to_console("[TTS] 텍스트 없음")
        return

    if not google_tts_client or not google_tts:
        log_to_console("[TTS] 초기화 안됨")
        return

    lang = tts_engine.voice_lang_of(tts_voice_name)
    try:
        segments = readaloud_text.split_for_reading(text, lang, lang, _get_english_words())
    except Exception as e:
        logging.error(f"조각 나누기 오류: {e}")
        log_to_console(f"[TTS] 조각 나누기 오류: {e}")
        return
    if not any(not tts_engine.is_silent_segment(seg.get("text")) for seg in segments):
        log_to_console("[TTS] 읽을 조각이 없습니다 (공백·마침표뿐)")
        return
    log_to_console(f"[TTS] 조각 {len(segments)}개로 나눔 (언어 {lang})")

    previous = tts_session
    stop_current_playback()                 # 앞 읽기 정지(세션 abort) + 미리듣기 정지
    _reading_work_area = _current_work_area()
    _reading_segment_idx = None

    box = {}
    try:
        session = tts_engine.TtsSession(
            text, segments,
            tts_engine.make_google_synthesize(google_tts_client, google_tts, tts_voice_name, log=log_to_console),
            tts_engine.sounddevice_stream_factory(),
            _make_tts_event_handler(box),
            rate=tts_speaking_rate, volume=tts_volume, muted=False,   # 음소거는 읽기마다 풀린다(확장 page-ui-host.js:105)
            before_play=tts_engine.play_start_beep, previous=previous, log=log_to_console)
    except Exception as e:
        logging.error(f"읽기 세션 생성 오류: {e}")
        log_to_console(f"[TTS] 읽기 시작 오류: {e}")
        return
    box["session"] = session
    # ⚠️ start() 전에 넣어야 session_start 알림이 "옛 세션"으로 버려지지 않는다.
    #    세 값을 락 안에서 한 번에 바꾼다 — 옛 세션의 끝 알림이 그 사이에 끼어 tts_playing 을 False 로 덮지 못하게.
    with _tts_state_lock:
        tts_session = session
        tts_playing = True
        tts_paused = False
    try:
        session.start()
    except Exception as e:
        # 스레드를 못 띄운 경우(드묾). 엔진이 STOPPED·session_end 를 이미 보냈으므로(→ tts_playing=False,
        # 하단 바·리더 창 정리) 여기서는 로그만 남긴다.
        logging.error(f"읽기 시작 오류: {e}")
        log_to_console(f"[TTS] 읽기 시작 오류: {e}")
    try:
        update_tray_menu()
    except Exception:
        pass

def stop_tts():
    """TTS 완전 중지 (단축키·플로팅 아이콘·하단 바 닫기·트레이에서 부름)"""
    stop_current_playback()
    log_to_console("[TTS] 중지 요청")

# ── 하단 바·리더 창 연결 (전부 Tk 메인 스레드) ───────────────────────────────

def _safe_ui(what, fn, *args, **kwargs):
    """하단 바·리더 창 메서드를 부른다. 그쪽에서 예외가 나도 앱과 읽기는 계속 가게 로그만 남긴다."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logging.error(f"[UI] {what} 실패: {e}")
        log_to_console(f"[UI] {what} 실패: {e}")
        return None

def _ensure_reading_ui():
    """(Tk 메인) 하단 바·리더 창을 처음 쓸 때 만든다. 만들다 실패하면 그 뒤로는 시도하지 않는다(로그 도배 방지).

    두 창 모두 포커스를 뺏지 않는 창(WS_EX_NOACTIVATE|TOOLWINDOW, 항상 위)으로 만드는 건 각 모듈의 몫이다
    (플로팅 아이콘 setup_floating_controller 와 같은 처리 — 읽던 창의 포커스를 뺏으면 Ctrl+C 가 엉뚱한 곳으로 간다).
    """
    global bottom_bar, reader_window, BottomBar, ReaderWindow
    if bottom_bar is None and BottomBar is not None and root is not None:
        try:
            bottom_bar = BottomBar(root, _on_bar_command, get_msg)
        except Exception as e:
            BottomBar = None
            logging.error(f"하단 바 생성 실패: {e}")
            log_to_console(f"[UI] 하단 바를 만들지 못했습니다(바 없이 읽기만 합니다): {e}")
    if reader_window is None and reader_window_enabled and ReaderWindow is not None and root is not None:
        try:
            reader_window = ReaderWindow(root, get_msg, on_geometry_changed=_on_reader_geometry_changed)
        except Exception as e:
            ReaderWindow = None
            logging.error(f"리더 창 생성 실패: {e}")
            log_to_console(f"[UI] 리더 창을 만들지 못했습니다(형광펜 없이 읽기만 합니다): {e}")

def _on_bar_command(cmd, value=None):
    """(Tk 메인) 하단 바 버튼 → 재생 엔진 명령. BottomBar(on_command) 가 부른다.

    cmd: "togglePause" | "stop" | "forward" | "rewind" | "mute" | "unmute" | "setRate"(value=배속) | "setVolume"(value=0.2~1)
    닫기(X) = "stop": 읽기 중지 + 바를 곧바로 숨김(확장 page-ui.js:582-585 도 바를 먼저 숨기고 stop 을 보낸다).
    속도·볼륨은 확장처럼 설정에 저장해 다음 읽기에도 쓴다(page-ui-host.js:193-203).
    """
    global tts_speaking_rate, tts_volume
    if cmd == "stop":
        if bottom_bar is not None:
            _safe_ui("하단 바 숨김", bottom_bar.hide)
        stop_tts()
        return
    session = tts_session
    if session is None:
        return
    if cmd in ("togglePause", "forward", "rewind", "mute", "unmute"):
        session.command(cmd)
    elif cmd == "setRate":
        session.set_rate(value)
        tts_speaking_rate = session.rate    # Cloud TTS 범위로 잘린 값
        save_settings()
    elif cmd == "setVolume":
        session.set_volume(value)
        tts_volume = session.volume
        save_settings()
    else:
        log_to_console(f"[UI] 알 수 없는 하단 바 명령: {cmd}")

def _on_reader_geometry_changed(geom):
    """(Tk 메인) 사용자가 리더 창을 옮기거나 크기를 바꿨다 → 위치 "WxH+X+Y" 를 설정에 기억한다."""
    global reader_window_geometry
    if not isinstance(geom, str) or not geom or geom == reader_window_geometry:
        return
    reader_window_geometry = geom
    save_settings()

def _show_reader_window(session):
    """(Tk 메인) 리더 창에 이번 읽기의 원문을 넣고 하단 바 바로 위에 띄운다. 꺼져 있거나 없으면 아무것도 안 한다."""
    if session is None or not reader_window_enabled:
        return
    _ensure_reading_ui()
    if reader_window is None:
        return
    _safe_ui("리더 창 시작", reader_window.start, session.source_text, session.segments)
    bar_height = 0
    if bottom_bar is not None:
        try:
            bar_height = int(getattr(bottom_bar, "height", 0) or 0)
        except Exception:
            bar_height = 0
    _safe_ui("리더 창 표시", reader_window.show, _reading_work_area or _current_work_area(), bar_height,
             geometry=reader_window_geometry)
    if _reading_segment_idx is not None:
        _safe_ui("형광펜", reader_window.highlight, _reading_segment_idx)

def _hide_reading_ui():
    """(Tk 메인) 읽기가 끝났다 → 하단 바를 숨기고, 리더 창은 칠을 지우고 숨긴다."""
    if bottom_bar is not None:
        _safe_ui("하단 바 숨김", bottom_bar.hide)
    if reader_window is not None:
        _safe_ui("리더 창 끝", reader_window.end)

def _handle_tts_event(session, kind, data):
    """(Tk 메인) 재생 엔진 알림 처리. check_gui_queue 가 부른다.

    지금 세션(tts_session)의 알림만 처리한다. 새 읽기가 옛 읽기를 대신한 뒤 도착한 옛 세션의 늦은 알림
    (특히 session_end)은 버린다 — 안 그러면 새 읽기의 하단 바·리더 창을 옛 세션이 숨겨 버린다.
    """
    global tts_session, _reading_segment_idx
    if session is None or session is not tts_session:
        return
    if kind == "session_start":
        _ensure_reading_ui()
        if bottom_bar is not None:
            _safe_ui("하단 바 표시", bottom_bar.show, _reading_work_area or _current_work_area())
        _show_reader_window(session)
    elif kind == "segment":
        _reading_segment_idx = data
        if reader_window is not None and reader_window_enabled:
            _safe_ui("형광펜", reader_window.highlight, data)
    elif kind == "state":
        if bottom_bar is not None:
            _safe_ui("하단 바 갱신", bottom_bar.update, data)
    elif kind == "session_end":
        _hide_reading_ui()
        with _tts_state_lock:
            tts_session = None
        _reading_segment_idx = None
        try:
            update_tray_menu()
        except Exception:
            pass

def toggle_reader_window():
    """(Tk 메인) 트레이 "리더 창" 체크 켬/끔. 읽는 도중에 켜면 바로 띄우고, 끄면 바로 숨긴다. 설정에 저장한다."""
    global reader_window_enabled
    reader_window_enabled = not reader_window_enabled
    save_settings()
    log_to_console(f"[UI] 리더 창 {'켬' if reader_window_enabled else '끔'}")
    if reader_window_enabled:
        if tts_session is not None and tts_playing:
            _show_reader_window(tts_session)
    elif reader_window is not None:
        _safe_ui("리더 창 끝", reader_window.end)
    try:
        update_tray_menu()
    except Exception:
        pass

def read_selected_text():
    """선택된 텍스트를 읽어옵니다. (Ctrl+C 트릭 사용)

    ⚠️ Tk 메인 스레드에서 부른다(단축키·플로팅 클릭이 root.after 로 부름).
    흐름: 눌린 수정자 키 떼기 → 클립보드 백업 → 클립보드 비우기 → Ctrl+C 흉내 → 0.5초 기다렸다 읽기
    3방향 분기 (07-27 확정):
      1) 선택한 글이 있다          → speak_text(글) — 읽는 중이어도 새 글로 다시 읽는다
      2) 선택 없음 + 읽는 중       → stop_tts() (중지가 아이콘 복원보다 먼저 — 숨긴 상태에서도 단축키로 멈추게)
      3) 선택 없음 + 읽지 않는 중  → 플로팅 아이콘 보이기/숨기기 토글(set_controller_visible)
    ⚠️ 클립보드를 비우는 단계를 지우지 말 것: 선택이 없으면 Ctrl+C 가 클립보드를 안 바꾸므로, 안 비우면 직전에
       복사해 둔 글을 "선택한 글" 로 착각해 읽는다(07-27 로그 §4-1). 선택 없음일 때는 백업을 되돌려 놓는다.
    ⚠️ time.sleep 합계 약 0.8초 동안 Tk 메인이 멈춘다(하단 바·리더 창·플로팅 아이콘도 그동안 멈춤).
       단축키로 멈출 때의 이 지연은 설계상 감수하기로 한 것이다. 이 사이 재생이 스스로 끝나면 tts_playing 이
       False 가 되어 2) 대신 3) 으로 갈 수 있다(드묾).
    """
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

        # 선택 여부를 확실히 판별하기 위해 클립보드를 비운다.
        # 선택된 텍스트가 없으면 Ctrl+C를 눌러도 클립보드가 그대로 남기 때문에,
        # 비우지 않으면 직전 복사물을 "선택된 텍스트"로 오인해서 읽어버린다.
        try:
            pyperclip.copy("")
            time.sleep(0.05)
        except Exception:
            pass

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

        # ── 선택된 텍스트가 없을 때: 중지 / 컨트롤러 복원으로 분기 ──
        if not new_text or len(new_text.strip()) == 0:
            # 판별하려고 비웠던 클립보드를 원래 내용으로 되돌린다
            try:
                pyperclip.copy(old_clipboard if old_clipboard else "")
            except Exception:
                pass

            if tts_playing:
                # 숨김 상태에서도 단축키만으로 멈출 수 있게 한다 (중지가 복원보다 우선)
                log_to_console("[TTS] 선택된 텍스트 없음 → 재생 중지")
                stop_tts()
            else:
                # 플로팅 아이콘 표시/숨김 토글
                log_to_console(f"[컨트롤러] 선택된 텍스트 없음 → 플로팅 아이콘 {'복원' if controller_hidden else '숨김'}")
                set_controller_visible(controller_hidden)
            return

        # 선택된 텍스트가 있으면 읽는다 (직전과 같은 텍스트여도 그대로 읽어준다)
        log_to_console(f"선택된 텍스트 감지: {new_text[:30]}...")
        speak_text(new_text)

    except Exception as e:
        logging.error(f"선택 영역 읽기 오류: {e}")
        log_to_console(f"선택 영역 읽기 오류: {str(e)}")

def extract_readme_files():
    """README 파일을 실행 파일이 있는 디렉토리에 추출합니다.

    exe 로 실행할 때만 한다: exe 안에 묶인 README.md·README.KR.md 를 exe 옆에 꺼내 둔다
    (트레이 "도움말" 이 작업 폴더의 README 를 연다). 이미 있으면 덮어쓰지 않는다 → 사용자가 고친 파일은 보존.
    로깅 준비 전에 불리므로 print 만 쓴다.
    """
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
# 직접 실행할 때만 앱이 뜬다. ⚠️ 이 파일을 import 만 해도 위쪽 모듈 코드(bottom_bar·reader_window import 등)는
# 돌지만, 트레이·키보드 훅·창은 main() 안에서만 뜬다. 그래도 테스트는 이 파일을 import 하지 않는다
# (tests/test_tts_engine.py 는 필요한 함수만 소스에서 뽑아 가짜 부품과 돌린다).
if __name__ == "__main__":
    print("\n============================================")
    print("     BluemingReadAloud 시작      ")
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
