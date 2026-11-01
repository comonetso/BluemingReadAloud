# usage_pill.py - 읽기 사용량 알약 (2026-11-01 리규형님 요청)
#
# "나가는 돈이 너무 많아 모니터링하려는 것" — 트레이 아이콘을 왼쪽 클릭하면 작은 알약이 뜨고, 지금 고른 목소리 종류의
# 이번 달 세 곳(Paseo·이 앱·크롬 확장) 합계를 계속 새로 보여 준다. 다시 왼쪽 클릭하면 숨는다(켜 둔 상태는 앱을 다시 켜도 유지).
# 끌어서 옮길 수 있고 옮긴 자리는 앱이 기억한다. 알약을 누르면 설정 창의 "읽기 사용량" 창이 뜬다(whisperer.show_usage_dialog).
# 글·색은 whisperer 가 정해 set_text 로 넘긴다(tts_usage.pill_text). 이 파일은 창만 맡는다.
#
# 창은 빨간 점(selection_button.py)과 같은 방식 — 머리 설명의 함정 1~6 을 그대로 따른다:
#   WS_EX_NOACTIVATE|TOOLWINDOW(눌러도 다른 앱의 포커스를 뺏지 않음·작업표시줄에 안 나옴), 보이기는 ShowWindow(SW_SHOWNOACTIVATE),
#   -alpha·-transparentcolor·deiconify 를 쓰지 않음, overrideredirect·topmost 는 처음 화면에 붙기 전에.
#   모양은 SetWindowRgn(CreateRoundRectRgn) 으로 양끝을 둥글게 자른다(층 창이 아니라 Tk 바탕색이 그대로 보인다).
# ⚠️ Tk 메인 스레드에서만 부른다.

import logging
import sys
import tkinter as tk

from selection_button import (_IS_WIN, _auto_scale, _no_autostyle, _read_gesture_settings, _work_area_at,
                              GWL_EXSTYLE, GWLP_HWNDPARENT, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_LAYERED,
                              WS_EX_NOACTIVATE, SW_HIDE, SW_SHOWNOACTIVATE, SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE,
                              SWP_FRAMECHANGED, SWP_NOOWNERZORDER, HWND_TOPMOST)

if _IS_WIN:
    import ctypes
    from ctypes import wintypes
    from selection_button import _u32, _g32, _GetWindowLongPtr, _SetWindowLongPtr
    _g32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
    _g32.CreateRoundRectRgn.restype = wintypes.HRGN

log = logging.getLogger(__name__)

# 색 — 하단 바·설정 창(darkly)과 어울리는 짙은 회색, 무료분을 넘으면 빨강(Claude 가 정함)
BG = "#2b2b2b"
FG = "#e6e6e6"
ALERT_BG = "#b03030"
ALERT_FG = "#ffffff"
MARGIN_PX = 12          # 처음 자리: 작업 영역 오른쪽 아래에서 띄우는 거리(CSS 픽셀, 배율을 곱한다)
PAD_X_PX, PAD_Y_PX = 14, 5
POPUP_GAP_PX = 8        # 알약을 눌러 뜬 사용량 창과 알약 사이(CSS 픽셀)


def popup_position(anchor_rect, size, work_area, gap):
    """알약 (x, y, w, h) 에 붙여 띄울 창의 왼쪽 위 — 오른쪽 끝을 알약 오른쪽 끝에 맞추고 알약 바로 위
    (2026-11-01 리규형님 스크린샷 "이런 식으로"). 위에 자리가 없으면 알약 아래. 작업 영역 밖으로는 안 나간다."""
    ax, ay, aw, ah = anchor_rect
    w, h = size
    x, y = ax + aw - w, ay - gap - h
    if work_area is not None:
        left, top, right, bottom = work_area
        if y < top:
            y = ay + ah + gap
        x = max(left, min(x, right - w))
        y = max(top, min(y, bottom - h))
    return x, y


