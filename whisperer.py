#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Powered by HRG

"""
BluemingReadAloud - 선택한 글을 읽어주는 TTS 프로그램 (Google Cloud Text-to-Speech)
Copyright (c) 2024 Yeogiaen

과거 STT(받아쓰기)+TTS 겸용 앱이었으나 STT를 걷어내고 TTS 전용으로 전환됨

■ 한눈에 보는 흐름
  단축키(기본 Ctrl+Alt+D) 또는 빨간 점 클릭(글을 드래그·더블클릭으로 고르면 선택 끝 옆에 뜬다 — 확장 selection-button.js)
    → read_selected_text : Ctrl+C 를 흉내 내 선택한 글을 클립보드로 가져온다
    → speak_text         : readaloud_text.split_for_reading 으로 줄 단위 조각을 만들고
                           tts_engine.TtsSession(합성 스레드 + 재생 스레드)을 시작한다
    → 엔진 알림          : 재생 스레드 → gui_queue → check_gui_queue(Tk 메인) → _handle_tts_event
                           → 하단 바(bottom_bar.py) + 형광펜
  형광펜은 두 가지 (2026-09-28 사용자 확정):
    - 원문 위 형광펜(source_highlight.py) — 읽기 시작 때 _begin_source_highlight 가 SourceHighlighter.begin 을 부른다.
      결과(on_result)가 ok 면 그 앱의 원문 위에 반투명 노란 막을 칠하고 리더 창은 띄우지 않는다.
    - 리더 창(reader_window.py) — 원문 위에 칠할 수 없을 때(ok=False)만, 트레이 "리더 창 사용" 이 켜져 있으면 띄운다.
      결과를 기다리는 동안은 띄우지 않는다.
  브라우저(Aside·웨일·크롬)에서는 쉰다 — 트레이 "브라우저에서 비활성화"(기본 켬). 그 브라우저들은 크롬 확장이 읽는다.
  (옛 플로팅 아이콘은 2026-09-28 사용자 결정으로 없앴다 — 빨간 점이 그 자리를 대신한다)

■ 스레드 지도 (⚠️ tkinter 는 스레드 안전하지 않다 — Tk 창은 Tk 메인 스레드에서만 만진다)
  - Tk 메인        : root.mainloop. 모든 창(빨간 점·하단 바·리더 창·설정 창)과 speak_text
  - pynput 키보드  : 전역 키보드 훅(setup_keyboard_listener). 여기서는 root.after 로 Tk 메인에 넘기기만 한다
  - pynput 마우스  : 전역 마우스 훅(setup_mouse_listener). 드래그·더블클릭 판정 후 gui_queue 에 넣기만 한다
  - pystray 스레드 : 트레이 아이콘·메뉴(setup_tray_icon). Tk 일은 gui_queue 에 문자열을 넣어 넘긴다
  - tts-producer / tts-player : 읽기 한 번마다 새로 뜨는 합성·재생 스레드(tts_engine.py). UI 는 gui_queue 로만
  - 원문 위 형광펜 UIA 스레드 : source_highlight.py 안의 전용 스레드 하나. 결과는 그쪽이 root.after 로 Tk 메인에 넘긴다
  - watchdog       : 30초마다 키보드 훅·마우스 훅이 살아 있는지 확인

■ 이 파일에서 절대 깨면 안 되는 약속 (근거: docs/session_logs/2026-06-07 §4, 2026-07-27 §4·§10)
  - 재생 중 판정은 tts_playing 으로 한다(is_speaking 은 죽은 변수라 지웠다)
  - 빨간 점 창은 포커스를 뺏으면 안 된다(WS_EX_NOACTIVATE — selection_button.py). 뺏으면 뒤이은 Ctrl+C 가
    글을 고른 창이 아니라 점으로 가서 "선택 없음" 이 된다
  - 훅 콜백(키보드·마우스)은 가볍게: 판정·변수 바꾸기·gui_queue.put 만. Tk 호출·파일 I/O·로그 금지
    (윈도우가 느린 훅을 조용히 떼어 낸다)
  - 재생 정지는 출력 스트림 abort 로(sd.stop() 은 OutputStream 을 못 멈춘다).
    재생 쪽 finally 에서 멈춤 신호를 clear() 하지 말 것(좀비 스레드 재발)
  - Ctrl+C 전에 클립보드를 비우는 동작을 유지할 것(안 비우면 "선택 없음" 을 판별할 수 없다)
  - 인증은 API 키 두 개 — TTS 키·Gemini 키(2026-09-29 사용자 결정, 서비스 계정 JSON 에서 바꿈). 인증 창에 넣고
    설정 파일에 저장한다. .env 는 읽지 않는다. 키 하나로 둘 다는 안 된다(init_tts_client 설명)
  - 이 파일은 UI Automation 을 직접 부르지 않는다. 원문 위 형광펜의 UIA 호출은 source_highlight.py 의 전용 스레드에서만
    한다(2026-09-28 VS Code 를 얼린 전례 — 창·문서 전체를 훑는 호출 금지는 그쪽 몫)
  - "브라우저인가" 판별(전경 창 → 프로세스 → 실행 파일 이름)은 Tk 메인에서만(_foreground_disabled_browser). 훅 콜백에서 하지 않는다
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
import spoken_text      # 말할 글 다듬기 — Paseo 상태바 플러그인 규칙(2026-10-28)
import tts_engine
# 읽기 이번 달 사용량 세기 · 세 곳(Paseo·이 앱·크롬 확장) 요금 브리지(2026-11-01) — 표준 라이브러리만 쓴다
import tts_usage
# 주 언어가 아닌 문장 번역(2026-09-29) — requests 는 번역기를 만들 때(init_tts_client) 불러온다
import translation

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
# 빨간 점(선택 끝 옆에 뜨는 읽기 버튼, selection_button.py) — 이것도 없어도 앱은 살아야 한다.
# 실패하면 빨간 점 없이 단축키로만 읽는다(마우스 훅도 띄우지 않는다). 오류는 main() 에서 로그로 남긴다.
try:
    import selection_button as _selection_button_mod
    from selection_button import SelectionButton, SelectionGestureDetector
    _selection_button_import_error = None
except Exception as _e:
    _selection_button_mod = None
    SelectionButton = None
    SelectionGestureDetector = None
    _selection_button_import_error = _e
# 읽기 사용량 알약(usage_pill.py, 2026-11-01) — 빨간 점 모듈의 Win32 도우미를 빌려 쓴다. 실패하면 알약만 없다
try:
    from usage_pill import UsagePill, popup_position as _pill_popup_position, POPUP_GAP_PX as _PILL_POPUP_GAP_PX
    _usage_pill_import_error = None
except Exception as _e:
    UsagePill = None
    _pill_popup_position = None
    _PILL_POPUP_GAP_PX = 8
    _usage_pill_import_error = _e
# 원문 위 형광펜(source_highlight.py — UI Automation 으로 다른 앱의 원문 줄 사각형을 얻어 그 위에 막을 칠한다).
# 이것도 없어도 앱은 살아야 한다(comtypes 가 없거나 파일이 없거나 import 오류). 실패하면 None →
# 원문 위 칠하기 없이 예전처럼 리더 창(켜져 있으면)으로만 형광펜을 보인다. 오류는 main() 에서 로그로 남긴다.
try:
    from source_highlight import SourceHighlighter
    _source_highlight_import_error = None
except Exception as _e:
    SourceHighlighter = None
    _source_highlight_import_error = _e
# 따라 읽기 창(follow_dialog.py, 2026-10-28) — 없어도 앱은 산다. 실패하면 None → 창 없이 고른 글만 읽는다(예전 그대로)
try:
    from follow_dialog import FollowDialog
    _follow_dialog_import_error = None
except Exception as _e:
    FollowDialog = None
    _follow_dialog_import_error = _e

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
console_log_file = None # 콘솔 로그 파일
keyboard_listener = None # 키보드 리스너
pynput_initialized = False # Pynput 초기화 여부
# (옛 플로팅 아이콘 전역 floating_controller·controller_canvas·controller_position·controller_hidden 과
#  tray_menu_updater 는 2026-09-28 플로팅 아이콘을 없애며 지웠다. 설정 파일에 남은 옛 키는 읽지 않는다)

# 빨간 점(선택 버튼) — 글을 드래그·더블클릭으로 고르면 선택 끝 옆에 뜨고, 누르면 읽는다(확장 js/selection-button.js)
selection_button_enabled = True  # 트레이 "텍스트 선택 시 읽기 버튼" 체크. 기본 켬 — 확장도 기본 켬(js/events.js:135 `selectionButton !== false`)
selection_button = None          # SelectionButton 창 (Tk 메인 스레드에서만 만들고 부른다). 못 만들면 None — 단축키 읽기는 그대로 된다
mouse_listener = None            # 전역 마우스 훅(pynput.mouse.Listener). 빨간 점이 켜져 있을 때만 돈다
_mouse_watchdog_started = False  # 마우스 훅 watchdog 스레드를 이미 띄웠는가 (한 번만 띄운다)
_selection_key_hook = None       # 키보드 훅이 키 누름마다 부르는 "빨간 점 숨김" 함수 (setup_mouse_listener 가 채운다)

# 브라우저에서 비활성화 (2026-09-28 사용자 확정: 빨간 점·단축키 모두 쉼)
# 전경 창의 실행 파일이 아래 이름이면 빨간 점을 띄우지 않고 단축키로 새 읽기를 시작하지 않는다
# — 그 브라우저들에는 크롬 확장 read-aloud-hrg 가 깔려 있어 확장이 읽는다(둘이 겹쳐 읽지 않게).
# ⚠️ msedgewebview2.exe(다른 앱 안의 웹 화면)는 브라우저가 아니다 — 대상 아님. Edge(msedge.exe)도 목록에 없다(사용자 지정 목록).
disable_in_browsers = True       # 트레이 "브라우저에서 비활성화" 체크. 기본 켬(사용자 확정)
_BROWSER_EXES = frozenset({"aside.exe", "whale.exe", "chrome.exe"})   # 소문자로 비교(대소문자 무시)
_TELEGRAM_EXES = frozenset({"telegram.exe"})   # 텔레그램 데스크톱 — 빨간 점은 "선택한 메시지"로 판단(2026-10-23 사용자 결정)
# 우클릭 메뉴 "선택" 을 뗀 순간 메뉴가 아직 떠 있으면 이 간격으로 다시 묻고 상한까지 기다린다(2026-10-23 사용자 확정).
# 근거: 개발 모드 실측 — 첫 확인은 메뉴(Ui::PopupMenu)만 잡혔고 0.1초 뒤 두 번째 확인에서 "선택됨"(처음 물은 뒤 0.23초).
TELEGRAM_MENU_RETRY_MS = 100
TELEGRAM_MENU_RETRY_MAX_S = 1.0

# 원문 위 형광펜 (source_highlight.py) — 전부 Tk 메인 스레드에서만 읽고 쓴다
source_highlight_enabled = True  # 설정 키만 있다. 트레이·설정 창에는 넣지 않는다(사용자가 트레이 목록을 정했다)
source_highlighter = None        # SourceHighlighter 객체. 처음 읽을 때 만든다(_ensure_source_highlighter). 못 만들면 None
_source_hl_session = None        # begin 을 부른 읽기 세션(이 세션의 결과만 받는다 — 늦게 온 옛 결과는 버림)
_source_hl_state = None          # None(안 씀) | "pending"(결과 기다림) | "on"(원문 위 칠하는 중) | "off"(못 칠함 → 리더 창)
_reading_ui_session = None       # session_start 를 처리해 하단 바를 띄운 세션(결과 ok=False 가 그 뒤에 오면 그때 리더 창을 띄운다)

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

# Google 인증 — API 키 두 개 (2026-09-29 사용자 결정. 그 전엔 서비스 계정 JSON 경로 google_credentials_path)
google_tts_api_key = None   # Cloud Text-to-Speech API 를 허용한 키. 없으면 시작할 때 필수 인증 창
gemini_api_key = None       # Gemini API 를 허용한 키(번역용). 없어도 되고, 없으면 번역할 때 멈추고 알린다

# Google Cloud TTS 관련 변수
google_tts = None          # google.cloud.texttospeech 모듈 (요청 객체를 만들 때 씀). init_tts_client 가 채운다
google_tts_client = None   # TextToSpeechClient. None 이면 "인증 안 됨" — speak_text 가 읽지 않고 돌아간다
# 주 언어가 아닌 문장 번역 (2026-09-29, translation.py). 규칙은 translation.py 머리 설명.
translate_enabled = True   # 설정 창 "일반" 체크. 기본 켬(사용자 결정)
# 번역된 조각은 원문 위 형광펜 막에 번역문을 쓴다(짙은 회색 바탕 + 흰 글씨, source_highlight caption). 끄면 노랑 형광펜만.
translation_overlay_enabled = True   # 설정 창 "일반" 체크. 기본 켬(2026-09-29 사용자 결정 "옵션으로 빼고 기본은 레이어로")
_translation_lookup = None  # (세션, 조각 글 → 번역문 함수). speak_text 가 넣고 session_end 가 비운다. Tk 메인에서만
gemini_translator = None   # translation.GeminiTranslator(키가 없거나 못 만들었으면 MissingTranslator). init_tts_client 가 채운다
tts_hotkey_modifiers = {"ctrl": True, "shift": False, "alt": True} # 기본 TTS 단축키: Ctrl+Alt+D
tts_hotkey_key = "D"
# 기본 음성 모델 — 2026-10-28 Paseo 상태바 플러그인·크롬 확장과 같은 목소리로(리규형님 지시, 그 전 기본은 Callirrhoe).
# 설정 창에서 고른 칸을 못 찾을 때도 이 값(2026-11-01 Paseo 기준 맞추기 — 그 전엔 옛 기본 Wavenet-A 였다)
DEFAULT_VOICE = "ko-KR-Chirp3-HD-Zephyr"
tts_voice_name = DEFAULT_VOICE
tts_speaking_rate = 1.0   # 재생 속도(기본 1.0). 하단 바 목록·Ctrl+↑/↓ 로 고른다 — 늘 tts_rate_step 간격의 값(tts_engine.snap_rate)
tts_rate_step = tts_engine.DEFAULT_RATE_STEP   # 속도 간격 0.1(0.5~2배) / 0.25(0.5~5배) — 2026-10-28 Paseo 기준(그 전 10-24 는 0.7~2.0 / 0.5~3.0)
tts_volume = 1.0          # 재생 볼륨 — 늘 1.0(2026-10-24 사용자 결정: 볼륨 막대 제거, 소리 크기는 윈도우 볼륨으로). 저장·읽기 안 함
# ※ TTS 재생 중 판정은 tts_playing(아래 TTS 재생 상태 변수)으로 한다

# 하단 바·리더 창 설정 (whisperer_settings.json 에 저장)
reader_window_enabled = True     # 트레이 "리더 창 사용" 체크. 켜면 원문 위에 칠할 수 없을 때 리더 창(원문 + 읽는 줄 형광펜)을 띄운다
reader_window_geometry = None    # 사용자가 옮기거나 크기를 바꾼 리더 창 위치 "WxH+X+Y" (None 이면 기본 위치)
bottom_bar_monitor = "foreground"  # 하단 바를 띄울 모니터: "foreground"(읽기 시작 순간 전경 창의 모니터) | "primary"(주 모니터)

# 하단 바·리더 창 객체 (Tk 메인 스레드에서만 만들고 부른다). 만들지 못하면 None — 읽기는 그대로 된다
bottom_bar = None
reader_window = None
_reading_work_area = None        # 이번 읽기에서 하단 바를 붙일 모니터 작업 영역 (left, top, right, bottom)
_reading_segment_idx = None      # 지금 형광펜을 칠한 조각 번호 (리더 창을 읽는 도중에 켤 때 다시 칠하려고)
# 형광펜·리더 창은 문단을 칠한다(2026-10-28 Paseo 기준). (세션, 문단 목록, 조각 → 문단 번호 표) — _paragraphs_of 가 채운다
_reading_paragraphs = None
_painted_para = None             # (세션, 문단 번호, 번역문) — 원문 형광펜에 마지막으로 넘긴 것(같은 문단의 다음 조각에서 다시 칠하지 않게)
_english_words = None            # 영어 단어 목록(data/english-words.js). 처음 읽을 때 한 번 불러온다
_english_words_loaded = False

# 설정 창 목소리 목록 — Paseo 상태바 플러그인 FEATURED_GOOGLE_VOICES 와 같은 여덟 개·같은 차례(2026-11-01 리규형님 지시
# "설정 UX 를 Paseo 와 맞추라"). 맨 위 Zephyr 는 기본값, 나머지 Chirp 3 HD 는 A→Z, 끝의 둘이 100만 자 4달러 칸(WaveNet —
# 한국어 여성은 A·B 둘뿐). 예전 목록의 남성 WaveNet·Neural2·Standard 는 뺐다 — 그 값이 저장돼 있으면 목록 맨 앞에 붙여 그대로 둔다.
KOREAN_VOICES = [
    "ko-KR-Chirp3-HD-Zephyr",
    "ko-KR-Chirp3-HD-Aoede",
    "ko-KR-Chirp3-HD-Callirrhoe",
    "ko-KR-Chirp3-HD-Despina",
    "ko-KR-Chirp3-HD-Kore",
    "ko-KR-Chirp3-HD-Leda",
    "ko-KR-Wavenet-A",
    "ko-KR-Wavenet-B",
]

# 읽기 이번 달 사용량(2026-11-01, tts_usage.py). 개발 모드·설치본이 %APPDATA%\BluemingReadAloud 의 같은 파일에 센다
tts_usage_counter = tts_usage.UsageCounter(log=lambda msg: log_to_console(msg))
extension_usage_reports = tts_usage.ExtensionReports()   # 크롬 확장이 받는 창구로 보낸 값
usage_receiver = None   # tts_usage.UsageReceiver — setup_usage_receiver() 가 띄운다(127.0.0.1:51888 TCP)
# 사용량 알약(usage_pill.py) — 트레이 왼쪽 클릭으로 켜고 끈다. 켬 상태·끌어 옮긴 자리는 whisperer_settings.json 에 남는다
usage_pill = None              # UsagePill (Tk 메인에서 처음 켤 때 만든다)
usage_pill_visible = False     # 켜 둔 상태 — 앱을 다시 켜도 유지(2026-11-01 리규형님 버튼)
usage_pill_position = None     # 끌어 옮긴 자리 [x, y] (None = 주 모니터 오른쪽 아래)
USAGE_TICK_MS = 5000           # 알약·사용량 창이 떠 있을 때 기록 파일을 다시 읽는 간격(Claude 가 정함 — Paseo 파일은 5분마다 바뀐다)
_usage_refresh_pending = False


def _count_tts_usage(voice_name, sent):
    """성공한 합성 요청 하나의 보낸 글을 이번 달 사용량에 더한다(합성·미리 듣기 스레드에서 불린다 — Tk 를 만지지 않는다).
    더한 뒤 알약·사용량 창을 바로 고치라고 gui_queue 에 알린다."""
    tts_usage_counter.count(tts_usage.usage_kind(voice_name), sent)
    gui_queue.put("usage_changed")

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
    mutex_ok = False   # Mutex 로 "첫 실행" 이 확인됐는지 — 확인됐으면 아래 소켓 백업은 하지 않는다
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
        mutex_ok = bool(_instance_mutex)   # 핸들이 0 이면 Mutex 생성 자체가 실패 → 소켓 백업으로
    except Exception as e:
        logging.warning(f"Mutex 생성 실패, 소켓 방식으로 대체: {e}")

    if mutex_ok:
        # Mutex 로 첫 실행임이 확인됐다 → 소켓 검사는 건너뛴다(위 docstring 대로 "Mutex 가 실패했을 때의 백업").
        # ⚠️ 예전에는 Mutex 가 성공해도 소켓 검사를 늘 했는데, 다른 프로그램이 UDP 51888 을 쓰면
        #   "이미 실행 중" 으로 잘못 알고 꺼졌다(2026-09-28 실측: TeamViewer_Service 가 0.0.0.0:51888 을 잡고 있었음).
        logging.info("프로그램 단일 인스턴스 확인 완료 (Mutex)")
        return True

    # 2차: 소켓 포트 바인딩 방식 (백업 — Mutex 생성이 실패했을 때만)
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
    - whisperer_console.log              : log_to_console() 기록. 설정 창 "콘솔 창 열기" 가 이 파일을 실시간으로 보여 준다
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

    # force=True: 이 함수보다 먼저 logging.info/warning 이 불리면(단일 실행 확인·창 아이콘 — main 앞부분) 파이썬이 기본 설정을
    # 알아서 깔고, 그 뒤 basicConfig 는 조용히 무시된다. 그래서 2026-07 부터 logs/whisperer_*.log 가 전부 0바이트였고
    # 형광펜 모듈이 남긴 기록(멈춤·숨김 이유)이 어디에도 없었다(2026-09-29 발견) → 먼저 깔린 설정을 덮어쓴다.
    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        handlers=log_handlers,
        force=True
    )
    # 외부 라이브러리의 세세한 기록(DEBUG)이 로그를 덮지 않게 — 경고 이상만 남긴다
    for noisy in ("comtypes", "urllib3", "PIL", "google", "grpc", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

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
    """콘솔 로그 파일에 메시지 기록 (사용자가 설정 창 "콘솔 창 열기" 로 보는 로그).

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

def init_tts_client(tts_key, gemini_key=None):
    """API 키로 Google Cloud TTS 클라이언트를 만들고, Gemini 키로 번역기를 만든다.

    반환:
      True  — google_tts / google_tts_client 준비 완료 (번역기는 키가 없어도 MissingTranslator 로 채워진다)
      False — google-cloud-texttospeech 모듈을 불러올 수 없어 건너뜀 (로그만 남김)
    TTS 키가 비었거나 클라이언트 생성이 실패하면 예외를 그대로 올린다(호출부가 인증 창을 띄우거나 오류를 표시한다).
    ⚠️ 클라이언트 생성은 키가 맞는지 확인하지 않는다(네트워크 요청 없음). 확인은 인증 창 "설정" 이 한다
       (_check_tts_key·translation.check_gemini_key). 시작할 때는 확인하지 않는다 — 인터넷이 끊긴 채 켜도 창이 뜨지 않게.

    부르는 곳 두 군데:
      - main() 시작 때: 설정 파일의 키로 시도. TTS 키가 없거나 예외면 필수 인증 창.
      - show_api_key_dialog 의 "설정" 버튼: 확인을 통과한 키로 시도.
    왜 키 두 개인가 (2026-09-29 사용자 결정 — 그 전엔 서비스 계정 JSON 파일):
      - 구글이 Gemini API 키는 서비스 계정에 묶게 하고, 묶인 키는 Vertex·Gemini 만 부른다. 실측: Gemini 키로 TTS 는
        401("API keys are not supported by this API"), TTS 키로 Gemini 는 403(API_KEY_SERVICE_BLOCKED) → 키 하나로는 안 된다.
      - 2026-06-07 에 키 방식을 버린 이유는 STT v2 의 IAM 제약이었다. STT 를 걷어내 그 제약은 없어졌다.
    전역 google_tts / google_tts_client 는 성공했을 때만 바꾼다 → 실패해도 앞에서 만든 클라이언트는 그대로 남는다.
    """
    global google_tts, google_tts_client

    if not tts_key:
        raise ValueError("TTS 키가 없습니다")

    # ⚠️ ImportError만 잡으면 안 된다. protobuf 버전 충돌(TypeError) 같은 import 시점 오류가
    #    "인증 파일 오류"로 올라가면, 필수 인증 창이 저장해도 계속 실패 + 취소 불가 → 영영 못 닫힌다.
    #    (옛 코드도 TTS import 오류는 except Exception으로 로그만 남겼다)
    try:
        from google.cloud import texttospeech
    except Exception as e:
        logging.error(f"Google Cloud TTS 모듈 로딩 실패: {e}")
        log_to_console(f"[TTS] TTS 모듈(google-cloud-texttospeech)을 불러올 수 없습니다: {e}")
        return False

    client = texttospeech.TextToSpeechClient(client_options={"api_key": tts_key})
    google_tts = texttospeech
    google_tts_client = client
    log_to_console("[TTS] Google Cloud TTS 클라이언트 초기화 성공 (API 키)")
    logging.info("Google Cloud TTS 클라이언트 초기화 완료 (API 키)")
    _init_translator(gemini_key)
    return True

def _check_tts_key(tts_key):
    """인증 창 "설정" 때 TTS 키가 맞는지 확인한다 — 한국어 음성 목록 요청 한 번. 틀리면 예외.

    실측(2026-09-29): TTS 키 성공(0.28초), Gemini 키 401 — 두 칸을 바꿔 넣어도 잡힌다.
    제한 시간은 번역과 같은 값(translation.TIMEOUT, 3초 — 사용자가 번역에 정한 값을 같이 쓴다).
    TTS 모듈을 못 불러오면 확인을 건너뛴다(예외로 올리면 필수 인증 창을 영영 못 닫는다 — init_tts_client 와 같은 규칙).
    """
    try:
        from google.cloud import texttospeech
    except Exception as e:
        log_to_console(f"[TTS] TTS 모듈을 불러올 수 없어 키 확인을 건너뜁니다: {e}")
        return
    client = texttospeech.TextToSpeechClient(client_options={"api_key": tts_key})
    client.list_voices(language_code="ko-KR", timeout=translation.TIMEOUT)

def _init_translator(gemini_key):
    """Gemini 키로 번역기를 만든다(2026-09-29 사용자 결정 — TTS 키와 따로인 키).

    키가 없거나 만들지 못해도 예외를 올리지 않는다 — 읽기는 그대로 돼야 한다.
    그때는 MissingTranslator 를 넣어 두어, 번역할 문장이 나오면 그 조각에서 멈추고 이유를 알린다(사용자 결정).
    """
    global gemini_translator
    if not gemini_key:
        gemini_translator = translation.MissingTranslator("Gemini 키가 설정되지 않았습니다 (설정 창 → 인증 설정)")
        log_to_console("[번역] Gemini 키가 없습니다 — 번역할 문장이 나오면 읽기를 멈추고 알립니다")
        return
    try:
        gemini_translator = translation.GeminiTranslator(gemini_key)
        log_to_console(f"[번역] Gemini 번역기 준비 ({translation.MODEL})")
    except Exception as e:
        gemini_translator = translation.MissingTranslator(str(e))
        logging.error(f"번역기 생성 실패: {e}")
        log_to_console(f"[번역] 번역기를 만들지 못했습니다: {e}")

