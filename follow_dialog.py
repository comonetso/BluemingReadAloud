# follow_dialog.py - 따라 읽기 창 (2026-10-28 리규형님)
"""한 문단 안에서 글을 고르고 읽기를 시작하면 "따라 읽기 할까요?" 를 묻는 작은 창.

모양·문구는 Paseo 상태바 플러그인 확인 창을 따른다(client/web.ts confirmBox, 10-23 — 정본은 그 저장소. 아래 값은
그 파일의 CSS 픽셀): 어두운 상자, 오른쪽에 [이 말만 읽기](테두리만) [따라 읽기](파란 기본 버튼).
Enter = 따라 읽기, 상자 바깥 클릭 = 이 말만 읽기(Paseo 와 같음).
이 앱에서 정한 것(리규형님 10-28 버튼): Esc = 아무것도 안 읽고 닫기 · 자리는 화면 가운데(전경 창의 모니터 작업 영역).
전경 창이 바뀌면(Alt+Tab 등) 아무것도 안 읽고 닫는다 — 하단 바 패널이 전경 창 바뀜에 닫히는 것과 같은 규칙(이 앱에서 고름).

포커스를 가져가지 않는다(WS_EX_NOACTIVATE). 포커스가 원래 앱에 남아야 고른 글과 원문 위 형광펜이 산다.
  - 보이기는 Tk deiconify 대신 Win32 ShowWindow(SW_SHOWNOACTIVATE) — deiconify 는 포커스를 강제로 가져간다
    (selection_button.py 머리말 함정 4). attributes("-alpha") 도 쓰지 않는다(NOACTIVATE 가 지워진다 — 같은 머리말 함정 2).
  - 그래서 키보드를 직접 못 받는다 → Enter·Esc 는 whisperer.py 전역 키 훅이 창이 떠 있는 동안만 삼켜 press_key 로 넘긴다
    (삼키지 않으면 메모장에서 Enter 가 고른 글을 줄바꿈으로 바꾼다). 바깥 클릭·전경 창 바뀜은 bottom_bar 처럼 POLL_MS 마다 본다.
Tk 메인 스레드에서만 쓴다. is_open 만 훅 스레드가 읽는다(대입 하나라 안전).
"""
import ctypes
import logging
import sys
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageTk

import bottom_bar as _bb

log = logging.getLogger(__name__)

# Paseo confirmBox(client/web.ts:1209-1226) 의 값 — CSS 픽셀, 화면 배율을 곱해 쓴다
BOX_BG = "#1f1f23"
BOX_FG = "#ececec"
BOX_BORDER = "#48484f"
BOX_RADIUS = 10
BOX_W = 380                 # width: min(90vw, 380px)
BOX_W_SCREEN = 0.9
PAD_TOP, PAD_SIDE, PAD_BOTTOM = 18, 18, 14
TEXT_PX = 15
BTN_PX = 14
BTN_PAD_Y, BTN_PAD_X = 7, 14
BTN_RADIUS = 7
BTN_GAP = 8
ROW_GAP = 16                # 글과 버튼 줄 사이(marginTop)
OK_BG, OK_BORDER, OK_FG = "#2563eb", "#3b82f6", "#ffffff"
CANCEL_BORDER, CANCEL_FG = "#55555c", "#dddddd"
POLL_MS = _bb.OUTSIDE_POLL_MS

_IS_WIN = sys.platform == "win32"
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_NOOWNERZORDER = 0x0001, 0x0002, 0x0010, 0x0200
VK_LBUTTON, VK_RBUTTON, VK_MBUTTON = 0x01, 0x02, 0x04


def _rounded_image(root, w, h, r, fill, outline, bg):
    """폭 w·높이 h·반지름 r 둥근 사각형(테두리 1px) 그림. 4배로 그려 줄여 가장자리를 매끄럽게(bottom_bar._pill_image 와 같은 방법)."""
    ss = 4
    big = Image.new("RGB", (w * ss, h * ss), bg)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=r * ss, fill=fill,
                                          outline=outline, width=ss)
    return ImageTk.PhotoImage(big.resize((w, h), Image.LANCZOS), master=root)


