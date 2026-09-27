# -*- coding: utf-8 -*-
"""
bottom_bar.py — 읽는 동안 화면 맨 아래에 붙는 "하단 컨트롤러 바"

■ 무엇을 하나
  크롬 확장 read-aloud-hrg 의 페이지 하단 재생 바(js/page-ui.js startBar~BAR_CSS, 548-979줄)를
  tkinter 로 옮긴 것이다. 확장의 레이아웃·색·크기를 그대로 따른다.
    - 높이 48px, 작업 영역(작업표시줄 제외) 폭 전체, 맨 위 3px 진행선
    - 가운데: [시간 · 이전 · 재생/일시정지 · 다음 · 음소거]
    - 오른쪽 끝: [설정 · 닫기]
    - 설정 버튼 위로 뜨는 작은 패널(속도·볼륨 슬라이더. 피치는 Chirp 이 안 쓰므로 없음)

■ 모듈 사이 약속 (다른 모듈이 이 이름·모양에 기대므로 바꾸지 말 것)
    bar = BottomBar(root, on_command, get_msg)
    bar.show(work_area)   # work_area=(left, top, right, bottom) 화면 좌표. 그 맨 아래에 폭 전체로 붙는다
                          # 부를 때마다 "새 읽기의 시작"으로 본다(진행선 0·패널 닫힘부터). 보이는 중에 불러도 같다
    bar.update(st)        # st = {"state", "elapsed", "total", "progress", "can_prev", "can_next",
                          #       "can_mute", "muted", "rate", "volume"}
    bar.hide() / bar.destroy()
    bar.height            # 바 높이(실제 픽셀). 리더 창을 그 바로 위에 놓을 때 쓴다
    on_command(cmd) 또는 on_command(cmd, value)
      cmd = "togglePause" | "stop" | "forward" | "rewind" | "mute" | "unmute"
            | "setRate"(value=배속 float) | "setVolume"(value=0.2~1)

■ 반드시 지킬 것 (함정)
  1. 모든 메서드는 Tk 메인 스레드에서만 부른다. tkinter 는 스레드 안전하지 않다.
     재생 스레드에서 바를 바꾸려면 whisperer.py 의 gui_queue(check_gui_queue)로 넘겨라
     (2026-07-27 로그 §4-5).
  2. 바·패널·말풍선은 포커스를 뺏으면 안 된다. 사용자는 다른 프로그램에서 글을 고른 채로
     바를 누른다. 그래서 WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW 를 건다
     (whisperer.py setup_floating_controller 의 Win32 처리와 같은 방식).
     이 스타일 때문에 키보드 입력(Esc 등)도 못 받는다 → 패널의 Esc·바깥 클릭은
     GetAsyncKeyState 로 살펴서 닫는다(_poll_outside).
  3. whisperer.py 는 ttkbootstrap 을 import 한다. ttkbootstrap 은 import 되는 순간
     tk.Canvas/tk.Toplevel/tk.Label 생성자를 바꿔 치워서 배경색을 테마색(흰색)으로 덮어쓴다
     (ttkbootstrap/style.py override_tk_widget_constructor). 그래서 위젯을 만들 때
     autostyle=False 를 넘긴다(_no_autostyle).
  4. 크기는 "CSS 픽셀 × DPI 배율"이다. 앱은 ttkbootstrap Window(hdpi=True)가
     SetProcessDPIAware 를 부르므로 tkinter 좌표가 실제 픽셀이다. 확장의 48px 는 CSS 픽셀이라
     배율 140% 화면에서 크롬은 약 67 실제 픽셀로 그린다. 같게 보이도록 배율을 곱한다(_px).
  5. 창을 숨길 때는 withdraw 만 쓰고, "맨 위로 다시 올리기"(keep-alive)는 보일 때만 돈다.
     숨긴 창에 lift/topmost 를 걸면 되살아날 수 있다(2026-07-27 로그 §4-3).
"""

from __future__ import annotations

import logging
import math
import sys
import time
import tkinter as tk
import tkinter.font as tkfont

# Pillow 는 앱의 필수 의존성이다(트레이 아이콘 pystray 가 쓴다). 동그라미 버튼 배경과 스피너를
# 가장자리가 매끄럽게(안티에일리어싱) 그리려고 쓴다. tkinter 캔버스의 oval 은 계단이 진다.
from PIL import Image, ImageDraw, ImageTk

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
#  확장 원본 값 (단위: CSS 픽셀) — 근거는 read-aloud-hrg js/page-ui.js (HEAD)
# ════════════════════════════════════════════════════════════════════
BAR_HEIGHT = 48          # const BAR_HEIGHT = 48 (page-ui.js:846)
BAR_PAD_X = 12           # .bar padding: 0 12px (page-ui.js:853)
PROGRESS_H = 3           # .progress height: 3px (page-ui.js:868)
CENTER_GAP = 6           # .center gap: 6px (page-ui.js:881)
TIME_MIN_W = 160         # .time min-width: 160px (page-ui.js:884)
TIME_MARGIN_R = 8        # .time margin-right: 8px (page-ui.js:885)
BTN_D = 36               # button 36×36 원형 (page-ui.js:896-898)
PLAY_D = 40              # button.play 40×40 (page-ui.js:918-919)
END_GAP = 4              # .end gap: 4px (page-ui.js:930)
FONT_PX = 14             # font: 14px/1 (page-ui.js:859)
SPINNER_D = 16           # .spinner 16×16 (page-ui.js:976-977)
SPINNER_BORDER = 2       # border: 2px (page-ui.js:979)
SPIN_PERIOD_MS = 800     # animation: spin 0.8s linear infinite (page-ui.js:982)
FILL_TRANSITION_MS = 1000  # .fill transition: width 1s linear (page-ui.js:875)

PANEL_W = 280            # .panel width: 280px (page-ui.js:939)
PANEL_RIGHT = 12         # .panel right: 12px (page-ui.js:937)
PANEL_GAP = 8            # bottom: calc(100% + 8px) → 바 위 8px (page-ui.js:938)
PANEL_PAD_Y = 8          # padding: 8px 14px (page-ui.js:941)
PANEL_PAD_X = 14
PANEL_RADIUS = 10        # border-radius: 10px (page-ui.js:943)
ROW_H = 36               # .row height: 36px (page-ui.js:950)
ROW_GAP = 10             # .row gap: 10px (page-ui.js:949)
NAME_W = 40              # .row .name width: 40px (page-ui.js:953)
VALUE_W = 48             # .row .value width: 48px (page-ui.js:965)
SMALL_FONT_PX = 13       # .name/.value font-size: 13px (page-ui.js:954, 967)

# 크롬 기본 range 입력의 모양 — 확장은 브라우저 기본 슬라이더(accent-color 만 지정)를 쓰므로
# 확장 코드에 값이 없다. 크롬 기본 모양을 눈대중으로 옮긴 값이다(보고서 "임의로 정한 것").
SLIDER_THUMB_D = 16      # 크롬 range 손잡이 지름(추정)
SLIDER_TRACK_H = 4       # 크롬 range 트랙 두께(추정)

# 이 모듈에서 정한 타이머 값 (확장에는 대응 값이 없음 → 보고서에 명시)
FILL_FRAME_MS = 50       # 진행선 1초 전환 애니메이션의 한 프레임 간격
SPIN_FRAMES = 20         # 스피너 한 바퀴(0.8초)를 몇 장으로 나눌지 → 40ms 마다 18도
OUTSIDE_POLL_MS = 50     # 패널이 열려 있는 동안 Esc·바깥 클릭을 살피는 간격
KEEP_ALIVE_MS = 3000     # 맨 위 다시 올리기 주기 — whisperer.py update_state 의 3초(500ms×6)와 같게


# ════════════════════════════════════════════════════════════════════
#  색 — CSS 의 반투명 흰색은 바탕색과 미리 섞어서 불투명 색으로 만든다
#  (tkinter 는 창 전체 투명도만 된다. 요소별 rgba 는 불가능)
# ════════════════════════════════════════════════════════════════════
def _blend(fg: str, bg: str, alpha: float) -> str:
    """fg 색을 alpha 만큼 bg 위에 얹은 색(#rrggbb)을 돌려준다. CSS rgba(…, alpha) 흉내."""
    f = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(round(bb + (ff - bb) * alpha)) for ff, bb in zip(f, b))