def main():
    """앱 초기화 순서를 한곳에 모은 함수. 순서가 곧 의존 관계라 함부로 바꾸지 말 것.

    1) README 추출 → 2) 로깅 → 3) 숨긴 Tk 루트(모든 창의 부모, 기본 아이콘) → 4) 모듈 로딩(load_modules)
    → 5) 설정 로딩(load_settings) → 6) 인증(TTS 클라이언트, 실패하면 필수 인증 창)
    → 7) 키보드 훅 → 8) 트레이(여기서 gui_queue 확인 루프도 시작) → 9) 빨간 점 창 + 마우스 훅 → 10) root.mainloop()
    - 키보드 훅(7)보다 설정(5)이 먼저여야 저장된 단축키로 훅이 뜬다.
    - 빨간 점(9)은 설정의 selection_button_enabled 를 보므로 설정 뒤. 마우스 훅이 넣는 "점 보이기" 는
      gui_queue 로 오므로 그 확인 루프를 여는 트레이(8) 뒤에 둔다.
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
        # 다크 테마(darkly) — 2026-09-28 사용자 요청 "옵션창, 트레이 컨텍스트메뉴 둘 다 다크모드" (예전엔 밝은 cosmo).
        #   설정 창·인증 창 등 ttkbootstrap 위젯이 모두 따라간다. 하단 바·리더 창은 autostyle 을 꺼 두어(_no_autostyle)
        #   자기 색을 그대로 쓴다. darkly 는 ttkbootstrap 기본 다크 테마 중 하나 [임의 — 다른 다크 테마로 바꿔도 됨].
        # iconphoto=None: ttkbootstrap 은 기본값('')이면 자기 아이콘을 "모든 창의 기본 아이콘"으로 건다
        # (ttkbootstrap window.py Window.__init__ 의 iconphoto(True, ...)). 그러면 iconbitmap 을 따로 안 부르는
        # 인증 창 같은 곳에 ttkbootstrap 아이콘이 뜬다 → 끄고 아래에서 favicon.ico 를 기본 아이콘으로 건다.
        _enable_dark_menus()   # 트레이 오른쪽 메뉴(윈도우 기본 팝업 메뉴)를 어둡게 — 메뉴를 만들기 전에 켠다
        root = ttk.Window(themename="darkly", iconphoto=None)
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
        if _selection_button_import_error is not None:
            logging.warning(f"빨간 점 모듈(selection_button) 로딩 실패 — 단축키로만 읽습니다: {_selection_button_import_error}")
            log_to_console(f"[UI] 빨간 점을 불러오지 못했습니다(단축키로만 읽습니다): {_selection_button_import_error}")
        if _source_highlight_import_error is not None:
            logging.warning(f"원문 위 형광펜 모듈(source_highlight) 로딩 실패 — 리더 창으로만 형광펜을 보입니다: {_source_highlight_import_error}")
            log_to_console(f"[UI] 원문 위 형광펜을 불러오지 못했습니다(리더 창으로만 보입니다): {_source_highlight_import_error}")
        if _follow_dialog_import_error is not None:
            logging.warning(f"따라 읽기 창 모듈(follow_dialog) 로딩 실패 — 고른 글만 읽습니다: {_follow_dialog_import_error}")
            log_to_console(f"[UI] 따라 읽기 창을 불러오지 못했습니다(고른 글만 읽습니다): {_follow_dialog_import_error}")

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

        # 설정에서 키를 이미 로드했으므로, TTS 클라이언트·번역기 만들기 시도 (키 확인 요청은 하지 않는다 — init_tts_client)
        if google_tts_api_key:
            try:
                log_to_console("[TTS] TTS 클라이언트 초기화 시도 중...")
                init_tts_client(google_tts_api_key, gemini_api_key)
            except Exception as e:
                logging.error(f"Google Cloud 인증 오류: {str(e)}")
                log_to_console(f"Google Cloud 인증 오류: {str(e)}")
                show_api_key_dialog(required=True)
        else:
            logging.warning("TTS API 키가 없습니다.")
            log_to_console("TTS API 키가 없습니다. 인증 창을 표시합니다.")
            show_api_key_dialog(required=True)

        # 키보드 리스너 설정
        print("키보드 리스너 설정 중...")
        log_to_console("키보드 리스너 설정 중...")
        setup_keyboard_listener()

        # 시스템 트레이 아이콘 설정
        print("시스템 트레이 아이콘 설정 중...")
        log_to_console("시스템 트레이 아이콘 설정 중...")
        setup_tray_icon()

        # 빨간 점(선택 버튼) 창 + 전역 마우스 훅 — 꺼져 있거나 모듈이 없으면 아무것도 안 띄운다
        print("빨간 점(선택 버튼) 설정 중...")
        log_to_console("빨간 점(선택 버튼) 설정 중...")
        setup_selection_button()

        # 크롬 확장 읽기 사용량 받는 창구(127.0.0.1:51888 TCP, 2026-11-01) — 못 열어도 읽기와 무관
        setup_usage_receiver()
        # 사용량 알약 — 지난번에 켜 둔 채 끝냈으면 다시 띄운다(트레이 왼쪽 클릭으로 켜고 끔)
        setup_usage_pill()

        # 초기화 완료
        logging.info("초기화 완료")
        print("\n프로그램이 시스템 트레이에서 실행 중입니다.")
        log_to_console("===================================")
        log_to_console("프로그램이 실행 중입니다.")
        log_to_console("시스템 트레이에서 아이콘을 확인하세요.")
        log_to_console(f"읽어주기 단축키: {_format_hotkey(tts_hotkey_modifiers, tts_hotkey_key)} (글을 선택하고 누르면 읽기 시작)")
        if selection_button is not None:
            log_to_console("빨간 점: 글을 드래그·더블클릭으로 고르면 선택 끝 옆에 뜹니다. 누르면 읽기 시작")
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
# 단축키 글자 키를 "삼키는 중"인지 — 누름을 삼켰으면 짝이 되는 뗌도 삼킨다(누르고 있는 동안의 자동 반복 포함)
_hotkey_swallowing = False
# 읽기 단축키(Ctrl+Space·Ctrl+화살표)로 삼킨 키의 vk — 짝이 되는 뗌도 삼킨다(2026-10-24 속도 키 → 10-28 읽기 키 다섯 개).
# 삼키는 중이 아니면 None
_read_key_swallowing = None
# 따라 읽기 창(2026-10-28): 떠 있는 창(FollowDialog — Tk 메인만 만진다)과, 훅이 Enter·Esc 를 삼켰을 때 그 vk(뗌도 삼킨다).
# 훅 스레드는 _follow_dialog_open(대입 하나)만 읽는다. _follow_ask_seq = 질의를 보낸 차례(늦게 온 옛 결과를 버린다)
_follow_dialog = None
_follow_dialog_open = False
_follow_key_swallowing = None
_follow_ask_seq = 0
# 키보드로 글을 골랐는지(Ctrl+A, Shift+화살표·Home·End·PgUp·PgDn) — 수정자 키를 모두 뗄 때 빨간 점을 띄운다(2026-09-28 사용자 요청)
_kbd_select_pending = False
# 빨간 점 "선택 확인" 세대 — 확인 결과를 기다리는 사이 hide(누름·키 입력)가 오면 올려서 늦은 결과를 버린다
_dot_query_gen = 0
# 마지막 우클릭 자리 (x, y) — 다음 "show"/"click" 처리 한 번에만 쓰고 지운다(텔레그램 메뉴 "선택" 용, 2026-10-24)
_tg_right_click = None


def _hotkey_vk(key_str):
    """설정된 단축키 글자("X", "d", "f9") → 윈도우 가상 키 코드. 모르는 모양이면 None(그 키는 삼키지 않는다 — 예전처럼)."""
    if not key_str:
        return None
    k = str(key_str).strip()
    if len(k) == 1:
        c = k.upper()
        if "A" <= c <= "Z" or "0" <= c <= "9":
            return ord(c)                     # VK_A~VK_Z = 'A'~'Z', VK_0~VK_9 = '0'~'9'
        return None
    if k[:1] in ("f", "F") and k[1:].isdigit() and 1 <= int(k[1:]) <= 24:
        return 0x6F + int(k[1:])              # VK_F1 = 0x70
    return None


def setup_keyboard_listener():
    """전역 키보드 훅(pynput Listener)을 띄워 읽기 단축키를 감시한다. 반환: 성공 True / 실패 False.

    동작 요약
      - on_press  : 수정자 키 상태를 기록하고, "설정된 수정자 + 설정된 글자" 가 맞으면 read_selected_text 를
                    Tk 메인으로 넘긴다(root.after). 읽기/중지/아무것도 안 함 3방향 분기는 read_selected_text 가 한다.
                    키를 누를 때마다 빨간 점도 숨긴다(_selection_key_hook — 판정·gui_queue.put 만 하는 가벼운 함수).
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
        global ctrl_pressed, shift_pressed, alt_pressed, _kbd_select_pending

        try:
            # 키를 누르면 빨간 점을 숨긴다(SelectionGestureDetector.on_other_input — 키 입력 = 숨김).
            # 이 함수는 판정과 gui_queue.put 만 한다(가벼움). 마우스 훅을 안 띄웠으면 None 이다.
            key_hook = _selection_key_hook
            if key_hook is not None:
                key_hook()
        except Exception:
            pass  # 빨간 점 숨김이 실패해도 아래 단축키 판정은 해야 한다

        try:
            # 키 상태 업데이트 (I/O 없이 빠르게 처리)
            if key == Key.ctrl_l or key == Key.ctrl_r:
                ctrl_pressed = True
            elif key == Key.shift_l or key == Key.shift_r:
                shift_pressed = True
            elif key == Key.alt_l or key == Key.alt_r:
                alt_pressed = True

            # 키보드로 고르는 동작인지 기억한다 — 띄우는 건 수정자를 다 뗄 때(on_release). 확장도 keyup 에서 선택을 확인한다
            # (selection-button.js:27). 여기서는 변수 하나만 바꾼다(훅 콜백 규칙).
            if ctrl_pressed and not alt_pressed and isinstance(key, KeyCode) and getattr(key, "vk", None) == 0x41:
                _kbd_select_pending = True                 # Ctrl+A
            elif shift_pressed and key in _select_nav_keys:
                _kbd_select_pending = True                 # Shift+화살표·Home·End·PgUp·PgDn

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
                # read_selected_text 가 선택 있음=읽기 / 선택 없음+재생 중=중지 / 선택 없음+대기=아무것도 안 함 으로 가른다.
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
        global ctrl_pressed, shift_pressed, alt_pressed, _kbd_select_pending

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

            # 키보드로 골랐고 이제 수정자를 다 뗐다 = 고르기가 끝났다 → 빨간 점 요청(자리는 Tk 메인이 정한다).
            # 큐에 넣기만 한다(훅 콜백 규칙 — UIA·Win32 조회는 Tk 메인과 형광펜 UIA 스레드에서).
            if _kbd_select_pending and not (ctrl_pressed or shift_pressed or alt_pressed):
                _kbd_select_pending = False
                gui_queue.put(("selection_button", "keyboard"))

        except Exception:
            pass  # 훅 콜백에서 예외 로깅도 타임아웃 유발 가능

        return True

    # Shift 와 함께 누르면 글을 고르는 이동 키들(on_press 가 _kbd_select_pending 판정에 쓴다)
    _select_nav_keys = {Key.left, Key.right, Key.up, Key.down, Key.home, Key.end, Key.page_up, Key.page_down}

    WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
    LLKHF_INJECTED = 0x10
    # 읽기 단축키 — Paseo 상태바 플러그인 기준(shared/shortcuts.ts, 2026-10-28 리규형님 지시). Ctrl 만 눌렀을 때
    READ_KEYS = {0x20: "toggle", 0x25: "rewind", 0x27: "forward", 0x28: "slower", 0x26: "faster"}  # Space ← → ↓ ↑
    # 따라 읽기 창이 떠 있는 동안만 삼키는 키(2026-10-28) — Enter = 따라 읽기, Esc = 아무것도 안 읽고 닫기
    FOLLOW_KEYS = {0x0D: "enter", 0x1B: "esc"}

    def win32_filter(msg, data):
        """(훅 스레드) 단축키 글자 키를 다른 앱에 넘기지 않고 삼킨다 — 2026-09-28 메모장 사고 수정.

        왜: 예전에는 단축키를 알아보기만 하고 키는 그대로 흘려보냈다. 그래서 메모장·워드처럼 글을 고칠 수 있는 곳에서
            Shift+X 를 누르면 대문자 X 가 입력돼 **선택한 글이 X 로 바뀌었다**(사용자 보고 "해당 글자가 지워져, X만 남아").
            그 뒤 Ctrl+C 로 가져올 글도 없어서 읽기도 안 됐다. VS Code 채팅창은 읽기 전용이라 드러나지 않았다.
        어떻게: 단축키 글자 키(vk)가 눌렸고 수정자 조건(on_press 와 같은 규칙)이 맞으면
            - 첫 누름: 읽기를 Tk 메인으로 넘기고(on_press 와 같은 root.after) 그 누름을 삼킨다
            - 누르고 있는 동안의 자동 반복 누름·짝이 되는 뗌: 삼키기만 한다(다시 읽지 않는다)
            삼킨 이벤트는 on_press 로도 오지 않는다 → on_press 의 단축키 판정은 이 필터가 실패했을 때의 대비로 남는다.
            수정자 키(Shift·Ctrl·Alt)는 삼키지 않는다 — 다른 앱에는 수정자만 눌렀다 떼진 것으로 보여 아무 글자도 안 들어간다.
        ⚠️ 앱이 흉내 낸 입력(LLKHF_INJECTED — read_selected_text 의 Ctrl+C)은 건드리지 않는다.
        ⚠️ suppress_event() 는 예외를 던져 pynput 에 "이 이벤트 막음" 을 알리는 방식이라 try 밖에서 불러야 한다.
        ⚠️ 훅 콜백이라 가볍게: 변수 확인·root.after 한 번뿐. 로그·파일 I/O 금지(윈도우가 느린 훅을 떼어 낸다).
        읽기 단축키(2026-10-28 Paseo 상태바 플러그인 기준 — 10-24 의 "Ctrl+←/→ = 속도" 를 바꿈, _read_key_action):
            Ctrl+Space 멈춤·다시 시작 · Ctrl+← 이전 문단 · Ctrl+→ 다음 문단 · Ctrl+↓ 한 단계 느리게 · Ctrl+↑ 한 단계 빠르게.
            읽기가 있을 때만(tts_session) 가로챈다. 멈춘 동안(tts_paused)은 Ctrl+Space 만 받고 화살표는 원래대로 넘긴다
            (기준 web.ts listenTtsSpeedKeys — 입력창의 Ctrl+←/→ 단어 이동이 그대로 되게). 읽기가 없으면 다섯 키 모두 넘긴다
            — Ctrl+Space 로 새 읽기를 시작하지는 않는다. Ctrl 만 눌렸을 때만 — Ctrl+Shift+←/→(단어 선택)·AltGr 는 넘긴다.
            그 누름은 삼켜서 앞 창에 가지 않게 하고(커서 이동·자동완성 등), 짝이 되는 뗌도 삼킨다.
        따라 읽기 창(2026-10-28): 창이 떠 있는 동안(_follow_dialog_open) Enter(따라 읽기)·Esc(닫기)를 수정자 없이 누르면
            삼켜서 창에 넘긴다(_follow_dialog_key). 창은 포커스를 안 받아 키가 앞 창으로 가기 때문 — 안 삼키면 메모장에서
            Enter 가 고른 글을 줄바꿈으로 바꾼다. 누르고 있는 동안의 자동 반복·짝이 되는 뗌도 삼킨다(창이 닫힌 뒤라도).
        """
        global _hotkey_swallowing, _read_key_swallowing, _follow_key_swallowing
        suppress = False
        try:
            vk = _hotkey_vk(tts_hotkey_key)
            if vk is not None and data.vkCode == vk and not (data.flags & LLKHF_INJECTED):
                if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if _hotkey_swallowing:
                        suppress = True                       # 누르고 있는 동안 자동 반복 — 삼키기만
                    elif ((not tts_hotkey_modifiers.get("ctrl", False) or ctrl_pressed) and
                          (not tts_hotkey_modifiers.get("shift", False) or shift_pressed) and
                          (not tts_hotkey_modifiers.get("alt", False) or alt_pressed)):
                        _hotkey_swallowing = True
                        suppress = True
                        try:
                            key_hook = _selection_key_hook    # on_press 가 하던 "키 누르면 빨간 점 숨김"
                            if key_hook is not None:
                                key_hook()
                        except Exception:
                            pass
                        if root:
                            root.after(10, read_selected_text)
                elif msg in (WM_KEYUP, WM_SYSKEYUP) and _hotkey_swallowing:
                    _hotkey_swallowing = False
                    suppress = True
            elif (data.vkCode in FOLLOW_KEYS and not (data.flags & LLKHF_INJECTED)
                  and (_follow_dialog_open or _follow_key_swallowing == data.vkCode)):
                if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if _follow_key_swallowing == data.vkCode:
                        suppress = True                       # 누르고 있는 동안 자동 반복 — 삼키기만
                    elif not (ctrl_pressed or shift_pressed or alt_pressed):
                        _follow_key_swallowing = data.vkCode
                        suppress = True
                        if root:
                            root.after(0, lambda k=FOLLOW_KEYS[data.vkCode]: _follow_dialog_key(k))
                elif msg in (WM_KEYUP, WM_SYSKEYUP) and _follow_key_swallowing == data.vkCode:
                    _follow_key_swallowing = None
                    suppress = True
            elif data.vkCode in READ_KEYS and not (data.flags & LLKHF_INJECTED):
                if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    action = READ_KEYS[data.vkCode]
                    if (ctrl_pressed and not shift_pressed and not alt_pressed and tts_session is not None
                            and (action == "toggle" or not tts_paused)):
                        _read_key_swallowing = data.vkCode
                        suppress = True
                        if root:
                            # 누르고 있으면 자동 반복마다 한 번(기준 keydown 처리와 같음)
                            root.after(0, lambda a=action: _read_key_action(a))
                elif msg in (WM_KEYUP, WM_SYSKEYUP) and _read_key_swallowing == data.vkCode:
                    _read_key_swallowing = None
                    suppress = True
        except Exception:
            suppress = False                                  # 판정이 깨지면 예전처럼 흘려보낸다(on_press 가 처리)
        if suppress and keyboard_listener is not None:
            keyboard_listener.suppress_event()
        return True

    # 리스너 시작
    try:
        global keyboard_listener
        if 'keyboard_listener' in globals() and keyboard_listener is not None:
            try:
                keyboard_listener.stop()
            except:
                pass

        keyboard_listener = Listener(on_press=on_press, on_release=on_release, win32_event_filter=win32_filter)
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
                        keyboard_listener = Listener(on_press=on_press, on_release=on_release, win32_event_filter=win32_filter)
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
    키 목록: language, google_tts_api_key, gemini_api_key, tts_hotkey{modifiers,key}, tts_settings{voice_name,speaking_rate,rate_step},
            reader_window_enabled, reader_window_geometry, bottom_bar_monitor, selection_button_enabled,
            disable_in_browsers, source_highlight_enabled, translate_enabled, translation_overlay_enabled
    """
    try:
        # ※ 설정 파일 전체를 이 dict로 덮어쓴다. 옛 STT 키(stt_enabled, hotkey, auto_detection,
        #   google_settings, whisper_settings)는 로드 시 무시되고, 첫 저장 때 파일에서 빠진다.
        #   옛 플로팅 아이콘 키(controller_position, controller_hidden)도 같다(2026-09-28 플로팅 아이콘 제거).
        #   옛 인증 파일 경로 키(google_credentials_path)도 같다(2026-09-29 API 키 방식으로 바꿈).
        #   볼륨(tts_settings.volume)도 같다(2026-10-24 볼륨 막대 제거 — 늘 1.0).
        # ⚠️ API 키가 평문으로 들어간다 — 이 파일은 .gitignore 에 있다(공개 저장소). 설치 파일에도 넣지 않는다.
        settings = {
            "language": current_language,
            "google_tts_api_key": google_tts_api_key,
            "gemini_api_key": gemini_api_key,
            "tts_hotkey": {
                "modifiers": tts_hotkey_modifiers,
                "key": tts_hotkey_key
            },
            "tts_settings": {
                "voice_name": tts_voice_name,
                "speaking_rate": tts_speaking_rate,
                # 속도 목록 간격 (2026-10-24 추가, 설정 창 "속도 간격")
                "rate_step": tts_rate_step
            },
            # 하단 바·리더 창 (2026-09-28 추가)
            "reader_window_enabled": reader_window_enabled,
            "reader_window_geometry": reader_window_geometry,
            "bottom_bar_monitor": bottom_bar_monitor,
            # 빨간 점(선택 버튼) 켬/끔 (2026-09-28 추가, 확장 옵션 selectionButton 과 같은 뜻)
            "selection_button_enabled": selection_button_enabled,
            # 브라우저(Aside·웨일·크롬)에서 빨간 점·단축키 쉬기 (2026-09-28 추가, 트레이 체크)
            "disable_in_browsers": disable_in_browsers,
            # 원문 위 형광펜 전체 켬/끔 (2026-09-28 추가). 트레이·설정 창에는 없다 — 이 파일을 직접 고쳐서만 끈다
            "source_highlight_enabled": source_highlight_enabled,
            # 주 언어가 아닌 문장 번역 켬/끔 (2026-09-29 추가, 설정 창 "일반" 체크)
            "translate_enabled": translate_enabled,
            # 번역문을 원문 위 막으로 표시 켬/끔 (2026-09-29 추가, 설정 창 "일반" 체크)
            "translation_overlay_enabled": translation_overlay_enabled,
            # 사용량 알약 켬/끔·끌어 옮긴 자리 (2026-11-01 추가, 트레이 왼쪽 클릭)
            "usage_pill_visible": usage_pill_visible,
            "usage_pill_position": usage_pill_position
        }
        print(f"저장할 설정: {_mask_keys(settings)}")
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
    - 새 키(reader_window_*, bottom_bar_monitor, selection_button_enabled,
      disable_in_browsers, source_highlight_enabled, translate_enabled, translation_overlay_enabled)는 값 모양이 이상하면 무시한다
      (true/false 가 아니면 기본값 유지).
    - 옛 플로팅 아이콘 키(controller_position, controller_hidden)는 남아 있어도 읽지 않는다(플로팅 아이콘 제거).
    - 옛 인증 파일 경로(google_credentials_path)도 읽지 않는다(2026-09-29 API 키 방식). 키가 없으면 main 이 필수 인증 창을 띄운다.
      앱 폴더의 google_credentials.json 을 찾아 쓰던 폴백도 없앴다. .env 도 읽지 않는다(사용자 결정: 인증 창에 입력).
    - 볼륨(tts_settings.volume)은 읽지 않는다 — 늘 1.0(2026-10-24 사용자 결정). 다음 저장 때 파일에서 빠진다.
    - 속도는 간격(rate_step, 없거나 이상하면 0.1) 목록의 가장 가까운 값으로 맞춰 읽는다(2026-10-24 사용자 결정 —
      예전 막대로 고른 0.33배·1.37배 같은 값도 목록 값이 된다).
    """
    global current_language, google_tts_api_key, gemini_api_key
    global tts_hotkey_modifiers, tts_hotkey_key, tts_voice_name, tts_speaking_rate, tts_rate_step
    global reader_window_enabled, reader_window_geometry, bottom_bar_monitor, selection_button_enabled
    global disable_in_browsers, source_highlight_enabled, translate_enabled, translation_overlay_enabled
    global usage_pill_visible, usage_pill_position
    try:
        if os.path.exists('whisperer_settings.json'):
            with open('whisperer_settings.json', 'r', encoding='utf-8') as f:
                settings = json.load(f)
                print(f"로드된 설정: {_mask_keys(settings)}")
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
                    tts_rate_step = tts_engine.normalize_rate_step(
                        settings["tts_settings"].get("rate_step", tts_engine.DEFAULT_RATE_STEP))
                    if "speaking_rate" in settings["tts_settings"]:
                        tts_speaking_rate = tts_engine.snap_rate(settings["tts_settings"]["speaking_rate"], tts_rate_step)

                # 하단 바·리더 창 설정 (없으면 기본값 유지). 값이 이상하면 무시한다
                if isinstance(settings.get("reader_window_enabled"), bool):
                    reader_window_enabled = settings["reader_window_enabled"]
                if "reader_window_geometry" in settings:
                    geom = settings["reader_window_geometry"]
                    reader_window_geometry = geom if isinstance(geom, str) and geom else None
                if settings.get("bottom_bar_monitor") in ("foreground", "primary"):
                    bottom_bar_monitor = settings["bottom_bar_monitor"]
                # 빨간 점 켬/끔 — true/false 가 아니면 무시(기본 켬 유지)
                if isinstance(settings.get("selection_button_enabled"), bool):
                    selection_button_enabled = settings["selection_button_enabled"]
                # 브라우저에서 비활성화·원문 위 형광펜 켬/끔 — true/false 가 아니면 무시(둘 다 기본 켬 유지)
                if isinstance(settings.get("disable_in_browsers"), bool):
                    disable_in_browsers = settings["disable_in_browsers"]
                if isinstance(settings.get("source_highlight_enabled"), bool):
                    source_highlight_enabled = settings["source_highlight_enabled"]
                # 번역 켬/끔 — true/false 가 아니면 무시(기본 켬 유지)
                if isinstance(settings.get("translate_enabled"), bool):
                    translate_enabled = settings["translate_enabled"]
                if isinstance(settings.get("translation_overlay_enabled"), bool):
                    translation_overlay_enabled = settings["translation_overlay_enabled"]
                # 사용량 알약 — 켬/끔은 true/false 만, 자리는 정수 두 개만(아니면 오른쪽 아래)
                if isinstance(settings.get("usage_pill_visible"), bool):
                    usage_pill_visible = settings["usage_pill_visible"]
                pos = settings.get("usage_pill_position")
                if (isinstance(pos, list) and len(pos) == 2
                        and all(isinstance(v, int) and not isinstance(v, bool) for v in pos)):
                    usage_pill_position = pos

                # API 키 두 개 (2026-09-29). 글자가 아니거나 비었으면 없는 것으로 둔다
                tts_key = settings.get("google_tts_api_key")
                google_tts_api_key = tts_key.strip() if isinstance(tts_key, str) and tts_key.strip() else None
                gem_key = settings.get("gemini_api_key")
                gemini_api_key = gem_key.strip() if isinstance(gem_key, str) and gem_key.strip() else None

            logging.info(f"설정 로드 완료: 언어={current_language}, 읽어주기 단축키 수정자={tts_hotkey_modifiers}, 단축키={tts_hotkey_key}")
            print(f"설정 로드 완료: 언어={current_language}, 읽어주기 단축키 수정자={tts_hotkey_modifiers}, 단축키={tts_hotkey_key}")
        # 설정 파일이 없는 경우는 무시하고 기본값 사용
    except Exception as e:
        logging.error(f"설정 로드 오류: {str(e)}")
        print(f"설정 로드 오류: {str(e)}")