class FollowDialog:
    """show() 로 띄우고, 고르면 창을 닫은 뒤 on_choice("follow" | "only" | "cancel") 를 한 번 부른다."""

    def __init__(self, root, message, ok_text, only_text, on_choice):
        self._root = root
        self._on_choice = on_choice
        self._message = message
        self._ok_text = ok_text
        self._only_text = only_text
        self.is_open = False       # 훅 스레드가 읽는다(Enter·Esc 를 삼킬지)
        self._done = False
        self._poll_id = None
        self._hwnd = None
        self._box = None           # 화면 좌표 (left, top, right, bottom)
        self._buttons = {}         # "follow"/"only" → 창 안 좌표 (x0, y0, x1, y1)
        self._images = []          # PhotoImage 참조(놓으면 그림이 사라진다)
        self._fg = None
        self._prev_mouse = False
        self.win = tk.Toplevel(root, **_bb._no_autostyle(tk.Toplevel))
        # ⚠ 처음 화면에 붙기 전에(selection_button.py 함정 3): 숨긴 채 테두리 없음·항상 위
        self.win.withdraw()
        self.win.overrideredirect(True)
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.win.configure(background=BOX_BG, borderwidth=0, highlightthickness=0)
        self._canvas = tk.Canvas(self.win, bg=BOX_BG, bd=0, highlightthickness=0, **_bb._no_autostyle(tk.Canvas))
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<ButtonRelease-1>", self._on_click)

    # ── 약속된 메서드 ──
    def show(self, work_area=None):
        """work_area(left, top, right, bottom) 가운데에 띄운다. 없으면 전경 창의 모니터. 포커스를 뺏지 않는다."""
        if self._done:
            return
        wa = work_area or _bb.foreground_work_area() or (
            0, 0, self._root.winfo_screenwidth(), self._root.winfo_screenheight())
        w, h = self._draw(wa)
        left = wa[0] + max(0, (wa[2] - wa[0] - w) // 2)
        top = wa[1] + max(0, (wa[3] - wa[1] - h) // 2)
        self._box = (left, top, left + w, top + h)
        try:
            self.win.geometry("%dx%d+%d+%d" % (w, h, left, top))
            self.win.update_idletasks()
        except tk.TclError:
            return
        hwnd = _bb._make_tool_window(self.win) if _IS_WIN else None
        if hwnd:
            self._hwnd = hwnd
            _bb._round_corners(hwnd, w, h, self._px(BOX_RADIUS))
            u = ctypes.windll.user32
            u.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            u.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                           SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
        else:
            self.win.deiconify()   # Win32 가 안 되는 환경에서만(포커스를 가져갈 수 있다)
        self.is_open = True
        self._fg = _bb._foreground_hwnd()
        self._prev_mouse = self._mouse_down()
        self._poll_id = self._root.after(POLL_MS, self._poll)

    def press_key(self, key):
        """훅이 삼킨 키(Tk 메인에서): "enter" = 따라 읽기, "esc" = 아무것도 안 읽고 닫기."""
        if key == "enter":
            self._finish("follow")
        elif key == "esc":
            self._finish("cancel")

    def close(self):
        """고르지 않고 닫는다(새 읽기가 시작될 때 등). on_choice 는 부르지 않는다."""
        self._finish(None)

    # ── 안쪽 ──
    def _px(self, css):
        return max(1, int(round(css * self._scale)))

    def _draw(self, wa):
        """상자·글·버튼을 그리고 (폭, 높이) 를 돌려준다."""
        self._scale = _bb._auto_scale(self._root)
        px = self._px
        family = _bb._pick_text_family(self._root)
        f_text = tkfont.Font(root=self._root, family=family, size=-px(TEXT_PX))
        f_btn = tkfont.Font(root=self._root, family=family, size=-px(BTN_PX))
        w = min(px(BOX_W), int((wa[2] - wa[0]) * BOX_W_SCREEN))
        c = self._canvas
        c.delete("all")
        text_id = c.create_text(px(PAD_SIDE), px(PAD_TOP), anchor="nw", text=self._message, fill=BOX_FG,
                                font=f_text, width=w - 2 * px(PAD_SIDE))
        bbox = c.bbox(text_id) or (0, 0, 0, px(TEXT_PX))
        bh = f_btn.metrics("linespace") + 2 * px(BTN_PAD_Y)
        row_y = bbox[3] + px(ROW_GAP)
        h = row_y + bh + px(PAD_BOTTOM)
        c.configure(width=w, height=h)
        self._images = [_rounded_image(self._root, w, h, px(BOX_RADIUS), BOX_BG, BOX_BORDER, BOX_BG)]
        bg_id = c.create_image(0, 0, anchor="nw", image=self._images[0])
        c.tag_lower(bg_id)
        x1 = w - px(PAD_SIDE)
        self._buttons = {}
        # 오른쪽부터: [따라 읽기](기본) 다음 그 왼쪽에 [이 말만 읽기] — Paseo row 순서(cancel, ok)와 같은 모양
        for key, label, fill, border, fg in (("follow", self._ok_text, OK_BG, OK_BORDER, OK_FG),
                                             ("only", self._only_text, BOX_BG, CANCEL_BORDER, CANCEL_FG)):
            bw = f_btn.measure(label) + 2 * px(BTN_PAD_X) + 2
            x0 = x1 - bw
            img = _rounded_image(self._root, bw, bh, px(BTN_RADIUS), fill, border, BOX_BG)
            self._images.append(img)
            c.create_image(x0, row_y, anchor="nw", image=img)
            c.create_text(x0 + bw // 2, row_y + bh // 2, text=label, fill=fg, font=f_btn)
            self._buttons[key] = (x0, row_y, x1, row_y + bh)
            x1 = x0 - px(BTN_GAP)
        try:
            c.configure(cursor="hand2")
        except tk.TclError:
            pass
        return w, h

    def _on_click(self, event):
        for key, (x0, y0, x1, y1) in self._buttons.items():
            if x0 <= event.x < x1 and y0 <= event.y < y1:
                self._finish(key)
                return

    @staticmethod
    def _mouse_down():
        return any(_bb._key_down(vk) for vk in (VK_LBUTTON, VK_RBUTTON, VK_MBUTTON))

    def _poll(self):
        """바깥에서 새로 누른 마우스 → 이 말만 읽기(Paseo 바깥 클릭) · 전경 창 바뀜 → 아무것도 안 읽고 닫기."""
        self._poll_id = None
        if self._done:
            return
        mouse = self._mouse_down()
        pressed = mouse and not self._prev_mouse
        self._prev_mouse = mouse
        if pressed:
            pos = _bb._cursor_pos()
            if pos and self._box and not (self._box[0] <= pos[0] < self._box[2] and self._box[1] <= pos[1] < self._box[3]):
                self._finish("only")
                return
        if _IS_WIN and _bb._foreground_hwnd() != self._fg:
            self._finish("cancel")
            return
        self._poll_id = self._root.after(POLL_MS, self._poll)

    def _finish(self, choice):
        if self._done:
            return
        self._done = True
        self.is_open = False
        if self._poll_id is not None:
            try:
                self._root.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None
        try:
            if self._hwnd:
                ctypes.windll.user32.ShowWindow(self._hwnd, SW_HIDE)
            self.win.destroy()
        except Exception:
            pass
        self._images = []
        if choice is not None:
            try:
                self._on_choice(choice)
            except Exception:
                log.exception("따라 읽기 창 고름 처리 실패")
