# -*- coding: utf-8 -*-
"""리더 창(ReaderWindow) — 원문을 보여 주고, 지금 읽는 조각을 형광펜으로 칠하는 작은 도구 창.

왜 이 창이 있나
  크롬 확장(read-aloud-hrg)은 웹 페이지 글자 위에 직접 형광펜을 칠한다. 데스크톱 앱은 클립보드로 글을
  받기 때문에 원래 앱(메모장·브라우저 등)의 글자 위에 칠할 수단이 없다. 그래서 받은 원문을 이 창에
  그대로 보여 주고, 확장처럼 "지금 읽는 조각(줄 단위)"을 칠한다. (원문 위에 칠하기=UIA 는 이번 범위 밖)

누가 어떻게 부르나 (모듈 사이 약속 — 이름·모양을 바꾸지 말 것)
  rw = ReaderWindow(root, get_msg, on_geometry_changed=None)
  rw.start(source_text, segments)   # segments = readaloud_text.split_for_reading() 결과
  rw.show(work_area, bar_height, geometry=None)
  rw.highlight(idx)                 # idx 조각을 칠함. None 이면 지움
  rw.end()                          # 읽기 끝: 칠 지우고 숨김
  rw.hide(); rw.destroy()

  ⚠ 모든 메서드는 Tk 메인 스레드에서만 부른다. tkinter 는 스레드 안전하지 않다(07-27 로그 §4-5).
    재생 스레드에서 부를 일이 있으면 whisperer.py 의 gui_queue → check_gui_queue 로 넘겨서 부른다.

이 창의 성질
  - 다크 모드(2026-09-28 사용자 요청 "하얀 바탕에 검은 글씨라 눈이 아프다"): 어두운 회색 바탕 + 흰 글자.
    색은 모두 확장 값에서 왔다 — 바탕 = 확장 설정 패널 rgba(56,56,56,.97), 머리 막대 = 확장 하단 바 rgba(86,86,86,0.95),
    형광펜 = 확장 단락 형광펜 rgba(255,226,0,0.3)(js/events.js:374)을 그 어두운 바탕에 합성한 색.
  - 형광펜은 확장(CSS Highlight)처럼 글자 부분만 칠한다: 줄바꿈 글자와 "자동 줄바꿈으로 접히는 자리의 공백"은
    칠하지 않는다(Tk 는 그 공백을 줄 오른쪽 끝까지 늘려 그려서, 칠하면 형광펜이 창 끝까지 뻗는다 — _trim_wrap_spaces).
  - 윈도우 제목 표시줄이 없는 창(overrideredirect) + 우리가 직접 그린 "머리 막대"(2026-09-28 사용자 요청
    "VS Code 에서 리더 창 끄기가 너무 힘들다 / 드래그로 옮기게 해 달라"):
      · 머리 막대 아무 곳이나 잡고 끌면 창이 옮겨진다(_drag_*).
      · 오른쪽 끝 큰 닫기 버튼(확장 바 버튼과 같은 36px) — 누르면 이번 읽기 동안 숨긴다. 읽기는 계속된다.
      · 오른쪽 아래 모서리 손잡이를 끌면 크기가 바뀐다.
    왜 윈도우 제목 표시줄을 버렸나: 포커스를 뺏지 않는 창(WS_EX_NOACTIVATE)의 작은 도구 창 제목 표시줄은
    잡기도 닫기도 어색했다(사용자 보고). 하단 바처럼 창 안에 직접 그리면 끌기·닫기를 우리가 확실히 처리한다.
  - 항상 위. 뜰 때도, 클릭해도 포커스를 뺏지 않는다(WS_EX_NOACTIVATE). 포커스를 뺏으면 사용자가 보던 앱에서
    다음 Ctrl+C(선택 읽기)가 엉뚱한 창으로 간다(07-27 로그 §4-4, 플로팅 아이콘과 같은 이유).
  - 활성 모니터에 뜬다(2026-09-28 사용자 요청): 저장해 둔 위치는 "그 위치가 있던 모니터 안에서의 자리"로 보고,
    지금 읽기를 시작한 모니터(부르는 쪽이 넘긴 work_area)의 같은 자리로 옮겨 띄운다(_place_saved).
  - 사용자가 옮기거나 크기를 바꾸면, 마우스 버튼을 뗀 뒤 한 번만 on_geometry_changed(geometry 문자열)를 부른다.

가장 중요한 함정 두 가지 (실측 근거는 각 함수 주석)
  1. 글자 위치: 파이썬은 이모지(BMP 밖 글자)를 1글자로 세지만, 이 PC 의 Tcl/Tk 8.6.15 는 Text 의
     "줄.칸" 인덱스에서 2칸으로 센다. → TkTextOffsets 가 파이썬 오프셋을 Tk "줄.칸" 인덱스로 바꾼다.
  2. 포커스: Tk 의 deiconify 는 창을 보이면서 강제로 포커스를 가져간다(tkWinWm.c 8.6.15
     TkpWinToplevelDeiconify → TkSetFocusWin(winPtr, 1)). → 보이기·숨기기는 Win32 ShowWindow 로 직접 한다.
  3. 속도: 줄바꿈 없는 긴 문단(원문 한 줄이 수천 자)에서 Tk 의 "표시 줄" 계산은 그 줄 첫머리부터 다시 배치해서
     매우 느리다(2026-09-28 실측, 5,000자 한 줄: `count -ypixels` 3.5초, `display linestart` 67ms, `see` 약 0.3초).
     예전 스크롤 코드는 칠할 때마다 Tk 메인 스레드를 최대 4.5초 멈췄다(바·트레이까지 멈춤).
     → _reveal·_trim_wrap_spaces 는 화면에 보이는 줄 정보(dlineinfo/bbox, 사실상 0ms)와 아래로 스크롤만 쓴다.
       `count -ypixels`·`display lineend/linestart`·`+N display lines` 를 칠하기·스크롤 경로에 다시 넣지 마라.
"""

import bisect
import ctypes
import logging
import re
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont

log = logging.getLogger(__name__)

__all__ = ["ReaderWindow", "TkTextOffsets", "HIGHLIGHT_BG"]

# ── 모양 값 ───────────────────────────────────────────────────────────────
# 다크 모드(2026-09-28 사용자 요청). 색마다 확장 값을 근거로 삼았고, 반투명 색은 아래 바탕에 합성해 불투명 색으로 바꿨다
# (Tk 는 반투명 색을 모른다). 합성식: 결과 = 알파 × 앞색 + (1 − 알파) × 바탕.
TEXT_BG = "#383838"        # 글 바탕 = 확장 설정 패널 배경 rgba(56,56,56,.97)(js/page-ui.js .panel). 하단 바(#565656)보다 한 톤 어둡다
TEXT_FG = "#FFFFFF"        # 글자 = 확장 바 글자색 #fff. 확장 단락 형광펜은 글자색을 바꾸지 않는다 → 칠한 곳도 흰 글자
HIGHLIGHT_BG = "#746B27"   # 형광펜 = 확장 단락 형광펜 rgba(255,226,0,0.3)(js/events.js:374)을 #383838 에 합성
                           #   (0.3×255+0.7×56, 0.3×226+0.7×56, 0.7×56) = (116,107,39). 흰 글자와의 대비 약 5.4:1
HEADER_BG = "#565656"      # 머리 막대·테두리 = 확장 하단 바 배경 rgba(86,86,86,0.95) → 하단 바와 한 벌로 보이게
HEADER_FG = "#FFFFFF"      # 닫기 아이콘 = 확장 바 글자색
HEADER_FG_DIM = "#CCCCCC"  # 제목 글자 = 확장 총 시간 글자색(흰색 70%)을 #565656 에 합성
HEADER_HOVER_BG = "#6E6E6E"  # 닫기 버튼에 마우스를 올렸을 때 = 확장 버튼 hover 흰색 14% 를 #565656 에 합성
# 머리 막대 높이 = 확장 바 버튼 36×36(js/page-ui.js .btn) — 닫기 버튼을 확장 버튼 크기로 크게(사용자: "끄기가 힘들다")
HEADER_HEIGHT_PX = 36      # 96 DPI 기준 px. 실제로는 화면 배율을 곱한다(_scale)
# 최소 크기: 폭은 확장 설정 패널 폭 280px(js/page-ui.js .panel) 을 빌렸다. 높이는 [임의] 머리 막대 + 글 약 3줄
MIN_WIDTH_PX = 280
MIN_HEIGHT_PX = 120        # [임의] 근거 없음 — 너무 작게 줄여 창을 잃어버리지 않게만
GRIP_PX = 16               # [임의] 오른쪽 아래 크기 손잡이 한 변(96 DPI 기준 px). 윈도우 기본 크기 손잡이와 비슷한 크기
# 닫기 아이콘 — 하단 바(bottom_bar.py ICON_FAMILIES·ICON_GLYPHS["close"])와 같은 윈도우 아이콘 글꼴 글리프 ChromeClose.
# 두 창의 닫기 모양을 맞추려고 같은 값을 쓴다. 아이콘 글꼴이 없으면 일반 글꼴의 "✕" 로 대신한다.
CLOSE_ICON_FAMILIES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")
CLOSE_GLYPH = ""     # ChromeClose ↔ 확장 Material close
CLOSE_GLYPH_PX = 13        # 하단 바 ICON_GLYPHS["close"] 와 같은 크기(CSS px)
CLOSE_FALLBACK = "✕"  # ✕
# 글꼴: 확장 바의 글꼴 목록(js/page-ui.js:859 system-ui, "Segoe UI", "Malgun Gothic")에서 고른다.
# Tk 는 글꼴을 하나만 받는다(브라우저처럼 글자마다 다른 글꼴로 넘어가지 못함). 한글이 주로 오므로
# 한글·영문을 모두 가진 "Malgun Gothic" 을 먼저, 없으면 "Segoe UI".
FONT_FAMILIES = ("Malgun Gothic", "Segoe UI")
FONT_SIZE_PT = 11          # [임의] 근거 없음. 11pt(100% 배율에서 약 15px). 보고서에 적음
TEXT_PADX = 10             # [임의] 글과 창 가장자리 사이 여백(px)
TEXT_PADY = 8              # [임의]

# 기본 위치·크기: 하단 바 바로 위 오른쪽, 작업 영역 폭 40%·높이 35% (오케스트레이터 지정 기본값)
DEFAULT_WIDTH_RATIO = 0.40
DEFAULT_HEIGHT_RATIO = 0.35