_SECRET_SETTING_KEYS = ("google_tts_api_key", "gemini_api_key")

def _mask_keys(settings):
    """설정 dict 를 콘솔·로그에 찍기 전에 API 키를 가린다(앞 4글자 + 길이만). 원본은 건드리지 않는다."""
    if not isinstance(settings, dict):
        return settings
    shown = dict(settings)
    for k in _SECRET_SETTING_KEYS:
        v = shown.get(k)
        if isinstance(v, str) and v:
            shown[k] = f"{v[:4]}…({len(v)}자)"
    return shown

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

    메뉴 (2026-09-28 사용자 확정 — 이 다섯 개만): "TTS 설정…", "리더 창 사용"(체크), "브라우저에서 비활성화"(체크),
      "텍스트 선택 시 읽기 버튼"(체크), "종료". 언어·인증 설정·콘솔 창 열기는 설정 창(show_tts_settings_dialog)으로 옮겼고,
      README 열기·TTS 재생/중지 항목은 없앴다(읽기 중지는 하단 바 ■ 나 선택 없이 단축키).
    ⚠️ 스레드 규칙: 트레이 메뉴 콜백(아래 안쪽 함수들)은 pystray 스레드에서 불린다.
       설정 창 열기·체크 항목 켬/끔은 직접 하지 말고 gui_queue 에 문자열을 넣어 Tk 메인(check_gui_queue)에 넘긴다
       (Tk 창을 만지거나 save_settings 를 부르는 일 — 07-27 로그 §4-5). 종료만 그 자리에서 한다.
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

        # (옛 트레이 항목 README 열기·인증 설정·콘솔 열기·언어 변경·TTS 재생/중지 는 2026-09-28 사용자 결정으로 뺐다.
        #  인증 설정·콘솔 열기·언어는 설정 창(show_tts_settings_dialog)에 있다 — open_console_window·_apply_language.
        #  README 열기는 없앴다.)

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
            원문 위 형광펜의 UIA 스레드·막 창도 프로세스와 함께 사라진다(destroy 를 따로 부르지 않는다 — 트레이 스레드라
            Tk 메인 전용인 막 창을 만질 수 없다).
            """
            try:
                tray_icon.stop()
                root.quit()
                sys.exit(0)
            except:
                os._exit(0)

        def update_tray_menu():
            """트레이 메뉴를 지금 상태(언어·체크 항목 3개)에 맞게 새로 만들어 끼운다.

            pystray 메뉴는 문구가 고정이고, 윈도우판은 checked/enabled 도 메뉴를 "만들 때" 한 번만 읽는다
            (pystray _win32.py _update_menu) → 상태가 바뀔 때마다 이 함수로 통째로 다시 만든다.
            어느 스레드에서 불러도 된다(pystray 메뉴 교체는 Tk 와 무관). 부르는 곳: 읽기 시작/끝, 설정 창의 언어 변경
            (_apply_language), toggle_reader_window, toggle_selection_button, toggle_disable_in_browsers.
            체크 항목 세 개는 전부 gui_queue 로 Tk 메인에 넘긴다 — 켬/끔 함수가 창(리더 창·빨간 점)을 만지고
            save_settings 를 부르기 때문(한 스레드에서만 저장하게).
            항목 순서는 사용자가 정한 목록 순서 그대로다(2026-09-28). 구분선 위치는 임의(설정 / 체크 3개 / 종료).
            """
            global tray_icon

            if not tray_icon: return

            base_items = [
                # 왼쪽 클릭 = 사용량 알약 켜고 끄기(2026-11-01). pystray 는 왼쪽 클릭에 "기본 항목"을 부른다
                # (_win32 _on_notify WM_LBUTTONUP → Menu.__call__ → default). visible=False 라 오른쪽 메뉴에는 안 나온다 —
                # 메뉴는 사용자가 정한 다섯 항목 그대로(2026-11-01 실측: 숨긴 기본 항목도 불린다)
                pystray.MenuItem("usage pill", lambda icon, item: gui_queue.put("toggle_usage_pill"),
                                 default=True, visible=False),
                pystray.MenuItem(get_msg("menu_tts_settings"), open_tts_settings),
                pystray.Menu.SEPARATOR,
                # 리더 창 사용 체크 — 켜 두면 "원문 위에 칠할 수 없을 때" 리더 창(원문 + 읽는 줄 형광펜)을 띄운다.
                # 체크 표시는 pystray 가 메뉴를 그릴 때 checked 함수를 불러 정한다(전역값을 그대로 읽음)
                pystray.MenuItem(get_msg("menu_reader_window"),
                                 lambda icon, item: gui_queue.put("toggle_reader_window"),
                                 checked=lambda item: reader_window_enabled),
                # 브라우저에서 비활성화 체크 — 켜면 Aside·웨일·크롬에서 빨간 점·단축키가 쉰다(확장이 읽는다)
                pystray.MenuItem(get_msg("menu_disable_in_browsers"),
                                 lambda icon, item: gui_queue.put("toggle_disable_in_browsers"),
                                 checked=lambda item: disable_in_browsers),
                # 빨간 점(선택 버튼) 켬/끔 체크 — 점 창(tkinter)을 숨기거나 만들어야 하므로 큐로 메인 스레드에 넘긴다.
                # 문구는 확장 옵션 "텍스트 선택 시 읽기 버튼"(_locales/ko/messages.json options_selection_button) 그대로.
                # 빨간 점 모듈을 못 불러왔거나 창을 못 만들었으면(SelectionButton=None) 흐리게 둔다(눌러도 뜰 점이 없다).
                pystray.MenuItem(get_msg("menu_selection_button"),
                                 lambda icon, item: gui_queue.put("toggle_selection_button"),
                                 checked=lambda item: selection_button_enabled,
                                 enabled=lambda item: SelectionButton is not None),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(get_msg("exit"), exit_program)
            ]

            tray_icon.menu = pystray.Menu(*base_items)

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
                        elif msg == "toggle_reader_window":
                            toggle_reader_window()
                        elif msg == "toggle_selection_button":
                            toggle_selection_button()
                        elif msg == "toggle_disable_in_browsers":
                            toggle_disable_in_browsers()
                        elif msg == "toggle_usage_pill":
                            toggle_usage_pill()
                        elif msg == "usage_changed":
                            _schedule_usage_refresh()
                        elif isinstance(msg, tuple) and msg and msg[0] == "selection_button":
                            # 마우스·키보드 훅이 넣은 빨간 점 명령 ("show", x, y) / ("hide",)
                            _handle_selection_button_msg(*msg[1:])
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

# ── 빨간 점(선택 버튼) 연결 — 확장 js/selection-button.js 의 윈도우판 ───────────────────────────
# 흐름: 전역 마우스 훅(pynput 스레드)이 "드래그로 골랐다 / 더블클릭으로 골랐다" 를 추정
#       → gui_queue ("selection_button", "show", x, y) → Tk 메인이 SelectionButton.show_at(x, y)
#       → 사용자가 점을 누름 → _on_selection_button_click → read_selected_text(Ctrl+C 로 선택한 글 가져오기)
# 왜 "추정" 인가: 윈도우는 다른 프로그램의 "글이 선택됨" 신호를 주지 않는다. UI Automation 으로 물어보는 방법은
#   VS Code 를 얼린 전례가 있어 쓰지 않는다(2026-09-28 사용자 결정). 그래서 마우스 동작(드래그·더블클릭)만 본다.
#   (원문 위 형광펜은 읽기를 시작할 때 한 번 UIA 로 선택 범위를 잡는다 — source_highlight.py 전용 스레드, 좁은 범위 호출만.
#    빨간 점을 띄울지 판단하는 데에는 여전히 UIA 를 쓰지 않는다)
#   브라우저(Aside·웨일·크롬)가 전경이면 점을 띄우지 않는다(트레이 "브라우저에서 비활성화" — _handle_selection_button_msg).
#   → 알려진 한계: 창 제목 막대를 끌어 옮겨도 점이 뜬다. 누르면 단축키와 똑같이 그 창에 Ctrl+C 를 보낸다 —
#     그 창에 전에 골라 둔 글이 남아 있으면 그 글을 읽고, 없으면 아무 일도 없다.
#     (터미널 창은 선택 없이 받은 Ctrl+C 를 "실행 중인 명령 중단" 으로 받는다 — 단축키도 같은 위험이 있다)
#     키보드(Shift+화살표)나 Shift+클릭으로 고른 글에는 점이 안 뜬다(단축키는 된다).
#     입력칸·편집기에서 고를 때도 뜬다(확장은 편집 중엔 안 띄우지만 — selection-button.js:94-102 — 여기선 알 방법이 없다).
# (옛 플로팅 아이콘 setup_floating_controller·set_controller_visible·update_state 는 2026-09-28 에 지웠다.
#  그 창의 Win32 처리(NOACTIVATE·TOOLWINDOW·SetWindowRgn 원형)는 selection_button.py 가 이어받았다)

_mouse_listener_lock = threading.Lock()   # 마우스 훅 켜기/끄기(Tk 메인)와 watchdog(별도 스레드)이 겹치지 않게


def _make_selection_hook(detector, contains, is_own_window, post, is_enabled, clock=time.monotonic, on_wheel=None):
    """전역 마우스·키보드 훅이 부를 빨간 점 판정 함수 3개를 만든다. 반환: (on_click, on_scroll, on_key).

    ⚠️ 셋 다 pynput 훅 스레드에서 불린다(on_click·on_scroll 은 마우스 훅 스레드, on_key 는 키보드 훅 스레드).
       윈도우는 훅이 늦게 돌아오면(LowLevelHooksTimeout) 훅을 조용히 떼어 낸다 → 여기서는
       판정(detector)·변수 바꾸기·post(= gui_queue.put) 만 한다. Tk 호출·파일 I/O·log_to_console 금지.
       예외도 밖으로 내지 않는다(콜백에서 예외가 나면 pynput 리스너가 멈춘다).
    인자 — 테스트에서 가짜로 바꿔 넣을 수 있게 전부 밖에서 받는다:
      detector            : selection_button.SelectionGestureDetector (on_press / on_release / on_other_input)
      contains(x, y)      : 그 화면 좌표가 지금 떠 있는 빨간 점 위인가 (SelectionButton.contains — 스레드 안전)
      is_own_window(x, y) : 그 좌표 아래 창이 우리 앱 창(하단 바·리더 창·설정 창·트레이 메뉴 등)인가
      post(msg)           : gui_queue.put
      is_enabled()        : 빨간 점이 켜져 있는가 (트레이 체크, 전역 selection_button_enabled)
      clock()             : 초 단위 시계 (더블클릭 시간 판정용)
      on_wheel()          : (선택) 휠을 굴릴 때마다 부른다 — 원문 위 형광펜에 "스크롤됐다" 알리기(_notify_source_scroll).
                            빨간 점 켬/끔과 상관없이 부른다. ⚠️ 플래그만 세우는 가벼운 함수여야 한다(훅 콜백 안이라서).
    걸러 내는 것
      - 점을 누른 것: 누른 좌표가 점 위면 그 누름·뗌을 detector 에 넘기지 않는다. 넘기면 누름이 "숨김" 을 내서
        점이 클릭을 받기도 전에 사라진다. 점 클릭 자체는 SelectionButton 이 on_click 으로 알려 준다.
      - 우리 앱 창 위에서 시작한 동작: 리더 창 머리 막대 끌기·하단 바 버튼·설정 창 글 고르기 등은 "다른 앱의 글 선택"
        이 아니다 → 누를 때 판별해 두고 그 뗌의 "보이기"·"클릭" 은 버린다. 누름의 "숨기기" 는 그대로 한다(다른 곳을 누르면 점은 사라진다).
    넘기는 것: 끌기·더블클릭의 뗌 → ("selection_button", "show", x, y), 한 번 클릭의 뗌 → ("selection_button", "click", x, y)
      (텔레그램 메시지 "선택" 용 — Tk 메인이 텔레그램이 앞 창일 때만 쓰고 나머지는 버린다, 2026-10-23),
      우클릭 누름 → ("selection_button", "rpress", x, y) (텔레그램 메뉴 "선택" 뒤 우클릭한 메시지를 보려고, 2026-10-24).
    "숨김" 중복 줄이기: 키를 칠 때마다·휠을 굴릴 때마다 "숨김" 을 넣으면 큐만 붐빈다 → 마지막으로 "보이기" 를 넣은 뒤
      아직 "숨김" 을 안 넣었을 때만 넣는다(shown_hint). Tk 메인이 따로 숨긴 경우(점 클릭·읽기 시작)엔 hint 가 남아
      다음 입력 때 "숨김" 이 한 번 더 갈 뿐이다(이미 숨은 점을 또 숨김 — 해 없음).
    """
    lock = threading.Lock()   # 마우스 훅 스레드와 키보드 훅 스레드가 detector·state 를 같이 쓰므로 한 번에 하나씩
    state = {"skip_release": False, "own_window": False, "shown_hint": False}

    def _hide_locked():
        # lock 을 쥔 채로 부른다. 보였을 수 있을 때만 "숨김" 을 넣는다
        if state["shown_hint"]:
            state["shown_hint"] = False
            post(("selection_button", "hide"))

    def on_click(x, y, button, pressed, *_rest):
        # pynput 1.8 은 끝에 injected(가짜 입력 여부)를 하나 더 준다 → *_rest 로 받고 쓰지 않는다
        # (원격 제어 프로그램의 입력도 가짜 입력으로 오므로 거르지 않는다)
        try:
            if not is_enabled():
                return
            now = clock()
            is_left = getattr(button, "name", None) == "left"   # pynput.mouse.Button.left — import 없이 이름으로 비교
            with lock:
                if not is_left:
                    # 오른쪽·가운데·옆 버튼: 누를 때 숨긴다(detector 약속: 다른 버튼 → 숨김)
                    if pressed:
                        detector.on_other_input()
                        _hide_locked()
                        if getattr(button, "name", None) == "right":
                            # 우클릭 자리 — 텔레그램 메뉴 "선택" 뒤 그 자리 메시지를 보려고(2026-10-24). 넘기기만 한다
                            post(("selection_button", "rpress", x, y))
                    return
                if pressed:
                    if contains(x, y):
                        state["skip_release"] = True   # 점을 누른 것 — 이어지는 뗌도 건너뛴다(뗄 때 점 밖으로 밀려도)
                        return
                    state["skip_release"] = False
                    state["own_window"] = bool(is_own_window(x, y))
                    # detector 는 "점이 떠 있으면 ('hide',)" 를 준다. 떠 있을 수 있는지는 shown_hint 가 더 정확히 안다
                    # (detector 의 보이기가 own_window 로 버려진 경우 detector 는 떠 있다고 믿는다) → 숨김 판단은 hint 로
                    detector.on_press(x, y, now)
                    _hide_locked()
                else:
                    if state["skip_release"]:
                        state["skip_release"] = False
                        return
                    result = detector.on_release(x, y, now)
                    if state["own_window"]:
                        return
                    if result and result[0] == "show":
                        state["shown_hint"] = True
                        post(("selection_button", "show", result[1], result[2]))
                    elif result is None:
                        # 한 번 클릭의 뗌 — 텔레그램 "선택"(우클릭 메뉴)·선택 상태에서 메시지 더 고르기가 한 번 클릭이다
                        # (2026-10-23). 어느 앱인지는 여기서 못 본다(프로세스 조회 금지) → 넘기기만 하고 Tk 메인이 텔레그램일
                        # 때만 쓴다. 점이 뜰 수 있으니 hint 를 세워 다음 입력 때 "숨김" 이 가게 한다.
                        state["shown_hint"] = True
                        post(("selection_button", "click", x, y))
        except Exception:
            pass   # 훅 콜백 — 로그도 남기지 않는다(파일 I/O 가 훅 시간 제한을 넘길 수 있다)

    def _other_input():
        # 휠·키 입력 → 숨김 (detector 약속: on_other_input 은 늘 ('hide',))
        try:
            if not is_enabled():
                return
            with lock:
                detector.on_other_input()
                _hide_locked()
        except Exception:
            pass

    def on_scroll(x, y, dx, dy, *_rest):
        # 원문 위 형광펜: 휠 뒤에는 칠한 줄이 화면에서 움직였으니 다시 조회하라고 알린다(플래그만 — SourceHighlighter 약속).
        # 빨간 점이 꺼져 있어도 알린다(점 켬/끔과 무관한 일). 예외는 삼킨다(훅 콜백).
        if on_wheel is not None:
            try:
                on_wheel()
            except Exception:
                pass
        # 확장은 스크롤하면 점을 선택 끝으로 따라 옮기지만(selection-button.js:29·117) 여기선 선택 위치를 모른다 → 숨긴다
        _other_input()

    def on_key():
        # 키보드 훅(setup_keyboard_listener 의 on_press)이 키 누름마다 부른다
        _other_input()

    return on_click, on_scroll, on_key


def _make_own_window_checker():
    """마우스 훅이 쓸 "이 화면 좌표 아래 창이 우리 앱 창인가" 판별 함수 is_own(x, y) 를 만든다.
    Win32 준비가 실패하면 늘 False 를 주는 함수를 돌려준다(그러면 우리 창 위 드래그에도 점이 뜰 뿐 앱은 돈다).

    방법: 좌표 아래 창(WindowFromPhysicalPoint, 없으면 WindowFromPoint) → 맨 바깥 창(GetAncestor GA_ROOT)
          → 그 창을 만든 프로세스 번호(GetWindowThreadProcessId) == 우리(os.getpid()) ?
    - 좌표는 저수준 마우스 훅이 준 값(MSLLHOOKSTRUCT.pt, "per-monitor aware" 실제 픽셀)이라 Physical 판을 먼저 쓴다.
      다만 윈도우 8.1 부터는 WindowFromPhysicalPoint 가 WindowFromPoint 와 똑같이 동작한다고 문서에 적혀 있다
      (기억에 근거 — 확신 중). 즉 좌표는 "우리 프로세스의 DPI 기준" 으로 해석된다. 앱은 시스템 DPI 인식이라
      모든 모니터 배율이 같으면(2026-09-28 이 PC: 두 모니터 모두 140%) 훅 좌표와 같다. 배율이 다른 모니터를 섞으면
      어긋날 수 있다(실측 못 함).
    - 세 호출 모두 다른 프로그램을 기다리지 않는 가벼운 호출이라 훅 콜백에서 불러도 된다고 판단했다.
      (WindowFromPoint 계열이 WM_NCHITTEST 를 보내는 건 부른 스레드 자신의 창뿐이라고 알려져 있다 — 훅 스레드는 창이 없다.
       근거는 기억 + ReactOS 구현(같은 스레드 창에만 보냄) — 확신 중상)
    - ctypes.windll.user32 에 argtypes 를 걸면 앱 전체에 영향이 가므로 따로 불러온 WinDLL 에만 건다
      (_current_work_area 와 같은 방식). 64비트에서 핸들이 잘리지 않게 restype 을 HWND 로 지정한다.
    """
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        try:
            from_point = user32.WindowFromPhysicalPoint
        except AttributeError:
            from_point = user32.WindowFromPoint
        from_point.argtypes = [wintypes.POINT]
        from_point.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        GA_ROOT = 2
        my_pid = os.getpid()
    except Exception as e:
        logging.warning(f"우리 창 판별 준비 실패 — 우리 창 위 드래그도 점을 띄웁니다: {e}")
        return lambda x, y: False

    def is_own(x, y):
        try:
            hwnd = from_point(wintypes.POINT(int(x), int(y)))
            if not hwnd:
                return False
            top = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(top, ctypes.byref(pid))
            return pid.value == my_pid
        except Exception:
            return False

    return is_own


def _new_gesture_detector():
    """SelectionGestureDetector 를 윈도우 시스템 설정값(드래그 임계값·더블클릭 시간·더블클릭 범위)으로 만든다.

    값은 selection_button.system_gesture_settings() 가 읽어 준다(GetSystemMetrics SM_CXDRAG 등 — 실패하면 그쪽이
    윈도우 기본값 4,4 / 0.5초 / 4,4 를 준다). 사용자가 윈도우 마우스 설정에서 더블클릭 속도를 바꿨으면 그 값을 따른다.
    ⚠️ 시스템 값 읽기나 detector 생성이 실패해도 앱이 죽으면 안 된다 → 실패하면 detector 기본값으로 만든다.
    setup_mouse_listener 가 부른다(Tk 메인, 또는 훅을 다시 띄우는 watchdog 스레드). Tk 는 만지지 않는다.
    log_to_console 을 여기서 해도 된다(훅 콜백 아님).
    """
    settings = None
    getter = getattr(_selection_button_mod, "system_gesture_settings", None)
    if getter is not None:
        try:
            settings = getter()
        except Exception as e:
            logging.warning(f"윈도우 드래그·더블클릭 설정 읽기 실패 → 기본값: {e}")
    try:
        if isinstance(settings, dict):
            detector = SelectionGestureDetector(**settings)
        elif isinstance(settings, (tuple, list)):
            detector = SelectionGestureDetector(*settings)
        else:
            detector = SelectionGestureDetector()
        if settings is not None:
            log_to_console(f"[빨간 점] 윈도우 드래그·더블클릭 설정: {settings}")
        return detector
    except Exception as e:
        logging.warning(f"드래그 판정기를 시스템 설정값으로 못 만듦 → 기본값: {e}")
        return SelectionGestureDetector()


def setup_mouse_listener():
    """전역 마우스 훅(pynput.mouse.Listener)을 띄워 빨간 점을 띄울 때를 감시한다. 반환: 성공(이미 떠 있음 포함) True / 실패 False.

    - 키보드 훅(setup_keyboard_listener)과 같은 방식: 데몬 스레드 + 30초마다 살아 있는지 보는 watchdog
      (30초는 키보드 watchdog 과 같은 값). watchdog 은 앱이 도는 동안 하나만 띄운다.
    - 훅 콜백은 _make_selection_hook 이 만든 가벼운 함수다(판정 + gui_queue.put 만).
    - 키보드 훅이 키 누름마다 부를 숨김 함수(_selection_key_hook)도 여기서 채운다(끄면 stop_mouse_listener 가 비운다).
    ⚠️ 빨간 점 모듈을 못 불러왔으면 띄우지 않는다(점이 없는데 온 화면 마우스를 볼 까닭이 없다).
    ⚠️ 원문 위 형광펜의 "휠 → 다시 조회"(notify_scroll)도 이 훅이 알린다. 그래서 빨간 점을 끄면(훅이 내려가면)
       휠 알림도 없다 — 그때 형광펜은 다음 조각으로 넘어갈 때 다시 조회된다(훅을 형광펜 때문에 따로 띄울지는 사용자 결정 대기).
    ⚠️ 윈도우는 느린 훅을 조용히 떼어 내기도 한다. 그때 리스너 스레드는 살아 있어 watchdog 이 못 알아챈다
       (키보드 watchdog 과 같은 한계).
    """
    global mouse_listener, _selection_key_hook, _mouse_watchdog_started
    if SelectionGestureDetector is None:
        return False
    try:
        from pynput.mouse import Listener as MouseListener
    except Exception as e:
        logging.error(f"마우스 감지 모듈(pynput.mouse) 로드 실패: {e}")
        log_to_console(f"[빨간 점] 마우스 감지 모듈을 불러오지 못해 빨간 점을 쓸 수 없습니다: {e}")
        return False

    with _mouse_listener_lock:
        if not selection_button_enabled:
            return False   # 그 사이 꺼졌다(watchdog 재시작과 트레이 끄기가 겹친 경우)
        if mouse_listener is not None and mouse_listener.is_alive():
            return True
        try:
            detector = _new_gesture_detector()
            is_own = _make_own_window_checker()

            def contains(x, y):
                # 훅 스레드에서 불린다. SelectionButton.contains 는 Tk 메인이 갱신한 사각형을 스레드 안전하게 읽는다(약속)
                btn = selection_button
                return btn is not None and bool(btn.contains(x, y))

            on_click, on_scroll, on_key = _make_selection_hook(
                detector, contains, is_own, gui_queue.put, lambda: selection_button_enabled,
                on_wheel=_notify_source_scroll)
            listener = MouseListener(on_click=on_click, on_scroll=on_scroll)
            listener.daemon = True
            listener.start()
            mouse_listener = listener
            _selection_key_hook = on_key
        except Exception as e:
            logging.error(f"마우스 리스너 시작 실패: {e}")
            log_to_console(f"[빨간 점] 마우스 감시를 시작하지 못했습니다(단축키로만 읽습니다): {e}")
            return False
    log_to_console("[빨간 점] 마우스 감시 시작 — 글을 드래그·더블클릭으로 고르면 선택 끝 옆에 빨간 점이 뜹니다")

    if not _mouse_watchdog_started:
        _mouse_watchdog_started = True

        def mouse_watchdog():
            """(별도 데몬 스레드) 마우스 훅 스레드가 죽었으면 새로 띄운다. 끈 상태(mouse_listener=None)면 건드리지 않는다."""
            global mouse_listener
            while True:
                try:
                    time.sleep(30)
                    listener = mouse_listener
                    if listener is not None and not listener.is_alive() and selection_button_enabled:
                        log_to_console("[Watchdog] 마우스 리스너 재시작 중...")
                        with _mouse_listener_lock:
                            # 확인과 이 잠금 사이에 사용자가 껐으면(None) 다시 띄우지 않는다
                            if mouse_listener is not listener:
                                continue
                            mouse_listener = None
                        if setup_mouse_listener():
                            log_to_console("[Watchdog] 마우스 리스너 재시작 완료")
                except Exception:
                    pass

        threading.Thread(target=mouse_watchdog, name="mouse-watchdog", daemon=True).start()
    return True


def stop_mouse_listener():
    """전역 마우스 훅을 내린다(트레이에서 빨간 점을 끌 때). 어느 스레드에서 불러도 된다.

    pynput 의 stop() 은 훅 스레드에 "멈춰" 를 보내고 바로 돌아온다(기다리지 않음).
    키보드 훅이 부르던 숨김 함수(_selection_key_hook)도 비운다.
    """
    global mouse_listener, _selection_key_hook
    with _mouse_listener_lock:
        listener = mouse_listener
        mouse_listener = None
        _selection_key_hook = None
    if listener is not None:
        try:
            listener.stop()
            log_to_console("[빨간 점] 마우스 감시 중지")
        except Exception as e:
            logging.warning(f"마우스 리스너 중지 오류: {e}")


def _ensure_selection_button():
    """(Tk 메인) 빨간 점 창을 처음 쓸 때 만든다. 만들다 실패하면 그 뒤로는 시도하지 않는다(_ensure_reading_ui 와 같은 방식).

    점 창은 포커스를 뺏지 않는 창(WS_EX_NOACTIVATE|WS_EX_TOOLWINDOW, 항상 위, 원형)이어야 한다 — selection_button.py 의 몫.
    뺏으면 점을 누른 뒤의 Ctrl+C 가 글을 고른 창이 아니라 점으로 가서 "선택 없음" 이 된다(07-27 로그 §4-4).
    반환: 점 창 또는 None.
    """
    global selection_button, SelectionButton
    if selection_button is None and SelectionButton is not None and root is not None:
        try:
            selection_button = SelectionButton(root, _on_selection_button_click, get_msg)
        except Exception as e:
            SelectionButton = None   # 트레이 체크 항목을 흐리게 하는 표시(enabled=lambda: SelectionButton is not None)
            logging.error(f"빨간 점 창 생성 실패: {e}")
            log_to_console(f"[UI] 빨간 점을 만들지 못했습니다(단축키로만 읽습니다): {e}")
            # ⚠️ pystray(윈도우판)는 enabled/checked 를 메뉴를 "만들 때" 한 번만 읽는다(pystray _win32.py _update_menu).
            #    main 9단계(여기)는 트레이(8단계) 뒤라 메뉴가 이미 "켜짐" 으로 만들어져 있다 → 다시 만들어야 흐려진다.
            #    안 그러면 사용자가 눌러 selection_button_enabled 만 뒤집혀 저장된다(2026-09-28 깨 보기).
            try:
                update_tray_menu()
            except Exception:
                pass   # 트레이 설정이 실패했으면 update_tray_menu 가 없다(setup_tray_icon 설명)
    return selection_button


def setup_selection_button():
    """(Tk 메인, main() 9단계) 빨간 점이 켜져 있으면 점 창을 만들고 전역 마우스 훅을 띄운다.

    꺼져 있으면 아무것도 안 띄운다(마우스 훅도 없음) — 트레이에서 켜면 그때 띄운다(toggle_selection_button).
    모듈을 못 불러왔으면(SelectionButton=None) 아무것도 안 한다(이유는 main() 이 이미 로그로 남겼다).
    """
    if SelectionButton is None:
        return
    if not selection_button_enabled:
        log_to_console("[빨간 점] 꺼져 있습니다 — 트레이 메뉴에서 켤 수 있습니다")
        return
    if _ensure_selection_button() is not None:
        setup_mouse_listener()


def _hide_selection_button():
    """(Tk 메인) 빨간 점을 숨긴다. 점 창이 없으면 아무것도 안 한다. 점 쪽에서 예외가 나도 앱은 계속 간다."""
    if selection_button is not None:
        _safe_ui("빨간 점 숨김", selection_button.hide)


def _enable_dark_menus():
    """이 앱의 윈도우 기본 팝업 메뉴(트레이 오른쪽 메뉴 — pystray 가 TrackPopupMenu 로 띄움)를 다크로 그리게 한다.

    왜: 트레이 메뉴는 Tk·ttkbootstrap 창이 아니라 윈도우가 그리는 메뉴라 앱 테마(darkly)가 닿지 않는다(2026-09-28 사용자 요청).
    어떻게: uxtheme 의 SetPreferredAppMode(서수 135)에 ForceDark(2) 를 주고 FlushMenuThemes(서수 136)로 반영한다.
        탐색기 등이 쓰는 방식이지만 **공개 문서에 없는 함수**라, 윈도우 10 1903 이전이거나 함수가 없으면 조용히 넘어간다(밝은 메뉴).
    """
    try:
        import ctypes as _ct
        ux = _ct.WinDLL("uxtheme")
        set_mode = ux[135]
        set_mode.argtypes = [_ct.c_int]
        set_mode.restype = _ct.c_int
        set_mode(2)                     # 0 기본 · 1 AllowDark · 2 ForceDark · 3 ForceLight
        flush = ux[136]
        flush.restype = None
        flush()
    except Exception as e:
        logging.debug(f"다크 메뉴 설정 실패(밝은 메뉴로 둠): {e}")


def _dark_title_bar(win):
    """Tk 창의 윈도우 제목 표시줄을 어둡게(DWM 다크 모드). ttkbootstrap 다크 테마는 창 안만 칠하고 제목 표시줄은 못 바꾼다.

    DWMWA_USE_IMMERSIVE_DARK_MODE = 20(윈도우 10 20H1 이후·11), 그 전 빌드는 19. 안 되면 조용히 넘어간다.
    창 틀이 만들어진 뒤라야 해서 update_idletasks 를 먼저 부른다(잠깐 밝은 제목이 보였다 바뀔 수 있다).
    """
    try:
        import ctypes as _ct
        win.update_idletasks()
        hwnd = _ct.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        on = _ct.c_int(1)
        for attr in (20, 19):
            if _ct.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, _ct.byref(on), _ct.sizeof(on)) == 0:
                break
    except Exception as e:
        logging.debug(f"다크 제목 표시줄 실패: {e}")


# 빨간 점을 띄우지 않는 창(최상위 창 클래스) — 끌기로 "글" 이 아니라 아이콘·파일을 고르는 곳.
# 2026-09-28 사용자 보고 "바탕화면에서 아이콘을 드래그로 선택해도 빨간 점이 생긴다": 점은 드래그 "추정" 으로 뜨므로
# (윈도우가 다른 앱의 "글 선택됨" 신호를 주지 않음) 이런 창은 이름으로 걸러야 한다.
#   Progman·WorkerW = 바탕화면, Shell_TrayWnd·Shell_SecondaryTrayWnd = 작업 표시줄(주·보조 모니터),
#   CabinetWClass = 파일 탐색기(파일을 사각형으로 끌어 고르는 같은 종류의 동작 — 사용자 보고와 같은 오탐이라 함께 뺌)
_NO_DOT_WINDOW_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "CabinetWClass"}


def _root_class_of(hwnd):
    """창 핸들 → 최상위 창(GetAncestor GA_ROOT)의 클래스 이름. 못 얻으면 ""."""
    try:
        import ctypes as _ct
        from ctypes import wintypes as _wt
        u32 = getattr(_root_class_of, "_u32", None)
        if u32 is None:
            u32 = _ct.WinDLL("user32")          # 전용 객체 — 다른 곳의 windll.user32 argtypes 와 섞이지 않게
            u32.GetAncestor.argtypes = [_wt.HWND, _wt.UINT]
            u32.GetAncestor.restype = _wt.HWND
            u32.GetClassNameW.argtypes = [_wt.HWND, _wt.LPWSTR, _ct.c_int]
            u32.WindowFromPoint.argtypes = [_wt.POINT]
            u32.WindowFromPoint.restype = _wt.HWND
            u32.GetForegroundWindow.restype = _wt.HWND
            _root_class_of._u32 = u32
        if not hwnd:
            return ""
        root_hwnd = u32.GetAncestor(hwnd, 2) or hwnd
        buf = _ct.create_unicode_buffer(256)
        u32.GetClassNameW(root_hwnd, buf, 256)
        return buf.value
    except Exception:
        return ""


def _no_dot_window_at(x, y):
    """(Tk 메인) (x, y) 아래 창이 빨간 점을 띄우지 않는 창(바탕화면·작업 표시줄·탐색기)이면 True."""
    try:
        from ctypes import wintypes as _wt
        _root_class_of(0)                        # 전용 user32 준비
        hwnd = _root_class_of._u32.WindowFromPoint(_wt.POINT(int(x), int(y)))
        return _root_class_of(hwnd) in _NO_DOT_WINDOW_CLASSES
    except Exception:
        return False


# WM_NCHITTEST 결과 중 "글 영역이 아닌 곳" — 제목 표시줄·메뉴·스크롤바·크기 조절 가장자리·최소/최대/닫기 버튼 등
# (HTCAPTION 2 ~ HTHELP 21). HTCLIENT(1)·HTNOWHERE(0)·HTTRANSPARENT(-1)·HTERROR(-2)는 막지 않는다.
_NONCLIENT_HITS = set(range(2, 22))


def _nonclient_at(x, y):
    """(Tk 메인) (x, y) 가 그 창의 "글 영역 밖"(제목 표시줄·가장자리·스크롤바 등)이면 True.

    왜: 2026-09-28 사용자 캡처 — 작업 관리자 제목 표시줄을 끌어 창을 옮겼는데 빨간 점이 떴다. 점은 드래그 "추정" 으로
        뜨므로 창 끌기·크기 조절·스크롤바 끌기도 걸린다. 글은 늘 창의 내용 영역(HTCLIENT)에 있으니 그 밖은 막는다.
    어떻게: 뗀 자리의 최상위 창에 WM_NCHITTEST 를 보내 그 자리가 창의 어느 부분인지 묻는다. 창을 끌어 옮긴 경우
        창이 커서를 따라오므로 뗀 자리도 여전히 제목 표시줄이다. 커스텀 제목 표시줄 앱(작업 관리자·크롬·VS Code)도
        끌 수 있는 곳은 HTCAPTION 을 돌려줘야 윈도우가 창을 옮겨 준다(그래서 같은 방법으로 잡힌다).
    ⚠️ 다른 앱에 메시지를 보내는 일이라 SendMessageTimeout(응답 없는 앱은 건너뜀, 100ms 제한)으로 한다.
       마우스 훅 콜백이 아니라 여기(Tk 메인)에서만 부른다. 묻지 못하면 막지 않는다(점을 띄움 — 예전과 같음).
    """
    try:
        import ctypes as _ct
        from ctypes import wintypes as _wt
        _root_class_of(0)
        u32 = _root_class_of._u32
        if not hasattr(_nonclient_at, "_ready"):
            u32.SendMessageTimeoutW.argtypes = [_wt.HWND, _wt.UINT, _wt.WPARAM, _wt.LPARAM, _wt.UINT, _wt.UINT,
                                                _ct.POINTER(_ct.c_ssize_t)]
            u32.SendMessageTimeoutW.restype = _ct.c_ssize_t
            _nonclient_at._ready = True
        hwnd = u32.WindowFromPoint(_wt.POINT(int(x), int(y)))
        if not hwnd:
            return False
        top = u32.GetAncestor(hwnd, 2) or hwnd                      # GA_ROOT
        lparam = ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)      # 음수 좌표(왼쪽 모니터)도 16비트 두 수로
        res = _ct.c_ssize_t(0)
        if not u32.SendMessageTimeoutW(top, 0x0084, 0, lparam, 0x0002, 100, _ct.byref(res)):  # WM_NCHITTEST, SMTO_ABORTIFHUNG
            return False
        hit = _ct.c_short(res.value & 0xFFFF).value
        return hit in _NONCLIENT_HITS
    except Exception:
        return False


def _no_dot_foreground():
    """(Tk 메인) 지금 전경 창이 빨간 점을 띄우지 않는 창이면 True (키보드로 고른 경우 — Ctrl+A 로 바탕화면 아이콘 전체 선택 등)."""
    try:
        _root_class_of(0)
        return _root_class_of(_root_class_of._u32.GetForegroundWindow()) in _NO_DOT_WINDOW_CLASSES
    except Exception:
        return False


def _cursor_pos():
    """지금 마우스 커서 화면 좌표 (x, y). 못 얻으면 None. (키보드로 고른 뒤 선택 끝 위치를 모를 때 빨간 점 자리)"""
    try:
        import ctypes as _ct
        from ctypes import wintypes as _wt
        pt = _wt.POINT()
        if _ct.windll.user32.GetCursorPos(_ct.byref(pt)):
            return (pt.x, pt.y)
    except Exception:
        pass
    return None


def _handle_selection_button_msg(action, *args):
    """(Tk 메인) 훅이 gui_queue 로 보낸 빨간 점 명령을 처리한다. check_gui_queue 가 부른다.

    ("show", x, y): (x, y) = 마우스를 뗀 화면 좌표. 점은 SelectionButton.show_at 이 그 오른쪽(GAP)에 띄운다.
                    꺼져 있으면(큐에 들어간 뒤 사용자가 끈 경우) 버린다.
                    "브라우저에서 비활성화" 가 켜져 있고 지금 전경 창이 Aside·웨일·크롬이면 지금 페이지 주소 종류를 물어
                    일반 웹페이지(http·https)일 때만 버린다(확장이 자기 점을 띄운다). 새 탭·확장 페이지·브라우저 설정·
                    내 PC 파일, 또는 주소를 모르면(느림 포함) 다른 앱과 똑같이 띄운다(2026-10-23 사용자 결정, _unless_web_page).
                    텔레그램이면 선택 끝 대신 "선택한 메시지"를 묻는다(_show_dot_if_telegram_selected).
                    ⚠️ 그 판별(전경 창 → 프로세스 → 실행 파일 이름)은 여기, Tk 메인에서 한다. 마우스 훅 콜백에서 하면
                       OpenProcess 등이 훅을 느리게 만들어 윈도우가 훅을 떼어 낼 수 있다(훅 콜백 규칙).
    ("click", x, y): 한 번 클릭의 뗌. 텔레그램이 앞 창일 때만 "선택한 메시지"를 묻고(우클릭 메뉴 "선택"·선택 상태에서
                    메시지 더 고르기), 다른 앱이면 버린다(2026-10-23).
    ("hide",)     : 숨긴다.
    ("rpress", x, y): 우클릭 누름. 자리를 _tg_right_click 에 기억만 한다 — 다음 "show"/"click" 처리 한 번에만 쓰고 지운다
                    (텔레그램이면 그 자리 메시지도 "선택됨"인지 본다, 2026-10-24 사용자 결정. 시간 제한 없음 — 한 번 쓰면 끝).
    ("keyboard",) : 키보드로 골랐다(Ctrl+A, Shift+화살표 등 — 키보드 훅 on_release). 자리 = 선택 끝 글자 옆(원문 형광펜의
                    UIA 스레드에 끝 글자 하나만 물음), 못 얻거나 끝이 화면 밖이면 마우스 옆, 고른 글이 없으면 안 띄움
                    (2026-09-28 사용자 확정 "선택 끝, 안 되면 마우스 옆"). 브라우저면 위 "show" 와 같은 주소 확인을 먼저 한다.
    """
    global _dot_query_gen, _tg_right_click
    if action == "rpress" and len(args) >= 2:
        _tg_right_click = (args[0], args[1])
        return
    if action == "keyboard":
        if not selection_button_enabled or selection_button is None or _no_dot_foreground():
            return
        browser = _foreground_disabled_browser()
        _dot_query_gen += 1
        gen = _dot_query_gen

        def place(pos):
            # ⚠️ "show" 갈래로 되넘기지 않는다 — 그 갈래는 선택 끝을 다시 묻고 모르면 안 띄워서, 끝 글자 위치를 모를 때
            #    (Ctrl+A 의 끝 = 파일 끝 줄바꿈·끝이 화면 밖) "마우스 옆" 이 한 번도 안 됐다(2026-10-28 리규형님 메모장 보고)
            if gen != _dot_query_gen or pos == "none":
                return                              # 기다리는 사이 다시 누르거나 키를 쳤다 / 커서만 있다 — 고른 글이 없다
            if not isinstance(pos, tuple):
                pos = _cursor_pos()                 # 끝 글자 위치를 모른다 → 마우스 옆
            if not pos:
                return
            if _is_telegram_exe(_foreground_exe_name()):
                _handle_selection_button_msg("show", pos[0], pos[1])   # 텔레그램은 "선택한 메시지"로 판단(show 갈래)
                return
            if selection_button is not None and selection_button_enabled:
                _safe_ui("빨간 점 표시", selection_button.show_at, pos[0], pos[1])

        def ask_end(_scheme=None):
            hl = _ensure_source_highlighter() if source_highlight_enabled else None
            if hl is not None and hasattr(hl, "query_selection_end"):
                _safe_ui("선택 끝 위치", hl.query_selection_end, place)
            else:
                place(None)

        _unless_web_page(browser, ask_end,
                         lambda scheme: logging.debug(f"[빨간 점] {browser} 웹페이지({scheme})에서는 띄우지 않음"))
        return
    if action == "hide":
        _dot_query_gen += 1        # 기다리던 "선택 확인" 결과가 늦게 와도 점을 띄우지 않게
        _hide_selection_button()
    elif action in ("show", "click") and len(args) >= 2:
        right_click, _tg_right_click = _tg_right_click, None      # 우클릭 자리는 이 한 번에만 쓴다
        if not selection_button_enabled or selection_button is None:
            return
        x, y = args[0], args[1]
        exe = _foreground_exe_name()
        if _is_telegram_exe(exe):
            # 텔레그램: 글 위치 기능이 없어 선택 끝을 못 묻는다 → "선택한 메시지"로 판단(끌기·한 번 클릭 둘 다)
            if not _nonclient_at(x, y):
                _show_dot_if_telegram_selected(x, y, right_click)
            return
        if action == "click":
            return                                   # 한 번 클릭은 텔레그램 "선택" 용 — 다른 앱에선 글을 고른 게 아니다
        if _no_dot_window_at(x, y) or _no_dot_foreground():
            # 바탕화면·작업 표시줄·탐색기 — 글이 아니라 아이콘·파일을 끌어 고른 것. 뗀 자리 판정이 빗나가도(2026-09-28
            # 사용자 보고 "바탕화면에서 여전히 뜬다") 바탕화면을 누르면 바탕화면이 앞 창이 되므로 앞 창으로도 한 번 더 본다
            return
        if _nonclient_at(x, y):
            return                                   # 제목 표시줄(창 옮기기)·가장자리(크기 조절)·스크롤바 — 글 영역 밖
        browser = exe if (disable_in_browsers and _is_disabled_browser_exe(exe)) else None
        _dot_query_gen += 1
        gen = _dot_query_gen

        def show_if_selected(_scheme=None):
            if gen != _dot_query_gen:
                return                               # 주소를 묻는 사이 다시 누르거나 키를 쳤다
            _show_dot_where_selected(x, y)

        # 브라우저면 일반 웹페이지(http·https)에서만 쉰다 — 크롬 확장이 자기 점을 띄운다. 드래그할 때마다 남기면 콘솔이
        # 넘치므로 파일 로그(debug)에만 남긴다. 새 탭·확장·설정·내 PC 파일·주소 모름이면 다른 앱과 같이(2026-10-23 사용자 결정)
        _unless_web_page(browser, show_if_selected,
                         lambda scheme: logging.debug(f"[빨간 점] {browser} 웹페이지({scheme})에서는 띄우지 않음"))


def _show_dot_where_selected(x, y):
    """(Tk 메인) 실제로 글이 선택됐을 때만 빨간 점을 띄운다 — 앞 앱에 선택 끝 글자 위치를 묻고 얻었으면 그 옆.

    2026-09-28 사용자 보고 "글자도 없는데 클릭만 해도 나타난다": 드래그 "추정"(4px 이상 움직임)만으로는 배율 140% 화면에서
    클릭할 때 손 떨림도 드래그가 됐다. 그래서 확장처럼 "선택이 있을 때만"(selection-button.js selectedRange) — 앞 앱의
    선택 끝 글자 위치를 UIA 로 한 자리만 묻고(원문 형광펜의 UIA 스레드, 1~20ms), 얻었으면 그 옆(확장과 같은 자리)에 띄운다.
    고른 글이 없거나("none") 글 문서가 아니거나 조회가 안 되면(None) 띄우지 않는다. 대가: UIA 글 기능이 없는 앱에선
    점이 안 뜬다(단축키로 읽는다 — 텔레그램은 _show_dot_if_telegram_selected 로 따로 본다).
    """
    global _dot_query_gen
    if selection_button is None or not selection_button_enabled:
        return
    hl = _ensure_source_highlighter() if source_highlight_enabled else None
    if hl is not None and hasattr(hl, "query_selection_end"):
        _dot_query_gen += 1
        gen = _dot_query_gen

        def place(pos):
            # 결과를 기다리는 사이 다시 누르거나 키를 쳤으면(hide 가 세대를 올림) 옛 결과는 버린다
            if gen != _dot_query_gen or not isinstance(pos, tuple):
                return
            if selection_button is not None and selection_button_enabled:
                _safe_ui("빨간 점 표시", selection_button.show_at, pos[0], pos[1])

        _safe_ui("선택 확인", hl.query_selection_end, place)
        return
    # UIA 를 못 쓰는 환경(모듈 없음·원문 형광펜 꺼짐)에서만 예전처럼 드래그 추정으로 띄운다
    _safe_ui("빨간 점 표시", selection_button.show_at, x, y)


def _show_dot_if_telegram_selected(x, y, right_click=None):
    """(Tk 메인) 텔레그램: 마우스를 뗀 뒤 메시지가 "선택"(우클릭 메뉴 → 선택) 상태면 뗀 자리 옆에 빨간 점.

    2026-10-23 사용자 결정: 텔레그램은 글 위치 기능이 없어(10-10 실측) 선택 끝을 못 묻는다 → "선택한 메시지"로 판단한다.
      자리 = 마우스를 뗀 자리 옆(메시지 칸은 창 너비로 잡힐 수 있어 메시지 끝 옆은 엉뚱해진다).
      때 = "선택" 을 누를 때와, 선택 상태에서 메시지를 더 누를 때마다. 선택이 다 풀렸으면 띄우지 않는다.
    점을 누르면 단축키와 같은 Ctrl+C 로 읽는다 — 텔레그램은 선택한 메시지 글을 복사해 준다(2026-10-23 실측, 머리말 없음).
    "선택한 메시지"를 묻는 일은 원문 형광펜 켬/끔과 무관하다(점 판단용 UIA 조회만 빌려 쓴다).
    우클릭 메뉴가 아직 떠 있으면(결과 "menu") TELEGRAM_MENU_RETRY_MS 뒤 다시 묻고, TELEGRAM_MENU_RETRY_MAX_S 를 넘으면 그만둔다
    (2026-10-23 개발 모드 시험 "처음엔 안 뜨고 다음엔 뜬다" — 뗀 순간 메뉴가 닫히는 중이었다, 로그로 확인). 그사이 다른 곳을
    누르거나 키를 치면(hide 가 세대를 올림) 그만둔다.
    한 번이라도 "menu" 가 나왔으면 그 뒤 False 도 한도까지 다시 묻는다(2026-10-24 — 10-23 설치본 로그: 메뉴를 누른 뒤 포커스는
    메시지로 돌아왔는데 선택 표시가 아직 안 켜져 False 로 끝난 경우가 있었다). None(느림·실패)은 바로 그만둔다.
    """
    global _dot_query_gen
    hl = _ensure_source_highlighter()
    if hl is None or not hasattr(hl, "query_telegram_selected"):
        return
    _dot_query_gen += 1
    gen = _dot_query_gen
    started = time.monotonic()
    tries = [0]
    from_menu = [False]      # 한 번이라도 "menu" 가 나왔는가(메뉴 항목을 누른 뒤의 확인)

    def ask():
        if gen != _dot_query_gen:
            return
        tries[0] += 1
        _safe_ui("텔레그램 선택 확인", hl.query_telegram_selected, x, y, place, right_click)

    def place(selected):
        if gen != _dot_query_gen:
            return
        waited = time.monotonic() - started
        # 진단 로그(원인 확정 전까지 — 사용자 결정): 몇 번째 확인에서 무엇이 나왔고 처음 물은 뒤 몇 ms 였는지
        logging.info(f"[텔레그램] 빨간 점 {tries[0]}번째 확인: {selected} (처음 물은 뒤 {waited * 1000:.0f}ms)")
        if selected == "menu":
            from_menu[0] = True
        if (selected == "menu" or (from_menu[0] and selected is False)) \
                and waited < TELEGRAM_MENU_RETRY_MAX_S and root is not None:
            root.after(TELEGRAM_MENU_RETRY_MS, ask)
            return
        if selected is not True:
            return
        if selection_button is not None and selection_button_enabled:
            _safe_ui("빨간 점 표시", selection_button.show_at, x, y)

    ask()


def _on_selection_button_click():
    """(Tk 메인) 빨간 점을 눌렀다(누르고 점 안에서 뗌) → 점을 숨기고 선택한 글을 읽는다.

    확장 selection-button.js:201-207 read() 도 점을 먼저 숨기고 읽기를 요청한다.
    글은 단축키와 같은 read_selected_text(Ctrl+C) 로 가져온다 — 점 창이 NOACTIVATE 라 포커스·선택이 원래 앱에 남아 있다.
    root.after(10) 로 한 번 미루는 건 점의 클릭 처리를 먼저 끝내려는 것(옛 플로팅 아이콘과 같은 처리).
    """
    _hide_selection_button()
    log_to_console("[빨간 점] 클릭 → 선택한 글 읽기")
    if root is not None:
        root.after(10, lambda: read_selected_text(from_selection_button=True))
    else:
        read_selected_text(from_selection_button=True)


def toggle_selection_button():
    """(Tk 메인) 트레이 "텍스트 선택 시 읽기 버튼" 체크 켬/끔. 설정에 저장한다.

    켜기: 점 창을 만들고(처음이면) 마우스 훅을 띄운다.
    끄기: 점을 숨기고 마우스 훅도 내린다(온 화면 마우스를 계속 볼 까닭이 없다). 큐에 남은 "보이기" 는
          _handle_selection_button_msg 가 꺼짐을 보고 버린다. (확장: 끄면 페이지의 점을 없앤다 — selection-button.js:65-67)
    """
    global selection_button_enabled
    selection_button_enabled = not selection_button_enabled
    save_settings()
    log_to_console(f"[빨간 점] {'켬' if selection_button_enabled else '끔'}")
    if selection_button_enabled:
        if _ensure_selection_button() is not None:
            setup_mouse_listener()
    else:
        _hide_selection_button()
        stop_mouse_listener()
    try:
        update_tray_menu()
    except Exception:
        pass


# ── 브라우저에서 비활성화 (2026-09-28 사용자 확정, 2026-10-23 웹페이지만으로 좁힘) ──────────────────
# Aside·웨일·크롬에는 크롬 확장 read-aloud-hrg 가 깔려 있어 확장이 빨간 점·읽기를 맡는다.
# 그 브라우저가 전경이고 지금 페이지가 일반 웹페이지(http·https)면 이 앱은 빨간 점을 띄우지 않고 단축키로 새 읽기를
# 시작하지 않는다(둘이 겹쳐 읽지 않게). 확장이 못 도는 페이지(새 탭·확장 페이지·브라우저 설정·내 PC 파일)와 주소를
# 모를 때(느림·문서 밖)는 이 앱이 다른 앱과 똑같이 동작한다(2026-10-23 사용자 결정). 주소는 _unless_web_page 가 묻는다.

def _foreground_exe_name():
    """(Tk 메인) 지금 전경 창을 만든 프로세스의 실행 파일 이름(예 "chrome.exe"). 모르면 None.

    방법: GetForegroundWindow → GetWindowThreadProcessId → OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)
          → QueryFullProcessImageNameW → 경로에서 파일 이름만.
    왜 Tk 메인에서만 부르나: OpenProcess·QueryFullProcessImageNameW 는 커널을 거치는 호출이라 마우스·키보드 훅 콜백에서
      부르면 훅이 느려져 윈도우가 훅을 조용히 떼어 낼 수 있다(훅 콜백 규칙). 그래서 gui_queue 처리·read_selected_text 에서 부른다.
    함정
      - ctypes.windll 공용 객체에 argtypes 를 걸면 앱 전체(다른 파일의 Win32 호출)에 영향이 가서 따로 불러온 WinDLL 에만 건다
        (_current_work_area 와 같은 방식). 64비트에서 핸들이 잘리지 않게 restype 을 지정한다.
      - QUERY_LIMITED 권한은 다른 사용자·높은 권한 프로세스에도 대개 열린다(앱은 exe 로 관리자 실행). 그래도 못 열면 None →
        "브라우저 아님" 으로 보고 평소대로 동작한다(쉬게 하는 쪽으로 잘못 가지 않게).
      - msedgewebview2.exe 는 다른 앱 안의 웹 화면이다. 전경 "최상위 창" 은 그 앱(예 Code.exe)의 것이라 여기서 나오지 않는다.
    """
    try:
        import ctypes
        from ctypes import wintypes
        api = getattr(_foreground_exe_name, "_api", None)
        if api is None:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            user32.GetForegroundWindow.argtypes = []
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            user32.GetWindowThreadProcessId.restype = wintypes.DWORD
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                            ctypes.POINTER(wintypes.DWORD)]
            kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            api = (user32, kernel32)
            _foreground_exe_name._api = api
        user32, kernel32 = api
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return None
        try:
            size = wintypes.DWORD(1024)   # 경로 글자 수 칸. 긴 경로(\\?\ 접두)도 이 안에 든다
            buf = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return None
            return os.path.basename(buf.value) or None
        finally:
            kernel32.CloseHandle(handle)
    except Exception as e:
        logging.debug(f"전경 창 실행 파일 조회 실패: {e}")
        return None


def _is_disabled_browser_exe(exe_name):
    """실행 파일 이름이 "쉬어야 할 브라우저"(Aside·웨일·크롬)인가. 대소문자 무시. 순수 함수(테스트용으로 따로 뺐다)."""
    return bool(exe_name) and str(exe_name).lower() in _BROWSER_EXES


def _is_telegram_exe(exe_name):
    """실행 파일 이름이 텔레그램 데스크톱인가. 대소문자 무시. 순수 함수(테스트용)."""
    return bool(exe_name) and str(exe_name).lower() in _TELEGRAM_EXES


def _is_web_scheme(scheme):
    """주소 종류(source_highlight.url_scheme 결과)가 일반 웹페이지(http·https)인가. 순수 함수(테스트용).

    그 밖(chrome-extension·chrome·aside·about·file 등)과 None(모름)은 False — 이 앱이 동작한다(2026-10-23 사용자 결정).
    """
    return bool(scheme) and str(scheme).lower() in ("http", "https")


def _unless_web_page(browser, proceed, on_web=None):
    """(Tk 메인) 브라우저면 지금 페이지가 일반 웹페이지인지 묻고, 아니면 proceed(scheme) 를 부른다.

    browser : _foreground_disabled_browser() 결과(브라우저 실행 파일 이름 또는 None).
      None → 묻지 않고 곧바로 proceed(None).
      브라우저 → 원문 형광펜의 UIA 스레드에 주소 종류를 묻는다(query_page_scheme — 포커스에서 위로 문서 요소 하나, 한 자리 호출).
        일반 웹페이지(http·https) → on_web(scheme) (크롬 확장 몫이라 쉰다).
        그 밖(새 탭·확장 페이지·브라우저 설정·내 PC 파일) 또는 모름(느림·문서 밖·UIA 없음) → proceed(scheme).
    결과는 Tk 메인에서 나중에 온다(보통 수 ms, 느리면 1초 제한 — 2026-10-23 Aside 실측 2~130ms, 가끔 2초 넘게 걸려 모름).
    """
    if not browser:
        proceed(None)
        return
    hl = _ensure_source_highlighter()
    if hl is None or not hasattr(hl, "query_page_scheme"):
        proceed(None)                       # 주소를 물을 수 없다 → 모름 → 동작(사용자 결정)
        return

    def done(scheme):
        if _is_web_scheme(scheme):
            if on_web is not None:
                on_web(scheme)
        else:
            proceed(scheme)

    try:
        hl.query_page_scheme(done)
    except Exception as e:
        logging.debug(f"페이지 주소 확인 요청 실패(모름 → 동작): {e}")
        proceed(None)


def _foreground_disabled_browser():
    """(Tk 메인) "브라우저에서 비활성화" 가 켜져 있고 전경 창이 그 브라우저면 실행 파일 이름, 아니면 None.

    꺼져 있으면 전경 창을 조회하지도 않는다(쓸데없는 호출을 줄이려고).
    """
    if not disable_in_browsers:
        return None
    exe = _foreground_exe_name()
    return exe if _is_disabled_browser_exe(exe) else None


def toggle_disable_in_browsers():
    """(Tk 메인) 트레이 "브라우저에서 비활성화" 체크 켬/끔. 설정에 저장하고 트레이 체크 표시를 다시 그린다.

    이미 떠 있는 빨간 점은 건드리지 않는다(트레이를 누르는 순간의 마우스 클릭이 이미 점을 숨긴다).
    """
    global disable_in_browsers
    disable_in_browsers = not disable_in_browsers
    save_settings()
    log_to_console(f"[브라우저] 브라우저(Aside·웨일·크롬)에서 비활성화 {'켬' if disable_in_browsers else '끔'}")
    try:
        update_tray_menu()
    except Exception:
        pass


def _notify_source_scroll():
    """(마우스 훅 스레드) 휠을 굴렸다 → 원문 위 형광펜에 "다시 조회" 를 알린다.

    SourceHighlighter.notify_scroll 은 약속상 "어느 스레드에서 불러도 된다(플래그만 세움)". 그래서 훅 콜백에서 불러도 된다.
    형광펜 객체가 없으면(아직 안 만듦·모듈 없음) 아무것도 안 한다. 예외를 밖으로 내지 않는다(훅 콜백).
    active 속성은 읽지 않는다 — 다른 스레드에서 읽어도 되는지 약속에 없어서.
    원문 위에 칠하는 중("on")일 때만 알린다 (2026-09-28 5차 깨 보기):
      형광펜의 휠 플래그는 칠하지 않는 동안 아무도 비우지 않는다(source_highlight.py _watch 만 비움, begin 도 안 비움).
      그래서 쉬는 동안 아무 창에서나 굴린 휠이 플래그로 남아 있다가 다음 읽기가 붙자마자 사각형 재조회를 여러 번
      (SETTLE_TICKS) 부른다 — 사용자 VS Code 에 쓸데없는 UIA 호출이 는다(scratchpad phase4_wiring\\verify_real_hl.py
      실측: 쉬는 동안 휠 5번 → 새 읽기 0.6초 동안 재조회 5번). "pending" 동안도 알리지 않는다 — 결과 ok 때 처음 사각형을
      어차피 새로 받는다.
    _source_hl_state 는 Tk 메인이 바꾸는 전역 문자열이다. 여기(훅 스레드)서는 읽기만 한다(대입 하나라 안전, 늦게 읽혀도
      알림 한 번이 빠지거나 더 갈 뿐 — 해 없음).
    """
    hl = source_highlighter
    if hl is None or _source_hl_state != "on":
        return
    try:
        hl.notify_scroll()
    except Exception:
        pass


# API 키 설정 대화 상자 표시 함수
def show_api_key_dialog(required=False):
    """Google API 키 두 개(TTS 키·Gemini 키)를 넣는 인증 창 (2026-09-29 — 그 전엔 서비스 계정 JSON 파일 고르기).

    ⚠️ Tk 메인 스레드에서만 부른다(main 의 인증 확인 / 설정 창 "인증 설정" 버튼 / 트레이 → gui_queue "show_api_key_dialog").
    흐름: 두 칸에 키 붙여넣기 → "저장" → 키 확인 요청(TTS: 음성 목록, Gemini: 모델 정보 — Gemini 칸이 비면 건너뜀)
          → 통과하면 init_tts_client → 설정 저장 → 1.5초 뒤 창 닫힘.
          실패하면 창에 빨간 글씨로 이유를 보이고 저장하지 않는다(창은 열어 둔다 — 파일 방식 때와 같은 규칙).
          두 칸을 바꿔 넣어도 확인에서 걸린다(실측: TTS 키로 Gemini 403, Gemini 키로 TTS 401).
    확인 요청은 Tk 메인에서 바로 한다(실측 0.3~0.5초씩, 제한 3초) — 그동안 창이 잠깐 멈춘다. 드물게 하는 일이라 그대로 둔다.
    필수 모드(시작할 때 TTS 키가 없거나 클라이언트를 못 만들었을 때): 클라이언트가 준비될 때까지 취소·X·Esc 로 닫을 수 없다.
      그래서 init_tts_client·_check_tts_key 는 "모듈 import 오류" 를 예외로 올리지 않는다
      (예외로 올리면 저장이 계속 실패하고 취소도 안 돼 창을 영영 못 닫는다 — init_tts_client 의 ⚠️ 설명).
    키 칸은 가려서(●) 보이고, "키 보이기" 체크로 드러낸다.
    wait_window() 로 창이 닫힐 때까지 이 함수가 돌아오지 않는다(그동안에도 Tk 이벤트는 돈다).
    반환: 저장했으면 True, 아니면 False.
    """
    global google_tts_api_key, gemini_api_key

    # 완전히 독립적인 모달 대화 상자 생성
    # (부모를 안 주면 기본 루트가 부모가 된다. 창 아이콘은 main 이 건 "기본 아이콘"(favicon.ico)을 따른다)
    dialog = ttk.Toplevel()
    dialog.title(get_msg("auth_title"))
    dialog.resizable(False, False)
    _dark_title_bar(dialog)   # 창 안은 darkly 테마, 윈도우 제목 표시줄도 어둡게

    # 모달 설정
    dialog.transient()
    dialog.grab_set()
    dialog.focus_set()
    dialog.attributes("-topmost", True)

    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frame, text=get_msg("auth_help"), justify=tk.LEFT, wraplength=560).pack(anchor="w", pady=(0, 15))

    # 키 두 칸 — 지금 저장된 키를 채워 둔다(가려서 보인다)
    fields = ttk.Frame(frame)
    fields.pack(fill=tk.X, pady=4)
    tts_var = tk.StringVar(value=google_tts_api_key or "")
    gem_var = tk.StringVar(value=gemini_api_key or "")
    ttk.Label(fields, text=get_msg("auth_tts_key")).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
    tts_entry = ttk.Entry(fields, textvariable=tts_var, width=52, show="●")
    tts_entry.grid(row=0, column=1, sticky="ew", pady=4)
    ttk.Label(fields, text=get_msg("auth_gemini_key")).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
    gem_entry = ttk.Entry(fields, textvariable=gem_var, width=52, show="●")
    gem_entry.grid(row=1, column=1, sticky="ew", pady=4)
    fields.columnconfigure(1, weight=1)

    show_var = tk.BooleanVar(value=False)

    def toggle_show():
        """"키 보이기" 체크: 두 칸의 가림(●)을 켜고 끈다."""
        mask = "" if show_var.get() else "●"
        tts_entry.config(show=mask)
        gem_entry.config(show=mask)

    ttk.Checkbutton(frame, text=get_msg("auth_show_keys"), variable=show_var,
                    command=toggle_show).pack(anchor="w", pady=(4, 0))

    # 결과 메시지 라벨 (bootstyle 활용)
    result_label = ttk.Label(frame, text="", wraplength=560, justify=tk.LEFT)
    result_label.pack(fill=tk.X, pady=10)

    # 버튼 프레임
    btn_frame = ttk.Frame(frame)
    btn_frame.pack(pady=10)

    # 결과 변수
    result = [False]

    def _first_line(e):
        """오류 문구를 창에 보일 만큼만(gRPC 오류는 여러 줄이라 첫 줄, 200자까지)."""
        text = str(e).strip().splitlines()
        return (text[0] if text else type(e).__name__)[:200]

    def save_credentials():
        """"저장" 버튼(또는 Enter): 키를 확인하고 통과하면 클라이언트·번역기를 만들고 설정 파일에 저장한다."""
        global google_tts_api_key, gemini_api_key

        tts_key = tts_var.get().strip()
        gem_key = gem_var.get().strip()

        if not tts_key:
            result_label.config(text=get_msg("auth_need_tts_key"), bootstyle="danger")
            return

        result_label.config(text=get_msg("auth_checking"), bootstyle="default")
        dialog.update_idletasks()
        try:
            _check_tts_key(tts_key)
        except Exception as e:
            result_label.config(text=get_msg("auth_tts_key_failed", _first_line(e)), bootstyle="danger")
            logging.error(f"TTS 키 확인 실패: {_first_line(e)}")
            return
        if gem_key:
            try:
                translation.check_gemini_key(gem_key)
            except Exception as e:
                result_label.config(text=get_msg("auth_gemini_key_failed", _first_line(e)), bootstyle="danger")
                logging.error(f"Gemini 키 확인 실패: {_first_line(e)}")
                return

        try:
            # texttospeech 모듈이 없으면 False(로그만) — 옛 파일 방식처럼 저장은 진행한다
            init_tts_client(tts_key, gem_key or None)
        except Exception as e:
            result_label.config(text=get_msg("auth_error", _first_line(e)), bootstyle="danger")
            logging.error(f"인증 설정 오류: {_first_line(e)}")
            return

        google_tts_api_key = tts_key
        gemini_api_key = gem_key or None
        save_settings()

        result_label.config(text=get_msg("auth_saved"), bootstyle="success")
        logging.info("Google API 키 설정됨")
        log_to_console("Google API 키 설정됨 (TTS 키" + (", Gemini 키" if gem_key else ", Gemini 키 없음") + ")")
        result[0] = True
        dialog.after(1500, dialog.destroy)

    def cancel():
        """"취소"·Esc·X 모두 여기로 온다. 필수 모드에서 클라이언트가 없으면 닫지 않고 안내만 한다."""
        if required and not google_tts_client:
            result_label.config(text=get_msg("auth_need_tts_key"), bootstyle="danger")
            return
        dialog.destroy()

    ttk.Button(btn_frame, text=get_msg("save"), command=save_credentials, width=12,
               bootstyle="success").pack(side=tk.LEFT, padx=10)
    ttk.Button(btn_frame, text=get_msg("cancel"), command=cancel, width=12,
               bootstyle="secondary").pack(side=tk.LEFT, padx=10)

    # 이벤트 바인딩
    dialog.bind("<Return>", lambda event: save_credentials())
    dialog.bind("<Escape>", lambda event: cancel())
    dialog.protocol("WM_DELETE_WINDOW", cancel)

    # 창 크기는 내용에 맞추고 화면 가운데에
    dialog.update_idletasks()
    width = max(600, dialog.winfo_reqwidth())
    height = dialog.winfo_reqheight()
    x = (dialog.winfo_screenwidth() // 2) - (width // 2)
    y = (dialog.winfo_screenheight() // 2) - (height // 2)
    dialog.geometry(f"{width}x{height}+{x}+{y}")
    (tts_entry if not tts_var.get() else gem_entry).focus_set()

    # 모달 대화 상자 실행
    dialog.wait_window()

    return result[0]


def open_console_window():
    """새 cmd 창을 열어 whisperer_console.log 를 실시간으로 보여 준다(PowerShell Get-Content -Wait).

    설정 창의 "콘솔 창 열기" 버튼이 부른다(Tk 메인). 예전에는 트레이 메뉴 항목(트레이 스레드)이었는데
    2026-09-28 사용자 결정으로 설정 창으로 옮겼다 — 내용은 옛 트레이 open_console 그대로다.
    작업 폴더에 open_console.bat 을 만들어 실행한다. ⚠️ bat 안의 "echo > whisperer_console.log" 가
    로그 파일을 한 번 비운다(옛 동작 그대로). Tk 를 만지지 않고 금방 돌아온다(Popen 은 기다리지 않음).
    """
    global console_log_file
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
        console_log_file = os.path.abspath("whisperer_console.log")

        # 콘솔 창이 열렸음을 로그에 기록
        log_to_console(get_msg("console_opened"))
        log_to_console(get_msg("program_status"))

    except Exception as e:
        log_to_console(get_msg("console_open_error", str(e)))


def _apply_language(lang):
    """(Tk 메인) 화면 언어를 lang("ko"|"en")으로 바꾸고 트레이 메뉴 문구도 새 언어로 다시 만든다. 바뀌었으면 True.

    설정 창 "저장" 이 부른다(저장 자체는 부르는 쪽의 save_settings 가 한다).
    옛 트레이 "언어 변경"(change_language)과 같은 일: 전역 current_language 바꾸기 → 로그 → update_tray_menu.
    하단 바·리더 창은 문구를 그릴 때마다 get_msg 를 새로 부르므로 따로 알릴 필요가 없다.
    이상한 값이면 아무것도 안 한다.
    """
    global current_language
    if lang not in ("ko", "en") or lang == current_language:
        return False
    current_language = lang
    log_to_console(get_msg("language_changed", current_language))
    try:
        update_tray_menu()
    except Exception:
        pass   # 트레이 설정이 실패했으면 update_tray_menu 가 없다(setup_tray_icon 설명)
    return True


# TTS 설정 대화상자
def show_tts_settings_dialog():
    """TTS 설정 대화상자를 표시합니다.

    ⚠️ Tk 메인 스레드에서만 부른다(트레이 → gui_queue "show_tts_settings").
    이미 열려 있으면 새로 만들지 않고 앞으로 올린다(함수 속성 .dialog 에 창을 기억).
    고칠 수 있는 것: 음성(KOREAN_VOICES), 속도(0.25~4.0), 단축키(Ctrl/Shift/Alt + 글자),
      그리고 2026-09-28 트레이에서 옮겨 온 "일반" 묶음 — 언어(한국어/English), "인증 설정" 버튼, "콘솔 창 열기" 버튼.
    저장하면 전역값을 바꾸고 파일에 쓴다. 읽는 중인 세션에는 적용되지 않고 다음 읽기부터 쓰인다
    (읽는 중 속도는 하단 바 설정 패널이 바꾼다).
    언어는 다른 값처럼 "저장" 을 눌러야 바뀐다(취소하면 그대로). 바뀌면 트레이 문구도 새 언어로(_apply_language).
    "인증 설정"·"콘솔 창 열기" 버튼은 누르는 즉시 동작한다(저장과 무관).
    ⚠️ 단축키를 바꿔도 키보드 훅은 전역값을 매번 읽으므로 곧바로 새 단축키가 먹는다(훅을 다시 띄울 필요 없음).
    창 크기: 예전엔 650x550 고정이었는데 "일반" 묶음이 늘어 내용이 잘릴 수 있다 → 다 만든 뒤 내용이 요구하는 높이로 맞춘다
    (폭은 650 이상).
    """
    global root, tts_hotkey_modifiers, tts_hotkey_key, tts_voice_name, tts_speaking_rate

    if hasattr(show_tts_settings_dialog, 'dialog') and show_tts_settings_dialog.dialog and show_tts_settings_dialog.dialog.winfo_exists():
        show_tts_settings_dialog.dialog.lift()
        return

    dialog = ttk.Toplevel(root)
    dialog.title(get_msg("dialog_tts_title"))
    dialog.geometry("650x550")   # 처음 자리 잡기용. 아래 끝에서 내용 높이에 맞춰 다시 정한다
    dialog.resizable(False, False)
    _dark_title_bar(dialog)      # 창 안은 darkly 테마, 윈도우 제목 표시줄도 어둡게
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

    # 목소리 칸 글 — "Zephyr · Chirp 3 HD · 100만 자 30달러 (이번 달 PC 앱 12,345자)" (2026-11-01 Paseo 와 같은 모양).
    # 숫자 = 이 앱이 이번 결제 달에 보낸 글자(종류별 — 같은 종류는 같은 숫자). 세 곳 합계는 "읽기 사용량" 창.
    # 기록을 못 읽으면 괄호를 뺀다. 저장된 목소리가 목록에 없으면 맨 앞에 붙인다(Paseo voiceOptions 와 같게)
    try:
        usage_now = tts_usage_counter.month_counts()
    except Exception:
        usage_now = None
    voice_ids = list(KOREAN_VOICES)
    if tts_voice_name and tts_voice_name not in voice_ids:
        voice_ids.insert(0, tts_voice_name)

    voice_options = []
    voice_map = {}

    current_voice_display = ""

    for v_id in voice_ids:
        used = None if usage_now is None else usage_now.get(tts_usage.usage_kind(v_id), 0)
        display_str = tts_usage.voice_label(v_id, used, get_msg("voice_price"), get_msg("voice_usage"))
        if display_str in voice_map:   # 다른 언어의 같은 이름(en-US-Chirp3-HD-Zephyr 등)이 저장돼 있으면 구분
            display_str = f"{display_str} [{v_id}]"
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
        sel_voice_id = voice_map.get(selected_disp, DEFAULT_VOICE)
        # 속도는 지금 저장된 값(하단 바 목록에서 고른 값 — 2026-10-24 설정 창에서 속도 칸을 뺐다)
        # 지금 속도로 들려준다. 서버 허용이 0.25~4.0 이라(2026-10-28 속도 범위가 5배까지 늘어남) 미리듣기만 4.0 에서 자른다
        sel_rate = min(tts_speaking_rate, 4.0)

        text = "안녕하세요. 이 목소리로 글을 읽어 드립니다."   # Paseo PREVIEW_TEXT.ko 와 같은 말(2026-11-01 설정 맞추기)

        def _preview():
            # (별도 스레드) 네트워크 요청이 Tk 메인을 멈추지 않게 따로 돈다. 여기서는 Tk 를 만지지 않는다.
            # 속도는 sel_rate 그대로(Cloud TTS 허용 0.25~4.0 안이어야 한다 — 읽기는 늘 1.0 으로 합성), 언어 코드는 ko-KR 고정(한국어 음성 목록뿐).
            try:
                if not google_tts_client:
                    log_to_console("TTS 클라이언트 미초기화")
                    return

                synthesis_input = google_tts.SynthesisInput(text=text)
                voice = google_tts.VoiceSelectionParams(language_code="ko-KR", name=sel_voice_id)
                audio_config = google_tts.AudioConfig(audio_encoding=google_tts.AudioEncoding.LINEAR16, sample_rate_hertz=24000, speaking_rate=sel_rate)

                response = google_tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
                _count_tts_usage(sel_voice_id, text)   # 미리 듣기도 Google 이 매긴다 — 읽기와 같이 센다(2026-11-01)

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


    # 2. 재생 속도 — 속도 간격만 (2026-10-24 사용자 결정: 속도는 하단 바 닫기 버튼 옆 목록에서 고른다.
    #    여기서는 간격만 정한다 — 2026-10-28 Paseo 기준으로 0.1 → 0.5~2배, 0.25 → 0.5~5배, 처음 0.1)
    rate_frame = ttk.Labelframe(dialog, text=get_msg("label_speaking_rate"), padding=15)
    rate_frame.pack(fill="x", **padding)

    rate_row = ttk.Frame(rate_frame)
    rate_row.pack(fill="x", pady=5)

    ttk.Label(rate_row, text=get_msg("label_rate_step")).pack(side="left", padx=5)

    def _step_text(step):
        # "0.1  (0.5x ~ 2x)" — 간격과 그 간격의 속도 범위를 같이 보인다(목록에는 1배 이상만 보이고 1배 아래는 Ctrl+↓ 로)
        lo, hi = tts_engine.RATE_STEPS[step]
        return f"{step:g}  ({tts_engine.format_rate(lo)} ~ {tts_engine.format_rate(hi)})"

    step_by_text = {_step_text(step): step for step in tts_engine.RATE_STEPS}
    step_var = tk.StringVar(value=_step_text(tts_engine.normalize_rate_step(tts_rate_step)))
    step_combo = ttk.Combobox(rate_row, textvariable=step_var, values=list(step_by_text),
                              state="readonly", width=22)
    step_combo.pack(side="left", padx=5)

    def current_step():
        return step_by_text.get(step_var.get(), tts_engine.DEFAULT_RATE_STEP)

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

    # 4. 일반 — 언어·인증 설정·콘솔 창 열기 (2026-09-28 사용자 결정: 트레이에서 이 창으로 옮김. README 열기는 없앰)
    general_frame = ttk.Labelframe(dialog, text=get_msg("group_general"), padding=15)
    general_frame.pack(fill="x", **padding)

    # 언어: 라디오 두 개. 이름은 그 언어 자신의 표기(한국어 / English)로 둔다 — 어느 언어 화면에서도 알아보게
    lang_row = ttk.Frame(general_frame)
    lang_row.pack(fill="x", pady=5)
    ttk.Label(lang_row, text=get_msg("label_language")).pack(side="left", padx=5)
    lang_var = tk.StringVar(value=current_language if current_language in ("ko", "en") else "ko")
    ttk.Radiobutton(lang_row, text=get_msg("language_name_ko"), value="ko", variable=lang_var).pack(side="left", padx=5)
    ttk.Radiobutton(lang_row, text=get_msg("language_name_en"), value="en", variable=lang_var).pack(side="left", padx=5)

    # 주 언어(= 음성 언어)가 아닌 문장은 번역해서 읽기 (2026-09-29 사용자 결정: 설정 창 체크, 기본 켬).
    # 트레이는 5항목 고정(2026-09-28 사용자 결정)이라 여기에만 둔다. 다른 값처럼 "저장" 을 눌러야 바뀐다.
    translate_var = tk.BooleanVar(value=translate_enabled)
    ttk.Checkbutton(general_frame, text=get_msg("label_translate_foreign"),
                    variable=translate_var).pack(anchor="w", padx=5, pady=5)
    # 번역문을 원문 위 막으로 표시 (2026-09-29 사용자 결정: 옵션, 기본 켬). 번역에 딸린 옵션이라 한 칸 들여 둔다
    overlay_var = tk.BooleanVar(value=translation_overlay_enabled)
    ttk.Checkbutton(general_frame, text=get_msg("label_translate_overlay"),
                    variable=overlay_var).pack(anchor="w", padx=(25, 5), pady=(0, 5))

    def open_credentials():
        """"인증 설정" 버튼: 옛 트레이 "Google Cloud 인증 설정" 과 같은 창(show_api_key_dialog, 필수 아님)을 연다.

        그 창은 모달(grab_set + wait_window)이라 닫힐 때까지 이 함수가 돌아오지 않는다(그동안 Tk 이벤트는 돈다).
        이 설정 창은 뒤에 그대로 남는다. 인증 파일은 그 창의 "설정" 이 바로 저장한다(이 창의 저장과 무관).
        """
        show_api_key_dialog(required=False)

    tool_row = ttk.Frame(general_frame)
    tool_row.pack(fill="x", pady=5)
    ttk.Button(tool_row, text=get_msg("btn_credentials"), command=open_credentials,
               bootstyle="info-outline").pack(side="left", padx=5)
    ttk.Button(tool_row, text=get_msg("open_console"), command=open_console_window,
               bootstyle="secondary-outline").pack(side="left", padx=5)
    # 세 곳(Paseo·이 앱·크롬 확장) 이번 달 읽기 사용량 창(2026-11-01). 트레이는 5항목 고정이라 여기에 둔다
    ttk.Button(tool_row, text=get_msg("btn_usage"), command=lambda: show_usage_dialog(anchor=_window_center(dialog)),
               bootstyle="info-outline").pack(side="left", padx=5)

    # 5. 저장 버튼 (미리듣기는 위로 이동함)
    button_frame = ttk.Frame(dialog)
    button_frame.pack(side="bottom", fill="x", pady=20)

    # (미리듣기 버튼 제거됨)

    def save_tts_settings_action():
        """"저장" 버튼: 창의 값을 전역 설정에 넣고 파일에 저장한 뒤 창을 닫는다.

        글자 칸이 비면 단축키 글자를 None 으로 둔다(→ 단축키가 꺼진다). 음성을 못 찾으면 기본값 DEFAULT_VOICE(Zephyr).
        언어가 바뀌었으면 _apply_language 가 전역 언어를 바꾸고 트레이 문구를 새 언어로 다시 만든다. 저장은 아래 한 번.
        """
        global tts_hotkey_modifiers, tts_hotkey_key, tts_voice_name, tts_speaking_rate, translate_enabled
        global translation_overlay_enabled, tts_rate_step

        tts_hotkey_modifiers["ctrl"] = ctrl_var.get()
        tts_hotkey_modifiers["shift"] = shift_var.get()
        tts_hotkey_modifiers["alt"] = alt_var.get()
        k = key_var.get().strip().upper()
        tts_hotkey_key = k if k else None

        selected_disp = voice_var.get()
        tts_voice_name = voice_map.get(selected_disp, DEFAULT_VOICE)
        # 간격이 바뀌면 지금 속도를 새 목록의 가장 가까운 값으로 맞추고(가운데면 빠른 쪽) 하단 바 목록도 바꾼다(2026-10-24).
        # 읽는 중이면 맞춘 속도를 바로 반영한다. 음성은 읽기마다 정해지므로 다음 읽기부터 바뀐다.
        tts_rate_step = current_step()
        snapped = tts_engine.snap_rate(tts_speaking_rate, tts_rate_step)
        if snapped != tts_speaking_rate:
            tts_speaking_rate = snapped
            if tts_session is not None:
                try:
                    tts_session.set_rate(tts_speaking_rate)
                except Exception:
                    pass
        _refresh_bar_rate_choices()

        _apply_language(lang_var.get())
        # 번역은 읽기를 시작할 때 정해지므로 다음 읽기부터 적용된다(읽는 중인 세션은 그대로)
        translate_enabled = bool(translate_var.get())
        # 막 표시는 다음 조각부터 바로 적용된다(조각이 바뀔 때마다 _caption_for 가 이 값을 본다)
        translation_overlay_enabled = bool(overlay_var.get())

        save_settings()
        _refresh_usage_views()   # 목소리 종류가 바뀌었으면 알약도 그 종류로(2026-11-01)

        log_to_console(get_msg("tts_hotkey_updated"))
        # 토스트 알림 (messagebox 대신)
        try:
            from ttkbootstrap.toast import ToastNotification
            ToastNotification(title="설정 저장", message="TTS 설정이 저장되었습니다.", duration=2000, bootstyle="success").show_toast()
        except: pass
        dialog.destroy()

    ttk.Button(button_frame, text=get_msg("save"), command=save_tts_settings_action, width=10, bootstyle="success").pack(side="right", padx=20)
    ttk.Button(button_frame, text=get_msg("cancel"), command=dialog.destroy, width=10, bootstyle="secondary").pack(side="right", padx=10)

    # 창 크기를 내용에 맞춘다: "일반" 묶음이 늘어 옛 고정 높이(550)로는 아래 저장 버튼 줄이 눌려 잘릴 수 있다.
    # (pack 은 창이 모자라면 나중에 넣은 위젯부터 줄인다 — 저장 버튼 줄이 가장 먼저 사라진다)
    try:
        dialog.update_idletasks()
        req_w = max(650, dialog.winfo_reqwidth())
        req_h = max(550, dialog.winfo_reqheight())
        dialog.geometry(f"{req_w}x{req_h}")
    except Exception:
        pass
    # 창 크기 자동 조절 및 강제 업데이트 (렌더링 문제 해결)
    dialog.update()


# ════════════════════════════════════════════════════════════════════
# 읽기 사용량 — 세 곳(Paseo·이 앱·크롬 확장) 요금 브리지 (2026-11-01, 계산은 tts_usage.py)
# ════════════════════════════════════════════════════════════════════

def _usage_time_text(value):
    """UTC datetime 또는 ISO 문자열 → 이 PC 시각 "11-01 16:05". 못 읽으면 "?"."""
    try:
        if isinstance(value, str):
            value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value.astimezone().strftime("%m-%d %H:%M")
    except Exception:
        return "?"


def _usage_counts_text(counts):
    """{"chirp3hd": 12345, "wavenet": 0} → "Chirp 3 HD 12,345 · WaveNet 0" (늘 보이는 두 종류 + 값이 있는 다른 종류)."""
    kinds = list(tts_usage.SHOWN_KINDS) + sorted(k for k in counts if k not in tts_usage.SHOWN_KINDS
                                                 and k not in tts_usage.IGNORED_KINDS and counts.get(k))
    return " · ".join(f"{tts_usage.KIND_NAME.get(k, k)} {tts_usage.group_digits(counts.get(k, 0))}" for k in kinds)


def _window_center(win):
    """Tk 창 가운데 화면 좌표 (x, y). 못 구하면 None."""
    try:
        return (win.winfo_rootx() + win.winfo_width() // 2, win.winfo_rooty() + win.winfo_height() // 2)
    except Exception:
        return None


def _monitor_area(point):
    """(x, y) 가 있는 모니터의 작업 영역 (왼, 위, 오른, 아래). 모르면 None(빨간 점 모듈의 Win32 도우미를 빌린다)."""
    if not point or _selection_button_mod is None:
        return None
    try:
        return _selection_button_mod._work_area_at(*point)
    except Exception:
        return None


def _center_on_monitor(win, anchor):
    """창을 anchor (x, y) 가 있는 모니터의 작업 영역 가운데로 옮긴다(2026-11-01 리규형님 "알약이 있는 모니터에").
    모니터를 모르면 그대로 둔다."""
    area = _monitor_area(anchor)
    if not area:
        return
    try:
        win.update_idletasks()
        w = max(win.winfo_reqwidth(), win.winfo_width())
        h = max(win.winfo_reqheight(), win.winfo_height())
        left, top, right, bottom = area
        win.geometry(f"+{left + max(0, (right - left - w) // 2)}+{top + max(0, (bottom - top - h) // 2)}")
    except Exception as e:
        logging.debug(f"창 자리 옮기기 실패: {e}")


def _place_near(win, rect):
    """떠 있는 창을 알약 사각형 (x, y, w, h) 바로 위에 붙인다(오른쪽 끝 맞춤 — usage_pill.popup_position).
    제목 표시줄·테두리까지 친 바깥 크기는 떠 있는 창에서 잰다(winfo_rootx/y 와 winfo_x/y 의 차)."""
    if _pill_popup_position is None:
        return
    try:
        win.update_idletasks()
        side = max(0, win.winfo_rootx() - win.winfo_x())
        title = max(0, win.winfo_rooty() - win.winfo_y())
        size = (win.winfo_width() + 2 * side, win.winfo_height() + title + side)
        gap = int(round(_PILL_POPUP_GAP_PX * float(root.winfo_fpixels("1i")) / 96.0))
        center = (rect[0] + rect[2] // 2, rect[1] + rect[3] // 2)
        x, y = _pill_popup_position(rect, size, _monitor_area(center), gap)
        win.geometry(f"+{x}+{y}")
    except Exception as e:
        logging.debug(f"알약 위에 창 붙이기 실패: {e}")


def _show_placed(win, anchor=None, near=None):
    """숨겨 만든 창을 자리 잡아 보인다. near(알약 사각형)면 그 위에, anchor 면 그 점의 모니터 가운데, 둘 다 없으면 Tk 기본 자리.
    near 는 바깥 크기를 재야 해서 투명하게 띄워 옮긴 뒤 보인다(일반 창이라 -alpha 를 써도 된다 — 금지는 NOACTIVATE 창)."""
    if near:
        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            pass
        win.deiconify()
        _place_near(win, near)
        try:
            win.attributes("-alpha", 1.0)
        except Exception:
            pass
    else:
        _center_on_monitor(win, anchor)
        win.deiconify()


def show_usage_dialog(anchor=None, near=None):
    """설정 창 "읽기 사용량" 버튼: 세 곳의 이번 결제 달 읽기 사용량을 종류별로 합쳐 보인다(2026-11-01 리규형님 지시 —
    "한 곳에서 세 곳 사용량을 볼 수 있게, PC 앱에서"). 무료분 대비 남은 양, 넘쳤으면 넘친 글자와 그 값(달러).
    자리(2026-11-01 리규형님 "알약이 있는 모니터에 — 자꾸 다른 모니터에 뜬다" + 스크린샷 "이런 식으로"):
      near = 알약 (x, y, w, h) → 알약 바로 위, 오른쪽 끝 맞춤(이미 열려 있어도 다시 붙인다).
      anchor = (x, y) → 그 점의 모니터 가운데(설정 창 버튼 = 설정 창 가운데. 이미 열려 있으면 다른 모니터일 때만 옮긴다).

    ⚠️ Tk 메인 스레드에서만. 이미 열려 있으면 앞으로 올린다. 기록 파일 셋(작다)을 열 때·[새로고침] 때·열려 있는 동안
    USAGE_TICK_MS 마다·이 앱이 세거나 확장 값을 받을 때 다시 읽고, 값이 달라졌을 때만 다시 그린다(_refresh_usage_views)
    (Paseo 파일은 Paseo PC 데몬이 5분마다 새로 쓴다). 알약을 눌러도 이 창이 뜬다(2026-11-01).
    숫자는 세 곳이 스스로 센 값 — 실제 청구는 Google 결제 화면이 정본.
    """
    existing = getattr(show_usage_dialog, "dialog", None)
    if existing is not None and existing.winfo_exists():
        if near:
            _place_near(existing, near)
        elif anchor and _monitor_area(_window_center(existing)) != _monitor_area(anchor):
            _center_on_monitor(existing, anchor)
        existing.lift()
        return

    import tkinter.font as tkfont
    dialog = ttk.Toplevel(root)
    dialog.withdraw()   # 자리를 잡은 뒤 보인다(_show_placed) — 다른 모니터 기본 자리에 잠깐 떴다 옮겨 가지 않게
    dialog.title(get_msg("usage_title"))
    dialog.resizable(False, False)
    _dark_title_bar(dialog)
    try:
        icon_path = _favicon_path()
        if icon_path:
            dialog.iconbitmap(icon_path)
    except Exception:
        pass
    show_usage_dialog.dialog = dialog
    bold = tkfont.nametofont("TkDefaultFont").copy()
    bold.configure(weight="bold")
    dialog._bold_font = bold   # 창이 붙들고 있어야 폰트가 사라지지 않는다

    body = ttk.Frame(dialog, padding=20)
    body.pack(fill="both", expand=True)

    def collect():
        month = tts_usage.billing_month()
        paseo = tts_usage.read_paseo_usage(month)
        ext_rows = extension_usage_reports.month_by_source(month)
        summary = tts_usage.summarize(tts_usage_counter.month_counts(month), paseo, ext_rows, month)
        receiver_port = usage_receiver.port if usage_receiver is not None and usage_receiver.running else None
        return month, paseo, ext_rows, summary, receiver_port

    def fill(data):
        month, paseo, ext_rows, summary, receiver_port = data
        for child in body.winfo_children():
            child.destroy()
        columns = 7

        row = 0
        ttk.Label(body, text=get_msg("usage_heading").format(month), font=bold).grid(
            row=row, column=0, columnspan=columns, sticky="w")
        row += 1
        start = tts_usage.month_start_utc(month)
        end = tts_usage.month_start_utc(tts_usage.next_month(month))
        ttk.Label(body, text=get_msg("usage_period").format(_usage_time_text(start), _usage_time_text(end))).grid(
            row=row, column=0, columnspan=columns, sticky="w", pady=(2, 12))

        row += 1
        heads = ("usage_col_kind", "usage_col_paseo", "usage_col_app", "usage_col_extension",
                 "usage_col_total", "usage_col_free", "usage_col_left")
        for col, key in enumerate(heads):
            ttk.Label(body, text=get_msg(key), font=bold).grid(
                row=row, column=col, sticky="w" if col == 0 else "e", padx=(0 if col == 0 else 14, 0))
        for k in summary["kinds"]:
            row += 1
            name = k["name"] + (f" ({get_msg('voice_price').format(k['price'])})" if k["price"] else "")
            if k["free"] is None:
                left, style = "—", None
            elif k["over"]:
                cost = f"{k['cost']:.2f}" if k["cost"] is not None else "?"
                left, style = get_msg("usage_over").format(tts_usage.group_digits(k["over"]), cost), "danger"
            else:
                left, style = get_msg("usage_left").format(tts_usage.group_digits(k["left"])), "success"
            cells = (name,
                     "—" if k["paseo"] is None else tts_usage.group_digits(k["paseo"]),
                     tts_usage.group_digits(k["app"]),
                     tts_usage.group_digits(k["extension"]),
                     tts_usage.group_digits(k["total"]),
                     "—" if k["free"] is None else tts_usage.group_digits(k["free"]),
                     left)
            for col, text in enumerate(cells):
                opts = {"bootstyle": style} if col == len(cells) - 1 and style else {}
                ttk.Label(body, text=text, **opts).grid(
                    row=row, column=col, sticky="w" if col == 0 else "e", padx=(0 if col == 0 else 14, 0), pady=2)

        row += 1
        ttk.Separator(body).grid(row=row, column=0, columnspan=columns, sticky="ew", pady=12)

        lines = []
        state = paseo.get("state")
        if state == "ok":
            lines.append(get_msg("usage_paseo_ok").format(_usage_time_text(paseo.get("updatedAt"))))
            for host in sorted(paseo["sources"], key=lambda h: (h != "PC", h)):
                lines.append(f"    {host}: {_usage_counts_text(paseo['sources'][host])}")
            if paseo["stale"]:
                lines.append(get_msg("usage_paseo_stale").format(", ".join(paseo["stale"])))
        elif state == "other_month":
            lines.append(get_msg("usage_paseo_other_month").format(paseo.get("month"), _usage_time_text(paseo.get("updatedAt"))))
        elif state == "broken":
            lines.append(get_msg("usage_paseo_broken"))
        else:
            lines.append(get_msg("usage_paseo_missing"))
        lines.append(get_msg("usage_app_note"))
        if ext_rows:
            lines.append(get_msg("usage_ext_heading"))
            # 같은 이름이 여럿이면(어사이드는 프로필마다 "Chromium") 설치 구분 글자 앞 8자를 덧붙여 가른다(2026-11-01)
            label_count = {}
            for r in ext_rows:
                label_count[r["label"]] = label_count.get(r["label"], 0) + 1
            for r in ext_rows:
                name = r["label"] or r["source"][:8]
                if r["label"] and label_count[r["label"]] > 1:
                    name = f"{r['label']} ({r['source'][:8]})"
                lines.append(get_msg("usage_ext_row").format(name, _usage_counts_text(r["counts"]),
                                                             _usage_time_text(r["updatedAt"])))
        else:
            lines.append(get_msg("usage_ext_none"))
        if receiver_port is not None:
            lines.append(get_msg("usage_receiver_on").format(f"{tts_usage.RECEIVER_HOST}:{receiver_port}"))
        else:
            lines.append(get_msg("usage_receiver_off"))
        for text in lines:
            row += 1
            ttk.Label(body, text=text).grid(row=row, column=0, columnspan=columns, sticky="w", pady=1)
        row += 1
        ttk.Label(body, text=get_msg("usage_note"), wraplength=640, justify="left").grid(
            row=row, column=0, columnspan=columns, sticky="w", pady=(12, 0))

        row += 1
        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=columns, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text=get_msg("usage_close"), command=dialog.destroy, width=10,
                   bootstyle="secondary").pack(side="right", padx=(10, 0))
        # 새로고침 = 이 창과 알약을 함께(2026-11-01 — 창만 바뀌고 알약은 다음 5초 주기까지 옛 숫자였다)
        ttk.Button(buttons, text=get_msg("usage_refresh"), command=lambda: (refresh(force=True), _refresh_usage_pill()),
                   width=10, bootstyle="info-outline").pack(side="right")

    last = {"key": None}

    def refresh(force=False):
        """값을 다시 모아 달라졌을 때만 다시 그린다(5초마다 불려도 깜빡이지 않게 — _refresh_usage_views)."""
        data = collect()
        key = json.dumps(data, sort_keys=True, default=str)
        if force or key != last["key"]:
            last["key"] = key
            fill(data)

    dialog._usage_refresh = refresh
    refresh(force=True)
    _show_placed(dialog, anchor, near)
    _schedule_usage_tick()


def setup_usage_receiver():
    """크롬 확장이 이번 달 읽기 사용량을 보내는 받는 창구(127.0.0.1:51888 TCP)를 띄운다(2026-11-01, tts_usage.UsageReceiver).

    포트를 못 열면 로그만 남기고 넘어간다(읽기와 무관 — 사용량 창에 "열지 못했습니다" 로 보인다).
    콘솔에는 확장 설치(source)마다 이 앱이 켜진 뒤 처음 받을 때 한 줄 — source 앞 8자·label·이번 달 숫자만(글·주소 없음).
    """
    global usage_receiver
    seen = set()
    rejected = set()

    def on_report(source, label, months):
        # 받는 창구 스레드에서 불린다 — Tk 를 만지지 않는다(알약·사용량 창은 gui_queue 로)
        gui_queue.put("usage_changed")
        if source in seen:
            return
        seen.add(source)
        month = tts_usage.billing_month()
        counts = months.get(month, {}) if isinstance(months, dict) else {}
        log_to_console(f"[사용량] 크롬 확장 기록 받음: {label or '-'} ({source[:8]}) {month} {_usage_counts_text(counts)}")

    def on_reject(reason):
        # 거절 까닭 — 까닭마다 이 앱이 켜진 뒤 처음 한 번만(확장은 셀 때마다 보내 같은 줄이 쌓이지 않게). 값·주소는 안 남긴다
        if reason in rejected:
            return
        rejected.add(reason)
        log_to_console(f"[사용량] 크롬 확장 기록 거절: {reason}")

    usage_receiver = tts_usage.UsageReceiver(extension_usage_reports, on_report=on_report, log=log_to_console,
                                             on_reject=on_reject)
    if usage_receiver.start():
        log_to_console(f"[사용량] 크롬 확장 받는 창구: {tts_usage.RECEIVER_HOST}:{usage_receiver.port}")


# ── 사용량 알약 (usage_pill.py, 2026-11-01 리규형님 버튼) ──
# 트레이 왼쪽 클릭 = 켜고 끄기(켬 상태 저장) · 끌어 옮긴 자리 저장 · 누르면 show_usage_dialog.
# 글 = 지금 고른 목소리 종류의 세 곳 합계 "Chirp 3 HD 18,944 / 1,000,000자"(넘으면 빨강 + 넘친 글자·달러).
# 새로 고치는 때: 이 앱이 셀 때·확장 값을 받을 때 바로("usage_changed"), 그리고 떠 있는 동안 USAGE_TICK_MS 마다(Paseo 파일).

def _usage_pill_text():
    """지금 고른 목소리 종류의 세 곳 합계 → (알약 글, 무료분 넘음)."""
    month = tts_usage.billing_month()
    paseo = tts_usage.read_paseo_usage(month)
    summary = tts_usage.summarize(tts_usage_counter.month_counts(month), paseo,
                                  extension_usage_reports.month_by_source(month), month)
    row = tts_usage.pill_row(summary, tts_usage.usage_kind(tts_voice_name))
    texts = {k: get_msg("pill_" + k) for k in ("under", "over", "plain", "no_paseo")}
    return tts_usage.pill_text(row, paseo.get("state") == "ok", texts)


def _usage_dialog_open():
    dialog = getattr(show_usage_dialog, "dialog", None)
    try:
        return dialog is not None and bool(dialog.winfo_exists())
    except Exception:
        return False


def _refresh_usage_pill():
    """알약이 떠 있으면 지금 값으로 고친다. Tk 메인 전용."""
    if usage_pill is not None and usage_pill.visible:
        try:
            usage_pill.set_text(*_usage_pill_text())
        except Exception as e:
            logging.warning(f"사용량 알약 갱신 실패: {e}")


def _refresh_usage_views():
    """알약(떠 있으면)과 사용량 창(열려 있으면)을 지금 값으로 고친다. Tk 메인 전용."""
    _refresh_usage_pill()
    if _usage_dialog_open():
        try:
            show_usage_dialog.dialog._usage_refresh()
        except Exception as e:
            logging.warning(f"사용량 창 갱신 실패: {e}")


def _schedule_usage_refresh():
    """"usage_changed" 가 몰려 와도(읽는 조각마다) 한 번만 다시 읽는다. Tk 메인 전용."""
    global _usage_refresh_pending
    if _usage_refresh_pending or not root:
        return
    _usage_refresh_pending = True

    def run():
        global _usage_refresh_pending
        _usage_refresh_pending = False
        _refresh_usage_views()
    root.after_idle(run)


_usage_tick_scheduled = False


def _schedule_usage_tick():
    """알약이나 사용량 창이 떠 있는 동안 USAGE_TICK_MS 마다 다시 읽게 한다(이미 돌고 있으면 그대로). Tk 메인 전용."""
    global _usage_tick_scheduled
    if _usage_tick_scheduled or not root:
        return
    _usage_tick_scheduled = True
    root.after(USAGE_TICK_MS, _usage_tick)


def _usage_tick():
    global _usage_tick_scheduled
    _usage_tick_scheduled = False
    if not ((usage_pill is not None and usage_pill.visible) or _usage_dialog_open()):
        return   # 둘 다 닫혔으면 멈춘다 — 다시 띄울 때 _schedule_usage_tick 이 다시 건다
    _refresh_usage_views()
    _schedule_usage_tick()


def _apply_usage_pill():
    """usage_pill_visible 에 맞춰 알약을 띄우거나 숨긴다(처음 띄울 때 창을 만든다). Tk 메인 전용."""
    global usage_pill
    if not usage_pill_visible:
        if usage_pill is not None:
            usage_pill.hide()
        return
    if UsagePill is None:
        log_to_console(f"[사용량] 알약을 띄울 수 없습니다(모듈 오류): {_usage_pill_import_error}")
        return
    if usage_pill is None:
        try:
            usage_pill = UsagePill(root, on_click=_open_usage_from_pill, on_moved=_usage_pill_moved)
        except Exception as e:
            log_to_console(f"[사용량] 알약 창을 만들지 못했습니다: {e}")
            return
    usage_pill.set_text(*_usage_pill_text())
    usage_pill.show(tuple(usage_pill_position) if usage_pill_position else None)
    _schedule_usage_tick()


def toggle_usage_pill():
    """트레이 왼쪽 클릭: 알약을 켜고 끈다. 켬 상태는 저장해 앱을 다시 켜도 유지한다. Tk 메인 전용(gui_queue "toggle_usage_pill")."""
    global usage_pill_visible
    usage_pill_visible = not usage_pill_visible
    _apply_usage_pill()
    save_settings()


def _open_usage_from_pill():
    """알약을 눌렀다 — 읽기 사용량 창을 알약 바로 위에(같은 모니터) 띄운다."""
    near = None
    if usage_pill is not None:
        try:
            near = usage_pill.rect()
        except Exception:
            near = None
    show_usage_dialog(near=near)


def _usage_pill_moved(x, y):
    """알약을 끌어 옮겨 놓은 자리를 기억한다(다음에 켤 때·앱을 다시 켤 때 그 자리)."""
    global usage_pill_position
    usage_pill_position = [int(x), int(y)]
    save_settings()


def setup_usage_pill():
    """앱을 켤 때 — 지난번에 알약을 켜 둔 채 끝냈으면 다시 띄운다."""
    if usage_pill_visible:
        _apply_usage_pill()


# ════════════════════════════════════════════════════════════════════
# TTS 재생 — 엔진은 tts_engine.py(TtsSession), 조각 나누기는 readaloud_text.py(split_for_reading)
#   옛 _preprocess_for_tts / _chunk_text_for_tts / _speak(producer·consumer) / _synthesize_chunk 는
#   2026-09-28 에 tts_engine.py·readaloud_text.py 로 옮기거나 대체했다.
# ════════════════════════════════════════════════════════════════════

# TTS 재생 관련 상태 변수
tts_playing = False   # 읽는 중인가 — 단축키 3방향 분기·트레이 메뉴가 이것으로 판정한다(is_speaking 아님)
tts_paused = False    # 지금 읽기가 일시정지인가 — 엔진 state 알림으로 갱신한다(하단 바 ⏯ 로 실제 일시정지된다)
tts_stop_event = threading.Event()  # 옛 파일 재생(play_tts_file) 전용. 읽기 엔진은 세션마다 자기 멈춤 신호를 쓴다
tts_current_file = None  # 현재 재생 파일 경로 (play_tts_file 전용 — 지금은 채우는 곳이 없다)
tts_session = None    # 지금 읽고 있는 tts_engine.TtsSession (없으면 None). Tk 메인 스레드에서만 바꾼다
# tts_session·tts_playing·tts_paused 를 "확인하고 고치기" 한 덩어리로 묶는 락.
# 왜 필요한가: 옛 읽기의 재생 스레드가 끝 알림(_make_tts_event_handler)에서 "내가 지금 세션이면 tts_playing=False"
#   를 하는 사이에, Tk 메인의 speak_text 가 새 세션을 넣고 tts_playing=True 로 만들면 → 옛 스레드가 뒤늦게 False 로
#   덮어써서 새 읽기가 재생 중인데도 "안 읽는 중" 으로 보였다(당시엔 플로팅 아이콘이 파랑·단축키가 "중지" 대신 "아이콘 숨김" 으로 갔다)
#   (2026-09-28 깨 보기, 확인과 대입 사이에 새 읽기를 끼워 넣어 재현 — tests/test_tts_engine.py TestWhispererGlue).
# ⚠️ 이 락을 쥔 채로 엔진 메서드(session.stop 등)나 UI 를 부르지 마라. 값만 읽고 쓰고 바로 놓는다.
_tts_state_lock = threading.Lock()

def stop_current_playback():
    """현재 재생 중인 오디오를 강제 중지합니다. 어느 스레드에서 불러도 된다(트레이 스레드에서도 불림).

    읽기는 session.stop() 이 세션 안에서 출력 스트림을 abort 한다(sd.stop() 은 OutputStream 을 못 멈춘다 — 06-07 §4).
    하단 바·리더 창 정리는 엔진이 보내는 session_end 알림을 Tk 메인 스레드가 받아서 한다(_handle_tts_event).
    ⚠️ 여기서 tts_stop_event 를 clear 하지 않는다. 읽기 엔진은 이 전역 신호를 쓰지 않는다(좀비 함정 — tts_engine.py 설명).

    세션을 꺼내는 일과 tts_playing=False 를 락 안에서 한 번에 한다(_tts_state_lock 설명 참고).
    다른 스레드의 정지(예전 트레이 "TTS 중지" — 지금은 트레이에 없다)와 Tk 메인의 새 읽기가 동시에 와도, 둘 중 먼저 락을 잡은 쪽 순서대로 일관되게 끝난다
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

    ⚠️ 죽은 코드: 부르던 곳은 트레이 toggle_tts 의 "마지막 파일 다시 재생" 뿐이었는데(tts_current_file 을 채우는 곳이 없어
       도달하지도 않았다), 2026-09-28 트레이에서 TTS 재생/중지 항목을 빼면서 부르는 곳이 아예 없어졌다.
       지우는 건 사용자 결정이라 남겨 두었다.
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
                            (읽던 창과 같은 화면에 바가 뜨게. 빨간 점은 WS_EX_NOACTIVATE 라 눌러도 전경을 뺏지 않는다)
      "primary"           — 주 모니터
    Win32: GetForegroundWindow → MonitorFromWindow(가까운 모니터) → GetMonitorInfoW 의 rcWork.
    ⚠️ ctypes.windll.user32 의 함수에 argtypes 를 걸면 앱 전체(다른 파일의 Win32 코드 등)에 영향이 가므로
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