WHITE = "#ffffff"
BAR_BG = "#565656"                          # background: rgba(86,86,86,0.95) (page-ui.js:857)
BAR_ALPHA = 0.95                            #   → 창 전체 -alpha 0.95 로 대신한다
BAR_FG = WHITE                              # color: #fff (page-ui.js:858)
TOTAL_FG = _blend(WHITE, BAR_BG, 0.70)      # .total rgba(255,255,255,0.7) (page-ui.js:891)
HOVER_BG = _blend(WHITE, BAR_BG, 0.14)      # button:hover rgba(255,255,255,0.14) (page-ui.js:906)
DISABLED_FG = _blend(WHITE, BAR_BG, 0.35)   # button:disabled opacity 0.35 (page-ui.js:913)
PROGRESS_BG = _blend(WHITE, BAR_BG, 0.18)   # .progress rgba(255,255,255,0.18) (page-ui.js:869)
PROGRESS_FILL = "#3d7cff"                   # .fill #3d7cff (page-ui.js:874)
PLAY_BG = "#333333"                         # button.play background #333 (page-ui.js:920)
PLAY_HOVER_BG = "#2a2a2a"                   # button.play:hover #2a2a2a (page-ui.js:924)
PLAY_FG = "#4d8dff"                         # button.play color #4d8dff (page-ui.js:921)
SPINNER_FG = "#4d8dff"                      # border-top-color #4d8dff (page-ui.js:980)
SPINNER_TRACK = _blend("#4d8dff", PLAY_BG, 0.30)   # border rgba(77,141,255,0.3) (page-ui.js:979)
PANEL_BG = "#383838"                        # .panel rgba(56,56,56,.97) (page-ui.js:942)
PANEL_ALPHA = 0.97
NAME_FG = _blend(WHITE, PANEL_BG, 0.85)     # .row .name rgba(255,255,255,0.85) (page-ui.js:955)
ACCENT = "#4d8dff"                          # .row input accent-color #4d8dff (page-ui.js:961)
SLIDER_TRACK_BG = "#efefef"                 # 크롬 기본 range 의 빈 트랙 색(추정)
# 말풍선(title 툴팁) — 확장은 브라우저 기본 툴팁을 쓴다. 윈도우 기본 툴팁 모양을 흉내 낸 값(추정).
TIP_BG = "#ffffff"
TIP_FG = "#000000"
TIP_BORDER = "#767676"
TIP_FONT_PX = 12         # 윈도우 기본 툴팁 글꼴 9pt = 96dpi 에서 12px

# 글꼴 — 확장: 14px/1 system-ui, "Segoe UI", "Malgun Gothic" … (page-ui.js:859)
# ⚠ Segoe UI 를 쓰면 Tk 가 한글("약", "계산 중", "속도")을 자동 대체 글꼴로 그리는데, 그 대체
#   글자가 **굵게** 나온다(2026-09-28 캡처로 확인). 크롬은 한글을 맑은 고딕 보통 굵기로 그린다.
#   맑은 고딕의 영문·숫자는 Segoe UI 를 바탕으로 만든 글자라 모양이 거의 같으므로,
#   맑은 고딕이 있으면 글자 전체를 맑은 고딕으로 그린다(_pick_text_family).
TEXT_FAMILIES = ("Malgun Gothic", "Segoe UI")
# 아이콘 — 확장은 Material 모양 SVG path(page-ui.js:809-820)를 쓴다. 여기서는 윈도우 기본
# 아이콘 글꼴의 글리프로 대신한다(오케스트레이터 기본값). 윈도우 11 은 Fluent, 10 은 MDL2.
ICON_FAMILIES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")
# (코드포인트, 글꼴 크기 CSS px). 크기는 Material 아이콘이 22px 상자 안에서 차지하는 잉크 크기에
# 글리프 잉크 크기를 맞춘 값이다(PIL 로 잉크 상자를 재서 정함).
ICON_GLYPHS = {
    "play": ("", 14),       # PlaySolid       ↔ Material play_arrow
    "pause": ("", 15),      # PauseSolid      ↔ Material pause
    "prev": ("", 13),       # PreviousSolid   ↔ Material skip_previous
    "next": ("", 13),       # NextSolid       ↔ Material skip_next
    "volume": ("", 17),     # Volume          ↔ Material volume_up
    "muted": ("", 17),      # Mute            ↔ Material volume_off
    "settings": ("", 17),   # SettingsSolid   ↔ Material settings
    "close": ("", 13),      # ChromeClose     ↔ Material close
}

# 문구 — get_msg 에 키가 없을 때 쓰는 한국어 기본값. 키 이름은 확장의 _locales 와 같게 맞췄다
# (read-aloud-hrg _locales/ko/messages.json:122-163 pagebar_*).
_DEFAULT_TEXT = {
    "pagebar_calculating": "계산 중",
    "pagebar_about": "약",
    "pagebar_prev": "이전 단락",
    "pagebar_next": "다음 단락",
    "pagebar_play": "재생",
    "pagebar_pause": "일시정지",
    "pagebar_loading": "불러오는 중",
    "pagebar_mute": "음소거",
    "pagebar_unmute": "음소거 해제",
    "pagebar_stop": "읽기 중지",
    "pagebar_settings": "음성 설정",
    "pagebar_rate": "속도",
    "pagebar_volume": "볼륨",
}


# ════════════════════════════════════════════════════════════════════
#  설정 패널 슬라이더 정의 — 확장 PARAMS(page-ui.js:822-844)를 그대로 옮김 (피치는 뺌)
# ════════════════════════════════════════════════════════════════════
def _fmt_percent(v: float) -> str:
    # JS Math.round 는 .5 를 올린다. 파이썬 round 는 짝수 쪽으로 가므로 floor(x+0.5) 로 맞춘다.
    return "%d%%" % math.floor(v * 100 + 0.5)


_PARAMS = {
    # 속도: 슬라이더 -1~1, 0.05 단위, 로그 눈금 rate = 3^v (0.33~3배), 표시 "1.00x"
    "rate": {
        "label": "pagebar_rate", "cmd": "setRate",
        "min": -1.0, "max": 1.0, "step": 0.05,
        "to_slider": lambda rate: math.log(rate) / math.log(3) if rate and rate > 0 else 0.0,
        "from_slider": lambda v: round(math.pow(3, v), 3),   # Number(Math.pow(3, value).toFixed(3))
        "format": lambda rate: "%.2fx" % rate,
    },
    # 볼륨: 0.2~1, 0.02 단위, 표시 "%"
    "volume": {
        "label": "pagebar_volume", "cmd": "setVolume",
        "min": 0.2, "max": 1.0, "step": 0.02,
        "to_slider": lambda v: v,
        "from_slider": lambda v: round(v, 2),                 # Number(value.toFixed(2))
        "format": _fmt_percent,
    },
}


def _snap(p: dict, v: float) -> float:
    """슬라이더 값을 step 눈금에 맞추고 범위 안으로 자른다.

    브라우저 range 입력은 value 를 넣으면 가장 가까운 눈금으로 맞춘다(동점이면 큰 쪽).
    """
    v = max(p["min"], min(p["max"], float(v)))
    n = math.floor((v - p["min"]) / p["step"] + 0.5)
    return round(max(p["min"], min(p["max"], p["min"] + n * p["step"])), 6)


def _format_time(sec) -> str:
    """초 → "HH:MM:SS". 확장 formatTime(page-ui.js:779-783)과 같다(시간은 99 를 넘어도 그대로)."""
    try:
        sec = max(0, int(math.floor(float(sec or 0))))
    except (TypeError, ValueError):
        sec = 0
    return "%02d:%02d:%02d" % (sec // 3600, (sec // 60) % 60, sec % 60)


# ════════════════════════════════════════════════════════════════════
#  Win32 헬퍼 (윈도우 전용. 다른 OS 에서는 아무것도 안 한다)
# ════════════════════════════════════════════════════════════════════
_IS_WIN = sys.platform == "win32"

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    # ⚠ ctypes.windll.user32 를 그대로 쓰지 않고 따로 불러온다.
    #   argtypes/restype 을 공용 객체에 걸면 whisperer.py 의 같은 함수 호출 방식까지 바뀐다.
    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _g32 = ctypes.WinDLL("gdi32", use_last_error=True)

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    _u32.GetParent.argtypes = [wintypes.HWND]
    _u32.GetParent.restype = wintypes.HWND
    _u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _u32.GetWindowLongW.restype = ctypes.c_long
    _u32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    _u32.SetWindowLongW.restype = ctypes.c_long
    try:  # 64비트에만 있다
        _u32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        _u32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        _set_window_long_ptr = _u32.SetWindowLongPtrW
    except AttributeError:
        _set_window_long_ptr = _u32.SetWindowLongW
    _u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _u32.SetWindowPos.restype = wintypes.BOOL
    _u32.GetForegroundWindow.argtypes = []
    _u32.GetForegroundWindow.restype = wintypes.HWND
    _u32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _u32.MonitorFromWindow.restype = wintypes.HANDLE
    _u32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    _u32.MonitorFromPoint.restype = wintypes.HANDLE
    _u32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFO)]
    _u32.GetMonitorInfoW.restype = wintypes.BOOL
    _u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _u32.GetAsyncKeyState.restype = ctypes.c_short
    _u32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    _u32.GetCursorPos.restype = wintypes.BOOL
    _u32.GetDoubleClickTime.argtypes = []
    _u32.GetDoubleClickTime.restype = wintypes.UINT
    _u32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
    _u32.SetWindowRgn.restype = ctypes.c_int
    _g32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
    _g32.CreateRoundRectRgn.restype = wintypes.HANDLE
    _g32.DeleteObject.argtypes = [wintypes.HANDLE]
    _g32.DeleteObject.restype = wintypes.BOOL

    _GWL_EXSTYLE = -20
    _GWLP_HWNDPARENT = -8
    _WS_EX_NOACTIVATE = 0x08000000
    _WS_EX_TOOLWINDOW = 0x00000080
    _WS_EX_APPWINDOW = 0x00040000
    _HWND_TOPMOST = wintypes.HWND(-1)
    _SWP_NOSIZE = 0x0001
    _SWP_NOMOVE = 0x0002
    _SWP_NOACTIVATE = 0x0010
    _SWP_FRAMECHANGED = 0x0020
    _MONITOR_DEFAULTTOPRIMARY = 1
    _MONITOR_DEFAULTTONEAREST = 2
    _VK_LBUTTON, _VK_RBUTTON, _VK_MBUTTON, _VK_ESCAPE = 0x01, 0x02, 0x04, 0x1B