# 사용자가 창을 끄는(드래그·크기 조절) 동안 마우스 버튼이 떨어졌는지 확인하는 간격.
# [임의] 100ms — whisperer.py check_gui_queue 주기와 같은 값으로 맞췄다. 저장 시점만 늦출 뿐 동작엔 영향 없음.
RELEASE_POLL_MS = 100

_HL_TAG = "readaloud_hl"   # 형광펜 태그 이름

# messages.py 에 키가 없을 때 쓰는 기본 한국어 문구 (messages.py 는 이 작업에서 수정 금지 → 보고서에 키 제안)
_DEFAULT_MSGS = {
    "reader_window_title": "리더 창",
}


# ════════════════════════════════════════════════════════════════════
# Win32 도우미 — 포커스를 뺏지 않는 창을 만들기 위한 최소한의 호출
# ════════════════════════════════════════════════════════════════════
# 전역 ctypes.windll.user32 의 argtypes 를 바꾸면 whisperer.py 의 기존 호출에 영향을 줄 수 있어서
# 이 모듈 전용 WinDLL 객체를 따로 만든다(함수 객체가 따로라 서로 간섭하지 않는다).

_IS_WINDOWS = sys.platform == "win32"

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_NOOWNERZORDER = 0x0200
HWND_TOPMOST = -1
MONITOR_DEFAULTTONEAREST = 2
DWMWA_EXTENDED_FRAME_BOUNDS = 9
SPI_GETWORKAREA = 0x0030
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02

if _IS_WINDOWS:
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        _dwmapi = ctypes.WinDLL("dwmapi")
    except OSError:  # DWM 이 없는 아주 옛 윈도우 — 테두리 보정만 빠진다
        _dwmapi = None

    _LONG_PTR = ctypes.c_ssize_t

    _user32.GetParent.argtypes = [wintypes.HWND]
    _user32.GetParent.restype = wintypes.HWND
    # 64비트 파이썬에는 GetWindowLongPtrW 가 있고, 32비트에는 매크로라 GetWindowLongW 만 있다
    _GetWindowLongPtr = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
    _SetWindowLongPtr = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
    _GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
    _GetWindowLongPtr.restype = _LONG_PTR
    _SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, _LONG_PTR]
    _SetWindowLongPtr.restype = _LONG_PTR
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetClientRect.restype = wintypes.BOOL
    _user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    _user32.ClientToScreen.restype = wintypes.BOOL
    _user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    _user32.MonitorFromPoint.restype = wintypes.HMONITOR

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    _user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    _user32.GetMonitorInfoW.restype = wintypes.BOOL
    try:
        # 스크롤바 다크 테마용(윈도우 10 1809+ 의 "DarkMode_Explorer" 테마). 없으면 스크롤바만 밝게 남는다
        _uxtheme = ctypes.WinDLL("uxtheme")
        _uxtheme.SetWindowTheme.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
        _uxtheme.SetWindowTheme.restype = ctypes.c_long
    except (OSError, AttributeError):
        _uxtheme = None
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
    _user32.SystemParametersInfoW.restype = wintypes.BOOL
    if _dwmapi is not None:
        _dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        _dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


def _wrapper_hwnd(toplevel):
    """Tk Toplevel 의 "바깥 틀(wrapper)" 창 핸들.

    Tk 는 윈도우에서 창을 두 겹으로 만든다: 바깥 틀(제목 표시줄이 있는 진짜 최상위 창) + 안쪽 자식 창.
    winfo_id() 는 안쪽 자식이라 GetParent 로 바깥 틀을 얻는다(whisperer.py setup_floating_controller 와 같은 방식).
    ⚠ Tk 가 틀을 다시 만들면(UpdateWrapper — wm resizable/overrideredirect/transient, -toolwindow 변경 등)
      핸들이 바뀐다. 그래서 저장해 두지 않고 쓸 때마다 새로 구한다.
    """
    if not _IS_WINDOWS:
        return None
    try:
        hwnd = _user32.GetParent(toplevel.winfo_id())
        return hwnd or None
    except Exception:
        return None


def _get_rect(fn, hwnd):
    r = wintypes.RECT()
    if not fn(hwnd, ctypes.byref(r)):
        return None
    return (r.left, r.top, r.right, r.bottom)


def _frame_metrics(hwnd):
    """창 틀의 여백을 잰다. 돌려주는 값: (inv, nc)

    inv = (왼, 위, 오른, 아래): GetWindowRect(창 사각형)와 "눈에 보이는 틀" 사이의 투명 여백.
          윈도우 10/11 은 크기 조절용 투명 테두리가 있어서 창 사각형이 눈에 보이는 것보다 크다.
          (실측, 시스템 DPI 134: 왼 9·위 0·오른 9·아래 9)
    nc  = (왼, 위, 오른, 아래): 눈에 보이는 틀과 글이 그려지는 안쪽(client) 사이. 위쪽이 제목 표시줄 높이.
          (실측: 왼 1·위 42·오른 1·아래 1)
    숨긴 창에서도 값이 나온다(실측: DwmGetWindowAttribute 가 숨긴 창에서도 S_OK). DWM 호출이 실패하면
    투명 여백을 0 으로 본다(그러면 보이는 틀이 몇 px 안쪽으로 들어갈 뿐 동작은 같다).
    """
    win = _get_rect(_user32.GetWindowRect, hwnd)
    client = _get_rect(_user32.GetClientRect, hwnd)
    if win is None or client is None:
        return None
    pt = wintypes.POINT(0, 0)
    _user32.ClientToScreen(hwnd, ctypes.byref(pt))
    cl, ct, cr, cb = pt.x, pt.y, pt.x + client[2], pt.y + client[3]
    vis = win
    if _dwmapi is not None:
        r = wintypes.RECT()
        if _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) == 0:
            cand = (r.left, r.top, r.right, r.bottom)
            # 보이는 틀은 창 사각형 안에 있어야 정상. 이상한 값이면 버린다
            if win[0] <= cand[0] <= cand[2] <= win[2] and win[1] <= cand[1] <= cand[3] <= win[3]:
                vis = cand
    inv = (vis[0] - win[0], vis[1] - win[1], win[2] - vis[2], win[3] - vis[3])
    nc = (cl - vis[0], ct - vis[1], vis[2] - cr, vis[3] - cb)
    return inv, nc


def _primary_work_area():
    """주 모니터의 작업 영역(작업표시줄 제외). show() 에 work_area 가 안 왔을 때만 쓰는 대비책."""
    if not _IS_WINDOWS:
        return None
    r = wintypes.RECT()
    if _user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
        return (r.left, r.top, r.right, r.bottom)
    return None


def _work_area_at(x, y):
    """(x, y) 화면 좌표가 있는 모니터의 작업 영역(작업표시줄 제외) (왼, 위, 오른, 아래).

    그 점이 어느 모니터 위에도 없으면(모니터를 뺐거나 해상도가 바뀜) 가장 가까운 모니터를 쓴다.
    저장해 둔 리더 창 위치가 "어느 모니터의 어느 자리"였는지 알아내는 데 쓴다(_place_saved).
    """
    if not _IS_WINDOWS:
        return None
    try:
        hmon = _user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST)
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if hmon and _user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcWork
            return (r.left, r.top, r.right, r.bottom)
    except Exception:
        pass
    return None


def _dark_scrollbar(scrollbar):
    """tk.Scrollbar(윈도우 기본 스크롤바 컨트롤)에 윈도우 다크 테마를 입힌다. 안 되면 조용히 밝게 둔다.

    Tk 의 윈도우 스크롤바는 네이티브 SCROLLBAR 컨트롤이라 bg·troughcolor 옵션이 먹지 않는다.
    대신 탐색기가 다크 모드에서 쓰는 테마("DarkMode_Explorer")를 SetWindowTheme 로 입히면 어둡게 그려진다.
    """
    if not _IS_WINDOWS or _uxtheme is None:
        return
    try:
        _uxtheme.SetWindowTheme(scrollbar.winfo_id(), "DarkMode_Explorer", None)
    except Exception as exc:
        log.debug("리더 창 스크롤바 다크 테마 실패(밝게 둠): %s", exc)


def _mouse_button_down():
    """마우스 왼쪽/오른쪽 버튼 중 하나라도 눌려 있으면 True.

    GetAsyncKeyState 는 "물리" 버튼을 본다. 왼손잡이 설정(버튼 바꿈)이면 주 버튼이 물리 오른쪽이라
    둘 다 본다. 끌기가 끝났는지(=손을 뗐는지) 판단하는 데만 쓴다.
    """
    if not _IS_WINDOWS:
        return False
    return bool((_user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000) or (_user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000))


def _first_present_family(widget, families, size=12):
    """families 중 이 PC 에 실제로 있는 첫 글꼴 이름. 없으면 None.

    판정 방법은 ReaderWindow._pick_font 와 같다: "없는 글꼴 이름"으로 만들면 Tk 가 대신 쓰는 글꼴과
    비교해서 다르면 있는 것으로 본다(글꼴 목록에 한글 이름만 있는 경우가 있어 목록 검사는 믿을 수 없다).
    """
    try:
        missing = tkfont.Font(widget, family="__readaloud_no_such_font__", size=size).actual("family")
    except Exception:
        missing = None
    for family in families:
        try:
            actual = tkfont.Font(widget, family=family, size=size).actual("family")
        except Exception:
            continue
        if actual and actual != missing:
            return family
    return None


def _no_autostyle(cls):
    """ttkbootstrap 이 tk 위젯 생성자를 바꿔치기했으면 {"autostyle": False} 를 돌려준다.

    whisperer.py 는 ttkbootstrap(cosmo 테마)을 쓴다. ttkbootstrap 은 import 되는 순간 tk.Text·tk.Toplevel 등의
    __init__ 를 감싸서(ttkbootstrap/style.py override_tk_widget_constructor) 테마 색을 덮어쓰고, 테마가
    바뀔 때마다 다시 덮어쓴다. 리더 창은 흰 배경·검정 글자로 고정해야 하므로 끈다.
    ttkbootstrap 이 없는 환경에서 autostyle 을 넘기면 "unknown option" 오류라, 감싸졌을 때만 넘긴다.
    """
    init = getattr(cls, "__init__", None)
    if getattr(init, "__name__", "") == "__init__wrapper":
        return {"autostyle": False}
    return {}


_GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")


