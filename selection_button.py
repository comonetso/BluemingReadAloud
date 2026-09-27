# -*- coding: utf-8 -*-
"""selection_button.py — 글을 선택하면 선택 끝 옆에 뜨는 "빨간 점". 누르면 선택한 글을 읽는다.

■ 무엇을 하나
  크롬 확장 read-aloud-hrg 의 선택 버튼(js/selection-button.js, HEAD afae39a)을 데스크톱으로 옮긴 것이다.
  확장: 글을 선택하면 선택 끝 옆에 빨간 점(지름 12px, 클릭 영역 22px)이 뜨고, 누르면 선택한 글을 읽는다.
  이 점이 생겨서 예전의 "플로팅 아이콘"은 필요 없어졌다(2026-09-28 사용자 결정).

■ 모듈 사이 약속 (다른 모듈이 이 이름·모양에 기대므로 바꾸지 말 것)
    det = SelectionGestureDetector(**system_gesture_settings())   # 순수 로직(Tk·Win32 없음). 시계(초)는 인자로
    det.on_press(x, y, t)    -> None | ("hide",)          # 왼쪽 버튼 누름
    det.on_release(x, y, t)  -> None | ("show", x, y)      # 왼쪽 버튼 뗌
    det.on_other_input()     -> ("hide",)                  # 휠·키 입력·다른 버튼

    btn = SelectionButton(root, on_click, get_msg)        # Tk 창. Tk 메인 스레드에서만
    btn.show_at(x, y)     # (x, y) = 마우스를 뗀 화면 좌표
    btn.hide(); btn.is_visible(); btn.destroy()
    btn.contains(x, y)    # ⚠ 예외: 마우스 훅 스레드에서 불러도 된다(Tk 를 부르지 않는다)
    btn.hwnd              # 점 창 바깥 틀 핸들(int 또는 None). ⚠ 이것도 어느 스레드에서 읽어도 된다

■ 왜 "마우스 드래그·더블클릭"으로 판단하나 (2026-09-28 사용자 확정)
  확장은 브라우저가 "선택이 바뀌었다(selectionchange)"를 알려 주지만, 윈도우는 다른 앱의 선택 상태를
  알려 주지 않는다. UI Automation 으로 물어보는 방법은 VS Code 를 얼린 전례가 있어 쓰지 않는다.
  그래서 "선택했을 법한 마우스 동작"(끌기, 더블·트리플클릭)을 보고 점을 띄운다 — 추정이다.
  창 끌기·스크롤바 끌기에도 점이 뜰 수 있다(사용자가 알고 받아들임. 누르지 않으면 다음 클릭에 사라진다).

■ 반드시 지킬 것 (함정)
  1. 점 창은 눌러도 포커스를 뺏으면 안 된다(WS_EX_NOACTIVATE). 뺏으면 뒤이은 Ctrl+C 가 사용자가 글을 고른
     앱이 아니라 이 창으로 가서 "선택 없음"이 된다(2026-07-27 로그 §4-4, 옛 플로팅 아이콘과 같은 이유).
     눌렀을 때 원래 앱이 그 클릭을 받지 않는 것도 중요하다 — 받으면 앱이 선택을 풀어 버린다
     (확장이 mousedown 을 preventDefault 하는 이유와 같다: selection-button.js:182-188).
  2. attributes("-alpha"/"-transparentcolor") 를 쓰지 마라. Tk 가 GWL_EXSTYLE 을 통째로 덮어써
     NOACTIVATE 가 지워진다(reader_window.py 주석, tkWinWm.c WmAttributesCmd). 투명한 바탕은 Tk 대신
     Win32 UpdateLayeredWindow(픽셀마다 알파)로 직접 그린다(_paint).
  3. overrideredirect/-topmost 는 처음 화면에 붙기 전에 건다. 매핑 뒤에 바꾸면 Tk 가 틀을 새로 만들어
     우리가 넣은 스타일이 사라진다(reader_window.py 같은 주석). 그래도 show_at 마다 다시 확인한다.
  4. 보이기는 Tk deiconify 대신 Win32 ShowWindow(SW_SHOWNOACTIVATE). Tk deiconify 는 포커스를 강제로
     가져간다(tkWinWm.c TkpWinToplevelDeiconify → TkSetFocusWin — reader_window.py 주석).
  5. tkinter 는 스레드 안전하지 않다. contains()·hwnd 만 예외로 어느 스레드에서 불러도 되게 만들었다
     (마우스 훅이 "점을 누른 것"을 거르려고 훅 스레드에서 부른다). 나머지는 gui_queue 로 넘겨서 부른다
     (2026-07-27 로그 §4-5).
  6. ttkbootstrap 이 tk.Toplevel 생성자를 바꿔 쳐서 바탕색을 덮어쓴다 → autostyle=False (_no_autostyle).

■ 조사만 하고 넣지 않은 것: "편집 중(입력칸)에는 점을 안 띄우기"(확장 selection-button.js:94-101)
  데스크톱에서 떠올릴 수 있는 판별은 GetGUIThreadInfo 의 hwndCaret(시스템 캐럿을 가진 창)이다.
  그런데 크롬·엣지·Electron(VS Code) 같은 크로미움 앱은 윈도우 시스템 캐럿을 쓰지 않고 캐럿을 직접 그린다.
  2026-09-28 이 PC 조사: 크로미움 창(Aside·Typeless, Chrome_WidgetWin_1)은 전부 hwndCaret=없음이었다.
  즉 크로미움에서는 입력칸 여부를 가를 수 없다. 반대로 워드·메모장처럼 캐럿을 쓰는 앱은 "문서 본문에서 글을
  고를 때"도 캐럿이 있어서 점이 안 뜨게 된다(읽고 싶은 곳인데). 그래서 넣지 않았다.
"""

from __future__ import annotations

import logging
import math
import sys
import threading
import tkinter as tk

log = logging.getLogger(__name__)

__all__ = ["SelectionGestureDetector", "SelectionButton", "system_gesture_settings",
           "dot_position", "circle_mask", "render_dot_bgra"]


# ════════════════════════════════════════════════════════════════════
#  확장 원본 값 (단위: CSS 픽셀) — 근거: read-aloud-hrg js/selection-button.js (HEAD)
# ════════════════════════════════════════════════════════════════════
SIZE_PX = 22            # const SIZE = 22 — 클릭 영역 (selection-button.js:13)
DOT_PX = 12             # const DOT = 12  — 눈에 보이는 점 (selection-button.js:14)
GAP_PX = 4              # const GAP = 4   — 선택 끝에서 띄우는 간격 (selection-button.js:15)
DOT_COLOR = "#ff3b30"   # background: #ff3b30 (selection-button.js:158)
DOT_RGB = (0xFF, 0x3B, 0x30)
HOVER_SCALE = 1.25      # button:hover::before { transform: scale(1.25) } (selection-button.js:161-163)