def pill_position(saved, size, work_area, margin):
    """알약 왼쪽 위 (x, y). saved 가 없으면 작업 영역 오른쪽 아래(margin 띄움), 있으면 그 자리를 작업 영역 안으로 끌어넣는다.
    work_area = (왼, 위, 오른, 아래) 또는 None(모름 — saved 그대로, 없으면 (0, 0))."""
    w, h = size
    if work_area is None:
        return (int(saved[0]), int(saved[1])) if saved else (0, 0)
    left, top, right, bottom = work_area
    if not saved:
        x, y = right - w - margin, bottom - h - margin
    else:
        x, y = int(saved[0]), int(saved[1])
    x = max(left, min(x, right - w))
    y = max(top, min(y, bottom - h))
    return x, y


class UsagePill:
    """사용량 알약 창. on_click() = 눌렀다 뗌(끌지 않음), on_moved(x, y) = 끌어서 옮긴 뒤 놓은 자리."""

    def __init__(self, root, on_click, on_moved):
        self._root = root
        self._on_click = on_click
        self._on_moved = on_moved
        self._destroyed = False
        self._visible = False
        self._alert = False
        self._styled_hwnd = None
        self._region_size = None
        self._press = None        # (마우스 x, y, 창 x, y) — 누른 순간
        self._dragging = False
        scale = _auto_scale(root)
        self._margin = int(round(MARGIN_PX * scale))
        self._drag_threshold = _read_gesture_settings(
            _u32.GetSystemMetrics if _IS_WIN else None, None)["drag_threshold"]

        self.win = tk.Toplevel(root, **_no_autostyle(tk.Toplevel))
        self.win.withdraw()                       # 함정 3: 처음 화면에 붙기 전에
        self.win.overrideredirect(True)
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.win.configure(background=BG, borderwidth=0, highlightthickness=0, cursor="hand2")
        self.win.title("BluemingReadAloud usage")
        self.label = tk.Label(self.win, text="", background=BG, foreground=FG, borderwidth=0,
                              padx=int(round(PAD_X_PX * scale)), pady=int(round(PAD_Y_PX * scale)),
                              **_no_autostyle(tk.Label))
        self.label.pack()
        for w in (self.win, self.label):
            w.bind("<ButtonPress-1>", self._on_press)
            w.bind("<B1-Motion>", self._on_motion)
            w.bind("<ButtonRelease-1>", self._on_release)
        try:
            self.win.update_idletasks()
        except tk.TclError:
            pass
        self._ensure_window()

    # ── 약속된 메서드 ───────────────────────────────────────────────────

    @property
    def visible(self):
        return self._visible and not self._destroyed

    def set_text(self, text, alert=False):
        """알약 글과 경고 색(무료분 넘음)을 바꾼다. 떠 있으면 크기를 글에 맞추고 자리는 그대로(화면 밖이면 안으로)."""
        if self._destroyed:
            return
        self._alert = bool(alert)
        bg, fg = (ALERT_BG, ALERT_FG) if alert else (BG, FG)
        try:
            self.label.configure(text=text, background=bg, foreground=fg)
            self.win.configure(background=bg)
        except tk.TclError:
            return
        if self._visible:
            x, y = self.win.winfo_x(), self.win.winfo_y()
            self._place((x, y))

    def show(self, saved=None):
        """saved = 기억한 왼쪽 위 (x, y) 또는 None(오른쪽 아래). 포커스를 뺏지 않고 띄운다."""
        if self._destroyed:
            return
        self._place(saved)
        hwnd = self._ensure_window()
        if hwnd:
            _u32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            _u32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                              SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
        else:
            self.win.deiconify()   # 윈도우가 아닐 때만(포커스를 가져갈 수 있다)
        self._visible = True

    def hide(self):
        self._visible = False
        self._press = None
        self._dragging = False
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

    def position(self):
        """지금 왼쪽 위 (x, y)."""
        return self.win.winfo_x(), self.win.winfo_y()

    def rect(self):
        """지금 (x, y, w, h) — 알약을 눌러 뜬 창을 그 위에 붙일 때 쓴다."""
        return self.win.winfo_x(), self.win.winfo_y(), self.win.winfo_width(), self.win.winfo_height()

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # ── 자리·모양 ─────────────────────────────────────────────────────

    def _size(self):
        self.win.update_idletasks()
        return max(self.label.winfo_reqwidth(), 1), max(self.label.winfo_reqheight(), 1)

    def _place(self, saved):
        w, h = self._size()
        anchor = saved if saved else (0, 0)   # 처음 자리는 주 모니터(0, 0 을 품은 모니터)
        x, y = pill_position(saved, (w, h), _work_area_at(*anchor) if _IS_WIN else None, self._margin)
        try:
            self.win.geometry("%dx%d+%d+%d" % (w, h, x, y))
            self.win.update_idletasks()
        except tk.TclError:
            return
        self._apply_region(w, h)

    def _apply_region(self, w, h):
        hwnd = self._current_hwnd()
        if not hwnd or self._region_size == (w, h, hwnd):
            return
        try:
            rgn = _g32.CreateRoundRectRgn(0, 0, w + 1, h + 1, h, h)   # 지름 = 높이 → 양끝이 반원
            if rgn and not _u32.SetWindowRgn(hwnd, rgn, True):
                _g32.DeleteObject(rgn)   # 성공하면 창이 가져가므로 지우지 않는다(윈도우 문서)
            self._region_size = (w, h, hwnd)
        except Exception as exc:
            log.debug("알약 모양 적용 실패(네모로 보임): %s", exc)

    def _current_hwnd(self):
        if not _IS_WIN or self._destroyed:
            return None
        try:
            hwnd = _u32.GetParent(self.win.winfo_id())
        except Exception:
            return None
        return int(hwnd) if hwnd else None

    def _ensure_window(self):
        """NOACTIVATE·TOOLWINDOW·소유자 분리·항상 위를 건다(selection_button._ensure_window 와 같은 방법, 층 창은 쓰지 않음)."""
        hwnd = self._current_hwnd()
        if not hwnd:
            return None
        try:
            ex = _GetWindowLongPtr(hwnd, GWL_EXSTYLE)
            want = ((ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW) & ~WS_EX_LAYERED
            if want != ex or self._styled_hwnd != hwnd:
                _SetWindowLongPtr(hwnd, GWLP_HWNDPARENT, 0)
                if want != ex:
                    _SetWindowLongPtr(hwnd, GWL_EXSTYLE, want)
                _u32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                  SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOOWNERZORDER)
                self._styled_hwnd = hwnd
                self._region_size = None
        except Exception as exc:
            log.warning("알약 Win32 스타일 적용 실패(포커스를 가져갈 수 있음): %s", exc)
        return hwnd

    # ── 누르기·끌기 ───────────────────────────────────────────────────

    def _on_press(self, event):
        self._press = (event.x_root, event.y_root, self.win.winfo_x(), self.win.winfo_y())
        self._dragging = False

    def _on_motion(self, event):
        if not self._press:
            return
        px, py, wx, wy = self._press
        dx, dy = event.x_root - px, event.y_root - py
        if not self._dragging and abs(dx) <= self._drag_threshold[0] and abs(dy) <= self._drag_threshold[1]:
            return
        self._dragging = True
        try:
            self.win.geometry("+%d+%d" % (wx + dx, wy + dy))
        except tk.TclError:
            pass

    def _on_release(self, event):
        press, dragging = self._press, self._dragging
        self._press = None
        self._dragging = False
        if not press:
            return
        if dragging:
            self._place(self.position())          # 화면 밖으로 놓았으면 안으로
            try:
                self._on_moved(*self.position())
            except Exception as exc:
                log.warning("알약 자리 저장 실패: %s", exc)
        else:
            try:
                self._on_click()
            except Exception as exc:
                log.warning("알약 클릭 처리 실패: %s", exc)