def _parse_geometry(geometry):
    """Tk geometry 문자열 "폭x높이+X+Y" → (폭, 높이, X, Y). 모양이 다르면 None.

    Tk 는 왼쪽 모니터(음수 좌표)를 "600x250+-2000+100" 처럼 "+-" 로 적는다(실측). 그 모양도 받는다.
    "-X"(오른쪽 끝에서 잰 거리) 모양은 Tk 가 이 창에 대해 돌려주는 일이 없으므로 받지 않는다(→ 기본 위치).
    """
    if not isinstance(geometry, str):
        return None
    m = _GEOMETRY_RE.match(geometry.strip())
    if not m:
        return None
    w, h, x, y = (int(v) for v in m.groups())
    if w <= 0 or h <= 0:
        return None
    return w, h, x, y


# ════════════════════════════════════════════════════════════════════
# 파이썬 글자 위치 → Tk Text 인덱스
# ════════════════════════════════════════════════════════════════════

_CR_BEFORE_LF = re.compile(r"\r(?=\n)")
_ASTRAL_RE = re.compile("[\U00010000-\U0010FFFF]")
_LONE_SURROGATE_RE = re.compile("[\ud800-\udfff]")
# 줄바꿈이 아닌 공백 글자(스페이스·탭·전각 공백 등) — 형광펜의 "접히는 자리 공백" 찾기용(_trim_wrap_spaces)
_INLINE_SPACE_RE = re.compile(r"[^\S\n]")


class TkTextOffsets:
    """원문의 파이썬 오프셋(코드 포인트 단위)을 Tk Text 의 "줄.칸" 인덱스로 바꾼다.

    왜 필요한가
      readaloud_text.split_for_reading() 의 src_start/src_end 는 파이썬 문자열 인덱스다(이모지 = 1글자).
      그런데 이 PC 의 Tcl/Tk 8.6.15 는 BMP 밖 글자(이모지 등)를 내부에서 서로게이트 두 개로 들고 있어서
      Text 의 "줄.칸" 인덱스에서 2칸을 차지한다. 실측(scratchpad phase2_reader/exp_index.py):
        "가😀나" → '가😀' 뒤가 "1.3"(파이썬이면 2), `count -chars` 도 이모지를 2로 셈, `string length "😀"` = 2.
      그래서 파이썬 오프셋을 그대로 칸 번호로 쓰면 이모지 뒤부터 칠이 한 칸씩 밀린다.

    어떻게 바꾸나
      1) 표시용 글(display)을 만든다: 원문에서 줄바꿈 CRLF 의 CR 만 뺀다(윈도우 클립보드는 CRLF).
         Tk Text 는 CR 을 글자로 그대로 들고 있어(실측) 줄 끝에 쓸데없는 글자가 생기기 때문이다.
         뺀 CR 위치를 기억해 두었다가 오프셋에서 그만큼 뺀다. 짝 없는 서로게이트는 U+FFFD 로 바꾼다(길이 같음).
      2) 표시용 글에서 줄 시작 위치(\\n 다음)와 BMP 밖 글자 위치를 기억한다.
      3) 오프셋 → (줄 번호, 그 줄 안 코드 포인트 칸) → 칸에 "그 줄에서 앞에 나온 BMP 밖 글자 수 × (단위-1)" 을 더한다.
         단위는 Tcl 에 `string length "😀"` 를 물어 정한다(8.6 = 2, Tk 9 = 1 이면 보정 없음).
      ※ "1.0 + N chars" 모양은 이 PC 의 Tk 8.6.15 에서 서로게이트 쌍을 한 글자로 건너뛰어(실측) 보정 없이도
        맞지만, 그 동작은 Tk 버전마다 다를 수 있어 쓰지 않는다. ReaderWindow 는 칠하기 전에 Tk 가 돌려준 글과
        원문 조각이 같은지 확인하고, 다르면 그 모양을 대안으로 한 번 더 시도한다.
    """

    def __init__(self, source_text, astral_units=2):
        src = source_text or ""
        self.source_len = len(src)
        # 뺀 CR 들의 "원문" 위치(오름차순)
        self._removed_cr = [m.start() for m in _CR_BEFORE_LF.finditer(src)]
        display = _CR_BEFORE_LF.sub("", src)
        # 짝 없는 서로게이트(깨진 클립보드 등)는 Tcl 로 넘길 때 문제가 될 수 있어 U+FFFD 로(길이 1 → 1, 위치 불변)
        display = _LONE_SURROGATE_RE.sub("�", display)
        self.display = display
        # 각 줄이 표시용 글에서 시작하는 위치. Tk 는 \n 에서만 줄을 나눈다(\r·U+2028 은 줄바꿈 아님 — 실측)
        self._line_starts = [0] + [m.end() for m in re.finditer("\n", display)]
        self._extra = max(int(astral_units) - 1, 0)
        self._astral = [m.start() for m in _ASTRAL_RE.finditer(display)] if self._extra else []

    def display_offset(self, offset):
        """원문 오프셋 → 표시용 글 오프셋(뺀 CR 만큼 앞으로). 범위 밖이면 양 끝으로 자른다."""
        off = min(max(int(offset), 0), self.source_len)
        # off 보다 앞에 있는(off 미만) 뺀 CR 개수만큼 당긴다. off 가 CR 자리 자체면 그 CR 은 안 센다 → \n 자리가 된다
        return off - bisect.bisect_left(self._removed_cr, off)

    def index(self, offset):
        """원문 오프셋 → Tk 인덱스 문자열 "줄.칸" (줄은 1부터, 칸은 0부터)."""
        return self.index_display(self.display_offset(offset))

    def index_display(self, d):
        """표시용 글 오프셋 → Tk 인덱스 문자열 "줄.칸"."""
        d = min(max(int(d), 0), len(self.display))
        line = bisect.bisect_right(self._line_starts, d) - 1
        start = self._line_starts[line]
        col = d - start
        if self._astral:
            # 이 줄 시작 ~ d 사이에 있는 BMP 밖 글자 수만큼 칸을 더 민다
            col += self._extra * (bisect.bisect_left(self._astral, d) - bisect.bisect_left(self._astral, start))
        return "%d.%d" % (line + 1, col)

    def display_slice(self, start, end):
        """원문 구간 [start, end) 에 해당하는 표시용 글(칠한 곳이 맞는지 대조할 때 쓴다)."""
        return self.display[self.display_offset(start):self.display_offset(end)]


def _astral_units(widget):
    """이 Tcl 이 BMP 밖 글자 하나를 몇 칸으로 세는지(8.6 = 2). 물어보다 실패하면 2(이 PC 실측값)."""
    try:
        return int(widget.tk.call("string", "length", "\U0001F600"))
    except Exception:
        return 2


# ════════════════════════════════════════════════════════════════════
# 리더 창
# ════════════════════════════════════════════════════════════════════