def _wrapper_hwnd(win):
    """tk.Toplevel 의 진짜 최상위 창 핸들(HWND)을 돌려준다.

    tkinter 의 winfo_id() 는 안쪽 자식 창이고, 그 부모가 윈도우가 보는 최상위 창(wrapper)이다.
    whisperer.py setup_floating_controller 와 같은 방식(GetParent(winfo_id())).
    """
    if not _IS_WIN:
        return None
    try:
        win.update_idletasks()
        return _u32.GetParent(win.winfo_id()) or None
    except Exception as e:
        log.debug("wrapper hwnd 조회 실패: %s", e)
        return None


def _set_topmost(hwnd, frame_changed=False):
    """창을 '항상 위' 무리의 맨 위로 올린다. 활성화(포커스 이동)는 하지 않는다.

    ⚠ SWP_NOACTIVATE 를 꼭 넣는다. 빠지면 SetWindowPos 가 창을 활성화할 수 있다.
    ⚠ SWP_SHOWWINDOW 는 넣지 않는다 → 숨긴 창을 되살리지 않는다.
    """
    if not (_IS_WIN and hwnd):
        return
    flags = _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE
    if frame_changed:
        flags |= _SWP_FRAMECHANGED
    try:
        _u32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, flags)
    except Exception as e:
        log.debug("SetWindowPos 실패: %s", e)


def _make_tool_window(win):
    """창을 '포커스를 안 뺏는 도구 창'으로 만든다. 여러 번 불러도 안전하다(멱등).

    하는 일 (whisperer.py setup_floating_controller 의 Win32 1)~3) 과 같다):
      1) 소유자(root) 연결 해제 → root.withdraw() 상태와 무관하게 독립적으로 보인다
      2) WS_EX_NOACTIVATE: 클릭해도 활성화되지 않는다 → 사용자가 읽던 창이 포커스를 유지한다
         WS_EX_TOOLWINDOW: 작업표시줄·Alt+Tab 에 안 나온다
      3) 항상 위 확정

    ⚠ tkinter 가 내부에서 wrapper 창을 새로 만드는 경우(-toolwindow 등 스타일 속성 변경)
      우리가 건 스타일이 사라진다. 그래서 show() 할 때마다 다시 부른다.
      -topmost/-alpha 는 창을 처음 띄우기 전에 한 번만 걸어 두고 다시 바꾸지 않는다.
    """
    hwnd = _wrapper_hwnd(win)
    if not hwnd:
        return None
    try:
        _set_window_long_ptr(hwnd, _GWLP_HWNDPARENT, 0)
        ex = _u32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        want = (ex | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW) & ~_WS_EX_APPWINDOW
        changed = want != ex
        if changed:
            _u32.SetWindowLongW(hwnd, _GWL_EXSTYLE, want)
        _set_topmost(hwnd, frame_changed=changed)
    except Exception as e:
        log.warning("하단 바 Win32 스타일 적용 실패(동작은 계속): %s", e)
    return hwnd


def _round_corners(hwnd, w, h, r):
    """창 모양을 둥근 사각형으로 자른다(설정 패널 border-radius 10px 흉내).

    SetWindowRgn 은 가장자리 매끄럽게 처리가 안 되어 모서리가 살짝 계단진다.
    """
    if not (_IS_WIN and hwnd):
        return
    try:
        rgn = _g32.CreateRoundRectRgn(0, 0, w + 1, h + 1, 2 * r, 2 * r)
        if rgn and not _u32.SetWindowRgn(hwnd, rgn, True):
            _g32.DeleteObject(rgn)   # 성공하면 영역은 시스템 소유가 되므로 지우면 안 된다
    except Exception as e:
        log.debug("둥근 모서리 적용 실패: %s", e)


def _key_down(vk) -> bool:
    """그 키(마우스 버튼 포함)가 지금 눌려 있는지. 포커스와 무관하게 전역으로 본다."""
    try:
        return bool(_u32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


def _cursor_pos():
    pt = wintypes.POINT()
    try:
        if _u32.GetCursorPos(ctypes.byref(pt)):
            return pt.x, pt.y
    except Exception:
        pass
    return None


def _foreground_hwnd():
    try:
        return _u32.GetForegroundWindow() if _IS_WIN else None
    except Exception:
        return None


def _tooltip_delay_ms() -> int:
    """말풍선이 뜨기까지 기다리는 시간.

    확장은 브라우저 기본 title 툴팁을 쓴다. 윈도우 기본 툴팁의 첫 대기 시간(TTDT_INITIAL)은
    더블클릭 시간(GetDoubleClickTime, 보통 500ms)이라 그 값을 따른다.
    """
    if _IS_WIN:
        try:
            return int(_u32.GetDoubleClickTime()) or 500
        except Exception:
            pass
    return 500


def foreground_work_area():
    """지금 전경 창이 있는 모니터의 작업 영역 (left, top, right, bottom) 을 돌려준다.

    "읽기를 시작한 순간 전경 창이 있는 모니터에 바를 띄운다"(오케스트레이터 기본값)를 위한
    도우미다. 읽기 시작 시점에 불러서 show(work_area) 에 넘기면 된다. 작업 영역은
    작업표시줄을 뺀 영역이라 바가 작업표시줄에 가리지 않는다.
    전경 창이 없으면 주 모니터. 실패하면 None.
    """
    if not _IS_WIN:
        return None
    try:
        hwnd = _u32.GetForegroundWindow()
        mon = _u32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST) if hwnd else None
        if not mon:
            mon = _u32.MonitorFromPoint(wintypes.POINT(0, 0), _MONITOR_DEFAULTTOPRIMARY)
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not _u32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return None
        r = mi.rcWork
        return (r.left, r.top, r.right, r.bottom)
    except Exception as e:
        log.warning("작업 영역 조회 실패: %s", e)
        return None


def _no_autostyle(cls) -> dict:
    """ttkbootstrap 이 그 위젯 생성자를 바꿔 쳤으면 {'autostyle': False} 를 돌려준다.

    ttkbootstrap 을 import 하면 tk.Canvas 등의 __init__ 이 '__init__wrapper' 로 바뀌고
    생성 직후 배경을 테마색으로 덮어쓴다(ttkbootstrap/style.py override_tk_widget_constructor).
    순수 tkinter 에 autostyle 을 넘기면 TclError 가 나므로 바뀐 경우에만 넘긴다.
    """
    return {"autostyle": False} if getattr(cls.__init__, "__name__", "") == "__init__wrapper" else {}


def _pick_text_family(root) -> str:
    """TEXT_FAMILIES 중 실제로 설치된 첫 글꼴 이름.

    맑은 고딕은 Tk 글꼴 목록에 한글 이름("맑은 고딕")으로 나오지만 "Malgun Gothic" 으로 요청해도
    잡힌다. 그래서 이름 대조 대신, 없는 글꼴을 요청했을 때 Tk 가 주는 기본 글꼴과
    다른 글꼴이 잡히면 "설치돼 있다"고 본다.
    """
    try:
        fallback = tkfont.Font(root=root, family="__no_such_font__", size=-12).actual("family")
    except Exception:
        fallback = None
    for fam in TEXT_FAMILIES:
        try:
            got = tkfont.Font(root=root, family=fam, size=-12).actual("family")
        except Exception:
            continue
        if got and got != fallback:
            return fam
    return TEXT_FAMILIES[-1]


def _auto_scale(root) -> float:
    """CSS 픽셀 → 실제 픽셀 배율 (= 화면 DPI / 96).

    앱은 DPI 인식 모드라(ttkbootstrap Window hdpi=True → SetProcessDPIAware) 배율 140% 화면에서
    Tk 가 약 134 DPI 를 보고한다 → 1.4 배. DPI 비인식 프로세스면 96 → 1.0 배(윈도우가 대신 확대).
    """
    try:
        s = float(root.winfo_fpixels("1i")) / 96.0
    except Exception:
        return 1.0
    return s if 0.5 <= s <= 4.0 else 1.0


class _Button:
    """바 위의 동그란 버튼 하나의 상태(그리기는 BottomBar 가 한다)."""

    __slots__ = ("key", "d", "cx", "cy", "visible", "enabled", "disc", "icon")

    def __init__(self, key, d):
        self.key = key
        self.d = d              # 지름(실제 픽셀)
        self.cx = self.cy = 0   # 중심 좌표(캔버스 안)
        self.visible = True
        self.enabled = True
        self.disc = None        # 배경 동그라미 이미지 아이템 id
        self.icon = None        # 아이콘 글리프 텍스트 아이템 id


# 약속된 update(st) 의 기본값. 빠진 키는 이 값으로 채운다.
_DEFAULT_ST = {
    "state": "LOADING", "elapsed": 0.0, "total": None, "progress": 0.0,
    "can_prev": False, "can_next": False, "can_mute": False, "muted": False,
    "rate": None, "volume": None,
}