def speak_text(text, hl_area=None):
    """선택한 글을 읽기 시작한다. ⚠️ Tk 메인 스레드에서만 부른다(read_selected_text 가 root.after 로 부름).

    hl_area(따라 읽기 창, 2026-10-28): (질의 번호, "para"|"all") — 원문 위 형광펜을 지금 선택 대신 따라 읽기 질의가 잡은
    범위(문단 / 문단부터 글 끝까지)로 맞춘다(SourceHighlighter.begin area). None 이면 예전처럼 지금 선택.

    1) readaloud_text.split_for_reading — 확장 드래그 읽기와 같은 규칙으로 줄 단위 조각 + 원문 위치를 만든다.
       lang/voice_lang 은 음성 이름 앞 두 덩어리(ko-KR). 영어 단어 목록은 data/english-words.js.
    2) 앞 읽기를 멈추고(세션 abort), 하단 바를 붙일 모니터를 지금(전경 창 기준) 정한다.
    3) 새 TtsSession 을 만들어 시작한다. 합성은 Google Cloud TTS(make_google_synthesize), 출력은 sounddevice.
       새 세션은 앞 세션의 재생 스레드가 스트림을 닫을 때까지 기다린 뒤 비프음 → 재생한다(previous=).
       시작 직전에 원문 위 형광펜을 시작한다(_begin_source_highlight — 결과는 나중에 Tk 메인으로 온다).
    4) 엔진 알림 → gui_queue → _handle_tts_event 가 하단 바·형광펜(원문 위 또는 리더 창)을 움직인다.
    """
    global tts_session, tts_playing, tts_paused, _reading_work_area, _reading_segment_idx, _translation_lookup

    log_to_console(f"[TTS] speak_text 호출됨 (원본 길이: {len(text) if text else 0})")

    if not text or not text.strip():
        log_to_console("[TTS] 텍스트 없음")
        return

    if not google_tts_client or not google_tts:
        log_to_console("[TTS] 초기화 안됨")
        return

    lang = tts_engine.voice_lang_of(tts_voice_name)
    voice_type = tts_engine.voice_type_of(tts_voice_name)
    # 2026-10-28 Paseo 상태바 플러그인 기준(리규형님 지시): 빈 줄로 나눈 문단 단위로 읽고, 말할 글은 spoken_text 규칙,
    # 한 요청 2000바이트 이하(readaloud_text.split_paragraphs_for_reading). 형광펜·이전/다음은 문단 단위.
    # 번역(2026-09-29): 켜져 있고 음성 언어가 지원 대상(지금은 한국어)이면, 한글이 없는 문장이 든 문단은 나누지 않고
    # 변환 전 글(주소는 "URL" 로 가림)을 번역 경로로 보낸다(translation.mark_for_translation). 규칙은 translation.py 머리 설명.
    use_translation = translate_enabled and translation.supports(lang)
    try:
        words = _get_english_words()           # 영어 대문자 낱말 사전 읽기(2026-10-28 — 크롬 확장 speakNames)
        segments = readaloud_text.split_paragraphs_for_reading(
            text, lang, voice_type, keep_whole=translation.plan if use_translation else None, words=words)
        raw_texts = translation.mark_for_translation(segments) if use_translation else set()
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
        voice_for_usage = tts_voice_name   # 이 읽기의 목소리(설정 창에서 바꿔도 이 읽기는 이 목소리로 센다)
        synthesize = tts_engine.make_google_synthesize(
            google_tts_client, google_tts, tts_voice_name, log=log_to_console,
            on_sent=lambda sent: _count_tts_usage(voice_for_usage, sent))
        if raw_texts:
            # 번역 대상 조각만 번역 → 읽기용 변환 → 합성. 번역 실패는 SegmentFailed → 그 조각 차례에 멈추고 알림
            translator = gemini_translator or translation.MissingTranslator("번역기가 준비되지 않았습니다(인증 전)")
            # on_translated: 번역이 끝나면(합성 스레드) Tk 메인에 알려 지금 칠하는 조각을 번역문 막으로 다시 칠하게 한다.
            # box["session"] 은 아래에서 세션을 만든 뒤 채워진다 — 번역은 start() 뒤에야 일어나므로 늘 채워져 있다.
            spoken_lang = spoken_text.speech_lang(lang)
            synthesize = translation.make_translating_synthesize(
                synthesize, translator, lambda t: spoken_text.make_spoken_text(t, spoken_lang, words),
                raw_texts, log=log_to_console,
                on_translated=lambda t: gui_queue.put(("tts_event", box.get("session"), "translation_ready", t)))
            log_to_console(f"[번역] 번역할 문장이 있는 문단 {sum(1 for s in segments if s['text'] in raw_texts)}개")
        session = tts_engine.TtsSession(
            text, segments,
            synthesize,
            tts_engine.sounddevice_stream_factory(),
            _make_tts_event_handler(box),
            rate=tts_speaking_rate, volume=tts_volume, muted=False,   # 음소거는 읽기마다 풀린다(확장 page-ui-host.js:105)
            before_play=tts_engine.play_start_beep, previous=previous, log=log_to_console)
    except Exception as e:
        logging.error(f"읽기 세션 생성 오류: {e}")
        log_to_console(f"[TTS] 읽기 시작 오류: {e}")
        return
    box["session"] = session
    # 번역문 막(2026-09-29): 조각이 바뀔 때 _caption_for 가 이 세션의 번역문을 찾아 형광펜에 넘긴다(옛 세션 것은 안 씀)
    _translation_lookup = (session, synthesize.translated_of) if raw_texts else None
    # ⚠️ start() 전에 넣어야 session_start 알림이 "옛 세션"으로 버려지지 않는다.
    #    세 값을 락 안에서 한 번에 바꾼다 — 옛 세션의 끝 알림이 그 사이에 끼어 tts_playing 을 False 로 덮지 못하게.
    with _tts_state_lock:
        tts_session = session
        tts_playing = True
        tts_paused = False
    # 원문 위 형광펜: 선택이 아직 살아 있는 지금(Ctrl+C 바로 뒤) 그 앱의 선택 범위를 잡게 한다.
    # begin 은 요청만 넣고 곧바로 돌아온다(UIA 는 형광펜 전용 스레드). 소리는 이 결과를 기다리지 않는다.
    # ⚠️ tts_session 을 넣은 "뒤" 에 부른다 — 결과 처리(_on_source_highlight_result)가 "지금 세션인가" 로 걸러서.
    _begin_source_highlight(session, hl_area)
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
    """TTS 완전 중지 (단축키·하단 바 닫기·트레이에서 부름)"""
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
    (빨간 점 selection_button.py 와 같은 처리 — 읽던 창의 포커스를 뺏으면 Ctrl+C 가 엉뚱한 곳으로 간다).
    """
    global bottom_bar, reader_window, BottomBar, ReaderWindow
    if bottom_bar is None and BottomBar is not None and root is not None:
        try:
            # 설정(톱니) 버튼 없이, 닫기 옆에 속도 목록 버튼 — 볼륨은 늘 1.0(2026-10-24 사용자 결정)
            bottom_bar = BottomBar(root, _on_bar_command, get_msg, show_settings=False)
            _refresh_bar_rate_choices()
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

def _rate_menu_items():
    """하단 바 속도 목록 [(배속, 글자), ...] — Paseo 기준 rateOptions(2026-10-28): 1배부터 위로(0.1 → 1.0x~2x,
    0.25 → 1.0x~5x), 지금 속도가 1배보다 느리면 그 값 하나만 맨 앞에(1배 아래는 Ctrl+↓ 로만 내려간다)."""
    return [(c, tts_engine.format_rate(c)) for c in tts_engine.rate_choices(tts_rate_step, tts_speaking_rate)]

def _refresh_bar_rate_choices():
    """(Tk 메인) 하단 바에 지금 속도 목록을 넘긴다 — 바를 만든 직후, 속도를 바꾼 뒤(1배 아래 값이 바뀜), 설정 창에서 간격을 저장한 뒤."""
    if bottom_bar is not None and hasattr(bottom_bar, "set_rate_choices"):
        _safe_ui("하단 바 속도 목록", bottom_bar.set_rate_choices, _rate_menu_items())

def _step_rate(direction):
    """(Tk 메인) 속도 단축키 — 한 단계 느리게(-1, Ctrl+↓)·빠르게(+1, Ctrl+↑). 0.5배~최댓값에서 멈춘다(돌지 않음).

    2026-10-28 Paseo 기준(stepSpeed): 지금 값 ± 간격을 snap_rate 로(tts_engine.step_rate). 소리가 나는 동안에만
    (키 필터가 멈춘 동안은 이 키를 넘긴다). 바꾸는 길은 하단 바 목록에서 고른 것과 같다(_on_bar_command "setRate").
    """
    if tts_session is None:
        return
    cur = tts_engine.snap_rate(tts_speaking_rate, tts_rate_step)
    new = tts_engine.step_rate(cur, tts_rate_step, direction)
    if new == cur:
        return
    logging.info(f"[속도] 단축키 {'느리게' if direction < 0 else '빠르게'}: {cur} → {new}")
    _on_bar_command("setRate", new)

def _read_key_action(action):
    """(Tk 메인) 읽기 단축키(키 필터 win32_filter 가 넘김) — Paseo 상태바 플러그인 기준(2026-10-28 리규형님 지시).

    "toggle"(Ctrl+Space) 멈춤 ↔ 다시 시작 · "rewind"(Ctrl+←) 이전 문단 · "forward"(Ctrl+→) 다음 문단 ·
    "slower"(Ctrl+↓)·"faster"(Ctrl+↑) 한 단계. 멈춘 동안은 "toggle" 만 한다(키 필터와 같은 규칙 — 그 사이 멈췄을 때 대비).
    """
    if tts_session is None:
        return
    if action == "toggle":
        _on_bar_command("togglePause")
    elif tts_paused:
        return
    elif action in ("rewind", "forward"):
        _on_bar_command(action)
    elif action in ("slower", "faster"):
        _step_rate(-1 if action == "slower" else 1)

def _on_bar_command(cmd, value=None):
    """(Tk 메인) 하단 바 버튼 → 재생 엔진 명령. BottomBar(on_command) 가 부른다.

    cmd: "togglePause" | "stop" | "forward" | "rewind" | "mute" | "unmute" | "setRate"(value=배속)
    닫기(X) = "stop": 읽기 중지 + 바를 곧바로 숨김(확장 page-ui.js:582-585 도 바를 먼저 숨기고 stop 을 보낸다).
    "setRate" = 닫기 옆 속도 목록에서 골랐다(2026-10-24 사용자 결정 — 속도는 여기서만 고른다). 지금 간격 목록 값으로 맞춰
        바로 반영하고 저장한다(설정 창 저장과 같은 효과, 2026-09-28 결정). 볼륨 명령(setVolume)은 없앴다 — 늘 1.0.
    """
    global tts_speaking_rate
    if cmd == "stop":
        if bottom_bar is not None:
            _safe_ui("하단 바 숨김", bottom_bar.hide)
        stop_tts()
        return
    session = tts_session
    if cmd == "setRate":
        tts_speaking_rate = tts_engine.snap_rate(value, tts_rate_step)
        if session is not None:
            session.set_rate(tts_speaking_rate)     # 즉시 반영(다음 0.1초 블록부터 — tts_engine 모듈 설명 "속도 즉시 반영")
        save_settings()
        _refresh_bar_rate_choices()                 # 1배 아래 값은 목록 맨 앞 한 칸이 지금 값을 따라간다(Paseo rateOptions)
        return
    if session is None:
        return
    if cmd in ("togglePause", "forward", "rewind", "mute", "unmute"):
        session.command(cmd)
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
    """(Tk 메인) 리더 창에 이번 읽기의 원문을 넣고 하단 바 바로 위에 띄운다. 꺼져 있거나 없으면 아무것도 안 한다.

    원문 위 형광펜이 이 읽기를 맡았거나(결과 ok) 결과를 기다리는 중이면 띄우지 않는다(2026-09-28 사용자 확정 —
    리더 창은 "원문 위에 칠할 수 없을 때만"). 부르는 곳 세 군데(session_start, 결과 ok=False, 트레이 켜기)가
    모두 여기를 거치므로 이 판정은 여기 한 곳에만 둔다.
    """
    if session is None or not reader_window_enabled:
        return
    if _source_highlight_blocks_reader(session):
        return
    _ensure_reading_ui()
    if reader_window is None:
        return
    _safe_ui("리더 창 시작", reader_window.start, session.source_text, _paragraphs_of(session)[0])
    bar_height = 0
    if bottom_bar is not None:
        try:
            bar_height = int(getattr(bottom_bar, "height", 0) or 0)
        except Exception:
            bar_height = 0
    _safe_ui("리더 창 표시", reader_window.show, _reading_work_area or _current_work_area(), bar_height,
             geometry=reader_window_geometry)
    para = _para_index(session, _reading_segment_idx)
    if para is not None:
        _safe_ui("형광펜", reader_window.highlight, para)

def _paragraphs_of(session):
    """(Tk 메인) 이 세션의 (문단 목록 [{"text", "src_start", "src_end"}], 조각 번호 → 문단 번호 표).

    2026-10-28 Paseo 상태바 플러그인 기준 — 읽는 문단에 형광펜. 엔진 조각(2000바이트 이하로 나눈 것)은 "para" 로 문단을
    알려 주고 원문 위치(src)는 문단 것이다. 형광펜(SourceHighlighter)·리더 창에는 문단 목록을 넘기고 문단 번호로 칠한다.
    "para" 가 없는 조각은 조각 하나 = 문단 하나(예전 동작).
    """
    global _reading_paragraphs
    if _reading_paragraphs is not None and _reading_paragraphs[0] is session:
        return _reading_paragraphs[1], _reading_paragraphs[2]
    paras, para_of = [], []
    last = None
    for i, seg in enumerate(getattr(session, "segments", None) or []):
        seg = seg if isinstance(seg, dict) else {}
        p = seg.get("para")
        if not isinstance(p, int) or isinstance(p, bool):
            p = ("piece", i)
        if not paras or p != last:
            paras.append({"text": seg.get("text") or "", "src_start": seg.get("src_start"), "src_end": seg.get("src_end")})
            last = p
        else:
            paras[-1]["text"] += " " + (seg.get("text") or "")
        para_of.append(len(paras) - 1)
    _reading_paragraphs = (session, paras, para_of)
    return paras, para_of

def _para_index(session, idx):
    """(Tk 메인) 조각 번호 → 문단 번호(형광펜·리더 창이 칠할 번호). 모르면 None."""
    if session is None or not isinstance(idx, int) or isinstance(idx, bool):
        return None
    para_of = _paragraphs_of(session)[1]
    return para_of[idx] if 0 <= idx < len(para_of) else None

def _hide_reading_ui():
    """(Tk 메인) 읽기가 끝났다 → 하단 바를 숨기고, 리더 창은 칠을 지우고 숨긴다."""
    if bottom_bar is not None:
        _safe_ui("하단 바 숨김", bottom_bar.hide)
    if reader_window is not None:
        _safe_ui("리더 창 끝", reader_window.end)

# ── 원문 위 형광펜 연결 (source_highlight.py, 2026-09-28) — 전부 Tk 메인 스레드 ─────────────────
# 흐름: speak_text → _begin_source_highlight(session) → SourceHighlighter.begin(원문, 조각, on_result)
#       → (형광펜 전용 UIA 스레드가 전경 앱의 선택 범위를 잡고 조각마다 원문 위치를 맞춤)
#       → on_result(ok, reason) 가 Tk 메인으로 온다 → _on_source_highlight_result
#       기다리는 동안("pending")에도 segment 번호는 SourceHighlighter.highlight 로 넘긴다(칠하지 않고 기억만 → 결과 ok 직후 칠함)
#       ok=True  → 상태 "on": 엔진 segment 알림마다 SourceHighlighter.highlight(idx). 리더 창은 안 띄움
#       ok=False → 상태 "off": 리더 창 사용이 켜져 있으면 리더 창(예전과 같음)
#       세션 끝 → _end_source_highlight → SourceHighlighter.end
# 상태는 전역 _source_hl_session(이 세션의 결과만 받음) + _source_hl_state 두 개로만 기억한다.
# ⚠️ 여기서는 UIA 를 직접 부르지 않는다. UIA 호출은 전부 SourceHighlighter 안의 전용 스레드에서만 한다
#    (VS Code 를 얼린 전례 — 전체 범위 호출 금지 규칙은 source_highlight.py 몫).

def _ensure_source_highlighter():
    """(Tk 메인) 원문 위 형광펜 객체를 처음 쓸 때 만든다. 만들다 실패하면 그 뒤로는 시도하지 않는다(로그 도배 방지).

    _ensure_reading_ui 와 같은 방식: 실패하면 클래스 전역을 None 으로 바꿔 둔다 → 앱을 다시 켤 때까지 리더 창만 쓴다.
    반환: 객체 또는 None.
    """
    global source_highlighter, SourceHighlighter
    if source_highlighter is None and SourceHighlighter is not None and root is not None:
        try:
            # on_stop(선택 인자, source_highlight.py 가 덧붙인 것): 읽는 도중 멈추면 이유를 콘솔에 남기려고만 넘긴다
            source_highlighter = SourceHighlighter(root, on_stop=_on_source_highlight_stop)
        except Exception as e:
            SourceHighlighter = None
            logging.error(f"원문 위 형광펜 생성 실패: {e}")
            log_to_console(f"[형광펜] 원문 위 형광펜을 만들지 못했습니다(리더 창으로만 보입니다): {e}")
    return source_highlighter

def _source_highlight_active():
    """(Tk 메인) 형광펜 객체의 active 속성(지금 원문 위 칠하기가 동작 중인가). 없거나 읽다 오류면 False."""
    hl = source_highlighter
    if hl is None:
        return False
    try:
        return bool(hl.active)
    except Exception:
        return False

def _source_highlight_blocks_reader(session):
    """(Tk 메인) 이 세션에서 리더 창을 띄우면 안 되는가 — 원문 위 형광펜이 결과를 기다리는 중("pending")이거나
    칠하는 중("on")이면 True. 안 쓰는 중(None)·못 칠함("off")이면 False(리더 창 규칙은 예전 그대로)."""
    return session is not None and session is _source_hl_session and _source_hl_state in ("pending", "on")

def _begin_source_highlight(session, area=None):
    """(Tk 메인, speak_text 가 부름) 이번 읽기의 원문 위 형광펜을 시작한다.

    - 앞 읽기가 쓰던 형광펜부터 끝낸다: 새 읽기가 앞 읽기를 대신하면 앞 세션의 session_end 는 "옛 세션" 이라 버려지므로
      (_handle_tts_event) 여기서 정리해야 앞 막이 남지 않는다.
    - 꺼져 있거나(source_highlight_enabled=False — 설정 파일로만 끔) 모듈·객체가 없으면 아무것도 안 한다
      → 상태 None → 리더 창은 예전처럼 session_start 때 뜬다.
    - begin 을 부르기 전에 상태를 "pending" 으로 둔다(결과가 혹시 begin 안에서 곧바로 와도 덮어쓰지 않게).
    - begin 이 예외를 내면 "off"(= 못 칠함 → 리더 창)로 본다.
    - 앞 읽기의 리더 창이 떠 있으면 숨긴다: 기다리는 동안엔 리더 창을 띄우지 않는 규칙인데, 그대로 두면 앞 글이 남아 보인다.
      (결과가 ok=False 로 오면 새 글로 다시 띄운다)
    """
    global _source_hl_session, _source_hl_state
    _end_source_highlight()
    if not source_highlight_enabled or session is None:
        return
    hl = _ensure_source_highlighter()
    if hl is None:
        return
    _source_hl_session = session
    _source_hl_state = "pending"

    def on_result(ok, reason=""):
        # SourceHighlighter 가 Tk 메인에서 부른다(약속: 내부에서 root.after 로 넘김). 어느 세션의 결과인지 붙여 넘긴다
        _on_source_highlight_result(session, ok, reason)

    try:
        if area is None:
            hl.begin(session.source_text, _paragraphs_of(session)[0], on_result)   # 문단 목록(2026-10-28)
        else:                                    # 따라 읽기 — 질의가 잡은 범위로(2026-10-28)
            hl.begin(session.source_text, _paragraphs_of(session)[0], on_result, area=area)
    except Exception as e:
        logging.error(f"원문 위 형광펜 시작 오류: {e}")
        log_to_console(f"[형광펜] 원문 위 형광펜을 시작하지 못했습니다(리더 창으로): {e}")
        if _source_hl_session is session:
            _source_hl_state = "off"
        return
    log_to_console("[형광펜] 원문 위 형광펜 준비 중 (결과가 올 때까지 리더 창은 띄우지 않습니다)")
    if reader_window is not None and _source_hl_session is session and _source_hl_state == "pending":
        _safe_ui("리더 창 끝", reader_window.end)

def _on_source_highlight_result(session, ok, reason=""):
    """(Tk 메인) SourceHighlighter.begin 의 결과. ok=True 면 원문 위에 칠하고, 아니면 리더 창(켜져 있으면)으로.

    - 지금 읽기(tts_session)이자 begin 을 부른 그 세션의 결과만 받는다. 새 읽기로 바뀐 뒤 늦게 온 옛 결과는 버린다.
    - ok=True: 상태 "on". 결과를 기다리는 사이 이미 지나간 조각은 여기서 다시 칠하지 않는다 — 기다리는 동안
      _handle_tts_event 가 그 번호를 SourceHighlighter.highlight 로 이미 넘겼고, SourceHighlighter 는 그 번호를 기억했다가
      이 콜백이 돌아온 직후 스스로 칠한다(source_highlight.py begin 설명·_handle "begin_ok").
      ⚠️ 여기서 highlight 를 또 부르면 같은 조각 사각형 조회·자동 스크롤 요청이 두 번 간다(2026-09-28 5차 깨 보기
      실측: 조각 0 에 reveal 요청 [True, True]) → 사용자 VS Code 에 UIA 호출만 는다.
    - ok=False: 상태 "off". 하단 바가 이미 떴으면(session_start 처리됨) 지금 리더 창을 띄운다.
      아직이면 session_start 가 띄운다(_show_reader_window 가 상태를 본다).
    - 한 번 ok=True 가 온 뒤에 ok=False 가 또 와도(약속엔 없지만) 같은 규칙으로 리더 창으로 넘어간다.
      (SourceHighlighter 는 읽는 도중 멈추면 on_result 가 아니라 on_stop 을 부른다 — 지금 on_stop 은 넘기지 않으므로
       도중에 멈추면 원문 위도 리더 창도 칠하지 않는다. 도중에 리더 창으로 넘길지는 사용자 결정 대기)
    """
    global _source_hl_state
    if session is None or session is not tts_session or session is not _source_hl_session:
        return
    ok = bool(ok)
    if ok:
        _source_hl_state = "on"
        log_to_console("[형광펜] 원문 위에 칠합니다 (리더 창은 띄우지 않음)")
        if reader_window is not None:
            # 보통은 이미 숨어 있다(기다리는 동안 안 띄움). ok=False 뒤에 ok=True 가 또 온 드문 경우에 떠 있던 리더 창을 거둔다
            _safe_ui("리더 창 끝", reader_window.end)
    else:
        _source_hl_state = "off"
        log_to_console(f"[형광펜] 원문 위에 칠할 수 없음 → 리더 창{'' if reader_window_enabled else '(꺼져 있음)'}: {reason}")
        if _reading_ui_session is session:
            _show_reader_window(session)

def _on_source_highlight_stop(reason=""):
    """(Tk 메인) SourceHighlighter 가 읽는 도중 원문 위 칠하기를 멈췄다(on_stop: "slow" 1초 넘는 호출 · "lost" 잡은 범위가
    사라짐(VS Code 가상 목록 등) · "target_closed" 대상 창 닫힘 · "error").

    지금은 콘솔에 이유만 남긴다 — 사용자가 VS Code 에서 시험할 때 "왜 칠하기가 멈췄는지" 를 보이게(형광펜 모듈의 로그는
    파일 로그에만 간다). 상태("on")는 바꾸지 않으므로 이 읽기의 남은 동안 원문 위도 리더 창도 칠하지 않는다(예전과 같음).
    ⚠️ 도중에 리더 창으로 넘길지는 사용자 결정 대기(2026-09-28 5차 보고). 넘기기로 하면 여기서
       _on_source_highlight_result(_source_hl_session, False, reason) 를 부르면 된다(같은 규칙 — 리더 창 사용이 켜져 있으면 띄움).
    end() 뒤에는 불리지 않는다(source_highlight.py 약속) → 늘 지금 읽기(_source_hl_session) 이야기다.
    """
    log_to_console(f"[형광펜] 읽는 도중 원문 위 칠하기를 멈췄습니다({reason}) — 이번 읽기는 형광펜 없이 계속 읽습니다")


def _end_source_highlight():
    """(Tk 메인) 원문 위 형광펜을 끝낸다(막 지우고 잡은 범위 놓기). 상태도 비운다. 시작한 적이 없으면 end 를 부르지 않는다."""
    global _source_hl_session, _source_hl_state
    began = _source_hl_session is not None
    _source_hl_session = None
    _source_hl_state = None
    hl = source_highlighter
    if began and hl is not None:
        _safe_ui("원문 형광펜 끝", hl.end)

def _handle_tts_event(session, kind, data):
    """(Tk 메인) 재생 엔진 알림 처리. check_gui_queue 가 부른다.

    지금 세션(tts_session)의 알림만 처리한다. 새 읽기가 옛 읽기를 대신한 뒤 도착한 옛 세션의 늦은 알림
    (특히 session_end)은 버린다 — 안 그러면 새 읽기의 하단 바·리더 창을 옛 세션이 숨겨 버린다.
    형광펜 (2026-09-28): 원문 위 형광펜이 "on" 이면 segment 마다 SourceHighlighter.highlight(idx),
      아니면 예전처럼 리더 창. 결과를 기다리는 동안("pending")은 리더 창을 칠하지 않고, 번호를
      SourceHighlighter.highlight 로 넘겨 둔다 — 결과 전에는 칠하지 않고 번호만 기억했다가 결과 ok 직후 스스로 칠한다
      (source_highlight.py begin 설명). begin 을 부른 뒤라야 한다(begin 앞 번호는 지워짐) — begin 은 session.start
      전에 불리고 segment 알림은 start 뒤에만 오므로 늘 begin 뒤다. _reading_segment_idx 에도 적어 둔다(결과가
      ok=False 면 _show_reader_window 가 그 번호로 리더 창을 칠한다).
    """
    global tts_session, _reading_segment_idx, _reading_ui_session, _translation_lookup, _reading_paragraphs, _painted_para
    if session is None or session is not tts_session:
        return
    if kind == "session_start":
        _ensure_reading_ui()
        if bottom_bar is not None:
            _safe_ui("하단 바 표시", bottom_bar.show, _reading_work_area or _current_work_area())
        _reading_ui_session = session
        _show_reader_window(session)   # 원문 위 형광펜이 기다리는 중·칠하는 중이면 안에서 건너뛴다
    elif kind == "segment":
        _reading_segment_idx = data
        caption = _caption_for(session, data)
        # 형광펜은 문단 번호로 칠한다(2026-10-28). 같은 문단의 다음 조각(2000바이트로 나뉜 것)이면 다시 칠하지 않는다 —
        # 같은 사각형 조회·자동 스크롤 요청이 또 가지 않게(UIA 호출을 늘리지 않는다)
        para = _para_index(session, data)
        repaint = para is not None and _painted_para != (session, para, caption)
        # 진단용(2026-09-29 Codex 분석 260929_211454): 실제로 읽기 시작한 조각 번호. 콘솔의 "조각 N/M 합성" 은
        # 미리 합성한 기록이라 재생 순서와 다르다 — 형광펜 로그와 같은 파일에 순서대로 남긴다
        logging.info(f"[형광펜] 재생 조각 {data + 1 if isinstance(data, int) else data} "
                     f"(문단 {para + 1 if para is not None else '?'}, 형광펜 상태 {_source_hl_state}, "
                     f"번역문 {'있음' if caption else '없음'})")
        if session is _source_hl_session and _source_hl_state == "on":
            if _source_highlight_active() and repaint:
                _painted_para = (session, para, caption)
                _safe_ui("원문 형광펜", source_highlighter.highlight, para, caption)
        elif session is _source_hl_session and _source_hl_state == "pending":
            if source_highlighter is not None and repaint:
                _painted_para = (session, para, caption)
                _safe_ui("원문 형광펜(결과 대기 중 번호 전달)", source_highlighter.highlight, para, caption)
        elif reader_window is not None and reader_window_enabled and not _source_highlight_blocks_reader(session):
            if para is not None:
                _safe_ui("형광펜", reader_window.highlight, para)
    elif kind == "state":
        if bottom_bar is not None:
            _safe_ui("하단 바 갱신", bottom_bar.update, data)
    elif kind == "translation_ready":
        # 번역이 방금 끝났다(data = 그 조각 글). 지금 칠하는(또는 결과를 기다리며 번호만 넘긴) 조각이 그 글이면
        # 번역문 막으로 다시 칠한다 — 첫 조각은 번역보다 칠하기가 먼저라 이게 없으면 노랑으로 남는다(2026-09-29 실사용).
        # 형광펜은 같은 번호에 번역문만 바뀌면 원문에 다시 묻지 않고 받아 둔 사각형으로 다시 그린다.
        idx = _reading_segment_idx
        if (isinstance(idx, int) and session is _source_hl_session and source_highlighter is not None
                and _source_hl_state in ("on", "pending")):
            try:
                same = session.segments[idx].get("text") == data
            except Exception:
                same = False
            caption = _caption_for(session, idx) if same else None
            para = _para_index(session, idx)
            if caption and para is not None:
                _painted_para = (session, para, caption)
                _safe_ui("원문 형광펜(번역문 도착)", source_highlighter.highlight, para, caption)
    elif kind == "segment_failed":
        # 번역 실패로 그 조각 차례에 읽기가 멈췄다(2026-09-29 사용자 결정 "읽기 멈추고 알림"). 정리는 곧 올 session_end 가 한다
        _notify_segment_failed(data)
    elif kind == "session_end":
        _end_source_highlight()
        _hide_reading_ui()
        if _translation_lookup is not None and _translation_lookup[0] is session:
            _translation_lookup = None      # 번역 결과(세션 캐시)를 놓는다
        with _tts_state_lock:
            tts_session = None
        _reading_segment_idx = None
        _reading_ui_session = None
        _reading_paragraphs = None
        _painted_para = None
        try:
            update_tray_menu()
        except Exception:
            pass

def _caption_for(session, idx):
    """(Tk 메인) idx 조각이 번역된 조각이면 원문 위 막에 쓸 번역문, 아니면 None(→ 노랑 형광펜).

    설정 "번역문을 원문 위에 막으로 표시"(translation_overlay_enabled)가 꺼져 있거나, 이 세션의 번역이 아니거나,
    아직 번역이 안 끝났으면 None. 번역은 합성 스레드가 2조각 앞서 하므로 조각 차례에는 보통 이미 있다.
    """
    if not translation_overlay_enabled or _translation_lookup is None:
        return None
    owner, lookup = _translation_lookup
    if owner is not session or not isinstance(idx, int):
        return None
    try:
        text = session.segments[idx].get("text")
        return lookup(text) if text else None
    except Exception:
        return None

def _notify_segment_failed(data):
    """(Tk 메인) 번역 실패로 읽기가 멈췄다고 경고 창으로 알린다(앱이 이미 쓰는 messagebox — 창이 포커스를 가져간다).

    창은 root.after 로 미뤄 연다 — 지금은 check_gui_queue 가 엔진 알림을 처리하는 중이라, 여기서 바로 모달 창을 열면
    뒤이은 session_end(하단 바 숨기기 등) 처리가 그 창 뒤로 밀린다.
    """
    data = data if isinstance(data, dict) else {}
    idx = data.get("index")
    reason = data.get("message") or ""
    log_to_console(f"[번역] 조각 {idx + 1 if isinstance(idx, int) else '?'} 번역 실패로 읽기를 멈춤: {reason}")
    root.after(0, lambda: messagebox.showwarning(get_msg("translate_failed_title"),
                                                 get_msg("translate_failed_body", reason)))

def toggle_reader_window():
    """(Tk 메인) 트레이 "리더 창 사용" 체크 켬/끔. 읽는 도중에 켜면 바로 띄우고, 끄면 바로 숨긴다. 설정에 저장한다.

    읽는 도중에 켜도 원문 위 형광펜이 그 읽기를 맡았거나 결과를 기다리는 중이면 띄우지 않는다(_show_reader_window 가 판단).
    """
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

# ── 따라 읽기 창 (2026-10-28 리규형님) ─────────────────────────────────────────
# 한 문단 안에서 고르고 읽기를 시작하면(단축키·빨간 점) "따라 읽기 할까요?" 를 묻는다. 일부만 골라도 그 문단 전체로 본다.
#   따라 읽기(Enter·기본) = 그 문단부터 지금 있는 글 끝까지 · 이 말만 읽기(바깥 클릭) = 그 문단만 · Esc = 아무것도 안 읽음.
# 여러 문단을 골랐거나, 글 요소가 없는 앱(텔레그램)·모를 때·원문 위 형광펜을 못 쓸 때는 묻지 않고 고른 글을 읽는다(예전 그대로).
# 문단과 아래 글은 클립보드가 아니라 원문 형광펜의 UIA 스레드가 가져온다(SourceHighlighter.query_follow_text).

def _close_follow_dialog():
    """(Tk 메인) 떠 있는 따라 읽기 창을 고르지 않고 닫는다. 기다리던 질의 결과도 버린다(_follow_ask_seq)."""
    global _follow_dialog, _follow_dialog_open, _follow_ask_seq
    _follow_ask_seq += 1
    dlg, _follow_dialog = _follow_dialog, None
    _follow_dialog_open = False
    if dlg is not None:
        try:
            dlg.close()
        except Exception as e:
            logging.debug(f"따라 읽기 창 닫기 실패: {e}")

def _follow_dialog_key(key):
    """(Tk 메인) 훅이 삼킨 Enter·Esc 를 떠 있는 창에 넘긴다."""
    dlg = _follow_dialog
    if dlg is not None:
        dlg.press_key(key)

# 따라 읽기 로그의 "멈춤" — SourceHighlighter.query_follow_text 결과 "stop"(2026-10-29)
_FOLLOW_STOP_TEXT = {"end": "글 끝", "time": "1초", "stop_above": "위로 튐", "stop_aside": "옆으로 비켜남"}

def _speak_or_ask_follow(text):
    """(Tk 메인, read_selected_text 가 부름) 고른 글을 읽는다 — 한 문단 안에서 골랐으면 먼저 따라 읽기 창을 띄운다."""
    global _follow_ask_seq
    _close_follow_dialog()
    hl = _ensure_source_highlighter() if source_highlight_enabled else None
    if FollowDialog is None or hl is None or not hasattr(hl, "query_follow_text"):
        speak_text(text)
        return
    if len(readaloud_text.split_paragraphs(text)) != 1:
        speak_text(text)                         # 여러 문단을 골랐다 — 묻지 않고 고른 것만(리규형님 10-28 버튼)
        return
    _follow_ask_seq += 1
    seq = _follow_ask_seq
    asked_at = time.monotonic()

    def done(result):
        if seq != _follow_ask_seq:
            return                               # 그사이 새 읽기·창 닫기 — 늦은 결과
        took = time.monotonic() - asked_at       # 문단·아래 글 가져오기(2026-10-28 창이 늦다는 보고 — 어디서 걸리는지 보려고)
        if not result or not result.get("inside") or not (result.get("para") or "").strip():
            why = "모름" if not result else ("한 문단 밖" if not result.get("inside") else "문단 글 없음")
            log_to_console(f"[따라 읽기] 묻지 않고 고른 글을 읽습니다({why} · {took:.2f}초)")
            speak_text(text)
            return
        stop = _FOLLOW_STOP_TEXT.get(result.get("stop"), result.get("stop") or "?")
        log_to_console(f"[따라 읽기] 창을 띄웁니다 — 틀={result.get('framework') or '?'} "
                       f"{'웹 문단 칸' if result.get('web') else '빈 줄 문단'} · 문단 {len(result['para'])}자 · "
                       f"끝까지 {len(result['all'])}자(아래 {result.get('pieces', 0)}조각"
                       f"{'' if result.get('complete') else ', 1초에서 끊음'}) · 멈춤 {stop}"
                       f" · 짧은 칸 건너뜀 {result.get('skipped', 0)} · 가져오기 {took:.2f}초")
        _show_follow_dialog(result, text)

    hl.query_follow_text(done)

def _show_follow_dialog(result, text):
    """(Tk 메인) 따라 읽기 창을 띄우고, 고르면 그 범위로 읽기를 시작한다(형광펜도 그 범위 — begin area)."""
    global _follow_dialog, _follow_dialog_open

    def choose(choice):
        global _follow_dialog, _follow_dialog_open
        if _follow_dialog is dlg:
            _follow_dialog = None
            _follow_dialog_open = False
        if choice == "follow":
            log_to_console("[따라 읽기] 따라 읽기 — 그 문단부터 글 끝까지")
            speak_text(result["all"], hl_area=(result["id"], "all"))
        elif choice == "only":
            log_to_console("[따라 읽기] 이 말만 읽기 — 그 문단만")
            speak_text(result["para"], hl_area=(result["id"], "para"))
        else:
            log_to_console("[따라 읽기] 닫음 — 읽지 않습니다")

    try:
        dlg = FollowDialog(root, get_msg("follow_prompt"), get_msg("follow_ok"), get_msg("follow_only"), choose)
        _follow_dialog = dlg
        dlg.show(_current_work_area())
        _follow_dialog_open = dlg.is_open
    except Exception as e:
        logging.error(f"따라 읽기 창 오류: {e}")
        log_to_console(f"[따라 읽기] 창을 띄우지 못해 고른 글을 읽습니다: {e}")
        _follow_dialog = None
        _follow_dialog_open = False
        speak_text(text)

COPY_WAIT_S = 0.5     # Ctrl+C 뒤 클립보드를 기다리는 최대 시간(예전 고정 대기와 같은 값)
COPY_POLL_S = 0.02    # 그동안 클립보드를 보는 간격(2026-10-28 리규형님 버튼)


def _wait_clipboard_text(paste, limit_s=COPY_WAIT_S, poll_s=COPY_POLL_S, clock=None, sleep=None):
    """Ctrl+C 뒤 클립보드에 글이 들어오면 바로 돌려준다(2026-10-28 리규형님 — 따라 읽기 창이 늦게 뜸. 예전엔 0.5초 고정).

    limit_s 가 지나도 비었으면(고른 글 없음) 마지막으로 한 번 더 읽어 그 값을 돌려준다. 읽기 오류(다른 앱이 클립보드를
    열고 있음 등)는 기한 전에는 넘기고 다음 확인에서 다시 본다 — 마지막 읽기의 오류만 부르는 쪽으로 올라간다.
    """
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    deadline = clock() + limit_s
    while clock() < deadline:
        sleep(poll_s)
        try:
            text = paste()
        except Exception:
            continue
        if text and text.strip():
            return text
    return paste()


def read_selected_text(from_selection_button=False, _page_checked=False):
    """선택된 텍스트를 읽어옵니다. (Ctrl+C 트릭 사용)

    ⚠️ Tk 메인 스레드에서 부른다(단축키·빨간 점 클릭이 root.after 로 부름).
    흐름: 눌린 수정자 키 떼기 → 클립보드 백업 → 클립보드 비우기 → Ctrl+C 흉내 → 글이 들어오면 바로 읽기(최대 0.5초)
    3방향 분기 (07-27 확정, 3) 은 2026-09-28 사용자 결정으로 바뀜):
      1) 선택한 글이 있다          → 빨간 점 숨김 + speak_text(글) — 읽는 중이어도 새 글로 다시 읽는다
      2) 선택 없음 + 읽는 중       → stop_tts()
      3) 선택 없음 + 읽지 않는 중  → 아무것도 안 함 (예전엔 플로팅 아이콘 보이기/숨기기 토글 자리 — 플로팅 아이콘을 없앴다)
    from_selection_button=True (빨간 점을 눌러 부른 경우): 선택이 없으면 읽는 중이어도 멈추지 않는다(2) 도 건너뜀).
      확장의 점은 읽기만 하고 멈추지는 않는다(selection-button.js:201-207 read()). 그리고 점은 드래그 "추정" 으로
      뜨므로 창 제목 막대를 끌어도 뜬다 — 그 점을 눌렀다고 읽던 글이 멈추면 안 된다.
    ⚠️ 클립보드를 비우는 단계를 지우지 말 것: 선택이 없으면 Ctrl+C 가 클립보드를 안 바꾸므로, 안 비우면 직전에
       복사해 둔 글을 "선택한 글" 로 착각해 읽는다(07-27 로그 §4-1). 선택 없음일 때는 백업을 되돌려 놓는다.
    ⚠️ time.sleep 합계 — 고른 글이 있으면 약 0.3초, 없으면 약 0.8초 — 동안 Tk 메인이 멈춘다(하단 바·리더 창·빨간 점도
       그동안 멈춤). 2026-10-28 전에는 0.5초를 고정으로 기다려 늘 약 0.8초였다(_wait_clipboard_text).
       단축키로 멈출 때의 이 지연은 설계상 감수하기로 한 것이다. 이 사이 재생이 스스로 끝나면 tts_playing 이
       False 가 되어 2) 대신 3)(아무것도 안 함) 으로 갈 수 있다(드묾 — 어차피 끝난 읽기라 결과는 같다).
    브라우저에서 비활성화 (2026-09-28 사용자 확정, 켜져 있고 전경 창이 Aside·웨일·크롬일 때) — 맨 처음에 판별한다.
      2026-10-23 부터 일반 웹페이지(http·https)에서만 쉰다 — 주소 종류를 먼저 묻고(_unless_web_page) 답이 오면
      _page_checked=True 로 이 함수를 다시 부른다. 새 탭·확장 페이지·브라우저 설정·내 PC 파일, 주소 모름(느림 포함)이면
      다른 앱과 똑같이 읽는다(사용자 결정). 웹페이지일 때:
      - 새 읽기를 시작하지 않는다(그 브라우저는 크롬 확장이 읽는다). Ctrl+C 도 보내지 않는다(클립보드도 안 건드림).
      - 단축키 + 이 앱이 읽는 중 → 멈춘다(멈추는 것은 막지 않는다 — 사용자 확정). 브라우저에 글이 선택돼 있어도 멈춘다:
        새 글을 읽지 않으니 "선택 있음 → 새로 읽기" 로 갈 수 없고, 그대로 읽게 두면 확장이 그 글을 읽을 때 둘이 겹친다.
      - 빨간 점 경로(from_selection_button)는 웹페이지에서는 점이 안 뜨므로 보통 오지 않는다. 와도 아무것도 안 한다.
      ⚠️ 판별(OpenProcess 등)은 여기(Tk 메인)에서 한다. 키보드 훅 콜백(on_press)에서 하면 훅이 느려진다.
    """
    global Controller, Key, pyperclip, ctrl_pressed, alt_pressed, shift_pressed

    browser = None if _page_checked else _foreground_disabled_browser()
    if browser:
        def on_web(scheme):
            if from_selection_button:
                log_to_console(f"[브라우저] {browser} 웹페이지에서는 읽지 않습니다(크롬 확장이 읽습니다)")
            elif tts_playing:
                log_to_console(f"[브라우저] {browser} 웹페이지에서 단축키 → 읽던 것 중지 (새 읽기는 크롬 확장 몫)")
                stop_tts()
            else:
                log_to_console(f"[브라우저] {browser} 웹페이지에서는 단축키로 읽지 않습니다(크롬 확장이 읽습니다)")

        def proceed(scheme):
            log_to_console(f"[브라우저] {browser} — 웹페이지가 아님({scheme or '주소 모름'}) → 이 앱이 읽습니다")
            read_selected_text(from_selection_button, _page_checked=True)

        _unless_web_page(browser, proceed, on_web)
        return

    if not Controller:
        try:
            from pynput.keyboard import Controller, Key
        except:
            log_to_console("pynput 모듈을 로드할 수 없습니다.")
            return

    try:
        keyboard = Controller()

        # 먼저 "지금 실제로 눌려 있는" 수정자 키만 뗀다(단축키 Shift+X 의 Shift 가 아직 눌려 있으면
        # 뒤의 Ctrl+C 가 Ctrl+Shift+C 가 되므로).
        # ⚠️ 예전에는 Ctrl·Alt·Shift 의 "뗌" 을 무조건 보냈다. 누르지도 않은 Alt 의 뗌을 받은 새 메모장(윈도우 11)은
        #    "Alt 를 눌렀다 뗐다" 로 알고 메뉴 키 팁(F·E·V…)을 띄운다 → 뒤이은 Ctrl+C 가 메뉴로 가서 글을 못 가져왔다
        #    (2026-09-28 사용자 캡처 — 메모장에서만 빨간 점·단축키가 "선택된 텍스트 없음" 이던 원인). 그래서 눌린 것만 뗀다.
        # Alt 가 정말 눌려 있으면(단축키에 Alt 가 든 경우) 떼기 전에 Ctrl 을 한 번 눌렀다 떼서 "Alt 만 눌렀다 뗌" 으로
        # 안 보이게 한다(Alt 단독 탭에만 메뉴가 뜬다).
        import ctypes as _ct
        def _key_down(vk):
            return bool(_ct.windll.user32.GetAsyncKeyState(vk) & 0x8000)
        if _key_down(0x12):          # VK_MENU(Alt)
            keyboard.press(Key.ctrl)
            keyboard.release(Key.ctrl)
            keyboard.release(Key.alt)
        if _key_down(0x11):          # VK_CONTROL
            keyboard.release(Key.ctrl)
        if _key_down(0x10):          # VK_SHIFT
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

        # 클립보드에 글이 들어오면 바로 넘어간다 — 비어 있으면 COPY_WAIT_S 까지 기다린다(_wait_clipboard_text)
        new_text = ""
        copy_t0 = time.monotonic()
        try:
            new_text = _wait_clipboard_text(pyperclip.paste)
            logging.info(f"클립보드 기다림 {time.monotonic() - copy_t0:.2f}초")
        except Exception as e:
            logging.error(f"클립보드 읽기 오류: {e}")
            log_to_console(f"클립보드 읽기 오류: {str(e)}")
            return

        logging.info(f"새 클립보드: '{new_text[:50] if new_text else ''}...' (길이: {len(new_text) if new_text else 0})")

        # ── 선택된 텍스트가 없을 때: 읽는 중이면 중지, 아니면 아무것도 안 함 ──
        if not new_text or len(new_text.strip()) == 0:
            # 판별하려고 비웠던 클립보드를 원래 내용으로 되돌린다
            try:
                pyperclip.copy(old_clipboard if old_clipboard else "")
            except Exception:
                pass

            if from_selection_button:
                # 빨간 점은 읽기만 한다(확장과 같음) — 선택이 없으면 읽던 글도 그대로 둔다
                log_to_console("[빨간 점] 선택된 텍스트 없음 → 아무것도 안 함")
            elif tts_playing:
                log_to_console("[TTS] 선택된 텍스트 없음 → 재생 중지")
                stop_tts()
            else:
                # 2026-09-28 사용자 결정: 선택 없이 단축키 = 아무것도 안 함 (예전 플로팅 아이콘 토글 자리)
                log_to_console("[TTS] 선택된 텍스트 없음 → 아무것도 안 함")
            return

        # 선택된 텍스트가 있으면 읽는다 (직전과 같은 텍스트여도 그대로 읽어준다)
        # 읽기가 시작되면 빨간 점은 숨긴다(확장 read() 도 점을 숨기고 읽는다 — selection-button.js:203)
        _hide_selection_button()
        log_to_console(f"선택된 텍스트 감지: {new_text[:30]}...")
        _speak_or_ask_follow(new_text)            # 한 문단 안이면 따라 읽기 창(2026-10-28)

    except Exception as e:
        logging.error(f"선택 영역 읽기 오류: {e}")
        log_to_console(f"선택 영역 읽기 오류: {str(e)}")

def extract_readme_files():
    """README 파일을 실행 파일이 있는 디렉토리에 추출합니다.

    exe 로 실행할 때만 한다: exe 안에 묶인 README.md·README.KR.md 를 exe 옆에 꺼내 둔다
    (예전 트레이 "README 열기" 가 작업 폴더의 README 를 열었다 — 2026-09-28 그 항목을 없앴다. 꺼내 두기는 사용자 결정 전이라 남겼다).
    이미 있으면 덮어쓰지 않는다 → 사용자가 고친 파일은 보존.
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