class ReaderWindow:
    """원문을 보여 주고 지금 읽는 조각을 칠하는 창. (모듈 설명의 "모듈 사이 약속" 참고)

    상태
      self._segments : start() 로 받은 조각 목록
      self._offsets  : TkTextOffsets (원문 오프셋 → Tk 인덱스)
      self._current  : 지금 칠한 Tk 구간 (시작, 끝) 또는 None — 창이 다시 보일 때 그 자리로 스크롤하려고 기억
      self._known_geometry : 마지막으로 "알고 있는" 창 geometry. 사용자가 바꾼 것만 저장 콜백으로 알리려고
                             우리가 직접 옮긴 뒤에도 갱신한다
      self.user_closed : 이번 읽기 중 사용자가 X 로 닫았으면 True (start() 때 False 로). 부르는 쪽이
                         "같은 읽기 동안 다시 띄우지 않기"에 쓸 수 있다. 이 클래스는 이 값으로 동작을 막지 않는다.
    """

    def __init__(self, root, get_msg, on_geometry_changed=None):
        self._root = root
        self._get_msg = get_msg
        self._on_geometry_changed = on_geometry_changed
        self._owner_thread = threading.current_thread()
        self._segments = []
        self._offsets = TkTextOffsets("")
        self._current = None
        self._pieces = None            # 지금 칠한 조각을 "원문 줄" 단위로 나눈 Tk 구간들 — 스크롤·폭 변경 뒤 다시 칠하려고 기억
        self._hl_disp = None           # 지금 칠한 조각의 (표시용 글 시작, 끝, 오프셋→Tk 인덱스 함수) — 접히는 공백 찾기용
        self._repaint_pending = False  # 다시 칠하기를 idle 에 한 번만 예약했는지(스크롤·크기 변경 때 연달아 오므로 묶는다)
        self._last_yview = None        # 마지막으로 받은 보이는 범위(yscrollcommand) — 같은 값이면 다시 칠하지 않는다
        self._known_geometry = None
        self._placing = False          # show() 가 창을 옮기는 중이면 True → 그 사이 Configure 는 사용자 조작이 아님
        self._release_poll_id = None   # 마우스 버튼 뗌 확인 after() 번호
        self._warned_mismatch = False  # 칠 위치 불일치 경고는 한 번만 로그
        self._destroyed = False
        self.user_closed = False

        # ⚠ 루트 창의 틀을 먼저 만들게 한다.
        #   Tk 는 "앱에서 처음 만들어지는 틀"에 SetActiveWindow 를 한다(tkWinWm.c 8.6.15 UpdateWrapper 끝,
        #   tsdPtr->firstWindow). 리더 창이 첫 번째가 되면 뜨지도 않았는데 활성 창이 되어 FocusIn 이 생긴다
        #   (실측 exp_focus.py: 루트 먼저 → 활성·FocusIn 없음 / 리더 창 먼저 → 활성 + FocusIn).
        #   앱에서는 보통 이미 루트·플로팅 창의 틀이 있어 아무 일도 안 일어나지만, 순서에 기대지 않으려고 넣었다.
        try:
            root.update_idletasks()
        except Exception:
            pass

        self.win = tk.Toplevel(root, **_no_autostyle(tk.Toplevel))
        # ⚠ 아래 세 줄은 "처음 화면에 붙기(첫 idle) 전"에 해야 한다.
        #   - withdraw: 만들자마자 번쩍 뜨지 않게. 첫 매핑 때 틀이 SW_HIDE 상태로 만들어진다(TkWmMapWindow).
        #   - -toolwindow: 작은 제목 표시줄 + 작업표시줄·Alt+Tab 에서 빠짐. 매핑 뒤에 바꾸면 Tk 가 틀을 새로
        #     만들어(UpdateWrapper) 우리가 넣은 WS_EX_NOACTIVATE 가 사라진다. 매핑 전이면 새로 만들지 않는다
        #     (tkWinWm.c WmAttributesCmd: updatewrapper 는 WM_NEVER_MAPPED 가 아닐 때만).
        #     또 Tk 가 틀 크기를 AdjustWindowRectEx 로 계산할 때 이 스타일을 알아야 안쪽 크기가 요청과 정확히 맞는다(실측).
        #   - -topmost: 항상 위. Tk 는 이걸 SetWindowPos(..., SWP_NOACTIVATE) 로 적용한다(틀 재생성 없음).
        self.win.withdraw()
        # 윈도우 제목 표시줄·테두리를 없앤다(overrideredirect). 끌기·닫기·크기 조절은 아래 머리 막대와 손잡이가 한다.
        # 매핑 전에 켜야 Tk 가 틀을 새로 만들지 않는다(매핑 뒤에 바꾸면 틀이 새로 생겨 NOACTIVATE 가 지워짐 —
        # 그래도 show() 가 _apply_window_styles() 로 다시 넣는다). 하단 바(bottom_bar.py)도 같은 방식이다.
        self.win.overrideredirect(True)
        try:
            self.win.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        # ⚠ 이 창에서 절대 쓰지 말 것: attributes("-alpha"/"-transparentcolor") — Tk 가 자기가 아는 확장 스타일로
        #   GWL_EXSTYLE 을 통째로 덮어써 WS_EX_NOACTIVATE 가 지워진다(tkWinWm.c WmAttributesCmd -alpha 분기).
        #   resizable()/overrideredirect()/transient() 도 틀을 새로 만든다. 꼭 써야 하면 뒤에 _apply_window_styles() 를 부를 것.
        self.win.title(self._msg("reader_window_title"))   # 제목 표시줄은 없지만 작업 관리자 등에 쓰이는 이름
        # 창 바탕을 머리 막대 색으로 두고 글 상자를 1px 안쪽에 놓아 "1px 테두리"로 보이게 한다.
        # (제목 표시줄이 없는 창은 윈도우 그림자·테두리도 없어서, 어두운 VS Code 위에서 경계가 사라지지 않게)
        self.win.configure(background=HEADER_BG)
        # Alt+F4 등 WM_CLOSE 가 와도 숨기기만. 읽기는 계속된다.
        self.win.protocol("WM_DELETE_WINDOW", self._on_close_button)

        # 화면 배율(96 DPI = 1.0). 앱은 DPI 를 인식하는 프로세스라(ttkbootstrap hdpi) Tk 좌표가 실제 픽셀이다 →
        # px 로 적은 크기(머리 막대·손잡이·최소 크기)에 배율을 곱해야 150% 화면에서도 같은 크기로 보인다.
        try:
            self._scale = max(float(self.win.winfo_fpixels("1i")) / 96.0, 1.0)
        except Exception:
            self._scale = 1.0
        self._min_w = int(round(MIN_WIDTH_PX * self._scale))
        self._min_h = int(round(MIN_HEIGHT_PX * self._scale))
        self._drag = None              # 끄는 중이면 ("move"|"size", 누른 곳 x, y, 그때 창 폭, 높이, x, y)
        self._build_header()

        # 글 상자 + 스크롤바를 담는 본문. 좌우·아래 1px 을 비워 창 바탕(머리 막대 색)이 테두리로 보이게 한다
        self.body = tk.Frame(self.win, background=TEXT_BG, borderwidth=0, highlightthickness=0,
                             **_no_autostyle(tk.Frame))
        self.body.pack(side="top", fill="both", expand=True, padx=1, pady=(0, 1))

        self.scrollbar = tk.Scrollbar(self.body, orient="vertical", **_no_autostyle(tk.Scrollbar))
        self.text = tk.Text(
            self.body,
            wrap="word",                 # 단어 단위 줄바꿈(오케스트레이터 지정)
            # 보이는 범위가 바뀔 때마다(스크롤·크기 변경) 스크롤바를 맞추고, 새로 보이는 곳의 형광펜을 다듬는다(_on_yscroll)
            yscrollcommand=self._on_yscroll,
            **_no_autostyle(tk.Text),
        )
        # ttkbootstrap 이 생성자 안에서 색을 덮어쓰는 경우까지 막으려고 만든 "뒤에" 설정한다
        self.text.configure(
            background=TEXT_BG,
            foreground=TEXT_FG,
            font=self._pick_font(),
            padx=TEXT_PADX,
            pady=TEXT_PADY,
            borderwidth=0,
            relief="flat",
            highlightthickness=0,
            insertwidth=0,               # 읽기 전용이라 깜빡이는 커서 없음
        )
        self.scrollbar.configure(command=self.text.yview)
        # 스크롤바 아래를 손잡이 크기만큼 비운다 → 오른쪽 아래 크기 손잡이가 스크롤바 아래 화살표를 가리지 않는다
        grip = int(round(GRIP_PX * self._scale))
        self.scrollbar.pack(side="right", fill="y", pady=(0, grip))
        self.text.pack(side="left", fill="both", expand=True)
        _dark_scrollbar(self.scrollbar)
        # 칠한 곳을 선택했을 때 등 — 선택 색은 윈도우 기본(파랑·흰 글자)이라 어두운 바탕에서도 잘 보여 그대로 둔다

        # 오른쪽 아래 크기 손잡이: 끌면 창 크기가 바뀐다. 윈도우 손잡이처럼 대각선 점 세 줄을 그린다
        self.grip = tk.Canvas(self.win, width=grip, height=grip, background=TEXT_BG, highlightthickness=0,
                              borderwidth=0, cursor="size_nw_se", **_no_autostyle(tk.Canvas))
        dot = max(int(round(2 * self._scale)), 1)
        for k in range(3):             # 오른쪽 아래 모서리에서 대각선으로 1·2·3 개씩
            for j in range(k + 1):
                cx = grip - dot * 2 * (j + 1)
                cy = grip - dot * 2 * (k - j + 1)
                self.grip.create_rectangle(cx, cy, cx + dot, cy + dot, fill=HEADER_FG_DIM, outline="")
        self.grip.place(relx=1.0, rely=1.0, x=-1, y=-1, anchor="se")
        for ev, fn in (("<ButtonPress-1>", lambda e: self._drag_start("size", e)),
                       ("<B1-Motion>", self._drag_motion), ("<ButtonRelease-1>", self._drag_end)):
            self.grip.bind(ev, fn)

        # 형광펜 태그. 새 태그는 기존 태그(sel 포함)보다 우선순위가 높아 선택 영역 색을 가린다 → sel 을 위로 올린다
        self.text.tag_configure(_HL_TAG, background=HIGHLIGHT_BG)
        self.text.tag_raise("sel")
        # 읽기 전용: 사용자가 글을 고칠 수 없게. 코드에서 넣을 때만 잠깐 normal 로 푼다(start()).
        # disabled 여도 마우스로 선택·휠 스크롤은 된다.
        self.text.configure(state="disabled")

        self._astral_units = _astral_units(self.text)
        self.win.bind("<Configure>", self._on_configure, add="+")
        # 글 상자 폭이 바뀌면 자동 줄바꿈 위치가 바뀐다 → 형광펜을 화면 줄 기준으로 다시 칠한다(_paint 참고)
        self.text.bind("<Configure>", self._on_text_configure, add="+")

        # 틀(wrapper)을 지금 만들어 둔다(숨긴 채). 그래야 첫 show() 전에 테두리 여백을 잴 수 있다.
        try:
            self.win.update_idletasks()
        except Exception:
            pass
        self._apply_window_styles()

    # ── 공개 메서드 ───────────────────────────────────────────────────

    def start(self, source_text, segments):
        """새 읽기 시작: 원문을 그대로 넣고(전처리 전 — 사용자가 선택한 모양 그대로) 조각 목록을 기억한다.

        창을 보이지는 않는다(보일지는 부르는 쪽이 설정 reader_window_enabled 를 보고 show() 로 정한다).
        segments 의 src_start/src_end 는 source_text 기준 파이썬 오프셋, 반열린 구간 [시작, 끝). None 가능.
        """
        self._check_thread("start")
        if self._destroyed:
            return
        self._segments = list(segments or [])
        self._offsets = TkTextOffsets(source_text or "", self._astral_units)
        self._current = None
        self._pieces = None
        self._hl_disp = None
        self._warned_mismatch = False
        self.user_closed = False
        t = self.text
        t.configure(state="normal")
        try:
            t.delete("1.0", "end")
            t.insert("1.0", self._offsets.display)
        finally:
            t.configure(state="disabled")
        t.yview_moveto(0.0)

    def highlight(self, idx):
        """idx 번 조각의 원문 구간을 칠하고 보이게 스크롤한다.

        - 앞의 칠은 항상 먼저 지운다(한 번에 한 조각만 칠함 — 확장 단락 형광펜과 같음).
        - idx 가 None 이면 지우기만 한다.
        - 구간이 None 인 조각(정렬 실패·공백뿐·"." 하나뿐 등)은 칠하지 않는다(확장도 형광펜만 포기, 읽기는 계속).
        - 칠하기 전에 Tk 에서 꺼낸 글과 원문 조각이 같은지 대조한다. 다르면 칠하지 않는다(엉뚱한 곳 칠하기 방지).
        """
        self._check_thread("highlight")
        if self._destroyed:
            return
        self.text.tag_remove(_HL_TAG, "1.0", "end")
        self._current = None
        self._pieces = None
        self._hl_disp = None
        if idx is None:
            return
        try:
            seg = self._segments[idx] if idx >= 0 else None
        except (IndexError, TypeError):
            seg = None
        if not seg:
            return
        s, e = seg.get("src_start"), seg.get("src_end")
        if s is None or e is None or e <= s:
            return
        spans = self._tk_spans(s, e)
        if spans is None:
            return
        whole, pieces, disp = spans
        self._pieces = pieces
        self._hl_disp = disp
        self._current = whole
        # 순서: ① 원문 줄 단위로 칠하고 ② 보이게 스크롤한 뒤 ③ 이제 화면에 보이는 "접히는 자리 공백"만 칠을 뗀다
        self._paint(trim=False)
        self._reveal(whole[0], whole[1])
        self._trim_wrap_spaces()

    def end(self):
        """읽기 끝(끝까지 읽음·정지): 칠을 지우고 창을 숨긴다. 글은 남겨 둔다(다음 start() 가 바꾼다)."""
        self._check_thread("end")
        if self._destroyed:
            return
        self.text.tag_remove(_HL_TAG, "1.0", "end")
        self._current = None
        self._pieces = None
        self._hl_disp = None
        self.hide()

    def show(self, work_area, bar_height, geometry=None):
        """창을 포커스를 뺏지 않고 띄운다.

        work_area  : (왼, 위, 오른, 아래) 모니터 작업 영역(작업표시줄 제외) 화면 좌표.
        bar_height : 하단 바 높이(px). 기본 위치에서 리더 창을 그 바로 위에 놓는 데 쓴다.
        geometry   : 저장해 둔 "폭x높이+X+Y"(on_geometry_changed 로 받았던 값). 있으면 그 위치가 있던 모니터 안에서의
                     자리를 지금 work_area(활성 모니터) 의 같은 자리로 옮겨 띄운다(_place_saved — 2026-09-28 사용자 요청
                     "현재 활성화된 모니터에 떠야 한다"). 저장값 자체는 바꾸지 않는다(원래 모니터로 돌아가면 원래 자리).
        기본 위치  : 하단 바 바로 위 오른쪽, 작업 영역 폭 40%·높이 35%(눈에 보이는 틀 기준).

        ⚠ 보이기는 Tk deiconify() 대신 Win32 ShowWindow(SW_SHOWNOACTIVATE) 로 한다.
          Tk deiconify 는 제목 표시줄이 있는 창에 대해 TkSetFocusWin(winPtr, 1)(강제 포커스)을 부른다
          (tkWinWm.c 8.6.15 TkpWinToplevelDeiconify). Win32 로 보이고 숨겨도 Tk 는 WM_WINDOWPOSCHANGED 에서
          상태를 따라온다(ConfigureTopLevel — 실측: wm state 가 normal/withdrawn 으로 맞게 바뀜).
        """
        self._check_thread("show")
        if self._destroyed:
            return
        self._placing = True
        try:
            area = self._valid_area(work_area) or _primary_work_area()
            try:
                bar_h = max(int(bar_height or 0), 0)
            except (TypeError, ValueError):
                bar_h = 0
            geom = None
            parsed = _parse_geometry(geometry) if geometry else None
            if parsed:
                geom = self._place_saved(parsed, area) if area else "%dx%d+%d+%d" % parsed
            use_default = geom is None
            if use_default:
                geom = self._default_geometry(area, bar_h) if area else None
            if geom:
                # 숨긴 채로 옮긴다(숨긴 창도 Tk 가 틀을 옮긴다 — 실측). 그래야 보이는 순간 제자리에 뜬다
                self.win.geometry(geom)
                self.win.update_idletasks()
            self._apply_window_styles()   # 혹시 틀이 새로 만들어졌으면 NOACTIVATE 다시
            hwnd = _wrapper_hwnd(self.win)
            if hwnd:
                _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
                _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
            else:
                # Win32 가 안 되는 환경(윈도우 아님 등) — 이때만 Tk 로 보인다(포커스를 가져갈 수 있음)
                self.win.deiconify()
            self.win.update_idletasks()
            if use_default and area and hwnd:
                # 숨긴 채 잰 여백이 보인 뒤와 다르면(드묾) 한 번 더 맞춘다
                again = self._default_geometry(area, bar_h)
                if again and again != geom:
                    self.win.geometry(again)
                    self.win.update_idletasks()
            # 숨긴 동안 wm geometry 값은 옛 크기를 돌려준다(실측) → 보인 "뒤"에 기억해야 정확하다
            self._known_geometry = self._current_geometry()
        finally:
            self._placing = False
        if self._current:
            self._reveal(self._current[0], self._current[1])
        if self._pieces:
            # 숨은 동안에는 화면 배치가 없어 "접히는 자리 공백"을 못 찾았다 → 보이고 스크롤한 지금 다시 칠한다
            self._paint()

    def hide(self):
        """창을 숨긴다(읽기·칠 상태는 그대로). Win32 로 숨기고, 안 되면 Tk withdraw."""
        self._check_thread("hide")
        if self._destroyed:
            return
        self._cancel_release_poll()
        hwnd = _wrapper_hwnd(self.win)
        if hwnd:
            _user32.ShowWindow(hwnd, SW_HIDE)
        else:
            self.win.withdraw()

    def destroy(self):
        """창을 없앤다(앱 종료 때). 두 번 불러도 괜찮다."""
        if self._destroyed:
            return
        self._destroyed = True
        self._cancel_release_poll()
        try:
            self.win.destroy()
        except Exception:
            pass

    def is_visible(self):
        """지금 화면에 보이는지(부르는 쪽 편의용)."""
        if self._destroyed:
            return False
        hwnd = _wrapper_hwnd(self.win)
        if hwnd:
            return bool(_user32.IsWindowVisible(hwnd))
        try:
            return bool(self.win.winfo_viewable())
        except Exception:
            return False

    # ── 내부: 창 스타일·위치 ──────────────────────────────────────────

    def _apply_window_styles(self):
        """바깥 틀에 WS_EX_NOACTIVATE(+TOOLWINDOW, APPWINDOW 끔)를 넣는다. 이미 있으면 아무것도 안 한다.

        - WS_EX_NOACTIVATE: 클릭해도 활성 창이 되지 않는다 → 사용자가 보던 앱의 포커스가 그대로다.
          (whisperer.py setup_floating_controller 의 플로팅 아이콘과 같은 처리. 07-27 로그 §4-4)
        - Tk 가 틀을 새로 만들면 이 비트가 사라지므로 show() 마다 다시 확인한다.
        - 플로팅 아이콘은 소유자 분리(GWLP_HWNDPARENT=0)도 하지만, 이 창은 transient 가 아니라서 Tk 가 처음부터
          소유자 없이 만든다(실측 GetWindow(GW_OWNER)=0) → 하지 않는다.
        """
        hwnd = _wrapper_hwnd(self.win)
        if not hwnd:
            return
        try:
            ex = _GetWindowLongPtr(hwnd, GWL_EXSTYLE)
            # WS_EX_TOPMOST 비트는 SetWindowLong 으로 바꾸지 않는다(윈도우 문서: 항상 위는 SetWindowPos 로).
            # 그래서 ex 에 있던 TOPMOST 비트는 그대로 두고, 항상 위는 아래 SetWindowPos(HWND_TOPMOST) 로 확정한다.
            want = (ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            if want != ex:
                _SetWindowLongPtr(hwnd, GWL_EXSTYLE, want)
                # FRAMECHANGED: 바뀐 스타일을 틀에 반영. NOACTIVATE: 이 호출이 창을 활성화하지 않게
                _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOOWNERZORDER)
        except Exception as exc:
            log.warning("리더 창 Win32 스타일 적용 실패(포커스를 가져갈 수 있음): %s", exc)

    @staticmethod
    def _valid_area(work_area):
        try:
            l, t, r, b = (int(v) for v in work_area)
        except Exception:
            return None
        if r <= l or b <= t:
            return None
        return (l, t, r, b)

    def _metrics(self):
        hwnd = _wrapper_hwnd(self.win)
        if hwnd:
            try:
                m = _frame_metrics(hwnd)
                if m:
                    return m
            except Exception:
                pass
        return (0, 0, 0, 0), (0, 0, 0, 0)

    def _default_geometry(self, area, bar_h):
        """기본 자리 계산: "눈에 보이는 틀"이 [작업영역 오른쪽 끝, 하단 바 윗변]에 붙고 폭 40%·높이 35%.

        Tk geometry 의 폭x높이는 "안쪽(client)" 크기이고 +X+Y 는 "창 사각형(투명 테두리 포함)" 왼쪽 위라서
        (실측: geometry 500x200+300+300 → GetWindowRect 왼쪽 위 (300,300), client 500x200),
        잰 여백(_frame_metrics)으로 바꿔 계산한다.
        """
        l, t, r, b = area
        vis_w = int(round((r - l) * DEFAULT_WIDTH_RATIO))
        vis_h = int(round((b - t) * DEFAULT_HEIGHT_RATIO))
        vis_right = r
        vis_bottom = b - bar_h
        vis_left = vis_right - vis_w
        vis_top = vis_bottom - vis_h
        inv, nc = self._metrics()
        client_w = max(vis_w - nc[0] - nc[2], 1)
        client_h = max(vis_h - nc[1] - nc[3], 1)
        x = vis_left - inv[0]
        y = vis_top - inv[1]
        return "%dx%d+%d+%d" % (client_w, client_h, x, y)

    def _place_saved(self, parsed, area):
        """저장 위치(다른 모니터였을 수 있음)를 지금 모니터(area)의 "같은 자리"로 옮긴 geometry 문자열.

        같은 자리란: 저장 위치가 있던 모니터에서 창이 오른쪽 절반에 있었으면 "오른쪽 끝과의 거리"를,
        왼쪽 절반이었으면 "왼쪽 끝과의 거리"를 지킨다(세로도 위/아래로 같게). 그래서
          - 오른쪽 아래(기본 위치)에 두고 쓰던 창은 어느 모니터에서든 오른쪽 아래에 뜨고,
          - 해상도가 다른 모니터로 가도 가장자리에 붙은 모양이 유지된다.
        같은 모니터면 결과가 저장 위치 그대로다(작업 영역을 벗어난 만큼만 안으로 밀어 넣는다).
        저장 위치가 어느 모니터에도 없으면(모니터를 뺐음) 가장 가까운 모니터를 기준으로 본다(_work_area_at).
        크기는 지금 작업 영역보다 크면 줄이고, 최소 크기(_min_w·_min_h)보다 작게는 줄이지 않는다.
        """
        w0, h0, x0, y0 = parsed
        al, at, ar, ab = area
        sl, st, sr, sb = _work_area_at(x0 + w0 // 2, y0 + h0 // 2) or area
        aw, ah = ar - al, ab - at
        w = max(min(w0, aw), min(self._min_w, aw))
        h = max(min(h0, ah), min(self._min_h, ah))
        if x0 + w0 / 2.0 >= (sl + sr) / 2.0:
            x = ar - (sr - (x0 + w0)) - w      # 오른쪽 끝과의 거리 유지
        else:
            x = al + (x0 - sl)                 # 왼쪽 끝과의 거리 유지
        if y0 + h0 / 2.0 >= (st + sb) / 2.0:
            y = ab - (sb - (y0 + h0)) - h      # 아래 끝과의 거리 유지(하단 바 위에 두었으면 계속 그 위)
        else:
            y = at + (y0 - st)                 # 위 끝과의 거리 유지
        x = min(max(x, al), ar - w)
        y = min(max(y, at), ab - h)
        return "%dx%d+%d+%d" % (w, h, x, y)

    # ── 내부: 머리 막대(끌기·닫기)와 크기 손잡이 ──────────────────────

    def _build_header(self):
        """머리 막대: 왼쪽 제목, 오른쪽 큰 닫기 버튼. 막대(제목 글자 포함) 아무 곳이나 잡고 끌면 창이 옮겨진다.

        왜 직접 그리나(2026-09-28 사용자 보고 "VS Code 에서 리더 창 끄기가 너무 힘들다 / 드래그로 옮기게"):
          포커스를 뺏지 않는 작은 도구 창(WS_EX_NOACTIVATE + toolwindow)의 윈도우 제목 표시줄은 얇고,
          잡기·닫기가 어색했다. 창 안에 직접 그리면 끌기·닫기를 Tk 이벤트로 확실히 처리한다(하단 바와 같은 방식).
        크기: 높이·닫기 칸 = 확장 바 버튼 36px(js/page-ui.js .btn) × 화면 배율 — 잡기 쉽고 누르기 쉽게.
        클릭해도 포커스를 뺏지 않는다: 창에 WS_EX_NOACTIVATE 가 있으면 윈도우가 마우스 클릭으로 창을 활성화하지 않는다.
        Tk 는 버튼을 누른 채 움직이면 마우스를 붙잡아(capture) 창 밖으로 나가도 B1-Motion 을 계속 준다 → 끌기가 끊기지 않는다.
        """
        hh = int(round(HEADER_HEIGHT_PX * self._scale))
        text_family = self._pick_font()[0]
        self.header = tk.Frame(self.win, height=hh, background=HEADER_BG, borderwidth=0, highlightthickness=0,
                               cursor="fleur", **_no_autostyle(tk.Frame))
        self.header.pack(side="top", fill="x")
        self.header.pack_propagate(False)      # 안의 글자 크기와 상관없이 높이를 hh 로 고정

        # 닫기 버튼 칸(hh × hh 정사각형). 누른 채 버튼 밖으로 나가서 떼면 닫지 않는다(보통 버튼과 같게 — _on_close_click)
        self.close_btn = tk.Frame(self.header, width=hh, height=hh, background=HEADER_BG, borderwidth=0,
                                  highlightthickness=0, cursor="hand2", **_no_autostyle(tk.Frame))
        self.close_btn.pack(side="right")
        self.close_btn.pack_propagate(False)
        icon_family = _first_present_family(self.win, CLOSE_ICON_FAMILIES)
        if icon_family:
            glyph, font = CLOSE_GLYPH, (icon_family, -int(round(CLOSE_GLYPH_PX * self._scale)))
        else:                                   # 아이콘 글꼴이 없는 윈도우 — 일반 글꼴의 ✕
            glyph, font = CLOSE_FALLBACK, (text_family, -int(round(14 * self._scale)))
        self.close_icon = tk.Label(self.close_btn, text=glyph, font=font, background=HEADER_BG, foreground=HEADER_FG,
                                   borderwidth=0, highlightthickness=0, cursor="hand2", **_no_autostyle(tk.Label))
        self.close_icon.pack(fill="both", expand=True)
        for w in (self.close_btn, self.close_icon):
            w.bind("<Enter>", lambda e: self._set_close_hover(True))
            w.bind("<Leave>", lambda e: self._set_close_hover(False))
            w.bind("<ButtonRelease-1>", self._on_close_click)

        # 제목 글자 — 확장 바 글꼴 크기 14px(js/page-ui.js:859), 색은 흰색 70%(확장 총 시간 글자색).
        # 왼쪽 여백 12px = 확장 바 좌우 여백(js/page-ui.js .bar padding)
        self.title_label = tk.Label(self.header, text=self._msg("reader_window_title"),
                                    font=(text_family, -int(round(14 * self._scale))),
                                    background=HEADER_BG, foreground=HEADER_FG_DIM, anchor="w", borderwidth=0,
                                    highlightthickness=0, cursor="fleur", **_no_autostyle(tk.Label))
        self.title_label.pack(side="left", fill="y", padx=(int(round(12 * self._scale)), 0))
        for w in (self.header, self.title_label):
            w.bind("<ButtonPress-1>", lambda e: self._drag_start("move", e))
            w.bind("<B1-Motion>", self._drag_motion)
            w.bind("<ButtonRelease-1>", self._drag_end)

    def _set_close_hover(self, on):
        """닫기 버튼에 마우스가 올라오면 배경을 밝게(확장 버튼 hover 흰색 14%)."""
        bg = HEADER_HOVER_BG if on else HEADER_BG
        for w in (self.close_btn, self.close_icon):
            try:
                w.configure(background=bg)
            except tk.TclError:
                pass

    def _on_close_click(self, event):
        """닫기 버튼에서 손을 뗐을 때: 손가락이 아직 버튼 위면 닫는다(= 이번 읽기 동안 숨김, 읽기는 계속)."""
        w = event.widget
        try:
            inside = 0 <= event.x < w.winfo_width() and 0 <= event.y < w.winfo_height()
        except tk.TclError:
            inside = False
        if inside:
            self._set_close_hover(False)
            self._on_close_button()

    def _drag_start(self, kind, event):
        """머리 막대("move") 또는 크기 손잡이("size")를 눌렀다 — 누른 곳과 그때 창 위치·크기를 기억한다."""
        g = _parse_geometry(self._current_geometry())
        if not g:
            self._drag = None
            return
        w, h, x, y = g
        self._drag = (kind, event.x_root, event.y_root, w, h, x, y)

    def _drag_motion(self, event):
        """누른 채 움직이는 동안: 움직인 만큼 창을 옮기거나(move) 크기를 바꾼다(size).

        화면 좌표(x_root/y_root)로 계산해서, 창이 따라 움직여도 손가락과 창 사이 거리가 그대로다.
        Tk 는 왼쪽 모니터(음수 좌표)를 "+-2000+100" 모양으로 받는다(실측) → "+%d+%d" 그대로 넣어도 된다.
        위치 저장은 여기서 하지 않는다: geometry 가 바뀌면 <Configure> → _poll_release 가 손을 뗀 뒤 한 번만 알린다.
        """
        if not self._drag:
            return
        kind, x0, y0, w, h, x, y = self._drag
        dx, dy = event.x_root - x0, event.y_root - y0
        try:
            if kind == "move":
                self.win.geometry("+%d+%d" % (x + dx, y + dy))
            else:
                self.win.geometry("%dx%d" % (max(w + dx, self._min_w), max(h + dy, self._min_h)))
        except tk.TclError:
            pass

    def _drag_end(self, event):
        """손을 뗐다 — 끌기 끝. (위치 저장은 _poll_release 가 실제 버튼 상태를 보고 한다)"""
        self._drag = None

    def _current_geometry(self):
        try:
            return self.win.wm_geometry()
        except Exception:
            return None

    # ── 내부: 사용자가 옮기거나 크기를 바꿨을 때 ───────────────────────

    def _on_configure(self, event):
        """창 크기·위치가 바뀔 때마다 온다(끄는 동안 연달아). 여기서는 "뗐는지 확인"만 예약한다.

        - Toplevel 에 건 바인딩은 자식 위젯(Text·스크롤바)의 Configure 도 받는다 → 창 자신 것만 본다.
        - show() 가 직접 옮기는 중(_placing)이면 사용자 조작이 아니다.
        """
        if event.widget is not self.win or self._placing or self._destroyed:
            return
        if self._on_geometry_changed is None:
            return
        if self._release_poll_id is None:
            self._release_poll_id = self.win.after(RELEASE_POLL_MS, self._poll_release)

    def _poll_release(self):
        """마우스 버튼이 떨어졌으면 geometry 가 바뀌었는지 보고 한 번만 알린다. 아직 누르고 있으면 다시 예약.

        "손을 뗀 뒤 한 번만"을 시간 추측(마지막 이벤트 뒤 N초) 대신 실제 버튼 상태로 판정한다.
        우리가 직접 옮긴 것(show)은 _known_geometry 와 같아서 알리지 않는다.
        최대화 상태(제목 표시줄 더블클릭)에서는 저장하지 않는다(다음에 복원하면 거대한 창이 되므로).
        """
        self._release_poll_id = None
        if self._destroyed:
            return
        if _mouse_button_down():
            self._release_poll_id = self.win.after(RELEASE_POLL_MS, self._poll_release)
            return
        try:
            if self.win.wm_state() != "normal":
                return
        except Exception:
            return
        geom = self._current_geometry()
        if not geom or geom == self._known_geometry:
            return
        self._known_geometry = geom
        try:
            self._on_geometry_changed(geom)
        except Exception as exc:  # 설정 저장이 실패해도 창 동작은 계속
            log.warning("리더 창 위치 저장 콜백 오류: %s", exc)

    def _cancel_release_poll(self):
        if self._release_poll_id is not None:
            try:
                self.win.after_cancel(self._release_poll_id)
            except Exception:
                pass
            self._release_poll_id = None

    def _on_close_button(self):
        """머리 막대의 닫기 버튼(또는 Alt+F4): 숨기기만 한다. 읽기(재생)는 건드리지 않는다.

        user_closed 를 세워 두면 부르는 쪽(whisperer.py)이 같은 읽기 동안 다시 띄우지 않는다.
        아예 안 보이게 하려면 트레이 메뉴 "리더 창" 체크를 끈다(설정에 저장됨).
        """
        self.user_closed = True
        self.hide()

    # ── 내부: 칠하기·스크롤 ───────────────────────────────────────────

    def _tk_spans(self, start, end):
        """원문 구간 → ((전체 시작, 전체 끝), [(줄 조각 시작, 끝), ...], (표시용 시작, 끝, 변환 함수)). 맞지 않으면 None.

        세 번째 값은 _trim_wrap_spaces 가 조각 안의 공백 위치를 Tk 인덱스로 바꿀 때 쓴다(대조를 통과한 변환 함수 그대로).

        대조: Tk 가 [전체 시작, 전체 끝) 에서 돌려준 글이 원문 조각(표시용 글)과 같을 때만 칠한다.
          1순위: TkTextOffsets 의 "줄.칸"(BMP 밖 글자 보정).
          2순위: "1.0 + N chars"(N = 표시용 글 코드 포인트 오프셋). 이 PC 의 Tk 8.6.15 는 +N chars 에서
                 서로게이트 쌍을 한 글자로 건너뛴다(실측) — 1순위가 어떤 이유로 틀릴 때의 대비책.
          둘 다 틀리면 칠하지 않는다(엉뚱한 곳을 칠하느니 안 칠한다 — 확장도 맞추지 못하면 형광펜만 포기).
        줄 조각: 조각이 여러 줄에 걸치면(짧은 줄 합치기 — 확장 speech.js:444) 줄바꿈 글자는 빼고 줄마다 칠한다.
          Tk 는 줄바꿈 글자에 배경을 칠하면 그 줄 오른쪽 끝까지 칠해 버린다(캡처로 확인). 확장(CSS Highlight)은
          글자 부분만 칠하므로 그 모양에 맞췄다. 창 폭 때문에 자동으로 접힌 "화면 줄"은 _paint 가 한 번 더 나눈다.
        """
        off = self._offsets
        ds, de = off.display_offset(start), off.display_offset(end)
        expected = off.display[ds:de]
        if not expected:
            return None
        candidates = (
            off.index_display,
            lambda d: self.text.index("1.0 + %d chars" % d),
        )
        for to_index in candidates:
            try:
                a, b = to_index(ds), to_index(de)
                if self.text.get(a, b) != expected:
                    continue
            except tk.TclError:
                continue
            pieces = []
            pos = ds
            while pos < de:
                nl = off.display.find("\n", pos, de)
                stop = de if nl == -1 else nl
                if stop > pos:
                    pieces.append((to_index(pos), to_index(stop)))
                if nl == -1:
                    break
                pos = nl + 1
            return (a, b), pieces, (ds, de, to_index)
        if not self._warned_mismatch:
            self._warned_mismatch = True
            log.warning("리더 창: 칠할 위치가 원문과 안 맞아 칠하지 않음 (src %s~%s)", start, end)
        return None

    def _paint(self, trim=True):
        """self._pieces(원문 줄 단위 Tk 구간)를 형광펜으로 칠한다. trim 이면 이어서 접히는 자리 공백을 다듬는다.

        태그만 바꾸는 일이라 싸다(글 배치를 다시 계산하지 않는다 — 배경색만 바꾸는 태그는 줄 높이에 영향이 없다).
        스크롤·창 크기 변경 때마다 _repaint_idle 이 이것을 다시 부른다.
        """
        t = self.text
        t.tag_remove(_HL_TAG, "1.0", "end")
        for a, b in (self._pieces or []):
            t.tag_add(_HL_TAG, a, b)
        if trim:
            self._trim_wrap_spaces()

    def _trim_wrap_spaces(self):
        """지금 화면에 보이는 부분에서, 자동 줄바꿈으로 "접히는 자리의 공백"에서만 형광펜을 뗀다.

        왜 (2026-09-28 통합 데모 캡처 ui_00_start.png 로 확인)
          Tk 는 단어 단위 줄바꿈(wrap="word")에서 줄이 접히는 자리의 공백 한 칸을 그 화면 줄 오른쪽 끝까지
          "늘려서" 그린다. 거기 배경을 칠하면 형광펜이 글자가 끝난 뒤 창 오른쪽 끝까지 뻗는다.
          확장(CSS Highlight, js/events.js:374)은 글자 부분만 칠하므로 그 공백만 뺀다. 칠할 조각 자체는 그대로다.
        어떻게 (싸게)
          Tk 의 "display lineend"·"+1 display lines"·`count -ypixels` 는 긴 원문 줄(줄바꿈 없는 긴 문단)에서
          줄 첫머리부터 다시 배치해서 아주 느리다(실측: 5,000자 한 줄에서 count 3.5초, display lineend 수십 ms).
          그래서 **화면에 보이는 줄만** 보는 bbox(화면 줄 정보 재사용, 사실상 0ms)로 판정한다:
            공백 글자 다음 글자가 더 아래 화면 줄에 있으면 = 그 공백이 화면 줄의 마지막 글자 = 접히는 자리.
            (원문 줄 끝의 공백은 다음 글자가 같은 화면 줄의 줄바꿈 글자라 걸리지 않는다)
          화면 밖 공백은 bbox 가 None 이라 건너뛴다 → 스크롤로 보이게 되면 _on_yscroll 이 다시 부른다.
        """
        rng = self._hl_disp
        if not rng or not self._pieces:
            return
        t = self.text
        try:
            if not t.winfo_viewable():
                return
            inset = int(t.cget("borderwidth")) + int(t.cget("highlightthickness"))
            right_limit = t.winfo_width() - inset - int(t.cget("padx"))
        except Exception:
            return
        ds, de, to_index = rng
        for m in _INLINE_SPACE_RE.finditer(self._offsets.display, ds, de):
            i = m.start()
            try:
                idx = to_index(i)
                bi = t.bbox(idx)
                if not bi:
                    continue                      # 화면 밖
                nxt = to_index(i + 1)
                bn = t.bbox(nxt)
                if bn is None:
                    # 다음 글자가 화면 밖(맨 아래 줄 끝) → 공백이 오른쪽 끝까지 늘어났는지로 본다
                    if bi[0] + bi[2] < right_limit - 2:
                        continue
                elif bn[1] <= bi[1]:
                    continue                      # 다음 글자가 같은 화면 줄 → 보통 공백
                t.tag_remove(_HL_TAG, idx, nxt)
            except tk.TclError:
                continue

    def _on_yscroll(self, first, last):
        """Text 의 yscrollcommand. 스크롤바를 맞추고, 보이는 범위가 바뀌었으면 형광펜 다듬기를 idle 에 예약한다.

        스크롤(휠·스크롤바·_reveal)과 창 크기 변경 모두 여기로 온다. 태그만 바꾸는 다듬기는 보이는 범위를 바꾸지
        않으므로 되먹임(무한 반복)이 생기지 않는다. 그래도 같은 범위면 예약하지 않는다.
        """
        try:
            self.scrollbar.set(first, last)
        except tk.TclError:
            pass
        view = (first, last)
        if view != self._last_yview:
            self._last_yview = view
            self._schedule_repaint()

    def _on_text_configure(self, event):
        """글 상자 크기가 바뀌었다(창 크기 조절·처음 뜸) → 접히는 자리가 바뀌므로 idle 때 한 번 다시 칠한다."""
        self._schedule_repaint()

    def _schedule_repaint(self):
        """다시 칠하기를 idle 에 하나만 예약한다(끄는 동안·휠 굴리는 동안 연달아 오므로 묶기)."""
        if self._destroyed or not self._pieces or self._repaint_pending:
            return
        self._repaint_pending = True
        try:
            self.win.after_idle(self._repaint_idle)
        except Exception:
            self._repaint_pending = False

    def _repaint_idle(self):
        self._repaint_pending = False
        if not self._destroyed and self._pieces:
            try:
                self._paint()
            except Exception as exc:   # 칠하기 실패가 창을 죽이지 않게
                log.debug("리더 창 다시 칠하기 실패: %s", exc)

    def _reveal(self, a, b):
        """칠한 구간이 다 보이게 스크롤한다 — 확장 규칙 그대로(js/page-ui.js revealRanges, HEAD afae39a :429-480).

          - 이미 전부 보이면 움직이지 않는다.
          - 안 보이면: 화면에 들어가는 길이면 "가운데", 화면보다 길면 "첫 줄을 맨 위"로.
          - 부드러운 스크롤 없이 바로 이동(Tk 는 원래 바로 이동).
        창이 숨겨져 있으면 배치 정보가 없어 계산하지 않는다(show() 가 보인 뒤 다시 부른다).

        ⚠ 성능 함정 (2026-09-28 실측, 줄바꿈 없는 5,000자 문단 두 개짜리 글)
          Tk Text 는 "긴 원문 줄" 안의 위치를 계산할 때 그 줄 첫머리부터 다시 배치한다. 그래서
            `count -ypixels`(조각 높이) 3.5초, `X display linestart` 67ms, `see` 약 300ms, 위로 스크롤 약 100~150ms,
          반면 아래로 스크롤 약 7ms, 화면에 있는 줄의 dlineinfo/bbox 는 사실상 0ms 였다.
          옛 방식(count 로 조각 높이 계산)은 칠할 때마다 최대 4.5초 동안 Tk 메인 스레드를 멈췄다
          (그동안 하단 바·트레이·gui_queue 가 전부 멈춘다). 그래서 아래처럼 싼 호출만 쓴다:
            1) dlineinfo(시작)·dlineinfo(끝 글자)가 화면 안이면 끝.
            2) 시작 글자가 화면에 온전히 없으면 see(시작) — 긴 줄에서 비싼 호출은 이것 하나.
            3) 끝이 아직 안 보이면 "넘치지 않을 만큼만" 아래로 스크롤하며(싸다) 끝이 보일 때까지 반복:
               끝이 화면 아래(yb ≥ 화면 아래)에 있으면 가운데 맞춤에 필요한 이동 D = (ya+yb)/2 − 화면 가운데
               ≥ (ya − 화면 위)/2 이므로 (ya − 화면 위)/2 만큼씩 내리면 절대 지나치지 않는다(위로 되돌릴 일 없음).
            4) 끝이 보이면 가운데로(보통 아래로 조금). 시작이 화면 맨 위까지 올라왔는데도 끝이 안 보이면
               조각이 화면보다 긴 것 → 첫 줄을 맨 위에 둔 채 끝.
        계산이 실패하면 Tk see() 로 대신한다.
        """
        t = self.text
        try:
            if not t.winfo_viewable():
                return
        except Exception:
            return
        try:
            # 글이 보이는 세로 범위(위젯 안 좌표): 테두리·강조선·위아래 여백(pady) 을 뺀 곳
            inset = int(t.cget("borderwidth")) + int(t.cget("highlightthickness"))
            view_top = inset + int(t.cget("pady"))
            view_bottom = t.winfo_height() - inset - int(t.cget("pady"))
            visible = view_bottom - view_top
            if visible <= 0:
                return
            view_center = (view_top + view_bottom) / 2.0
            last = t.index("%s -1 chars" % b)

            def span():
                """(시작 줄 윗변, 시작 줄 아랫변, 끝 글자 줄 아랫변). 화면에 없는 줄은 None. 화면 줄 정보만 써서 싸다."""
                ia, ib = t.dlineinfo(a), t.dlineinfo(last)
                return ((ia[1] if ia else None), (ia[1] + ia[3] if ia else None),
                        (ib[1] + ib[3] if ib else None))

            def scroll(d):
                d = int(round(d))
                if d:
                    t.tk.call(str(t), "yview", "scroll", d, "pixels")

            ya, ya_bottom, yb = span()
            # 1) 이미 전부 보이나
            if ya is not None and yb is not None and ya >= view_top and yb <= view_bottom:
                return
            # 2) 시작 글자를 화면에 들인다(이미 온전히 보이면 건너뜀)
            if ya is None or ya < view_top or ya_bottom > view_bottom:
                t.see(a)
                ya, ya_bottom, yb = span()
                if ya is None:
                    return
            # 3)·4) 아래로만 조금씩 내리며 끝을 찾고, 찾으면 가운데 맞춤
            for _ in range(40):                    # 매번 남은 거리가 절반 이하로 줄어 보통 10번 안에 끝난다
                if yb is not None and yb <= view_bottom:
                    if yb - ya <= visible:
                        scroll((ya + yb) / 2.0 - view_center)
                    else:
                        scroll(ya - view_top)
                    return
                step = int((ya - view_top) / 2)
                if step <= 0:
                    scroll(ya - view_top)          # 조각이 화면보다 길다 → 첫 줄을 맨 위로
                    return
                scroll(step)
                ya, ya_bottom, yb = span()
                if ya is None:
                    return
        except Exception:
            try:
                t.see(b)
                t.see(a)
            except Exception:
                pass

    # ── 내부: 기타 ────────────────────────────────────────────────────

    def _pick_font(self):
        """FONT_FAMILIES 중 실제로 있는 첫 글꼴. 하나도 없으면 Tk 기본 글꼴.

        ⚠ tkfont.families() 에 이름이 있는지로 판정하면 안 된다: 한국어 윈도우는 목록에 "맑은 고딕"(한글 이름)만
          있고 "Malgun Gothic" 은 없다(실측). 그런데 "Malgun Gothic" 으로 만들면 Tk 가 "맑은 고딕"으로 잘 찾는다.
          그래서 "없는 글꼴 이름"이 대신 바뀌는 글꼴과 비교해, 다르면 있는 것으로 본다.
          (처음에 목록으로 판정했다가 Segoe UI 로 떨어져 한글이 다른 글꼴(굵어 보임)로 대체되는 것을 캡처로 확인함)
        """
        try:
            missing = tkfont.Font(self._root, family="__readaloud_no_such_font__", size=FONT_SIZE_PT).actual("family")
        except Exception:
            missing = None
        for family in FONT_FAMILIES:
            try:
                actual = tkfont.Font(self._root, family=family, size=FONT_SIZE_PT).actual("family")
            except Exception:
                continue
            if actual and actual != missing:
                return (family, FONT_SIZE_PT)
        return ("TkDefaultFont", FONT_SIZE_PT)

    def _msg(self, key):
        """messages.py 문구. 키가 없으면(get_message 는 "[Missing message: 키]" 를 돌려준다) 기본 한국어."""
        default = _DEFAULT_MSGS.get(key, key)
        try:
            text = self._get_msg(key) if self._get_msg else None
        except Exception:
            text = None
        if not text or (isinstance(text, str) and text.startswith("[Missing message")):
            return default
        return text

    def _check_thread(self, name):
        """Tk 메인 스레드가 아닌 곳에서 부르면 경고 로그만 남긴다(동작은 그대로 — 재생을 죽이지 않으려고).

        tkinter 는 스레드 안전하지 않다. 재생 스레드에서는 gui_queue → check_gui_queue 로 넘겨서 불러야 한다.
        """
        if threading.current_thread() is not self._owner_thread:
            log.warning("ReaderWindow.%s 가 Tk 메인 스레드가 아닌 곳에서 불림 — gui_queue 로 넘겨야 한다", name)


# ════════════════════════════════════════════════════════════════════
# 데모 — python reader_window.py [--shots 폴더] [--seconds 8] [--interval 0.8]
#   한글·영어·목록·이모지 섞인 원문을 조각으로 나눠 0.8초마다 차례로 칠하고, 8초 뒤 끝낸다.
#   --shots 를 주면 칠할 때마다 창을 캡처해 reader_NN.png 로 저장하고, 칠한 글과 원문 조각이 같은지 출력한다.
#   (whisperer.py 는 import 하지 않는다. 소리를 내지 않는다.)
# ════════════════════════════════════════════════════════════════════

_DEMO_TEXT = "\r\n".join([
    "블루밍 리더 창 데모입니다 😀 이모지 뒤에서도 형광펜이 맞아야 합니다.",
    "The quick brown fox 🦊 jumps over the lazy dog, and README.md is read aloud.",
    "- 첫째 목록: 사과 🍎 와 배",
    "- 둘째 목록: VS Code 에서 page-ui-host.js 파일을 열어요",
    "짧은 줄",
    "👨‍👩‍👧 가족 이모지(여러 글자가 이어진 것) 뒤 문장도 정확히 칠해져야 합니다.",
    "",
    "마지막 문단은 조금 길게 씁니다. 창 폭을 넘어서 여러 줄로 접히고, 창 높이보다 아래로 내려가면 "
    "자동으로 스크롤되어 칠한 조각이 가운데로 와야 합니다 🎉 Mixed English and 한국어 sentence here.",
    "끝.",
])


def _demo(argv):
    import argparse
    import os
    import time

    p = argparse.ArgumentParser(description="ReaderWindow 데모")
    p.add_argument("--shots", default=None, help="캡처 저장 폴더(없으면 캡처 안 함)")
    p.add_argument("--seconds", type=float, default=8.0)
    p.add_argument("--interval", type=float, default=0.8)
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import readaloud_text as rt

    # 앱과 같은 환경: ttkbootstrap 창(SetProcessDPIAware 를 켠다)을 숨긴 루트로
    try:
        import ttkbootstrap as ttkb
        root = ttkb.Window(themename="cosmo")
    except Exception:
        if _IS_WINDOWS:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        root = tk.Tk()
    root.withdraw()
    # 앱 시작과 같은 상태로 만든다: 루트 틀을 먼저 만든다. Tk 는 앱의 "첫 틀"에 SetActiveWindow 를 해서
    # 이 순간 (숨긴) 루트가 전경을 가져갈 수 있다 — 앱이 시작될 때 원래 일어나는 일이고 리더 창과는 무관.
    # 데모가 사용자의 포커스를 빼앗은 채 끝나지 않게, 가져갔으면 원래 창에 돌려준다(지금 우리가 전경이라 가능).
    orig_fg = ctypes.windll.user32.GetForegroundWindow() if _IS_WINDOWS else None
    root.update_idletasks()
    root.update()
    if _IS_WINDOWS and orig_fg and ctypes.windll.user32.GetForegroundWindow() != orig_fg:
        ctypes.windll.user32.SetForegroundWindow(orig_fg)
        root.update()

    words = None
    words_path = os.path.join(here, "data", "english-words.js")
    if os.path.exists(words_path):
        words = rt.load_english_words(words_path)
    segments = rt.split_for_reading(_DEMO_TEXT, "ko-KR", "ko-KR", words)

    # 데모용: 주 모니터 작업 영역, 하단 바 높이는 확장 BAR_HEIGHT 48px(js/page-ui.js:846)을 DPI 로 늘린 값
    area = _primary_work_area() or (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem() if _IS_WINDOWS else 96
    except Exception:
        dpi = 96
    bar_h = int(round(48 * dpi / 96.0))

    saved = []
    rw = ReaderWindow(root, get_msg=lambda key, *a: "[Missing message: %s]" % key,
                      on_geometry_changed=saved.append)
    fg_before = ctypes.windll.user32.GetForegroundWindow() if _IS_WINDOWS else None
    rw.start(_DEMO_TEXT, segments)
    rw.show(area, bar_h)
    print("work_area", area, "bar_h", bar_h, "geometry", rw.win.wm_geometry(), "segments", len(segments))

    shots = args.shots
    if shots:
        os.makedirs(shots, exist_ok=True)
    results = []
    order = list(range(len(segments)))

    def step(i=0):
        if i >= len(order):
            return
        idx = order[i]
        rw.highlight(idx)
        seg = segments[idx]
        if seg["src_start"] is None:
            got, want = None, None
        else:
            # 칠한 곳을 Tk 에서 다시 꺼내, TkTextOffsets 를 거치지 않은 원문 조각(CRLF→LF)과 비교한다.
            # 줄바꿈 글자와 "자동으로 접히는 자리의 공백"은 칠하지 않으므로(_paint) 공백을 뺀 글끼리 비교하고,
            # 칠한 조각 안에 줄바꿈이 섞이지 않았는지도 본다.
            r = rw.text.tag_ranges(_HL_TAG)
            got = [rw.text.get(r[k], r[k + 1]) for k in range(0, len(r), 2)]
            whole = _DEMO_TEXT[seg["src_start"]:seg["src_end"]].replace("\r\n", "\n")
            want = [part for part in whole.split("\n") if part]
        squash = lambda s: re.sub(r"\s+", "", s or "")   # noqa: E731
        ok = (got is None and want is None) or (
            squash("".join(got)) == squash("".join(want)) and not any("\n" in g for g in got))
        results.append((idx, ok, want))
        print("seg %02d  src=%s~%s  match=%s  pieces=%d  %r" % (idx, seg["src_start"], seg["src_end"], ok,
                                                             len(got or []), want))
        if shots:
            root.update()
            _capture(rw, os.path.join(shots, "reader_%02d.png" % idx))
        rw.win.after(int(args.interval * 1000), step, i + 1)

    focus_events = []
    rw.win.bind("<FocusIn>", lambda e: focus_events.append(str(e.widget)), add="+")

    def finish():
        fg_after = ctypes.windll.user32.GetForegroundWindow() if _IS_WINDOWS else None
        ours = _wrapper_hwnd(rw.win)
        print("foreground unchanged:", fg_before == fg_after, "| foreground is reader window:", bool(ours) and fg_after == ours,
              "| FocusIn events on reader:", focus_events, "| saved geometry callbacks:", saved)
        rw.end()
        print("all match:", all(ok for _, ok, _ in results))
        rw.destroy()
        root.destroy()

    root.after(300, step)
    root.after(int(args.seconds * 1000), finish)
    root.mainloop()


def _capture(rw, path):
    """데모 캡처: 리더 창의 눈에 보이는 틀 영역만 잘라 저장한다(PIL.ImageGrab)."""
    try:
        from PIL import ImageGrab
        hwnd = _wrapper_hwnd(rw.win)
        inv, _nc = _frame_metrics(hwnd)
        l, t, r, b = _get_rect(_user32.GetWindowRect, hwnd)
        box = (l + inv[0], t + inv[1], r - inv[2], b - inv[3])
        ImageGrab.grab(bbox=box, all_screens=True).save(path)
    except Exception as exc:
        print("capture failed:", exc)


if __name__ == "__main__":
    _demo(sys.argv[1:])