class BottomBar:
    """화면 맨 아래 재생 컨트롤러 바.

    ■ 창 3개로 이루어진다
      - 바 본체(_win): 캔버스 하나에 진행선·시간·버튼을 모두 그린다. 버튼은 위젯이 아니라
        캔버스 그림이고, 마우스 위치로 어느 버튼인지 직접 판정한다(_hit). 원형 버튼의
        클릭 영역도 원이다(브라우저는 border-radius 로 클릭 영역도 원으로 자른다).
      - 설정 패널(_panel): 설정 버튼 위 8px 에 뜨는 작은 창. 속도·볼륨 슬라이더.
      - 말풍선(_tip): 버튼에 마우스를 올리면 뜨는 이름표(확장의 title 툴팁).
      셋 다 WS_EX_NOACTIVATE 라 눌러도 포커스를 안 뺏는다.

    ■ 상태 흐름 (확장 renderBar/displayedTime/scheduleTime 과 같은 구조, page-ui.js:685-744)
      update(st) 로 받은 마지막 상태와 받은 시각을 기억해 두고, PLAYING 이면 그 뒤 흐른 시간을
      더해 1초마다 스스로 시계를 돌린다. 재생 스레드의 알림이 늦어도 시계가 멈추지 않는다.
    """

    # ─────────────────────────────── 생성 ───────────────────────────────
    def __init__(self, root, on_command, get_msg, scale=None):
        """root: 앱 tk 루트(숨겨져 있어도 됨). on_command(cmd[, value]). get_msg(key, *args).

        scale: CSS 픽셀 → 실제 픽셀 배율. None 이면 화면 DPI 로 자동(_auto_scale).
               (약속 밖의 선택 인자. 안 넘기면 된다)

        ⚠ 여기서 창 3개를 만들고 "투명도 0 으로 한 번 띄웠다가" 바로 숨긴다(_make_popup).
          처음 띄울 때 Win32 스타일(포커스 안 뺏기)을 미리 걸어 두기 위해서다.
          그래야 나중에 읽기 도중 show() 할 때 처음 뜨는 순간부터 포커스를 안 뺏는다.
        """
        self._root = root
        self._on_command = on_command
        self._get_msg = get_msg
        self._s = float(scale) if scale else _auto_scale(root)
        self._destroyed = False
        self._visible = False
        self._work_area = None
        self._w = 1                          # 바 폭(실제 픽셀) — show() 에서 정해진다
        self._h = self._px(BAR_HEIGHT)       # 바 높이(실제 픽셀)
        self._last = None                    # (st dict, time.monotonic()) — 마지막 update
        self._play_state = None              # 재생 버튼이 지금 그리고 있는 상태
        self._hover = None                   # 마우스가 올라가 있는 버튼 key
        self._pressed = None                 # 눌린 채인 버튼 key (뗄 때 같은 버튼이면 클릭)
        self._panel_open = False
        self._settings_enabled = False
        self._muted = False
        self._layout_key = None
        self._jobs = {}                      # 이름 → root.after id (타이머 관리)
        # 진행선 전환 애니메이션(확장 .fill transition: width 1s linear)
        self._fill_drawn = 0.0
        self._fill_from = 0.0
        self._fill_target = 0
        self._fill_t0 = 0.0
        self._spin_idx = 0
        # 설정 패널
        self._slider_vals = {k: _snap(p, p["to_slider"](1.0)) for k, p in _PARAMS.items()}
        self._editing = {k: False for k in _PARAMS}
        self._drag = None                    # (key, 누르기 시작할 때 값)
        self._poll_prev = None               # 바깥 클릭 감시: 직전 (esc, mouse) 눌림 상태
        self._panel_fg = None                # 패널을 열 때의 전경 창(바뀌면 닫는다 = 확장 blur)
        self._tip_key = None

        # 글꼴 — 크기는 음수(= 픽셀 단위)로 줘야 DPI 배율을 우리가 직접 통제한다
        fam = _pick_text_family(root)
        self._font = tkfont.Font(root=root, family=fam, size=-self._px(FONT_PX))
        self._font_small = tkfont.Font(root=root, family=fam, size=-self._px(SMALL_FONT_PX))
        self._font_tip = tkfont.Font(root=root, family=fam, size=-self._px(TIP_FONT_PX))
        fams = set(tkfont.families(root))
        self._icon_family = next((f for f in ICON_FAMILIES if f in fams), ICON_FAMILIES[-1])
        self._icon_fonts = {}                # 크기(px) → Font

        self._make_images()
        self._build_bar()
        self._build_panel()
        self._build_tip()
        self._render()

    def _px(self, css):
        """CSS 픽셀 → 실제 픽셀(정수)."""
        return max(1, int(round(css * self._s)))

    @property
    def height(self):
        """바 높이(실제 픽셀). 리더 창을 바 바로 위에 놓을 때 쓴다."""
        return self._h

    def _t(self, key):
        """get_msg 로 문구를 가져온다. 없는 키면 한국어 기본값.

        messages.get_message 는 없는 키에 "[Missing message: key]" 를 돌려주므로 그것도 없는 것으로 본다.
        언어가 바뀔 수 있으므로 그릴 때마다 새로 부른다.
        """
        s = None
        if self._get_msg:
            try:
                s = self._get_msg(key)
            except Exception:
                s = None
        if not isinstance(s, str) or not s.strip() or s.startswith("[Missing message"):
            return _DEFAULT_TEXT.get(key, key)
        return s

    def _icon_font(self, css_size):
        px = self._px(css_size)
        f = self._icon_fonts.get(px)
        if f is None:
            f = self._icon_fonts[px] = tkfont.Font(root=self._root, family=self._icon_family, size=-px)
        return f

    # ─────────────────────── 창·그림 재료 만들기 ───────────────────────
    def _make_popup(self, bg, alpha):
        """포커스를 안 뺏는 테두리 없는 '항상 위' 창을 만들어 숨겨 둔다.

        순서가 중요하다:
          1) overrideredirect·topmost·alpha 를 **처음 띄우기 전에** 모두 건다.
             (나중에 바꾸면 tkinter 가 wrapper 창을 새로 만들어 Win32 스타일이 날아갈 수 있다)
          2) 투명도 0 으로 1×1 크기로 한 번 띄워(update_idletasks) wrapper 창을 만들게 한다
             → 화면에 깜빡임이 없다.
          3) 그 wrapper 에 NOACTIVATE|TOOLWINDOW 를 건다(_make_tool_window).
          4) 숨긴 뒤 진짜 투명도로 되돌린다.
        """
        win = tk.Toplevel(self._root, **_no_autostyle(tk.Toplevel))
        win.overrideredirect(True)
        win.configure(bg=bg)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.0)
        win.geometry("1x1+0+0")
        win.update_idletasks()
        hwnd = _make_tool_window(win)
        win.withdraw()
        win.attributes("-alpha", alpha)
        return win, hwnd

    def _disc_image(self, d, fill, bg):
        """지름 d 픽셀의 매끄러운 동그라미 이미지(바탕 bg). 4배로 그려 줄여서 가장자리를 매끄럽게."""
        ss = 4
        big = Image.new("RGB", (d * ss, d * ss), bg)
        ImageDraw.Draw(big).ellipse((0, 0, d * ss - 1, d * ss - 1), fill=fill)
        return ImageTk.PhotoImage(big.resize((d, d), Image.LANCZOS), master=self._root)

    def _spinner_frames(self, disc_fill):
        """로딩 스피너 한 바퀴 분의 이미지들 (확장 .spinner, page-ui.js:975-986).

        재생 버튼(40px, 배경 disc_fill) 위에 지름 16px·두께 2px 고리를 그린다. 고리는
        흐린 파랑(30%), 윗부분 1/4 (CSS border-top 은 원에서 -135°~-45° 구간)만 진한 파랑.
        그 1/4 호를 SPIN_FRAMES 장에 걸쳐 시계 방향으로 돌린다.
        """
        ss = 4
        d = self._px(PLAY_D)
        sd = self._px(SPINNER_D)
        bw = self._px(SPINNER_BORDER)
        c = d * ss / 2
        box = (c - sd * ss / 2, c - sd * ss / 2, c + sd * ss / 2 - 1, c + sd * ss / 2 - 1)
        frames = []
        for i in range(SPIN_FRAMES):
            big = Image.new("RGB", (d * ss, d * ss), BAR_BG)
            dr = ImageDraw.Draw(big)
            dr.ellipse((0, 0, d * ss - 1, d * ss - 1), fill=disc_fill)
            dr.ellipse(box, outline=SPINNER_TRACK, width=bw * ss)
            a = 360.0 * i / SPIN_FRAMES
            dr.arc(box, start=-135 + a, end=-45 + a, fill=SPINNER_FG, width=bw * ss)
            frames.append(ImageTk.PhotoImage(big.resize((d, d), Image.LANCZOS), master=self._root))
        return frames

    def _make_images(self):
        """버튼 배경 동그라미·스피너·슬라이더 손잡이 이미지를 미리 만들어 둔다.

        ⚠ PhotoImage 는 파이썬 참조가 사라지면 화면에서도 사라진다 → self._img 에 붙잡아 둔다.
        """
        bd, pd = self._px(BTN_D), self._px(PLAY_D)
        self._img = {
            "hover": self._disc_image(bd, HOVER_BG, BAR_BG),
            "play": self._disc_image(pd, PLAY_BG, BAR_BG),
            "play_hover": self._disc_image(pd, PLAY_HOVER_BG, BAR_BG),
            "thumb": self._disc_image(self._px(SLIDER_THUMB_D), ACCENT, PANEL_BG),
        }
        self._spin = {False: self._spinner_frames(PLAY_BG), True: self._spinner_frames(PLAY_HOVER_BG)}

    def _build_bar(self):
        """바 본체 창과 캔버스 그림 요소를 만든다(위치는 _layout 이 잡는다)."""
        self._win, self._hwnd = self._make_popup(BAR_BG, BAR_ALPHA)
        c = self._canvas = tk.Canvas(self._win, width=1, height=self._h, bg=BAR_BG, bd=0,
                                     highlightthickness=0, **_no_autostyle(tk.Canvas))
        c.pack(fill="both", expand=True)
        ph = self._px(PROGRESS_H)
        # 진행선 — 바 맨 위에 겹쳐 붙는다(.progress position:absolute; top:0)
        self._prog_bg = c.create_rectangle(0, 0, 1, ph, fill=PROGRESS_BG, width=0, outline="")
        self._prog_fill = c.create_rectangle(0, 0, 0, ph, fill=PROGRESS_FILL, width=0, outline="",
                                             state="hidden")
        # 시간 텍스트 — 경과(흰색) + " / 약 00:01:23"(흰색 70%)
        self._time_el = c.create_text(0, 0, text="00:00:00", fill=BAR_FG, font=self._font, anchor="e")
        self._time_tot = c.create_text(0, 0, text="", fill=TOTAL_FG, font=self._font, anchor="e")
        # 버튼들 — 가운데 4개 + 오른쪽 끝 2개
        self._buttons = {}
        for key in ("prev", "play", "next", "mute", "settings", "close"):
            b = _Button(key, self._px(PLAY_D if key == "play" else BTN_D))
            if key == "play":
                b.disc = c.create_image(0, 0, image=self._img["play"])
            else:
                b.disc = c.create_image(0, 0, image=self._img["hover"], state="hidden")
            b.icon = c.create_text(0, 0, text="", fill=BAR_FG, anchor="center")
            self._buttons[key] = b
        self._spinner = c.create_image(0, 0, image=self._spin[False][0], state="hidden")
        # 확장 초기 상태: 음소거 숨김, 설정 비활성, 재생 버튼은 스피너 (page-ui.js:595-605)
        self._buttons["mute"].visible = False
        self._buttons["settings"].enabled = False

        c.bind("<Motion>", self._on_bar_motion)
        c.bind("<Leave>", self._on_bar_leave)
        c.bind("<ButtonPress-1>", self._on_bar_press)
        c.bind("<ButtonRelease-1>", self._on_bar_release)

    def _build_panel(self):
        """설정 패널 창(속도·볼륨 두 줄)을 만든다 (확장 .panel/.row, page-ui.js:935-969)."""
        self._panel, self._panel_hwnd = self._make_popup(PANEL_BG, PANEL_ALPHA)
        self._pw = self._px(PANEL_W)
        self._ph = self._px(PANEL_PAD_Y) * 2 + self._px(ROW_H) * len(_PARAMS)
        self._panel.geometry("%dx%d+0+0" % (self._pw, self._ph))
        pc = self._panel_canvas = tk.Canvas(self._panel, width=self._pw, height=self._ph, bg=PANEL_BG,
                                            bd=0, highlightthickness=0, **_no_autostyle(tk.Canvas))
        pc.pack(fill="both", expand=True)
        _round_corners(self._panel_hwnd, self._pw, self._ph, self._px(PANEL_RADIUS))

        # 한 줄 = [이름 40px] 10px [슬라이더(남는 폭)] 10px [값 48px], 좌우 여백 14px
        x_name = self._px(PANEL_PAD_X)
        x_in0 = x_name + self._px(NAME_W) + self._px(ROW_GAP)
        x_val = self._pw - self._px(PANEL_PAD_X)
        x_in1 = x_val - self._px(VALUE_W) - self._px(ROW_GAP)
        th = self._px(SLIDER_TRACK_H)
        self._rows = {}
        for i, key in enumerate(_PARAMS):
            cy = self._px(PANEL_PAD_Y) + self._px(ROW_H) * i + self._px(ROW_H) / 2
            row = {
                "cy": cy, "x0": x_in0, "x1": x_in1,
                "name": pc.create_text(x_name, cy, text="", fill=NAME_FG, font=self._font_small, anchor="w"),
                # 트랙은 양 끝이 둥근 굵은 선. 채워진 부분(왼쪽)은 강조색.
                "track": pc.create_line(x_in0 + th / 2, cy, x_in1 - th / 2, cy, width=th,
                                        fill=SLIDER_TRACK_BG, capstyle="round"),
                "fill": pc.create_line(x_in0 + th / 2, cy, x_in0 + th / 2, cy, width=th,
                                       fill=ACCENT, capstyle="round"),
                "thumb": pc.create_image(x_in0, cy, image=self._img["thumb"]),
                "value": pc.create_text(x_val, cy, text="", fill=BAR_FG, font=self._font_small, anchor="e"),
            }
            self._rows[key] = row
            self._draw_slider(key)

        pc.bind("<ButtonPress-1>", self._on_panel_press)
        pc.bind("<B1-Motion>", self._on_panel_drag)
        pc.bind("<ButtonRelease-1>", self._on_panel_release)
        pc.bind("<Motion>", self._on_panel_motion)

    def _build_tip(self):
        """버튼 이름 말풍선 창(확장의 title 툴팁 대신)."""
        self._tip, self._tip_hwnd = self._make_popup(TIP_BORDER, 1.0)
        self._tip_label = tk.Label(self._tip, text="", bg=TIP_BG, fg=TIP_FG, font=self._font_tip,
                                   padx=self._px(6), pady=self._px(2), bd=0,
                                   **_no_autostyle(tk.Label))
        # 1px 테두리: 창 배경(TIP_BORDER)이 라벨 둘레로 1px 보이게 한다
        self._tip_label.pack(padx=1, pady=1)

    # ─────────────────────────── 약속된 메서드 ───────────────────────────
    def show(self, work_area=None):
        """work_area(작업 영역) 맨 아래에 폭 전체로 바를 붙여 보인다. **부를 때마다 새 읽기의 시작으로 본다.**

        work_area 를 안 주면 foreground_work_area() 로 전경 창의 모니터를 쓴다.

        ⚠ 새 읽기 = 진행선 0·재생 버튼 상태 새로·설정 패널 닫힘에서 시작한다
          (확장은 읽기마다 바 요소를 통째로 새로 만든다 — startBar 가 removeBar 부터, page-ui.js:548-549).
        ⚠ 이미 보이는 중에 불려도 마찬가지다. whisperer.py 는 읽는 도중 새 읽기를 시작하면 hide 없이 show 만
          부른다(앞 세션의 session_end 는 "옛 세션 알림"이라 버려진다 — _handle_tts_event). 예전에는 이때
          앞 읽기의 상태·진행선이 남아 진행선이 옛 위치에서 0 으로 1초 동안 거꾸로 흘렀다
          (2026-09-28 통합 점검에서 코드 흐름으로 확인). 그래서 보이는 중이면 앞 읽기의 마지막 상태(_last)도 버린다.
          숨긴 동안 받은 update 는 새 읽기의 것이므로(hide 가 _last 를 비운 뒤에 온 것) 그대로 살려 보인다.
        """
        if self._destroyed:
            return
        wa = work_area or foreground_work_area() or (
            0, 0, self._root.winfo_screenwidth(), self._root.winfo_screenheight())
        left, top, right, bottom = (int(v) for v in wa)
        self._work_area = (left, top, right, bottom)
        w = max(1, right - left)
        was_visible = self._visible
        if w != self._w:
            self._w = w
            self._layout_key = None
        self._win.geometry("%dx%d+%d+%d" % (w, self._h, left, bottom - self._h))
        if was_visible:
            # 앞 읽기가 끝나기 전에 새 읽기가 왔다 → 앞 읽기의 흔적(상태·패널·말풍선)을 지운다
            self._last = None
            self._set_panel_open(False)
            self._hide_tip()
        self._cancel("fill")
        self._fill_drawn = self._fill_from = 0.0
        self._fill_target = -1              # 다음 _render 에서 반드시 목표를 다시 잡게
        self._play_state = None             # 스피너를 다시 돌리게(같은 상태면 건너뛰므로)
        self._visible = True
        self._render()
        if not was_visible:
            self._win.deiconify()           # overrideredirect 창이라 Tk 가 포커스를 강제로 옮기지 않는다(tkWinWm.c TkpWinToplevelDeiconify)
            self._hwnd = _make_tool_window(self._win) or self._hwnd
            self._after("keep", KEEP_ALIVE_MS, self._keep_alive)
        if self._panel_open:
            self._place_panel()

    def hide(self):
        """바·패널·말풍선을 숨기고 타이머를 모두 멈춘다. 읽기가 끝나거나 멈출 때 부른다.

        ⚠ 마지막 상태(_last)도 비운다. 다음 show() 는 새 읽기로 보고 "불러오는 중" 모양에서 시작한다.
        """
        if self._destroyed:
            return
        self._visible = False
        self._set_panel_open(False)
        self._hide_tip()
        for name in list(self._jobs):
            self._cancel(name)
        self._hover = self._pressed = None
        self._last = None
        try:
            self._win.withdraw()
        except tk.TclError:
            pass
        self._render()

    def destroy(self):
        """창을 모두 없앤다. 앱 종료 때 부른다. 이후 다른 메서드는 아무것도 안 한다."""
        if self._destroyed:
            return
        try:
            self.hide()
        except Exception:
            pass
        self._destroyed = True
        for w in (self._tip, self._panel, self._win):
            try:
                w.destroy()
            except Exception:
                pass

    def update(self, st):
        """재생 상태를 받아 바를 다시 그린다 (확장 renderBar, page-ui.js:685-702).

        st 에 빠진 키는 _DEFAULT_ST 로 채운다. 숨겨진 동안 불러도 상태를 기억해 두었다가
        show() 때 그대로 보인다. state 가 "STOPPED" 이면 바를 숨긴다
        (확장: 읽기가 끝나면 바 자체가 사라진다 — removeBar, page-ui.js:611).
        """
        if self._destroyed:
            return
        merged = dict(_DEFAULT_ST)
        merged.update(st or {})
        if merged.get("state") == "STOPPED":
            self.hide()
            return
        self._last = (merged, time.monotonic())
        self._render()

    # ───────────────────────────── 그리기 ─────────────────────────────
    def _current(self):
        return self._last if self._last else (dict(_DEFAULT_ST), time.monotonic())

    def _displayed_time(self):
        """지금 보여 줄 (경과, 총, 진행률). 확장 displayedTime(page-ui.js:718-723) 그대로.

        PLAYING 이면 마지막 update 이후 흐른 시간을 경과에 더한다. 총 시간이 경과보다 짧게
        추정돼 있으면 경과로 끌어올린다. 총 시간을 모르면(None) 받은 progress 를 쓴다.
        """
        st, at = self._current()
        try:
            elapsed = float(st.get("elapsed") or 0.0)
        except (TypeError, ValueError):
            elapsed = 0.0
        if st.get("state") == "PLAYING":
            elapsed += time.monotonic() - at
        total = st.get("total")
        if total is not None:
            try:
                total = max(float(total), elapsed)
            except (TypeError, ValueError):
                total = None
        progress = (elapsed / total) if total else st.get("progress")
        return elapsed, total, progress

    def _render(self):
        """마지막 상태로 바 전체를 다시 그린다. 싸므로 update 때마다 불러도 된다."""
        if self._destroyed:
            return
        st, _ = self._current()
        state = st.get("state") or "LOADING"
        b = self._buttons
        # 재생 버튼 모양: LOADING 스피너 / PAUSED ▶ / 그 밖 ⏸ (renderPlayButton, page-ui.js:747-758)
        self._set_play_state(state)
        # 이전/다음: 확장은 PLAYING·PAUSED 일 때만 누를 수 있다(page-ui.js:695-696).
        # 약속된 can_prev/can_next 도 함께 본다(첫/마지막 조각 등은 재생 엔진이 판단).
        navigable = state in ("PLAYING", "PAUSED")
        b["prev"].enabled = navigable and bool(st.get("can_prev"))
        b["next"].enabled = navigable and bool(st.get("can_next"))
        # 음소거: can_mute 일 때만 보인다(page-ui.js:697)
        b["mute"].visible = bool(st.get("can_mute"))
        self._muted = bool(st.get("muted"))
        # 설정: 값(rate/volume)이 없으면 비활성(page-ui.js:706)
        self._settings_enabled = st.get("rate") is not None or st.get("volume") is not None
        b["settings"].enabled = self._settings_enabled
        if self._panel_open and not self._settings_enabled:
            self._set_panel_open(False)
        self._render_params(st)
        self._render_time()
        self._redraw_buttons()
        self._schedule_tick()
        if self._tip_key:
            self._tip_label.configure(text=self._button_label(self._tip_key))

    def _render_time(self):
        """시간 글자와 진행선 목표를 갱신한다 (확장 renderTime, page-ui.js:725-733)."""
        elapsed, total, progress = self._displayed_time()
        el = _format_time(elapsed)
        if total is not None:
            tot = " / %s %s" % (self._t("pagebar_about"), _format_time(total))
        else:
            tot = " / %s" % self._t("pagebar_calculating")
        c = self._canvas
        c.itemconfigure(self._time_el, text=el)
        c.itemconfigure(self._time_tot, text=tot)
        self._layout(self._font.measure(el), self._font.measure(tot))
        try:
            frac = max(0.0, min(1.0, float(progress or 0.0)))
        except (TypeError, ValueError):
            frac = 0.0
        self._set_fill_target(int(round(frac * self._w)))

    def _layout(self, el_w, tot_w):
        """가운데 무리와 오른쪽 무리의 위치를 잡는다.

        확장 .bar 는 grid "1fr auto 1fr"(page-ui.js:855): 가운데 칸은 내용 폭만큼, 좌우 칸은 남는
        폭을 반씩 → 가운데 무리가 바 한가운데 온다. 단 오른쪽 칸은 설정·닫기 폭보다 좁아질 수
        없다(1fr 의 최소 = 내용 폭). 시간 글자 폭이 바뀌거나 음소거가 보이고 숨을 때 버튼이
        조금 움직이는 것도 확장과 같다.
        """
        tw = max(self._px(TIME_MIN_W), el_w + tot_w)
        mute_vis = self._buttons["mute"].visible
        key = (self._w, tw, el_w, tot_w, mute_vis)
        if key == self._layout_key:
            return
        self._layout_key = key
        p = self._px
        W, H = self._w, self._h
        cy = H / 2.0
        gap = p(CENTER_GAP)
        center = ["prev", "play", "next"] + (["mute"] if mute_vis else [])
        center_w = tw + p(TIME_MARGIN_R) + sum(gap + self._buttons[k].d for k in center)
        end_w = p(BTN_D) * 2 + p(END_GAP)
        avail = W - 2 * p(BAR_PAD_X)
        side = (avail - center_w) / 2.0
        if side < end_w:                              # 오른쪽 칸이 설정·닫기보다 좁아지면
            side = max(0.0, avail - center_w - end_w)
        x = p(BAR_PAD_X) + side
        c = self._canvas
        # 시간: 폭 tw 상자 안 오른쪽 정렬(.time text-align:right)
        c.coords(self._time_tot, x + tw, cy)
        c.coords(self._time_el, x + tw - tot_w, cy)
        x += tw + p(TIME_MARGIN_R)
        for k in center:
            bt = self._buttons[k]
            x += gap
            bt.cx, bt.cy = x + bt.d / 2.0, cy
            x += bt.d
        # 오른쪽 끝: [설정] 4px [닫기], 오른쪽 여백 12px
        close, sett = self._buttons["close"], self._buttons["settings"]
        close.cx, close.cy = W - p(BAR_PAD_X) - close.d / 2.0, cy
        sett.cx, sett.cy = close.cx - close.d / 2.0 - p(END_GAP) - sett.d / 2.0, cy
        for bt in self._buttons.values():
            c.coords(bt.disc, bt.cx, bt.cy)
            c.coords(bt.icon, bt.cx, bt.cy)
        c.coords(self._spinner, self._buttons["play"].cx, cy)
        c.coords(self._prog_bg, 0, 0, W, p(PROGRESS_H))
        self._draw_fill()

    def _redraw_buttons(self):
        """버튼 모양(보임·활성·호버·아이콘)을 지금 상태대로 칠한다."""
        c = self._canvas
        for key, bt in self._buttons.items():
            if not bt.visible:
                c.itemconfigure(bt.disc, state="hidden")
                c.itemconfigure(bt.icon, state="hidden")
                continue
            if key == "play":
                hover = self._hover == "play"
                c.itemconfigure(bt.disc, image=self._img["play_hover" if hover else "play"], state="normal")
                loading = self._play_state == "LOADING"
                glyph, size = ICON_GLYPHS["play" if self._play_state == "PAUSED" else "pause"]
                c.itemconfigure(bt.icon, text=glyph, font=self._icon_font(size), fill=PLAY_FG,
                                state="hidden" if loading else "normal")
                c.itemconfigure(self._spinner, state="normal" if loading else "hidden")
                continue
            # 호버 배경: 활성 버튼에 마우스가 올라가 있을 때. 설정은 패널이 열려 있는 동안에도
            # (button.settings[aria-expanded="true"], page-ui.js:932-934)
            bg_on = bt.enabled and (self._hover == key or (key == "settings" and self._panel_open))
            c.itemconfigure(bt.disc, state="normal" if bg_on else "hidden")
            icon_key = {"mute": "muted" if self._muted else "volume"}.get(key, key)
            glyph, size = ICON_GLYPHS[icon_key]
            c.itemconfigure(bt.icon, text=glyph, font=self._icon_font(size), state="normal",
                            fill=BAR_FG if bt.enabled else DISABLED_FG)
        # 손가락 커서: 활성 버튼 위에서만 (button cursor:pointer / disabled cursor:default)
        hb = self._buttons.get(self._hover)
        c.configure(cursor="hand2" if hb is not None and hb.enabled else "")

    def _set_play_state(self, state):
        """재생 버튼 상태를 바꾸고, LOADING 이면 스피너를 돌린다."""
        if state == self._play_state:
            return
        self._play_state = state
        if state == "LOADING" and self._visible:
            self._spin_idx = 0
            self._after("spin", 0, self._spin_step)
        else:
            self._cancel("spin")

    def _spin_step(self):
        """스피너 한 칸 돌리기. 0.8초에 한 바퀴(SPIN_FRAMES 장)."""
        if self._destroyed or not self._visible or self._play_state != "LOADING":
            return
        frames = self._spin[self._hover == "play"]
        self._spin_idx = (self._spin_idx + 1) % len(frames)
        self._canvas.itemconfigure(self._spinner, image=frames[self._spin_idx])
        self._after("spin", max(1, SPIN_PERIOD_MS // SPIN_FRAMES), self._spin_step)

    def _schedule_tick(self):
        """PLAYING 이면 표시된 초가 바뀌는 순간에 맞춰 다시 그린다 (확장 scheduleTime, page-ui.js:736-745).

        다음 정수 초까지 남은 ms 만큼 기다린다. 타이머 오차로 경계 직전에 깨어 같은 초를
        다시 그리지 않도록 올림 + 1ms 한다.
        """
        self._cancel("tick")
        st, _ = self._current()
        if not self._visible or st.get("state") != "PLAYING":
            return
        ms = self._displayed_time()[0] * 1000.0
        delay = int(math.ceil(1000.0 - (ms % 1000.0))) + 1
        self._after("tick", delay, self._on_tick)

    def _on_tick(self):
        if self._destroyed or not self._visible:
            return
        self._render_time()
        self._schedule_tick()

    # 진행선 — CSS transition: width 1s linear 흉내
    def _set_fill_target(self, px):
        """진행선 목표 폭을 정한다. 폭이 바뀌면 지금 그려진 폭에서 목표까지 1초 동안 곧게 움직인다.

        전환 도중 목표가 또 바뀌면 그 자리에서 새로 1초 전환을 시작한다(CSS transition 과 같다).
        """
        if px == self._fill_target:
            return
        self._fill_target = px
        self._fill_from = self._fill_drawn
        self._fill_t0 = time.monotonic()
        if not self._visible:
            self._fill_drawn = self._fill_from = float(px)
            self._draw_fill()
            return
        if "fill" not in self._jobs:
            self._fill_step()

    def _fill_step(self):
        self._jobs.pop("fill", None)
        if self._destroyed:
            return
        t = (time.monotonic() - self._fill_t0) * 1000.0 / FILL_TRANSITION_MS
        if t >= 1.0 or not self._visible:
            self._fill_drawn = float(self._fill_target)
        else:
            self._fill_drawn = self._fill_from + (self._fill_target - self._fill_from) * t
        self._draw_fill()
        if self._visible and self._fill_drawn != self._fill_target:
            self._after("fill", FILL_FRAME_MS, self._fill_step)

    def _draw_fill(self):
        w = int(round(self._fill_drawn))
        c = self._canvas
        if w <= 0:
            c.itemconfigure(self._prog_fill, state="hidden")
        else:
            c.coords(self._prog_fill, 0, 0, w, self._px(PROGRESS_H))
            c.itemconfigure(self._prog_fill, state="normal")

    # ──────────────────────────── 마우스(바) ────────────────────────────
    def _hit(self, x, y):
        """(x, y) 에 있는 보이는 버튼의 key. 동그라미 안쪽만 버튼으로 친다."""
        for key, bt in self._buttons.items():
            if bt.visible and (x - bt.cx) ** 2 + (y - bt.cy) ** 2 <= (bt.d / 2.0) ** 2:
                return key
        return None

    def _on_bar_motion(self, e):
        key = self._hit(e.x, e.y)
        if key != self._hover:
            self._hover = key
            self._redraw_buttons()
            self._schedule_tip(key)

    def _on_bar_leave(self, _e):
        if self._hover is not None:
            self._hover = None
            self._redraw_buttons()
        self._schedule_tip(None)

    def _on_bar_press(self, e):
        key = self._hit(e.x, e.y)
        self._pressed = key if key and self._buttons[key].enabled else None
        self._schedule_tip(None)

    def _on_bar_release(self, e):
        """누른 버튼 위에서 떼야 클릭으로 친다(브라우저 click 과 같음)."""
        key = self._hit(e.x, e.y)
        pressed, self._pressed = self._pressed, None
        if key and key == pressed and self._buttons[key].enabled:
            self._activate(key)

    def _activate(self, key):
        """버튼이 눌렸을 때 할 일 (확장 startBar 의 button(...) 콜백, page-ui.js:577-586)."""
        if key == "prev":
            self._send("rewind")
        elif key == "play":
            self._send("togglePause")
        elif key == "next":
            self._send("forward")
        elif key == "mute":
            self._send("unmute" if self._muted else "mute")
        elif key == "settings":
            self._set_panel_open(not self._panel_open)
        elif key == "close":
            # 확장: stop 을 보내고 곧바로 바를 숨긴다(page-ui.js:583-586)
            self._send("stop")
            self.hide()

    def _send(self, cmd, value=None):
        """on_command 호출. 받는 쪽 예외가 Tk 이벤트 루프를 깨지 않게 막는다."""
        try:
            if value is None:
                self._on_command(cmd)
            else:
                self._on_command(cmd, value)
        except Exception:
            log.exception("하단 바 명령 처리 실패: %s", cmd)

    # ───────────────────────────── 말풍선 ─────────────────────────────
    def _button_label(self, key):
        if key == "play":
            return self._t({"LOADING": "pagebar_loading", "PAUSED": "pagebar_play"}.get(
                self._play_state, "pagebar_pause"))
        if key == "mute":
            return self._t("pagebar_unmute" if self._muted else "pagebar_mute")
        return self._t({"prev": "pagebar_prev", "next": "pagebar_next",
                        "settings": "pagebar_settings", "close": "pagebar_stop"}[key])

    def _schedule_tip(self, key):
        self._hide_tip()
        self._cancel("tip")
        if key:
            self._after("tip", _tooltip_delay_ms(), lambda k=key: self._show_tip(k))

    def _show_tip(self, key):
        """버튼 바로 위, 가운데 맞춰 이름표를 띄운다. 작업 영역 밖으로 나가지 않게 자른다."""
        self._jobs.pop("tip", None)
        if self._destroyed or not self._visible or self._hover != key:
            return
        bt = self._buttons[key]
        self._tip_label.configure(text=self._button_label(key))
        self._tip.update_idletasks()
        tw, th = self._tip.winfo_reqwidth(), self._tip.winfo_reqheight()
        left, top, right, bottom = self._work_area
        bar_y = bottom - self._h
        x = int(left + bt.cx - tw / 2.0)
        x = max(left, min(right - tw, x))
        y = int(bar_y + bt.cy - bt.d / 2.0 - self._px(4) - th)
        self._tip.geometry("%dx%d+%d+%d" % (tw, th, x, y))
        self._tip.deiconify()
        self._tip_hwnd = _make_tool_window(self._tip) or self._tip_hwnd
        self._tip_key = key

    def _hide_tip(self):
        if self._tip_key is not None:
            self._tip_key = None
            try:
                self._tip.withdraw()
            except tk.TclError:
                pass

    # ──────────────────────────── 설정 패널 ────────────────────────────
    def _set_panel_open(self, open_):
        """패널 열기/닫기 (확장 togglePanel, page-ui.js:647-662).

        열려 있는 동안 _poll_outside 가 Esc·바깥 클릭·전경 창 바뀜(확장의 blur)을 살핀다.
        ⚠ 이 창들은 포커스를 받지 않으므로 FocusOut·<Escape> 바인딩으로는 알 수 없다.
        """
        if open_ and (self._destroyed or not self._visible or not self._settings_enabled):
            return
        if open_ == self._panel_open:
            return
        self._panel_open = open_
        if open_:
            self._place_panel()
            self._panel.deiconify()
            self._panel_hwnd = _make_tool_window(self._panel) or self._panel_hwnd
            self._panel_fg = _foreground_hwnd()
            self._poll_prev = self._poll_state()
            self._after("poll", OUTSIDE_POLL_MS, self._poll_outside)
        else:
            self._cancel("poll")
            self._drag = None
            for k in self._editing:
                self._editing[k] = False
            try:
                self._panel.withdraw()
            except tk.TclError:
                pass
            # 끌던 값이 반영 안 됐을 수 있으니 마지막 상태로 되돌려 그린다
            self._render_params(self._current()[0])
        self._redraw_buttons()

    def _place_panel(self):
        """패널을 바 오른쪽 끝에서 12px 안쪽, 바 위 8px 에 놓는다."""
        left, top, right, bottom = self._work_area
        x = left + self._w - self._px(PANEL_RIGHT) - self._pw
        y = bottom - self._h - self._px(PANEL_GAP) - self._ph
        self._panel.geometry("%dx%d+%d+%d" % (self._pw, self._ph, x, y))

    def _poll_state(self):
        esc = _key_down(_VK_ESCAPE) if _IS_WIN else False
        mouse = any(_key_down(v) for v in (_VK_LBUTTON, _VK_RBUTTON, _VK_MBUTTON)) if _IS_WIN else False
        return esc, mouse

    def _poll_outside(self):
        """패널이 열려 있는 동안 '닫을 때'를 살핀다 (확장 listenOutside, page-ui.js:678-683).

        - Esc 가 새로 눌림
        - 마우스 버튼이 새로 눌렸는데 그 자리가 바·패널 밖
          (확장도 바 안을 누르는 것은 바깥으로 치지 않는다 — composedPath().includes(host))
        - 전경 창이 바뀜(확장의 window blur 에 해당)
        """
        self._jobs.pop("poll", None)
        if self._destroyed or not self._panel_open:
            return
        esc, mouse = self._poll_state()
        prev_esc, prev_mouse = self._poll_prev or (False, False)
        self._poll_prev = (esc, mouse)
        close = esc and not prev_esc
        if not close and mouse and not prev_mouse:
            pos = _cursor_pos()
            if pos and not (self._inside_bar(*pos) or self._inside_panel(*pos)):
                close = True
        if not close and _IS_WIN and _foreground_hwnd() != self._panel_fg:
            close = True
        if close:
            self._set_panel_open(False)
        else:
            self._after("poll", OUTSIDE_POLL_MS, self._poll_outside)

    def _inside_bar(self, x, y):
        left, top, right, bottom = self._work_area
        return left <= x < left + self._w and bottom - self._h <= y < bottom

    def _inside_panel(self, x, y):
        try:
            px, py = self._panel.winfo_rootx(), self._panel.winfo_rooty()
        except tk.TclError:
            return False
        return px <= x < px + self._pw and py <= y < py + self._ph

    def _render_params(self, st):
        """update 로 받은 rate/volume 을 슬라이더에 반영한다. 끌고 있는 슬라이더는 건드리지 않는다
        (확장 renderParams, page-ui.js:704-714)."""
        for key, p in _PARAMS.items():
            self._panel_canvas.itemconfigure(self._rows[key]["name"], text=self._t(p["label"]))
            val = st.get(key)
            if self._editing[key] or val is None:
                continue
            try:
                self._slider_vals[key] = _snap(p, p["to_slider"](float(val)))
                shown = p["format"](float(val))
            except (TypeError, ValueError):
                continue
            self._draw_slider(key, shown)

    def _draw_slider(self, key, shown=None):
        """슬라이더 한 줄을 그린다. shown 이 없으면 슬라이더 값으로 표시 글자를 만든다.

        손잡이 중심은 입력 칸 양 끝에서 손잡이 반지름만큼 안쪽 사이를 움직인다(브라우저 range 와 같음).
        """
        p, row = _PARAMS[key], self._rows[key]
        pc = self._panel_canvas
        v = self._slider_vals[key]
        frac = (v - p["min"]) / (p["max"] - p["min"])
        r = self._px(SLIDER_THUMB_D) / 2.0
        tx = row["x0"] + r + frac * (row["x1"] - row["x0"] - 2 * r)
        th = self._px(SLIDER_TRACK_H)
        pc.coords(row["fill"], row["x0"] + th / 2.0, row["cy"], max(row["x0"] + th / 2.0, tx), row["cy"])
        pc.coords(row["thumb"], tx, row["cy"])
        if shown is None:
            shown = p["format"](p["from_slider"](v))
        pc.itemconfigure(row["value"], text=shown)

    def _slider_at(self, x, y):
        """(x, y) 가 어느 슬라이더 입력 칸 안인지. 칸 높이는 손잡이 지름만큼."""
        half = self._px(SLIDER_THUMB_D) / 2.0
        for key, row in self._rows.items():
            if row["x0"] <= x <= row["x1"] and abs(y - row["cy"]) <= half:
                return key
        return None

    def _set_slider_from_x(self, key, x):
        p, row = _PARAMS[key], self._rows[key]
        r = self._px(SLIDER_THUMB_D) / 2.0
        span = max(1.0, row["x1"] - row["x0"] - 2 * r)
        frac = max(0.0, min(1.0, (x - row["x0"] - r) / span))
        v = _snap(p, p["min"] + frac * (p["max"] - p["min"]))
        if v != self._slider_vals[key]:
            self._slider_vals[key] = v
            self._draw_slider(key)       # 확장 input 이벤트: 끄는 동안 값 글자만 바뀐다

    def _on_panel_press(self, e):
        key = self._slider_at(e.x, e.y)
        if not key:
            return
        self._drag = (key, self._slider_vals[key])
        self._editing[key] = True
        self._set_slider_from_x(key, e.x)

    def _on_panel_drag(self, e):
        if self._drag:
            self._set_slider_from_x(self._drag[0], e.x)

    def _on_panel_release(self, _e):
        """손을 뗄 때 한 번만 명령을 보낸다 (확장 change 이벤트, page-ui.js:637-642).

        누를 때와 값이 같으면 보내지 않는다(브라우저도 제자리에서 떼면 change 가 없다).
        """
        if not self._drag:
            return
        key, start = self._drag
        self._drag = None
        self._editing[key] = False
        v = self._slider_vals[key]
        if v != start:
            p = _PARAMS[key]
            self._send(p["cmd"], p["from_slider"](v))

    def _on_panel_motion(self, e):
        self._panel_canvas.configure(cursor="hand2" if self._slider_at(e.x, e.y) else "")

    # ───────────────────────────── 기타 ─────────────────────────────
    def _keep_alive(self):
        """보이는 동안 3초마다 '항상 위'를 다시 확정한다(플로팅 아이콘 update_state 와 같은 주기).

        ⚠ 보일 때만 돈다. hide() 가 이 타이머를 끊는다. SWP_SHOWWINDOW 를 안 쓰므로
          혹시 숨긴 창에 불려도 되살리지 않는다.
        """
        self._jobs.pop("keep", None)
        if self._destroyed or not self._visible:
            return
        _set_topmost(self._hwnd)
        if self._panel_open:
            _set_topmost(self._panel_hwnd)     # 패널은 바보다 위
        if self._tip_key:
            _set_topmost(self._tip_hwnd)
        self._after("keep", KEEP_ALIVE_MS, self._keep_alive)

    def _after(self, name, ms, fn):
        """이름 붙은 타이머. 같은 이름을 다시 걸면 앞의 것은 취소된다."""
        self._cancel(name)
        if self._destroyed:
            return
        try:
            self._jobs[name] = self._root.after(ms, fn)
        except tk.TclError:
            pass

    def _cancel(self, name):
        job = self._jobs.pop(name, None)
        if job is not None:
            try:
                self._root.after_cancel(job)
            except tk.TclError:
                pass


# ════════════════════════════════════════════════════════════════════
#  데모 — python bottom_bar.py [--shots 폴더]
#  가짜 update 를 흘려보내고 6초 뒤 스스로 끝난다. 소리·단축키·트레이 없음.
#  --shots 를 주면 상태마다 바 영역을 PIL.ImageGrab 으로 찍어 bar_<상태>.png 로 저장한다.
# ════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO)
    shots = None
    if "--shots" in sys.argv:
        shots = sys.argv[sys.argv.index("--shots") + 1]
        os.makedirs(shots, exist_ok=True)

    # 앱과 같은 조건(ttkbootstrap Window → DPI 인식 + 자동 스타일 패치)으로 띄운다.
    try:
        import ttkbootstrap as _ttkb
        demo_root = _ttkb.Window(themename="cosmo")
    except Exception:
        if _IS_WIN:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        demo_root = tk.Tk()
    demo_root.withdraw()

    def _demo_cmd(cmd, value=None):
        print("[demo] on_command:", cmd, value, flush=True)

    # 없는 키 흉내 → 한국어 기본값 폴백 확인
    demo_bar = BottomBar(demo_root, _demo_cmd, lambda key, *a: "[Missing message: %s]" % key)
    wa = foreground_work_area() or (0, 0, demo_root.winfo_screenwidth(), demo_root.winfo_screenheight())
    print("[demo] scale=%.3f height=%d work_area=%s" % (demo_bar._s, demo_bar.height, wa), flush=True)

    base = {"state": "LOADING", "elapsed": 0.0, "total": None, "progress": 0.0,
            "can_prev": False, "can_next": False, "can_mute": True, "muted": False,
            "rate": 1.0, "volume": 1.0}

    def _grab(name, with_panel=False):
        if not shots:
            return
        from PIL import ImageGrab
        demo_root.update()
        left, top, right, bottom = wa
        y0 = bottom - demo_bar.height
        if with_panel:
            y0 -= demo_bar._ph + demo_bar._px(PANEL_GAP) + 4
            box = (max(left, right - 900), y0, right, bottom)
        else:
            box = (left, y0 - 4, right, bottom)
        ImageGrab.grab(bbox=box, all_screens=True).save(os.path.join(shots, "bar_%s.png" % name))
        print("[demo] saved", name, box, flush=True)

    steps = [
        (0, lambda: (demo_bar.update(dict(base)), demo_bar.show(wa))),
        (700, lambda: _grab("LOADING")),
        (1000, lambda: demo_bar.update(dict(base, state="PLAYING", elapsed=12.0, total=83.0,
                                             progress=12 / 83.0, can_prev=True, can_next=True))),
        (2300, lambda: _grab("PLAYING")),
        (2600, lambda: demo_bar.update(dict(base, state="PAUSED", elapsed=13.4, total=83.0,
                                             progress=13.4 / 83.0, can_prev=True, can_next=False,
                                             muted=True, rate=1.25, volume=0.6))),
        (3700, lambda: _grab("PAUSED")),
        (4000, lambda: demo_bar._set_panel_open(True)),
        (4600, lambda: _grab("PANEL", with_panel=True)),
        (6000, lambda: (demo_bar.destroy(), demo_root.destroy())),
    ]
    for ms, fn in steps:
        demo_root.after(ms, fn)
    demo_root.mainloop()
    print("[demo] 끝", flush=True)