# 확장에 없는 값 — 이 모듈에서 정했다(보고서 "임의로 정한 것")
RING_ALPHA = 1          # [임의] 점 둘레(클릭 영역 22px 중 점 밖)의 불투명도 1/255.
                        #   눈에는 안 보이지만(0 이 아니므로) 윈도우가 "창 위를 눌렀다"로 판정한다.
                        #   알파 0 이면 클릭이 아래 앱으로 새서 앱이 선택을 풀어 버린다(함정 1).
SUPERSAMPLE = 8         # [임의] 점 가장자리를 매끄럽게 그리려고 8배로 그려 줄인다(덮인 비율 = 알파)

# 윈도우 기본값 — 시스템 설정을 못 읽었을 때만 쓴다(윈도우 기본: 끌기 4px, 더블클릭 500ms·4px)
DEFAULT_DRAG_THRESHOLD = (4, 4)
DEFAULT_DOUBLE_CLICK_TIME = 0.5
DEFAULT_DOUBLE_CLICK_SIZE = (4, 4)

_DEFAULT_MSGS = {
    # 확장 _locales/ko/messages.json:173-175 "selection_button_title" 그대로
    "selection_button_title": "선택한 글 읽기",
}


# ════════════════════════════════════════════════════════════════════
#  Win32 도우미 — 이 모듈 전용 WinDLL 객체(공용 ctypes.windll 에 형 선언을 걸면
#  whisperer.py 의 같은 함수 호출 방식까지 바뀐다 — bottom_bar.py·reader_window.py 와 같은 이유)
# ════════════════════════════════════════════════════════════════════
_IS_WIN = sys.platform == "win32"

SM_CXDOUBLECLK = 36
SM_CYDOUBLECLK = 37
SM_CXDRAG = 68
SM_CYDRAG = 69

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _g32 = ctypes.WinDLL("gdi32", use_last_error=True)

    _LONG_PTR = ctypes.c_ssize_t
    # 64비트 파이썬에는 GetWindowLongPtrW 가 있고, 32비트에는 매크로라 GetWindowLongW 만 있다
    _GetWindowLongPtr = getattr(_u32, "GetWindowLongPtrW", _u32.GetWindowLongW)
    _SetWindowLongPtr = getattr(_u32, "SetWindowLongPtrW", _u32.SetWindowLongW)
    _GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
    _GetWindowLongPtr.restype = _LONG_PTR
    _SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, _LONG_PTR]
    _SetWindowLongPtr.restype = _LONG_PTR

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    class _BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                    ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    class _BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    class _BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    _u32.GetParent.argtypes = [wintypes.HWND]
    _u32.GetParent.restype = wintypes.HWND
    _u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _u32.SetWindowPos.restype = wintypes.BOOL
    _u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _u32.ShowWindow.restype = wintypes.BOOL
    _u32.IsWindowVisible.argtypes = [wintypes.HWND]
    _u32.IsWindowVisible.restype = wintypes.BOOL
    _u32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
    _u32.SetWindowRgn.restype = ctypes.c_int
    _u32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    _u32.MonitorFromPoint.restype = wintypes.HMONITOR
    _u32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    _u32.GetMonitorInfoW.restype = wintypes.BOOL
    _u32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _u32.GetSystemMetrics.restype = ctypes.c_int
    _u32.GetDoubleClickTime.argtypes = []
    _u32.GetDoubleClickTime.restype = wintypes.UINT
    _u32.GetDC.argtypes = [wintypes.HWND]
    _u32.GetDC.restype = wintypes.HDC
    _u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _u32.ReleaseDC.restype = ctypes.c_int
    _u32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                         ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                         ctypes.POINTER(wintypes.POINT), wintypes.DWORD,
                                         ctypes.POINTER(_BLENDFUNCTION), wintypes.DWORD]
    _u32.UpdateLayeredWindow.restype = wintypes.BOOL
    _g32.CreateEllipticRgn.argtypes = [ctypes.c_int] * 4
    _g32.CreateEllipticRgn.restype = wintypes.HRGN
    _g32.PtInRegion.argtypes = [wintypes.HRGN, ctypes.c_int, ctypes.c_int]
    _g32.PtInRegion.restype = wintypes.BOOL
    _g32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    _g32.DeleteObject.restype = wintypes.BOOL
    _g32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    _g32.CreateCompatibleDC.restype = wintypes.HDC
    _g32.DeleteDC.argtypes = [wintypes.HDC]
    _g32.DeleteDC.restype = wintypes.BOOL
    _g32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(_BITMAPINFO), wintypes.UINT,
                                      ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    _g32.CreateDIBSection.restype = wintypes.HBITMAP
    _g32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    _g32.SelectObject.restype = wintypes.HGDIOBJ

GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_LAYERED = 0x00080000
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
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0
BI_RGB = 0


# ════════════════════════════════════════════════════════════════════
#  시스템 설정 읽기
# ════════════════════════════════════════════════════════════════════
def system_gesture_settings():
    """윈도우 시스템 설정의 "끌기 시작 거리·더블클릭 시간·더블클릭 범위"를 읽어 돌려준다.

    돌려주는 값은 SelectionGestureDetector 의 인자 그대로다 → SelectionGestureDetector(**system_gesture_settings())
      {"drag_threshold": (cx, cy), "double_click_time": 초, "double_click_size": (cx, cy)}
    왜 시스템 값인가: 사용자가 제어판에서 더블클릭 속도를 바꿨으면 앱들(크롬·VS Code 포함)도 그 값으로
      더블클릭을 판단한다. 같은 값을 써야 "앱은 단어를 골랐는데 점은 안 뜨는" 어긋남이 줄어든다.
    함정: 이 값들은 화면 배율과 무관한 실제 픽셀이다(2026-09-28 실측: 배율 140%·DPI 인식 프로세스에서도
      SM_CXDRAG=4, SM_CXDOUBLECLK=4. GetSystemMetricsForDpi(…, 134) 도 4). 마우스 훅 좌표도 실제 픽셀이라 맞는다.
    실패하면(윈도우가 아님, 0 이 옴) 윈도우 기본값 4,4 / 0.5초 / 4,4.
    """
    if not _IS_WIN:
        return _read_gesture_settings(None, None)
    return _read_gesture_settings(_u32.GetSystemMetrics, _u32.GetDoubleClickTime)


def _read_gesture_settings(get_metric, get_double_click_ms):
    """system_gesture_settings 의 본체. 읽는 함수를 인자로 받아서 테스트에서 가짜로 바꿀 수 있게 했다.

    GetSystemMetrics 는 실패하면 0 을 돌려준다 → 0 은 "못 읽음"으로 보고 기본값.
    SM_CXDRAG 는 음수일 수 있다(문서: 음수면 왼쪽으로 빼고 오른쪽으로 더한다 = 크기는 절댓값) → abs.
    """
    def metric(index, default):
        if get_metric is None:
            return default
        try:
            v = abs(int(get_metric(index)))
        except Exception:
            return default
        return v if v > 0 else default

    ms = 0
    if get_double_click_ms is not None:
        try:
            ms = int(get_double_click_ms())
        except Exception:
            ms = 0
    return {
        "drag_threshold": (metric(SM_CXDRAG, DEFAULT_DRAG_THRESHOLD[0]),
                           metric(SM_CYDRAG, DEFAULT_DRAG_THRESHOLD[1])),
        "double_click_time": ms / 1000.0 if ms > 0 else DEFAULT_DOUBLE_CLICK_TIME,
        "double_click_size": (metric(SM_CXDOUBLECLK, DEFAULT_DOUBLE_CLICK_SIZE[0]),
                              metric(SM_CYDOUBLECLK, DEFAULT_DOUBLE_CLICK_SIZE[1])),
    }


# ════════════════════════════════════════════════════════════════════
#  감지 로직 (순수 — Tk·Win32 없이 테스트한다)
# ════════════════════════════════════════════════════════════════════
class SelectionGestureDetector:
    """마우스 누름·뗌만 보고 "방금 글을 선택했을 법한가"를 판단한다. 점을 띄울지/숨길지만 알려 준다.

    규칙 (2026-09-28 사용자 확정 + 오케스트레이터 지정)
      - 뗌에서 show: 누른 곳과 뗀 곳이 끌기 임계값 "이상" 떨어졌으면(가로 |dx| ≥ cx 또는 세로 |dy| ≥ cy) = 끌어서 선택.
      - 뗌에서 show: 더블클릭·트리플클릭(연속 클릭 수 ≥ 2)의 뗌 = 단어·문단 선택.
      - 한 번 클릭은 show 하지 않는다. 점이 떠 있으면 "누름"에서 hide(확장도 선택이 사라지면 숨긴다:
        selection-button.js:82-85 selectionchange → isCollapsed → hide).
      - 휠·키·다른 버튼 → hide (on_other_input).
    연속 클릭 판정 (윈도우 더블클릭과 같은 방식: 누름과 누름 사이를 잰다)
      - 앞 누름에서 double_click_time 초 "이내"(≤), 그리고 앞 누름 자리 기준 가로 ±cx/2·세로 ±cy/2 "이내"(≤)이면
        앞 누름의 클릭 수 + 1. 아니면 1. 범위는 윈도우 문서의 SM_CXDOUBLECLK 설명("첫 클릭 자리를 둘러싼 사각형의
        폭")을 따라 가운데 기준 절반씩으로 잡았다. 경계(=)를 포함할지는 [임의]로 포함 쪽.
      - 트리플클릭은 "두 번째 누름"과 비교한다(각 누름이 앞 누름과 이어지는지).
    함정·한계 (추정 규칙이라 생기는 것 — 사용자가 알고 받아들임)
      - 창 끌기·스크롤바 끌기에도 show 가 나온다.
      - 누름·뗌 두 점만 보므로, 멀리 끌었다가 누른 자리 근처로 돌아와 떼면 끌기로 못 본다.
      - Shift+클릭(선택 넓히기)·키보드 선택(Shift+화살표, Ctrl+A)은 show 하지 않는다(확장은 keyup 에도 띄운다:
        selection-button.js:27). 키 입력은 사용자 결정대로 hide 다.
      - 휠·키 입력은 누르고 있는 끌기를 끊지 않는다(끌면서 휠로 스크롤해 길게 고르는 경우가 있어서).
    "점이 떠 있다"는 이 객체의 짐작이다(마지막으로 show 를 알렸고 그 뒤 hide 를 안 알렸으면 떠 있다고 본다).
      점이 다른 이유로 이미 숨었으면 hide 가 한 번 더 나올 수 있는데, hide 는 여러 번 불러도 괜찮으니 문제없다.
    시계 t 는 초 단위 숫자(부르는 쪽이 time.monotonic() 등으로 넘긴다). 스레드 안전하지 않다 — 한 스레드(훅)에서만 부른다.
    """

    def __init__(self, drag_threshold=DEFAULT_DRAG_THRESHOLD, double_click_time=DEFAULT_DOUBLE_CLICK_TIME,
                 double_click_size=DEFAULT_DOUBLE_CLICK_SIZE):
        self._drag_x = abs(float(drag_threshold[0]))
        self._drag_y = abs(float(drag_threshold[1]))
        self._dbl_time = float(double_click_time)
        self._dbl_half_x = abs(float(double_click_size[0])) / 2.0
        self._dbl_half_y = abs(float(double_click_size[1])) / 2.0
        self._press = None        # 지금 눌려 있는 왼쪽 버튼: (x, y, 연속 클릭 수). 떼면 None
        self._last_press = None   # 바로 앞 누름: (x, y, t, 연속 클릭 수) — 연속 클릭 판정용
        self._shown = False       # 점이 떠 있다고 짐작하는지

    def on_press(self, x, y, t):
        """왼쪽 버튼 누름. 연속 클릭 수를 세어 두고, 점이 떠 있으면 ("hide",) 를 돌려준다.

        한 번 클릭이 선택을 풀기 때문에 누르는 순간 숨긴다. 더블클릭의 두 번째 누름에서도 숨겼다가
        그 뗌에서 새 자리에 다시 띄운다.
        """
        count = 1
        last = self._last_press
        if last is not None:
            lx, ly, lt, lcount = last
            dt = t - lt
            if (0 <= dt <= self._dbl_time
                    and abs(x - lx) <= self._dbl_half_x and abs(y - ly) <= self._dbl_half_y):
                count = lcount + 1
        self._last_press = (x, y, t, count)
        self._press = (x, y, count)
        if self._shown:
            self._shown = False
            return ("hide",)
        return None

    def on_release(self, x, y, t):
        """왼쪽 버튼 뗌. 끌어서 뗐거나(임계값 이상) 더블·트리플클릭의 뗌이면 ("show", x, y).

        누름을 못 본 뗌(훅이 버튼을 누른 채 시작된 경우 등)은 판단할 근거가 없어 None.
        """
        press = self._press
        self._press = None
        if press is None:
            return None
        px, py, count = press
        dragged = abs(x - px) >= self._drag_x or abs(y - py) >= self._drag_y
        if dragged or count >= 2:
            self._shown = True
            return ("show", x, y)
        return None

    def on_other_input(self):
        """휠·키 입력·다른 버튼 → 언제나 ("hide",). 누르고 있는 끌기와 연속 클릭 기록은 건드리지 않는다."""
        self._shown = False
        return ("hide",)


# ════════════════════════════════════════════════════════════════════
#  모양 계산 (순수 — 테스트한다)
# ════════════════════════════════════════════════════════════════════
def dot_position(x, y, size, gap, work_area):
    """점 창의 왼쪽 위 좌표 (left, top).

    확장 reposition()(selection-button.js:116-131)을 따른다: 왼쪽 = 선택 끝 + GAP, 세로 가운데 = 선택 줄 가운데,
    그리고 화면 안으로 끌어넣기. 데스크톱은 선택 끝 대신 "마우스를 뗀 자리"(x, y)를 쓴다(사용자 결정).
    work_area = (왼, 위, 오른, 아래) 그 모니터의 작업 영역(작업표시줄 제외). None 이면 끌어넣지 않는다.
    세로: top = y - size//2 → 홀수 크기에서 점 가운데가 y 픽셀 한가운데에 온다.
    커서와 겹치면 왼쪽으로 (2026-09-28 사용자 확정):
      모니터 오른쪽 끝에서 약 size 픽셀(배율 140% 에서 31px) 안쪽에서 떼면, 끌어넣기 때문에 점이 마우스 바로 밑에 뜬다.
      최대화한 창의 세로 스크롤바(VS Code·크롬, 화면 오른쪽 끝)를 끌고 놓으면 이렇게 되어, 같은 자리를 다시 누르면
      스크롤바 대신 점이 눌렸다(3차 검증 verifyDot.md ④-1). 그래서 끌어넣은 결과 점 창 사각형이 뗀 자리 픽셀
      (floor(x), floor(y))을 덮으면 커서 왼쪽(뗀 x − GAP − 점 크기)에 놓는다. 세로 자리는 그대로.
      - "겹침" 은 원(클릭 영역)이 아니라 창 사각형으로 본다 — 모서리는 원 밖이라 눌리지 않지만, 넉넉하게 피하는 쪽을 골랐다.
      - 끌어넣기를 안 할 때(work_area=None)는 점이 늘 x + GAP 오른쪽이라 겹치지 않으므로(GAP ≥ 1) 이 보정을 하지 않는다.
      - 왼쪽으로 옮긴 자리도 작업 영역 왼쪽 끝보다 앞이면 왼쪽 끝으로 붙인다(그러면 다시 겹칠 수 있지만 모니터 폭이
        점 두 개 + GAP 보다 좁을 때뿐이라 실제로는 없다).
      확장은 화면 안으로 끌어넣기만 한다(selection-button.js:125) — 이 보정은 데스크톱에서만 생기는 문제라 확장에 없다.
    """
    left = int(math.floor(x)) + int(gap)
    top = int(math.floor(y)) - int(size) // 2
    if work_area:
        l, t, r, b = (int(v) for v in work_area)
        s = int(size)
        left = max(l, min(left, r - s))
        top = max(t, min(top, b - s))
        cx, cy = int(math.floor(x)), int(math.floor(y))
        if left <= cx < left + s and top <= cy < top + s:
            left = max(l, cx - int(gap) - s)
    return left, top


def circle_mask(size):
    """size×size 칸마다 "원형 클릭 영역 안인가"(True/False) 표. 행(y) 튜플의 튜플.

    창 모양(SetWindowRgn)과 똑같은 표를 쓰려고 윈도우에서는 같은 GDI 원(CreateEllipticRgn(0, 0, size+1, size+1))을
    PtInRegion 으로 한 칸씩 물어서 만든다. 그래서 contains()·점 둘레의 보이지 않는 칠·창 모양이 한 칸도 어긋나지 않는다.
    +1 인 까닭: GDI 원은 오른쪽·아래 경계를 빼고 그린다. +1 이라야 상하좌우 대칭이 된다(2026-09-28 실측:
    22px 에서 +0 은 비대칭, +1 은 대칭. 옛 플로팅 아이콘도 SIZE + 1 을 썼다).
    윈도우가 아니면 같은 모양을 수식으로 흉내 낸다(칸 가운데가 원 안인지).
    """
    size = int(size)
    if _IS_WIN:
        rgn = None
        try:
            rgn = _g32.CreateEllipticRgn(0, 0, size + 1, size + 1)
            if rgn:
                return tuple(tuple(bool(_g32.PtInRegion(rgn, x, y)) for x in range(size)) for y in range(size))
        except Exception as exc:
            log.debug("원 모양 표를 GDI 로 못 만듦 — 수식으로: %s", exc)
        finally:
            if rgn:
                _g32.DeleteObject(rgn)
    c = size / 2.0
    r2 = c * c
    return tuple(tuple((x + 0.5 - c) ** 2 + (y + 0.5 - c) ** 2 <= r2 for x in range(size)) for y in range(size))


def render_dot_bgra(size, dot_diameter, mask, rgb=DOT_RGB, ring_alpha=RING_ALPHA, supersample=SUPERSAMPLE):
    """UpdateLayeredWindow 에 넘길 그림(위→아래, 한 칸 4바이트 B·G·R·A, 알파를 곱해 둔 값)을 만든다.

    - 가운데 지름 dot_diameter(실제 픽셀, 소수 가능) 빨간 원. 가장자리는 supersample 배로 그려 줄여서
      "덮인 비율 = 알파"로 매끄럽게(확장은 브라우저가 매끄럽게 그린다).
    - 원 밖이지만 클릭 영역(mask) 안인 칸은 알파 ring_alpha(=1/255) — 눈에 안 보이지만 클릭은 이 창이 받는다.
    - mask 밖은 알파 0(투명·클릭 통과. 어차피 창 모양 SetWindowRgn 으로 잘린다).
    알파를 곱해 두는 까닭: UpdateLayeredWindow(AC_SRC_ALPHA)는 "미리 곱한 알파" 그림을 요구한다(윈도우 문서).
    """
    from PIL import Image, ImageDraw   # Pillow 는 앱의 필수 의존성(트레이 아이콘·하단 바가 이미 쓴다)

    size = int(size)
    ss = max(int(supersample), 1)
    big = Image.new("L", (size * ss, size * ss), 0)
    c = size * ss / 2.0
    r = dot_diameter * ss / 2.0
    ImageDraw.Draw(big).ellipse((c - r, c - r, c + r - 1, c + r - 1), fill=255)
    box = getattr(Image, "Resampling", Image).BOX   # 칸 평균 = 덮인 비율
    cover = big.resize((size, size), box).tobytes()
    red, green, blue = rgb
    out = bytearray(size * size * 4)
    for y in range(size):
        row = mask[y]
        for x in range(size):
            a = cover[y * size + x]
            if row[x]:
                a = max(a, ring_alpha)
            else:
                a = 0
            i = (y * size + x) * 4
            out[i] = (blue * a + 127) // 255
            out[i + 1] = (green * a + 127) // 255
            out[i + 2] = (red * a + 127) // 255
            out[i + 3] = a
    return bytes(out)


def _auto_scale(root):
    """CSS 픽셀 → 실제 픽셀 배율(= 화면 DPI / 96). bottom_bar.py _auto_scale 과 같은 방법.

    앱은 DPI 인식 모드라(ttkbootstrap Window hdpi=True → SetProcessDPIAware) 배율 140% 에서 약 1.4.
    """
    try:
        s = float(root.winfo_fpixels("1i")) / 96.0
    except Exception:
        return 1.0
    return s if 0.5 <= s <= 4.0 else 1.0


def _no_autostyle(cls):
    """ttkbootstrap 이 tk 위젯 생성자를 바꿔치기했으면 {"autostyle": False} (reader_window.py 와 같은 판정)."""
    init = getattr(cls, "__init__", None)
    if getattr(init, "__name__", "") == "__init__wrapper":
        return {"autostyle": False}
    return {}


def _work_area_at(x, y):
    """(x, y) 가 있는 모니터의 작업 영역(작업표시줄 제외) (왼, 위, 오른, 아래). 모니터 밖이면 가장 가까운 모니터."""
    if not _IS_WIN:
        return None
    try:
        hmon = _u32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST)
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if hmon and _u32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcWork
            return (r.left, r.top, r.right, r.bottom)
    except Exception:
        pass
    return None


def _update_layered(hwnd, size, bgra):
    """UpdateLayeredWindow 로 창 그림을 통째로 바꾼다(위치는 그대로 — pptDst=NULL). 성공하면 True.

    순서: 화면 DC → 메모리 DC → 32비트 DIB(위→아래: biHeight 음수)에 그림 복사 → ULW(ULW_ALPHA, 픽셀마다 알파)
    → 뒷정리. 창에 WS_EX_LAYERED 가 있어야 하고, 그 창에 SetLayeredWindowAttributes 를 부른 적이 없어야 한다
    (둘을 섞으면 ULW 가 실패한다 — 그래서 Tk -alpha 를 쓰지 않는다).
    """
    screen = mem = bmp = old = None
    try:
        screen = _u32.GetDC(None)
        mem = _g32.CreateCompatibleDC(screen)
        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = size
        bmi.bmiHeader.biHeight = -size
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        bits = ctypes.c_void_p()
        bmp = _g32.CreateDIBSection(mem, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        if not bmp or not bits.value:
            return False
        ctypes.memmove(bits.value, bgra, len(bgra))
        old = _g32.SelectObject(mem, bmp)
        sz = wintypes.SIZE(size, size)
        src = wintypes.POINT(0, 0)
        blend = _BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        return bool(_u32.UpdateLayeredWindow(hwnd, screen, None, ctypes.byref(sz), mem, ctypes.byref(src),
                                             0, ctypes.byref(blend), ULW_ALPHA))
    except Exception as exc:
        log.debug("UpdateLayeredWindow 실패: %s", exc)
        return False
    finally:
        if mem and old:
            _g32.SelectObject(mem, old)
        if bmp:
            _g32.DeleteObject(bmp)
        if mem:
            _g32.DeleteDC(mem)
        if screen:
            _u32.ReleaseDC(None, screen)


# ════════════════════════════════════════════════════════════════════
#  점 창
# ════════════════════════════════════════════════════════════════════
class SelectionButton:
    """선택 끝 옆에 뜨는 빨간 점 창. 점 위에서 누르고 점 위에서 떼면 on_click() 을 부르고 숨는다.

    모양 (확장 selection-button.js:133-167)
      - 클릭 영역 = 지름 22px 원(× 화면 배율). 눈에 보이는 것은 가운데 지름 12px 빨간 점 #ff3b30 뿐이고
        둘레는 투명하게 보이지만 누르면 이 창이 받는다(RING_ALPHA — 함정 1).
      - 마우스를 올리면(클릭 영역 안) 점이 1.25배(확장 hover). 확장의 0.1초 전환 애니메이션은 넣지 않았다.
      - 손가락 모양 커서(확장 cursor: pointer).
    어떻게 그리나
      - Tk 로 그리지 않는다. 창 틀에 WS_EX_LAYERED 를 걸고 UpdateLayeredWindow 로 "픽셀마다 알파가 있는 그림"을
        직접 올린다. Tk 로는 창의 일부만 투명하게 할 수단이 -transparentcolor 뿐인데, 그건 NOACTIVATE 를 지우고
        (함정 2) 투명한 곳은 클릭도 통과시켜(=아래 앱이 선택을 풀어 버림) 쓸 수 없다.
      - 창 모양은 원(SetWindowRgn, 옛 플로팅 아이콘과 같은 CreateEllipticRgn(0,0,S+1,S+1)) → 네 모서리는 창이 아니다.
      - UpdateLayeredWindow 가 실패하면(거의 없음) 대신 원 전체(22px)를 빨갛게 칠한 창으로 보인다(_fallback).
    모든 메서드는 Tk 메인 스레드에서만. 예외: contains()·hwnd 는 어느 스레드에서나(Tk 를 안 부른다).
    실측 (2026-09-28, 배율 140%·모니터 두 대, 3초 데모 — scratchpad phase3_shots\\v2_verify.py·v4_fallback.py)
      - 확장 스타일 0x8080088 = NOACTIVATE·LAYERED·TOOLWINDOW·TOPMOST, APPWINDOW 없음, 소유자 없음. 전경 창 그대로.
      - GetWindowRect = (_pos, _size) 그대로. 창 모양(GetWindowRgn)·WindowFromPoint·contains() 가 31×31 모든 칸에서
        일치(주 모니터 가운데·오른쪽 아래 끝, 왼쪽 모니터 음수 좌표 두 곳, 보이는 채로 옮긴 뒤).
      - WindowFromPoint 는 점 위에서 Tk 안쪽 자식 창을 돌려주고, Tk winfo_containing 도 이 창을 가리킨다
        → Tk 의 마우스 추적이 점 위를 "창 안"으로 보므로 hover 가 저절로 풀리지 않는다(실제 마우스로는 못 잼).
      - 점 지름 약 16.9px(12×1.397), hover 약 20.9px, 가운데 색 (255,59,48), 둘레는 바탕과 1 단계 차이(안 보임).
      - _fallback(ULW 실패)도 처음부터·떠 있는 중 둘 다 31px 빨간 원으로 보이고 NOACTIVATE 가 남는다.
    """

    def __init__(self, root, on_click, get_msg):
        self._root = root
        self._on_click = on_click
        self._get_msg = get_msg
        self._owner_thread = threading.current_thread()
        self._destroyed = False
        self._scale = _auto_scale(root)
        self._size = max(int(round(SIZE_PX * self._scale)), 3)
        self._gap = int(round(GAP_PX * self._scale))
        self._mask = circle_mask(self._size)
        self._frames = {   # 점 그림 두 장을 미리 만들어 둔다(hover 때 바꿔 끼우기만)
            False: render_dot_bgra(self._size, DOT_PX * self._scale, self._mask),
            True: render_dot_bgra(self._size, DOT_PX * HOVER_SCALE * self._scale, self._mask),
        }
        self._hover = False
        self._pressed = False
        self._visible = False
        self._pos = None          # 떠 있을 때 (left, top). contains() 가 훅 스레드에서 읽는다 → 통째로 바꿔 끼운다
        self._hwnd = None         # 바깥 틀 핸들(int). hwnd 속성이 훅 스레드에서 읽는다
        self._styled_hwnd = None  # 스타일·모양·그림을 건 틀(Tk 가 틀을 새로 만들면 달라진다 → 다시 건다)
        self._painted = None      # 지금 틀에 올라간 그림이 hover 인지(False/True). None = 아직 안 그림
        self._fallback = False    # UpdateLayeredWindow 가 안 돼서 빨간 원 창으로 대신하는 중

        self.win = tk.Toplevel(root, **_no_autostyle(tk.Toplevel))
        # ⚠ 아래는 "처음 화면에 붙기(첫 idle) 전"에 한다(함정 3). withdraw 라서 첫 매핑 때 틀이 숨은 채로 만들어진다.
        self.win.withdraw()
        self.win.overrideredirect(True)
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        # 바탕색은 보이지 않는다(그림은 UpdateLayeredWindow 가 올린다). 대신 쓰는 경우(_fallback)에만 보인다
        self.win.configure(background=DOT_COLOR, cursor="hand2", borderwidth=0, highlightthickness=0)
        self.win.title(self._msg("selection_button_title"))   # 제목 표시줄은 없지만 접근성·작업 관리자에 쓰이는 이름
        s = self._size
        self.win.geometry("%dx%d+0+0" % (s, s))
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self.win.bind("<ButtonPress-1>", self._on_press)
        self.win.bind("<ButtonRelease-1>", self._on_release)
        self.win.bind("<Enter>", lambda e: self._set_hover(True))
        self.win.bind("<Leave>", lambda e: self._set_hover(False))
        try:
            self.win.update_idletasks()   # 숨은 틀을 만들게 한다 → 보이기 전에 스타일을 미리 건다
        except tk.TclError:
            pass
        self._ensure_window()

    # ── 약속된 메서드 ───────────────────────────────────────────────────

    def show_at(self, x, y):
        """마우스를 뗀 화면 좌표 (x, y) 오른쪽에 점을 띄운다. 포커스를 뺏지 않는다.

        자리: 클릭 영역 왼쪽 = x + GAP, 세로 가운데 = y, 그 모니터 작업 영역 밖으로 안 나가게(dot_position).
              끌어넣은 결과 점이 커서(뗀 자리)를 덮으면 커서 왼쪽(x − GAP − 크기)으로 옮긴다(dot_position 설명).
        이미 떠 있으면 새 자리로 옮긴다. hover·누름 상태는 새로 시작한다.
        """
        self._check_thread("show_at")
        if self._destroyed:
            return
        s = self._size
        left, top = dot_position(x, y, s, self._gap, _work_area_at(x, y))
        self._pressed = False
        self._hover = False
        try:
            # 숨긴 채로 옮긴다(숨은 창도 Tk 가 틀을 옮긴다 — reader_window.py 실측). 보이는 순간 제자리
            self.win.geometry("%dx%d+%d+%d" % (s, s, left, top))
            self.win.update_idletasks()
        except tk.TclError:
            return
        hwnd = self._ensure_window()
        if hwnd:
            _u32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            _u32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                              SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
        else:
            # Win32 가 안 되는 환경(윈도우 아님)에서만 Tk 로 보인다(포커스를 가져갈 수 있다)
            self.win.deiconify()
        self._visible = True
        self._pos = (left, top)

    def hide(self):
        """점을 숨긴다. 여러 번 불러도 된다."""
        self._check_thread("hide")
        self._pos = None          # 훅 스레드의 contains() 가 바로 False 를 보도록 먼저
        self._visible = False
        self._pressed = False
        if self._destroyed:
            return
        hwnd = self._current_hwnd()
        if hwnd:
            _u32.ShowWindow(hwnd, SW_HIDE)
        else:
            try:
                self.win.withdraw()
            except tk.TclError:
                pass
        if self._hover:
            self._hover = False
            self._paint()         # 다음에 뜰 때 작은 점부터

    def is_visible(self):
        """지금 화면에 떠 있는지."""
        if self._destroyed:
            return False
        hwnd = self._current_hwnd()
        if hwnd:
            return bool(_u32.IsWindowVisible(hwnd))
        return self._visible

    def destroy(self):
        """창을 없앤다(앱 종료 때). 두 번 불러도 괜찮다."""
        self._pos = None
        self._visible = False
        if self._destroyed:
            return
        self._destroyed = True
        self._hwnd = None
        try:
            self.win.destroy()
        except Exception:
            pass

    def contains(self, x, y):
        """화면 좌표 (x, y) 가 지금 떠 있는 점의 원형 클릭 영역 안인지. 안 떠 있으면 False.

        ⚠ 마우스 훅 스레드에서 부른다(점을 누른 것은 "선택 동작"이 아니므로 감지 로직에 넘기지 않으려고).
          그래서 Tk 를 부르지 않고, show_at/hide 가 통째로 바꿔 끼우는 self._pos 튜플과 고정된 원 표(_mask)만 읽는다.
        원 표는 창 모양(SetWindowRgn)과 같은 GDI 원에서 만들었다(circle_mask) → 윈도우가 이 창에 클릭을 주는
        칸과 정확히 같다.
        """
        pos = self._pos
        if pos is None:
            return False
        try:
            ix = int(math.floor(x)) - pos[0]
            iy = int(math.floor(y)) - pos[1]
        except (TypeError, ValueError):
            return False
        if not (0 <= ix < self._size and 0 <= iy < self._size):
            return False
        return self._mask[iy][ix]

    @property
    def hwnd(self):
        """점 창 바깥 틀 핸들(int). 아직 없거나 없앤 뒤면 None. 어느 스레드에서 읽어도 된다(저장된 값만 돌려준다)."""
        return self._hwnd

    # ── 누름·뗌·hover (Tk 메인 스레드 — Tk 이벤트) ──────────────────────

    def _inside(self, wx, wy):
        """창 안 좌표 (wx, wy) 가 원형 클릭 영역 안인지(contains 와 같은 표)."""
        try:
            ix, iy = int(wx), int(wy)
        except (TypeError, ValueError):
            return False
        return 0 <= ix < self._size and 0 <= iy < self._size and self._mask[iy][ix]

    def _on_press(self, event):
        """왼쪽 버튼 누름: 점 위에서 눌렀는지만 기억한다. 읽기는 "뗄 때" 한다(확장 click 과 같음)."""
        self._pressed = self._visible and self._inside(event.x, event.y)

    def _on_release(self, event):
        """왼쪽 버튼 뗌: 점 위에서 눌렀고 점 위에서 뗐으면 on_click() 뒤 숨긴다. 밖에서 떼면 아무것도 안 한다.

        누른 뒤 밖으로 끌고 나가도 Tk 가 이 창으로 뗌을 보내 준다(누름 동안의 암묵적 잡기) → event.x/y 가 창 밖 좌표.
        on_click 이 예외를 내도 점은 숨긴다(확장 read() 도 읽기 요청 전에 hide: selection-button.js:201-207).
        """
        was = self._pressed
        self._pressed = False
        if not was or not self._inside(event.x, event.y):
            return
        try:
            self._on_click()
        except Exception:
            log.exception("선택 버튼 on_click 실패")
        finally:
            self.hide()

    def _set_hover(self, on):
        """마우스가 클릭 영역에 들어오면 점을 1.25배로, 나가면 원래대로(확장 button:hover::before)."""
        on = bool(on)
        if on == self._hover:
            return
        self._hover = on
        if not self._destroyed:
            self._paint()

    # ── 창 스타일·모양·그림 ─────────────────────────────────────────────

    def _current_hwnd(self):
        """Tk 틀 핸들을 새로 구한다(Tk 가 틀을 다시 만들면 바뀌므로 저장값에 기대지 않는다). Tk 메인 스레드 전용."""
        if not _IS_WIN or self._destroyed:
            return None
        try:
            hwnd = _u32.GetParent(self.win.winfo_id())
        except Exception:
            return None
        self._hwnd = int(hwnd) if hwnd else None
        return self._hwnd

    def _ensure_window(self):
        """틀에 스타일·원 모양·그림이 걸려 있게 한다. 이미 걸려 있으면 거의 아무것도 안 한다(멱등). 틀 핸들을 돌려준다.

        - WS_EX_NOACTIVATE: 눌러도 활성 창이 되지 않는다(함정 1). WS_EX_TOOLWINDOW: 작업표시줄·Alt+Tab 에 안 나온다.
          WS_EX_APPWINDOW 는 끈다. WS_EX_LAYERED: 픽셀마다 알파 그림(UpdateLayeredWindow).
        - 소유자 분리(GWLP_HWNDPARENT=0): root 가 숨어 있어도 독립적으로 보이게(옛 플로팅 아이콘·bottom_bar 와 같음).
        - 항상 위는 SetWindowPos(HWND_TOPMOST)로(스타일 비트로 바꾸지 않는다 — 윈도우 문서).
        """
        hwnd = self._current_hwnd()
        if not hwnd:
            return None
        try:
            ex = _GetWindowLongPtr(hwnd, GWL_EXSTYLE)
            want = (ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            want = (want & ~WS_EX_LAYERED) if self._fallback else (want | WS_EX_LAYERED)
            if want != ex or self._styled_hwnd != hwnd:
                _SetWindowLongPtr(hwnd, GWLP_HWNDPARENT, 0)
                if want != ex:
                    _SetWindowLongPtr(hwnd, GWL_EXSTYLE, want)
                    self._painted = None     # 층 창이 새로 켜졌으면 그림을 다시 올려야 보인다
                _u32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                  SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOOWNERZORDER)
            if self._styled_hwnd != hwnd:
                rgn = _g32.CreateEllipticRgn(0, 0, self._size + 1, self._size + 1)
                if rgn and not _u32.SetWindowRgn(hwnd, rgn, True):
                    _g32.DeleteObject(rgn)   # 성공하면 창이 가져가므로 지우지 않는다(윈도우 문서)
                self._styled_hwnd = hwnd
                self._painted = None
        except Exception as exc:
            log.warning("선택 버튼 Win32 스타일 적용 실패(포커스를 가져갈 수 있음): %s", exc)
        if self._painted != self._hover:
            self._paint()
        return hwnd

    def _paint(self):
        """지금 hover 상태에 맞는 점 그림을 틀에 올린다. 실패하면 빨간 원 창(_fallback)으로 바꾼다."""
        if self._fallback or not _IS_WIN:
            return
        hwnd = self._current_hwnd()
        if not hwnd:
            return
        if _update_layered(hwnd, self._size, self._frames[self._hover]):
            self._painted = self._hover
            return
        # 층 창 그림이 안 된다 → 층 창을 끄고 Tk 바탕색(빨강)이 원 모양 창 전체로 보이게 한다.
        # 클릭 영역은 그대로 22px 원이고, 점이 12px 가 아니라 22px 로 보이는 것만 다르다.
        log.warning("선택 버튼: UpdateLayeredWindow 실패 — 빨간 원 창으로 대신 보인다")
        self._fallback = True
        try:
            ex = _GetWindowLongPtr(hwnd, GWL_EXSTYLE)
            _SetWindowLongPtr(hwnd, GWL_EXSTYLE, ex & ~WS_EX_LAYERED)
            _u32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                              SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOOWNERZORDER)
        except Exception as exc:
            log.debug("층 창 끄기 실패: %s", exc)

    # ── 기타 ──────────────────────────────────────────────────────────

    def _msg(self, key):
        """messages.py 문구. 키가 없으면(get_message 는 "[Missing message: 키]") 기본 한국어(확장 문구)."""
        default = _DEFAULT_MSGS.get(key, key)
        try:
            text = self._get_msg(key) if self._get_msg else None
        except Exception:
            text = None
        if not text or (isinstance(text, str) and text.startswith("[Missing message")):
            return default
        return text

    def _check_thread(self, name):
        """Tk 메인 스레드가 아닌 곳에서 부르면 경고 로그만 남긴다(reader_window.py 와 같은 방식)."""
        if threading.current_thread() is not self._owner_thread:
            log.warning("SelectionButton.%s 가 Tk 메인 스레드가 아닌 곳에서 불림 — gui_queue 로 넘겨야 한다", name)


# ════════════════════════════════════════════════════════════════════
# 데모 — python selection_button.py [--shots 폴더]
#   3초 안에 스스로 닫힌다. 포커스를 뺏지 않는 어두운/밝은 바탕 창 위에 점을 띄워 캡처하고,
#   스타일(NOACTIVATE·LAYERED)·WindowFromPoint·contains·클릭(Tk 내부 event_generate — 운영체제 입력 흉내 아님)을 확인한다.
#   (whisperer.py 는 import 하지 않는다. 마우스·키보드 훅을 걸지 않는다. 커서를 움직이지 않는다.)
# ════════════════════════════════════════════════════════════════════
def _demo(argv):  # pragma: no cover - 사람이 눈으로 보는 데모
    import argparse
    import os

    p = argparse.ArgumentParser(description="SelectionButton 데모(3초 이내)")
    p.add_argument("--shots", default=None, help="캡처 저장 폴더")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    u = ctypes.windll.user32

    try:
        import ttkbootstrap as ttkb   # 앱과 같은 환경(SetProcessDPIAware 를 켠다)
        root = ttkb.Window(themename="cosmo")
    except Exception:
        u.SetProcessDPIAware()
        root = tk.Tk()
    root.withdraw()
    orig_fg = u.GetForegroundWindow()
    root.update_idletasks()
    root.update()
    if orig_fg and u.GetForegroundWindow() != orig_fg:   # 첫 틀이 전경을 가져갔으면 돌려준다(reader_window 데모와 같음)
        u.SetForegroundWindow(orig_fg)
        root.update()
    fg_before = u.GetForegroundWindow()

    area = _work_area_at(0, 0) or (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
    scale = _auto_scale(root)
    bw, bh = int(240 * scale), int(60 * scale)
    bx, by = area[2] - bw - int(40 * scale), area[3] - bh - int(40 * scale)

    # 바탕 창(왼쪽 VS Code 다크 #1e1e1e, 오른쪽 흰색) — 포커스를 뺏지 않게 NOACTIVATE 로
    back = tk.Toplevel(root, **_no_autostyle(tk.Toplevel))
    back.withdraw()
    back.overrideredirect(True)
    back.attributes("-topmost", True)
    back.geometry("%dx%d+%d+%d" % (bw, bh, bx, by))
    cv = tk.Canvas(back, width=bw, height=bh, highlightthickness=0, bd=0, background="#1e1e1e",
                   **_no_autostyle(tk.Canvas))
    cv.pack(fill="both", expand=True)
    cv.create_rectangle(bw // 2, 0, bw, bh, fill="#ffffff", width=0)
    cv.create_text(8, bh // 2, text="선택한 글", fill="#d4d4d4", anchor="w")
    cv.create_text(bw // 2 + 8, bh // 2, text="선택한 글", fill="#222222", anchor="w")
    back.update_idletasks()
    bh_wnd = _u32.GetParent(back.winfo_id())
    ex = u.GetWindowLongW(bh_wnd, GWL_EXSTYLE)
    u.SetWindowLongW(bh_wnd, GWL_EXSTYLE, (ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
    u.ShowWindow(bh_wnd, SW_SHOWNOACTIVATE)

    clicks = []
    btn = SelectionButton(root, on_click=lambda: clicks.append(1),
                          get_msg=lambda k, *a: "[Missing message: %s]" % k)
    results = {}
    shots = args.shots
    if shots:
        os.makedirs(shots, exist_ok=True)

    def grab(name, pad=6):
        if not shots:
            return
        from PIL import ImageGrab, Image
        l, t = btn._pos
        s = btn._size
        img = ImageGrab.grab(bbox=(l - pad, t - pad, l + s + pad, t + s + pad), all_screens=True)
        img.save(os.path.join(shots, "dot_%s.png" % name))
        img.resize((img.width * 8, img.height * 8), Image.NEAREST).save(os.path.join(shots, "dot_%s_x8.png" % name))

    def style_info():
        h = btn.hwnd
        ex_ = _GetWindowLongPtr(h, GWL_EXSTYLE)
        return {"hwnd": h, "exstyle": hex(ex_), "NOACTIVATE": bool(ex_ & WS_EX_NOACTIVATE),
                "LAYERED": bool(ex_ & WS_EX_LAYERED), "TOOLWINDOW": bool(ex_ & WS_EX_TOOLWINDOW),
                "TOPMOST": bool(ex_ & 0x8), "APPWINDOW": bool(ex_ & WS_EX_APPWINDOW),
                "owner": u.GetWindow(h, 4), "fallback": btn._fallback}

    def hit(sx, sy):
        u.WindowFromPoint.restype = wintypes.HWND
        u.WindowFromPoint.argtypes = [wintypes.POINT]
        w = u.WindowFromPoint(wintypes.POINT(sx, sy))
        return bool(w) and (int(w) == btn.hwnd or _u32.GetParent(w) == btn.hwnd)

    s = btn._size
    dark_x, dark_y = bx + bw // 4, by + bh // 2
    light_x, light_y = bx + (3 * bw) // 4, by + bh // 2

    def step1():
        btn.show_at(dark_x, dark_y)
        root.update()
        results["style"] = style_info()
        results["visible"] = btn.is_visible()
        l, t = btn._pos
        c = s // 2
        results["pos"] = (l, t, "expected_left", dark_x + btn._gap, "expected_center_y", dark_y)
        # WindowFromPoint 는 윈도우의 실제 클릭 판정(창 모양·알파)을 따른다 — 읽기 전용 질의
        results["hit_center"] = hit(l + c, t + c)
        results["hit_ring"] = hit(l + 1, t + c)            # 점 밖이지만 클릭 영역 안(알파 1)
        results["hit_corner"] = hit(l, t)                  # 원 밖 모서리 → 아래 창
        results["contains_center"] = btn.contains(l + c, t + c)
        results["contains_corner"] = btn.contains(l, t)
        results["contains_ring"] = btn.contains(l + 1, t + c)
        root.after(120, step2)

    def step2():
        grab("dark")
        btn.win.event_generate("<Enter>")    # Tk 내부 이벤트(커서는 안 움직인다) → 바인딩이 hover 로 잇는지
        root.update()
        results["hover_after_enter"] = btn._hover
        root.after(80, step3)

    def step3():
        grab("dark_hover")
        btn.win.event_generate("<Leave>")
        results["hover_after_leave"] = btn._hover
        btn.show_at(light_x, light_y)
        root.update()
        root.after(120, step4)

    def step4():
        grab("light")
        # 클릭: 점 위에서 누르고 밖에서 뗌 → 아무 일 없음
        c = s // 2
        l0, t0 = btn._pos
        btn.win.event_generate("<ButtonPress-1>", x=c, y=c)
        btn.win.event_generate("<ButtonRelease-1>", x=s + 20, y=c)
        results["drag_out_clicks"] = len(clicks)
        results["drag_out_visible"] = btn.is_visible()
        # 점 위에서 누르고 점 위에서 뗌 → on_click 1번 + 숨김
        btn.win.event_generate("<ButtonPress-1>", x=c, y=c)
        btn.win.event_generate("<ButtonRelease-1>", x=c + 1, y=c)
        results["click_clicks"] = len(clicks)
        results["click_visible"] = btn.is_visible()
        results["contains_after_hide"] = btn.contains(l0 + c, t0 + c)
        # 화면 오른쪽 아래 끝에서 뗀 경우 → 작업 영역 안으로
        btn.show_at(area[2] - 1, area[3] - 1)
        root.update()
        l, t = btn._pos
        results["clamp"] = (l, t, l + s <= area[2], t + s <= area[3], "area", area)
        btn.hide()
        root.after(50, finish)

    def finish():
        fg_after = u.GetForegroundWindow()
        results["foreground_unchanged"] = (fg_before == fg_after)
        results["foreground_is_ours"] = fg_after in (btn.hwnd, bh_wnd)
        for k, v in results.items():
            print(k, v)
        btn.destroy()
        back.destroy()
        root.destroy()

    root.after(100, step1)
    root.after(2800, lambda: (print("watchdog"), root.destroy()))   # 무슨 일이 있어도 3초 안에 닫는다
    root.mainloop()


if __name__ == "__main__":
    _demo(sys.argv[1:])
