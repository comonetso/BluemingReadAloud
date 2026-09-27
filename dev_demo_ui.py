# -*- coding: utf-8 -*-
"""dev_demo_ui.py — 재생 엔진 + 하단 바 + 리더 창을 한데 묶어 "소리 없이" 돌려 보는 개발용 통합 데모.

■ 무엇을 하나
  tts_engine.TtsSession 을 가짜 합성·가짜 출력으로 돌리고, 엔진 알림을 BottomBar·ReaderWindow 에 연결한다.
  그다음 사람이 누르는 것처럼 하단 바 버튼을 차례로 눌러 본다(Tk 안에서만 도는 가짜 클릭 — 운영체제
  마우스 입력은 흉내 내지 않는다).
      재생 → 일시정지 → 재개 → 음소거/해제 → 이전(첫 조각: 처음부터) → 다음 → 이전(3초 안: 이전 조각)
      → 다음 3번 연타(750ms 묶기, 마지막 조각이면 "다음" 꺼짐) → 설정 패널에서 속도 슬라이더 끌기
      → 이전(3초 넘음: 지금 조각 처음부터) → 닫기(X = 정지)
  그리고 단계마다 아래가 서로 맞는지 스스로 확인하고 PASS/FAIL 을 찍는다.
      - 하단 바 상태(재생 버튼 모양)·시간·진행선  ↔  엔진이 계산한 상태·경과·진행률
      - 리더 창 형광펜 위치                         ↔  엔진이 알린 조각 번호의 원문 구간
      - 실제로 "재생되는" 소리가 어느 조각인가        ↔  형광펜 조각 (가짜 소리 샘플 값에 조각 번호를 심어 둠)
      - 바·패널·말풍선·리더 창에 WS_EX_NOACTIVATE|TOOLWINDOW|TOPMOST 가 붙었는가 (GetWindowLongW)
      - 전경 창이 우리 창으로 바뀌지 않았는가, 우리 창에 FocusIn 이 오지 않았는가
      - 정지 뒤: 바·리더 창이 숨었는가, 스트림을 abort 했는가, 재생·합성 스레드가 끝났는가(좀비 없음)
  --shots 폴더를 주면 단계마다 화면(하단 바 가운데 ~ 리더 창)을 찍어 ui_NN_이름.png 로 저장한다.

■ 쓰는 법
      python -B dev_demo_ui.py [--shots 폴더]
  15초 안에 스스로 끝난다(감시 타이머가 14.5초에 강제 종료). 모두 통과하면 종료 코드 0, 아니면 1.

■ 절대 하지 않는 것 (무인 실행 규칙)
  - whisperer.py 를 import·실행하지 않는다(트레이·전역 키보드 훅이 뜬다). 그래서 whisperer.py 의 연결부
    (_handle_tts_event / _on_bar_command)를 여기 DemoGlue 에 **같은 순서로 따로 옮겨** 두었다.
    whisperer.py 연결부를 고치면 여기도 맞춰야 한다.
  - 스피커로 소리를 내지 않는다: 출력은 FakeStream(장치를 열지 않음), 비프음(before_play)도 넘기지 않는다.
  - Google TTS 를 부르지 않는다: 합성은 fake_synthesize(글자 수에 비례한 길이의 가짜 샘플).
  - 다른 프로그램에 UI Automation 을 조회하지 않는다. 운영체제 입력(SendInput)도 흉내 내지 않는다.

■ 함정 메모
  - 엔진 알림은 재생 스레드에서 온다. Tk 는 스레드 안전하지 않으므로 queue 에 넣고, Tk 메인 스레드가
    100ms 마다 꺼내 처리한다(whisperer.py check_gui_queue 와 같은 주기·구조). 확인 단계(checkpoint)는
    확인 직전에 큐를 한 번 더 비워서 "가장 최신 알림"이 화면에 반영된 상태를 본다.
  - 시간 확인은 실제 시계(time.monotonic)로 한다. 이 PC 가 바쁘면 조금 늦을 수 있어 허용 오차를 둔다.
"""

import os
import sys

sys.dont_write_bytecode = True   # 프로젝트 폴더에 __pycache__ 를 새로 만들지 않게(python -B 와 같은 효과)

import argparse
import ctypes
import logging
import queue
import re
import threading
import time

_T_PROC = time.monotonic()       # 프로세스 시작 시각(준비에 걸린 시간 보고용)

# ── 감시 타이머: 무슨 일이 있어도 14.5초 뒤에는 프로세스를 끝낸다(무인 실행에서 창이 남지 않게) ──
WATCHDOG_SEC = 14.5
_watchdog = threading.Timer(WATCHDOG_SEC, lambda: (print("[demo] 감시 타이머: 시간 초과로 강제 종료", flush=True),
                                                   os._exit(3)))
_watchdog.daemon = True          # 정상 종료를 막지 않게
_watchdog.start()

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np                    # noqa: E402
import tkinter as tk                  # noqa: E402

import bottom_bar                     # noqa: E402
import messages                       # noqa: E402
import reader_window                  # noqa: E402
import readaloud_text                 # noqa: E402
import tts_engine                     # noqa: E402

_IS_WIN = sys.platform == "win32"

# ════════════════════════════════════════════════════════════════════
# 데모 값 (전부 이 데모에서 정한 값 — 앱 동작 규칙이 아니다)
# ════════════════════════════════════════════════════════════════════
SEC_PER_CHAR = 0.07       # 가짜 소리 길이 = 공백 뺀 글자 수 × 0.07초 ÷ 속도 (보통 한국어 낭독 빠르기쯤)
FIRST_SYNTH_DELAY = 1.00  # 첫 조각 합성 대기(네트워크 흉내). 이 사이 바는 "계산 중" 이어야 한다
                          # (첫 표시에 수백 ms 가 걸릴 수 있어 넉넉히 — 0.4 로 했더니 확인이 늦어 이미 추정이 나왔다)
SYNTH_DELAY = 0.10        # 그 뒤 조각 합성 대기
GUI_POLL_MS = 100         # whisperer.py check_gui_queue 주기와 같게

# 원문 — 윈도우 클립보드처럼 CRLF. 줄마다 공백 뺀 UTF-8 60바이트(한글 20자)를 넘겨야 짧은 줄 합치기
# (readaloud_text / 확장 speech.js:440-491)에 걸리지 않고 한 줄 = 한 조각이 된다.
# 첫 줄은 이모지를 넣어 리더 창의 "이모지 = Tk 2칸" 보정(reader_window.TkTextOffsets)도 함께 본다.
DEMO_TEXT = "\r\n".join([
    "블루밍 리더 창 통합 데모의 첫 번째 줄입니다 😀 이 줄은 일부러 길게 써서 일시정지와 재개와 처음부터 다시 읽기를 모두 이 줄 안에서 확인합니다.",
    "두 번째 줄은 다음 버튼을 눌렀을 때 형광펜이 이 줄로 옮겨 오는지 보는 줄입니다.",
    "세 번째 줄에는 README.md 와 VS Code 같은 영어 단어가 섞여 있어요, 연타하면 건너뜁니다.",
    # 마지막 줄은 길게: 이 줄이 정해진 지 3초가 지난 뒤 "이전"을 눌러 "지금 조각 처음부터"(3초 규칙)를 본다
    "네 번째 줄은 마지막 줄이라서 여기까지 오면 다음 버튼이 회색으로 꺼져야 하고, 삼 초가 지난 뒤 이전을 누르면 이 줄을 처음부터 다시 읽어야 합니다.",
])

# 각 단계에서 기대하는 것. (시각 ms, 이름, 할 일)  — 시각은 session.start() 부터 잰다.
# 기대값 근거: 3초 규칙·750ms 묶기 = 확장 speech.js:35-36, 202-213 (tts_engine.RESTART_AFTER, MOVE_DELAY)
TIMELINE = [
    (200,  "cp",    "start",         dict(state="PLAYING", hl=0, calc=True)),
    (1150, "cp",    "playing",       dict(state="PLAYING", hl=0, audio=0)),
    (1250, "click", "play",          None),                                   # 일시정지
    (1700, "cp",    "paused",        dict(state="PAUSED", hl=0, frozen=True)),
    (2000, "click", "play",          None),                                   # 재개
    (2400, "cp",    "resumed",       dict(state="PLAYING", hl=0, audio=0)),
    (2500, "click", "mute",          None),                                   # 음소거
    (2800, "cp",    "muted",         dict(state="PLAYING", hl=0, muted=True)),
    (2900, "click", "mute",          None),                                   # 음소거 해제
    (3200, "click", "prev",          None),   # 첫 조각에서 이전 = 처음부터(기다리지 않음, 확장 document.js:332-339)
    (3600, "cp",    "restart",       dict(state="PLAYING", hl=0, audio=0, restart=True, muted=False)),
    (3700, "click", "next",          None),   # 다음 → 형광펜은 바로 1, 소리는 750ms 뒤
    (3900, "cp",    "next_pending",  dict(state="PLAYING", hl=1, audio=0)),
    (4900, "cp",    "next",          dict(state="PLAYING", hl=1, audio=1)),
    (5100, "click", "prev",          None),   # 조각 1 이 정해진 지 3초 안 됨 → 이전 조각(0)
    (6300, "cp",    "prev",          dict(state="PLAYING", hl=0, audio=0)),
    (6400, "click", "next",          {"mark": "burst_first"}),   # 연타 3번 → 목표만 3까지 옮기고 이동은 마지막 누름 750ms 뒤 한 번
    (6550, "click", "next",          None),
    (6700, "click", "next",          None),
    # 연타로 목표가 마지막 조각(3)이 되면 소리는 아직 조각 0 이어도 "다음" 은 곧바로 꺼진다(can_next 는 목표 기준).
    # 확인은 마지막 누름 0.35초 뒤: 재생 스레드는 0.1초 블록을 쓰는 사이에만 알림을 보내고(tts_engine BLOCK_SAMPLES),
    # 화면은 100ms 마다 큐를 비우므로 형광펜이 옮겨지기까지 최대 약 0.2초 걸린다(0.09초 뒤 확인했다가 실패한 적 있음).
    (7050, "cp",    "burst_pending", dict(state="PLAYING", hl=3, audio=0, next_enabled=False)),
    (7900, "cp",    "last",          dict(state="PLAYING", hl=3, audio=3, next_enabled=False, burst=True)),
    (8100, "click", "settings",      None),   # 설정 패널 열기
    (8400, "drag",  "rate",          0.5),    # 속도 슬라이더를 가운데(1.00x)에서 0.5 칸(=3^0.5=1.732x)으로 끌고 뗌 → setRate 한 번
    (8700, "cp",    "panel",         dict(state="PLAYING", hl=3, audio=3, next_enabled=False, panel=True)),
    (8800, "click", "settings",      None),   # 패널 닫기
    # 조각 3 은 마지막 연타(6.7초)에 정해졌다 → 9.95초면 3초가 넘었다 → 이전 = 지금 조각(3) 처음부터(확장 speech.js:206)
    (9950, "click", "prev",          None),
    (10400, "cp",   "restart_last",  dict(state="PLAYING", hl=3, audio=3, restart=True, next_enabled=False)),
    # 읽는 도중 새 읽기(단축키로 다른 글을 읽힘): 앞 세션 정지 → 새 세션. 바는 hide 없이 show 만 다시 불린다
    # (앞 세션의 늦은 STOPPED·session_end 는 "옛 세션 알림"이라 버려진다) → 진행선·상태가 새로 시작해야 한다
    (10600, "newread", "second",     None),
    (11100, "cp",   "new_reading",   dict(state="PLAYING", hl=0, calc=True, new_reading=True)),
    (11300, "click", "close",        None),   # 닫기(X) = 읽기 중지 + 바 숨김
    (11800, "cp",   "stopped",       dict(bar_visible=False, reader_visible=False, stopped=True)),
    (12100, "end",  "finish",        None),
]

# 읽는 도중 새로 시작하는 두 번째 읽기(한 줄이 한 조각이 되게 20자 넘게)
SECOND_TEXT = "\r\n".join([
    "두 번째 읽기입니다. 앞 읽기가 끝나기 전에 새로 시작했으니 진행선과 시간은 처음부터 다시 흘러야 합니다.",
    "이 줄은 두 번째 읽기의 둘째 줄이고, 데모는 여기까지 읽기 전에 닫기 버튼으로 끝납니다.",
])


# ════════════════════════════════════════════════════════════════════
# 가짜 부품 — 소리를 내지 않는다
# ════════════════════════════════════════════════════════════════════

class FakeStream:
    """가짜 출력 스트림(sd.OutputStream 흉내). 장치를 열지 않으므로 소리가 절대 나지 않는다.

    실제 장치처럼 "쓴 소리 길이만큼 실제 시간이 흐르게" write 를 막는다 → 하단 바 시계와 엔진 경과가
    실제 시간으로 맞는지 볼 수 있다. 막는 동안 20ms 마다 abort 를 확인해서, 엔진 stop() 의 abort 가
    블로킹 write 를 곧바로 풀어 주는지도 실제처럼 확인된다(함정: 정지는 sd.stop() 이 아니라 abort 로).
    쓴 블록마다 (재생 시작 시각, 샘플 수, 샘플 값) 을 기록한다. 샘플 값에는 조각 번호가 심겨 있다(fake_synthesize).
    시각은 write 가 "시작된" 때다 → 마지막 기록 = 지금 장치에서 나가고 있는 블록.
    """

    def __init__(self, sample_rate):
        self.sr = sample_rate
        self.calls = []                       # start/stop/abort/close 부른 순서
        self.blocks = []                      # (재생 시작 monotonic 시각, 샘플 수, 첫 샘플 값)
        self._aborted = threading.Event()
        self._t_end = None                    # 지금까지 쓴 소리가 "다 재생되는" 시각
        self._lock = threading.Lock()

    def start(self):
        self.calls.append("start")

    def write(self, block):
        if self._aborted.is_set():
            raise RuntimeError("aborted")
        n = len(block)
        value = int(block[0]) if n else 0
        now = time.monotonic()
        # 일시정지로 쓰기가 멈췄다가 다시 오면(장치는 그동안 무음) 지금부터 다시 센다
        if self._t_end is None or self._t_end < now:
            self._t_end = now
        with self._lock:
            self.blocks.append((self._t_end, n, value))   # 이 블록이 나가기 시작하는 시각
        self._t_end += n / float(self.sr)
        while True:
            left = self._t_end - time.monotonic()
            if left <= 0:
                break
            if self._aborted.wait(min(left, 0.02)):
                raise RuntimeError("aborted")

    def stop(self):
        self.calls.append("stop")

    def abort(self):
        self.calls.append("abort")
        self._aborted.set()

    def close(self):
        self.calls.append("close")

    def last_value(self, since=None):
        """가장 최근에 쓴 블록의 샘플 값(since 뒤에 쓴 것만). 없으면 None."""
        with self._lock:
            for t, _n, v in reversed(self.blocks):
                if since is None or t >= since:
                    return v
                break
        return None

    def values_between(self, t0, t1):
        with self._lock:
            return [v for t, _n, v in self.blocks if t0 <= t <= t1]


def make_fake_synthesize(texts, synth_log, t0_box):
    """가짜 합성 함수 synthesize(text, rate) 를 만든다 (tts_engine.make_google_synthesize 자리).

    소리 길이 = 공백 뺀 글자 수 × SEC_PER_CHAR ÷ 속도. 샘플 값은 (조각 번호 + 1) × 100 으로 채운다.
      → 출력 쪽에서 "지금 어느 조각 소리가 나가고 있나"를 샘플 값만 보고 알 수 있다.
      → 음소거면 엔진이 게인 0 을 곱하므로 값이 0 이 된다(음소거 확인).
    이 값은 FakeStream 에만 들어가고 장치로는 가지 않는다(소리 없음).
    합성 요청마다 (시작 시각, 조각 번호) 를 synth_log 에 남긴다 — 연타 때 중간 조각을 합성하지 않는지 확인용.
    """
    index_of = {}
    for i, t in enumerate(texts):
        index_of.setdefault(t, i)
    first = {"done": False}

    def synthesize(text, rate):
        idx = index_of.get(text, -1)
        t0 = t0_box.get("t0") or time.monotonic()
        synth_log.append((time.monotonic() - t0, idx))
        time.sleep(SYNTH_DELAY if first["done"] else FIRST_SYNTH_DELAY)
        first["done"] = True
        sec = tts_engine.count_spoken_chars(text) * SEC_PER_CHAR / max(float(rate or 1.0), 0.01)
        return np.full(max(int(sec * tts_engine.SAMPLE_RATE), 1), (idx + 1) * 100, dtype=np.int16)

    return synthesize


# ════════════════════════════════════════════════════════════════════
# 엔진 ↔ 하단 바·리더 창 연결 (whisperer.py 연결부를 같은 순서로 옮긴 것)
# ════════════════════════════════════════════════════════════════════

class DemoGlue:
    """whisperer.py _handle_tts_event / _on_bar_command / _show_reader_window 와 같은 순서로 부른다.

    ⚠ 이 클래스의 메서드는 전부 Tk 메인 스레드에서만 불린다. 엔진 알림(on_event)은 재생 스레드에서 오므로
      queue 에만 넣고(push), Tk 메인의 pump() 가 꺼내 처리한다(whisperer.py gui_queue → check_gui_queue).
    """

    def __init__(self, root, bar, reader, work_area):
        self.root = root
        self.bar = bar
        self.reader = reader
        self.work_area = work_area
        self.session = None              # 지금 읽기 세션 (whisperer.py tts_session)
        self.q = queue.Queue()
        self.events = []                 # (시각, kind, 요약) — 지금 세션 알림만, 보고용
        self.ignored = []                # 옛 세션이 늦게 보낸 알림(버림) — (kind, 요약)
        self.last_segment = None         # 마지막으로 받은 형광펜 조각 번호 (whisperer.py _reading_segment_idx)
        self.commands = []               # 하단 바가 보낸 명령
        self.took = {}                   # 알림 종류 → (가장 오래 걸린 처리 시간, 횟수)

    def make_on_event(self, box):
        """세션 하나의 on_event 를 만든다(whisperer.py _make_tts_event_handler 와 같은 모양).

        box["session"] 에 그 세션이 들어간다. 재생 스레드에서 불리므로 UI 를 만지지 않고 큐에만 넣는다.
        """
        def on_event(kind, data):
            self.q.put((box, kind, data))
        return on_event

    def begin(self, session):
        """(Tk 메인) 새 읽기를 지금 세션으로 삼는다 — whisperer.py speak_text 의
        `_reading_segment_idx = None` → `tts_session = session` 과 같은 순서(start() 전에 불러야 한다)."""
        self.last_segment = None
        self.session = session

    def pump(self):
        """(Tk 메인) 큐에 쌓인 엔진 알림을 모두 처리한다."""
        while True:
            try:
                box, kind, data = self.q.get_nowait()
            except queue.Empty:
                return
            self.handle(box.get("session"), kind, data)

    def handle(self, session, kind, data):
        """(Tk 메인) whisperer.py _handle_tts_event 와 같은 처리. 처리마다 걸린 시간을 재 둔다(UI 가 버벅이는지 보려고).

        지금 세션의 알림만 처리한다. 새 읽기가 앞 읽기를 대신한 뒤 도착한 옛 세션 알림(특히 STOPPED·session_end)은
        버린다 — 안 그러면 새 읽기의 바·리더 창을 옛 세션이 숨긴다(whisperer.py 와 같은 규칙).
        """
        if session is None or session is not self.session:
            self.ignored.append((kind, data.get("state") if isinstance(data, dict) and "state" in data else None))
            return
        t = time.monotonic()
        try:
            self._handle(kind, data, t)
        finally:
            took = time.monotonic() - t
            prev = self.took.get(kind, (0.0, 0))
            self.took[kind] = (max(prev[0], took), prev[1] + 1)

    def _handle(self, kind, data, t):
        if kind == "session_start":
            self.events.append((t, kind, len(data.get("segments") or [])))
            # 바를 먼저 띄우고(show), 리더 창은 원문을 넣은 뒤(start) 바 높이만큼 위에 띄운다(show)
            self.bar.show(self.work_area)
            self.reader.start(data["source_text"], data["segments"])
            self.reader.show(self.work_area, self.bar.height, geometry=None)
            if self.last_segment is not None:
                self.reader.highlight(self.last_segment)
        elif kind == "segment":
            self.events.append((t, kind, data))
            self.last_segment = data
            self.reader.highlight(data)
        elif kind == "state":
            self.events.append((t, kind, data.get("state")))
            self.bar.update(data)
        elif kind == "session_end":
            self.events.append((t, kind, None))
            self.bar.hide()
            self.reader.end()
            self.last_segment = None
            self.session = None          # whisperer.py: tts_session = None

    def on_command(self, cmd, value=None):
        """(Tk 메인) 하단 바 버튼 → 엔진 (whisperer.py _on_bar_command 와 같음. 설정 저장만 뺐다)."""
        self.commands.append((time.monotonic(), cmd, value))
        if cmd == "stop":
            self.bar.hide()
            if self.session is not None:
                self.session.stop()
            return
        if self.session is not None:
            self.session.command(cmd, value)


# ════════════════════════════════════════════════════════════════════
# Win32 확인 도구 (읽기만 — 우리 프로세스 창의 스타일과 전경 창만 본다)
# ════════════════════════════════════════════════════════════════════

WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
NEED_EX = WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST

if _IS_WIN:
    from ctypes import wintypes
    # ⚠ 공용 ctypes.windll.user32 에 형 선언을 걸지 않으려고 따로 불러온다(bottom_bar.py 와 같은 이유)
    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _u32.GetWindowLongW.restype = ctypes.c_long
    _u32.GetForegroundWindow.argtypes = []
    _u32.GetForegroundWindow.restype = wintypes.HWND
    _u32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _u32.SetForegroundWindow.restype = wintypes.BOOL
    _u32.GetActiveWindow.argtypes = []
    _u32.GetActiveWindow.restype = wintypes.HWND
    _u32.IsWindowVisible.argtypes = [wintypes.HWND]
    _u32.IsWindowVisible.restype = wintypes.BOOL
    _u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _u32.GetWindowRect.restype = wintypes.BOOL


def ex_style(hwnd):
    """창의 확장 스타일(GWL_EXSTYLE) 값. 읽을 수 없으면 None."""
    if not (_IS_WIN and hwnd):
        return None
    return _u32.GetWindowLongW(hwnd, -20) & 0xFFFFFFFF


def fg_hwnd():
    return _u32.GetForegroundWindow() if _IS_WIN else None


def hwnd_int(h):
    """HWND(c_void_p 값 또는 int) → 비교용 정수."""
    if h is None:
        return 0
    return int(getattr(h, "value", h) or 0)


# ════════════════════════════════════════════════════════════════════
# 본체
# ════════════════════════════════════════════════════════════════════

def main(argv):
    ap = argparse.ArgumentParser(description="엔진 + 하단 바 + 리더 창 통합 데모(소리 없음)")
    ap.add_argument("--shots", default=None, help="단계별 캡처 저장 폴더(없으면 캡처 안 함)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    if args.shots:
        os.makedirs(args.shots, exist_ok=True)

    # ── 1) 앱과 같은 루트: ttkbootstrap Window(DPI 인식 + tk 위젯 자동 스타일 패치) 를 숨겨서 ──
    try:
        import ttkbootstrap as ttkb
        root = ttkb.Window(themename="cosmo")
    except Exception:
        if _IS_WIN:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        root = tk.Tk()
    root.withdraw()
    # Tk 는 앱의 "첫 창 틀"에 SetActiveWindow 를 해서 이 순간 (숨긴) 루트가 전경을 가져갈 수 있다.
    # 앱 시작 때 원래 일어나는 일이고 바·리더 창과는 무관 → 가져갔으면 원래 창에 돌려준다(reader_window 데모와 같음).
    orig_fg = fg_hwnd()
    root.update_idletasks()
    root.update()
    if _IS_WIN and orig_fg and hwnd_int(fg_hwnd()) != hwnd_int(orig_fg):
        _u32.SetForegroundWindow(orig_fg)
        root.update()
    fg0 = fg_hwnd()

    get_msg = lambda key, *a: messages.get_message(key, *a, language="ko")   # noqa: E731

    # ── 2) 조각 나누기 (whisperer.py speak_text 와 같은 호출) ──
    words = None
    wpath = os.path.join(HERE, "data", "english-words.js")
    if os.path.exists(wpath):
        words = readaloud_text.load_english_words(wpath)
    # ── 3) 하단 바·리더 창 (앱처럼 Tk 메인에서 한 번 만든다) ──
    work_area = bottom_bar.foreground_work_area() or (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
    glue = None
    bar = bottom_bar.BottomBar(root, lambda cmd, value=None: glue.on_command(cmd, value), get_msg)
    reader = reader_window.ReaderWindow(root, get_msg, on_geometry_changed=None)
    glue = DemoGlue(root, bar, reader, work_area)
    print("[demo] work_area=%s bar.height=%d scale=%.3f" % (work_area, bar.height, bar._s), flush=True)

    # 우리 창에 FocusIn 이 오면 기록(포커스를 뺏었다는 뜻)
    focus_hits = []
    for w in (bar._win, bar._panel, bar._tip, reader.win):
        w.bind("<FocusIn>", lambda e: focus_hits.append(str(e.widget)), add="+")

    # ── 4) 엔진 (가짜 합성·가짜 출력, 비프음 없음) ──
    synth_log = []
    t0_box = {}
    streams = []

    def open_stream():
        s = FakeStream(tts_engine.SAMPLE_RATE)
        streams.append(s)
        return s

    # 지금 읽기(세션)와 그 조각들. 읽는 도중 새 읽기를 시작하면(new_reading) 통째로 바뀐다 → 확인 코드는 늘 cur 를 본다
    cur = {}

    def new_session(text):
        """whisperer.py speak_text 와 같은 순서로 세션을 만든다(아직 start 하지 않음).

        조각 나누기 → 세션 생성(previous=앞 세션: 새 세션은 앞 세션의 재생 스레드가 스트림을 닫을 때까지 기다린다).
        """
        segs = readaloud_text.split_for_reading(text, "ko-KR", "ko-KR", words)
        texts = [s["text"] for s in segs]
        durs = [tts_engine.count_spoken_chars(t) * SEC_PER_CHAR for t in texts]
        print("[demo] 조각 %d개, 가짜 소리 길이(초): %s" % (len(segs), ", ".join("%.2f" % d for d in durs)), flush=True)
        for i, s in enumerate(segs):
            print("   #%d src=%s~%s text=%r" % (i, s["src_start"], s["src_end"], s["text"][:50]), flush=True)
        box = {}
        s = tts_engine.TtsSession(
            text, segs, make_fake_synthesize(texts, synth_log, t0_box), open_stream, glue.make_on_event(box),
            rate=1.0, volume=1.0, muted=False, before_play=None, previous=cur.get("s"),
            log=lambda msg: None)
        box["session"] = s
        return {"s": s, "segs": segs, "text": text, "durs": durs}

    cur.update(new_session(DEMO_TEXT))
    glue.begin(cur["s"])

    results = []          # (이름, 통과?, 설명 목록)
    shots = []            # (이름, 파일)
    marks = {}            # 단계 이름 → 그 순간의 monotonic 시각 (소리 확인 구간용)

    def our_hwnds():
        hs = [bar._hwnd, bar._panel_hwnd, bar._tip_hwnd, reader_window._wrapper_hwnd(reader.win)]
        return {hwnd_int(h) for h in hs if h}

    # ── 확인 도구 ──
    def highlighted_lines():
        r = reader.text.tag_ranges(reader_window._HL_TAG)
        return [reader.text.get(r[k], r[k + 1]) for k in range(0, len(r), 2)]

    def squash(s):
        return re.sub(r"\s+", "", s or "")

    def stretched_ends():
        """칠한 구간 중 "마지막 글자가 공백이고 그 공백이 글 상자 오른쪽 끝까지 늘어난" 것의 Tk 인덱스 목록.

        Tk 는 자동 줄바꿈으로 접히는 자리의 공백을 오른쪽 끝까지 늘려 그린다 → 거기 칠하면 형광펜이 뻗어 보인다
        (reader_window._trim_wrap_spaces 가 막는 것). 화면 밖 글자는 bbox 가 없어 볼 수 없다.
        """
        t = reader.text
        r = t.tag_ranges(reader_window._HL_TAG)
        right = t.winfo_width() - int(t.cget("padx")) - 2
        out = []
        for k in range(0, len(r), 2):
            a = str(r[k])
            for n, ch in enumerate(t.get(r[k], r[k + 1])):     # 칠한 구간 안의 모든 공백을 본다(가운데 접힘 포함)
                if ch not in " \t　":
                    continue
                idx = t.index("%s + %d chars" % (a, n))
                bb = t.bbox(idx)
                if bb and bb[0] + bb[2] >= right:
                    out.append(idx)
        return out

    def expected_lines(idx):
        s = cur["segs"][idx]
        if s["src_start"] is None:
            return []
        whole = cur["text"][s["src_start"]:s["src_end"]].replace("\r\n", "\n")
        return [p for p in whole.split("\n") if p]

    def engine_snapshot():
        # 엔진 내부 계산을 그대로 빌린다(개발용 데모라 비공개 메서드를 읽기만 한다)
        s = cur["s"]
        with s._cond:
            return s._snapshot_locked(s._clock())

    def reader_visible_rect():
        hwnd = reader_window._wrapper_hwnd(reader.win)
        if not hwnd:
            return None
        m = reader_window._frame_metrics(hwnd)
        r = reader_window._get_rect(_u32.GetWindowRect, hwnd)
        if not (m and r):
            return None
        inv = m[0]
        return (r[0] + inv[0], r[1] + inv[1], r[2] - inv[2], r[3] - inv[3])

    last_reader_rect = {"r": None}

    def grab(name):
        if not args.shots:
            return
        try:
            from PIL import ImageGrab
            root.update()
            left, top, right, bottom = work_area
            rr = reader_visible_rect() if reader.is_visible() else None
            if rr:
                last_reader_rect["r"] = rr
            rr = rr or last_reader_rect["r"]
            bbox = bar._canvas.bbox(bar._time_el)
            x0 = left + (bbox[0] if bbox else bar._w // 2 - 400) - 20
            if rr:
                x0 = min(x0, rr[0])
            y0 = (rr[1] if rr else bottom - bar.height) - 6
            box = (max(left, x0), max(top, y0), right, bottom)
            path = os.path.join(args.shots, "ui_%02d_%s.png" % (len(shots), name))
            ImageGrab.grab(bbox=box, all_screens=True).save(path)
            shots.append((name, path))
        except Exception as e:
            print("[demo] 캡처 실패(%s): %s" % (name, e), flush=True)

    def checkpoint(name, exp):
        """한 단계 확인. exp 의 키만 확인한다.

        확인 코드 자체가 예외를 내도(예: 바가 안 숨었는데 상태 값을 읽으려다) 그 단계를 "통과"로 흘리지 않도록
        예외를 FAIL 로 기록한다. (대조군 실험에서 예외로 단계가 통째로 빠져 통과처럼 보인 적이 있다)
        """
        notes = []
        try:
            ok = _checkpoint_body(name, exp, notes)
        except Exception as e:
            import traceback
            ok = False
            notes.append("FAIL 확인 중 예외: %r" % e)
            notes.append("     " + traceback.format_exc().strip().splitlines()[-2].strip())
        try:
            grab(name)
        except Exception:
            pass
        results.append((name, ok, notes))
        t = marks.get(name, time.monotonic()) - t0_box["t0"]
        print("[cp] %-14s %s  t=%.2fs" % (name, "PASS" if ok else "FAIL", t), flush=True)
        for n in notes:
            print("      " + n, flush=True)

    def _checkpoint_body(name, exp, notes):
        glue.pump()                        # 가장 최신 알림을 화면에 반영
        root.update_idletasks()
        now = time.monotonic()
        marks[name] = now
        ok = True

        def check(cond, msg):
            nonlocal ok
            if not cond:
                ok = False
            notes.append(("OK  " if cond else "FAIL") + " " + msg)

        bar_visible = exp.get("bar_visible", True)
        reader_visible = exp.get("reader_visible", True)
        check(bar._visible == bar_visible, "하단 바 보임=%s (기대 %s)" % (bar._visible, bar_visible))
        check(reader.is_visible() == reader_visible, "리더 창 보임=%s (기대 %s)" % (reader.is_visible(), reader_visible))

        if "state" in exp:
            eng = cur["s"].state
            last = (bar._last or ({},))[0].get("state")
            check(eng == exp["state"], "엔진 상태=%s (기대 %s)" % (eng, exp["state"]))
            check(last == exp["state"] and bar._play_state == exp["state"],
                  "바 상태=%s·재생버튼=%s (기대 %s)" % (last, bar._play_state, exp["state"]))
        if "hl" in exp:
            got, want = highlighted_lines(), expected_lines(exp["hl"])
            check(glue.last_segment == exp["hl"], "형광펜 알림 조각=%s (기대 %s)" % (glue.last_segment, exp["hl"]))
            # 리더 창은 줄바꿈 글자와 "자동으로 접히는 자리의 공백"을 칠하지 않는다(reader_window._paint) →
            # 공백을 뺀 글끼리 비교하고, 칠한 조각에 줄바꿈이 섞이지 않았는지 본다.
            same = squash("".join(got)) == squash("".join(want)) and not any("\n" in g for g in got)
            check(same, "리더 창 칠한 글 = 조각 %d 원문 (칠한 조각 %d개)%s" %
                  (exp["hl"], len(got), "" if same else " (칠함 %r)" % got))
            # 접히는 자리 공백이 칠해져 형광펜이 창 오른쪽 끝까지 뻗었나(화면에 보이는 것만 볼 수 있다)
            stretched = stretched_ends()
            check(not stretched, "형광펜이 접힌 자리 공백으로 오른쪽 끝까지 뻗지 않음 %s" % stretched)
        if "audio" in exp and streams:
            v = streams[-1].last_value(since=now - 0.25)
            playing = (v // 100 - 1) if v else None
            check(playing == exp["audio"], "지금 나가는 소리 = 조각 %s (기대 %s)" % (playing, exp["audio"]))
        if bar._visible and bar._last:
            snap = engine_snapshot()
            shown_el, shown_tot, _ = bar._displayed_time()
            diff = abs(shown_el - snap["elapsed"])
            # 허용 오차: 보통 0.6초. 첫 소리를 기다리는 동안(calc)은 바가 PLAYING 이라 스스로 시계를 돌리고
            # 엔진은 1초마다 상태를 다시 보내 바로잡으므로 최대 1초까지 벌어질 수 있다(확장 displayedTime 과 같은 동작)
            tol = 1.05 if exp.get("calc") else 0.6
            check(diff <= tol, "바 경과 %.2fs ↔ 엔진 %.2fs (차 %.2f ≤ %.2f)" % (shown_el, snap["elapsed"], diff, tol))
            fill = bar._fill_target / float(max(bar._w, 1))
            check(abs(fill - snap["progress"]) <= 0.05,
                  "진행선 %.3f ↔ 엔진 progress %.3f" % (fill, snap["progress"]))
            tot_text = bar._canvas.itemcget(bar._time_tot, "text")
            el_text = bar._canvas.itemcget(bar._time_el, "text")
            if exp.get("calc"):
                check(snap["total"] is None and "계산 중" in tot_text, "총 시간 '계산 중' 표시: %r" % tot_text)
            else:
                check(snap["total"] is not None and "약" in tot_text, "총 시간 추정 표시: %r (엔진 %.2f)" %
                      (tot_text, snap["total"] or -1))
            notes.append("     표시: %s%s" % (el_text, tot_text))
            if exp.get("restart") and "hl" in exp:
                # 처음부터 다시 읽었으면 "이 조각 안에서 흐른 시간"이 짧아야 한다(0.8초 = 누른 뒤 확인까지 0.4초 + 여유)
                in_seg = snap["elapsed"] - sum(cur["durs"][:exp["hl"]])
                check(in_seg <= 0.8, "처음부터 다시: 조각 %d 안 경과 %.2fs ≤ 0.8" % (exp["hl"], in_seg))
            if exp.get("frozen"):
                # 일시정지면 바가 1초 시계를 멈추고(tick 예약 없음), 엔진은 소리를 쓰지 않아야 한다
                quiet = streams[-1].values_between(now - 0.3, now) if streams else []
                check("tick" not in bar._jobs and not quiet,
                      "일시정지 중 바 시계 멈춤(tick 예약 %s)·최근 0.3초 쓴 블록 %d개" % ("tick" in bar._jobs, len(quiet)))
            nav = exp.get("state") in ("PLAYING", "PAUSED")
            check(bar._buttons["prev"].enabled == nav, "이전 버튼 활성=%s" % bar._buttons["prev"].enabled)
            want_next = exp.get("next_enabled", nav)
            check(bar._buttons["next"].enabled == want_next, "다음 버튼 활성=%s (기대 %s)" %
                  (bar._buttons["next"].enabled, want_next))
        if "muted" in exp:
            check(cur["s"].muted == exp["muted"] and bar._muted == exp["muted"],
                  "음소거 엔진=%s 바=%s (기대 %s)" % (cur["s"].muted, bar._muted, exp["muted"]))
            if streams:
                vals = streams[-1].values_between(now - 0.15, now)
                if exp["muted"]:
                    check(bool(vals) and all(v == 0 for v in vals), "음소거 중 쓴 블록 값이 전부 0 (%d개)" % len(vals))
                else:
                    check(bool(vals) and all(v != 0 for v in vals), "해제 뒤 쓴 블록 값이 0 아님 (%d개)" % len(vals))
        if exp.get("burst"):
            t_burst = marks_click.get("burst_first")
            later = [(t, i) for t, i in synth_log if t_burst is not None and t >= t_burst]
            check(later and all(i == 3 for _, i in later),
                  "연타 뒤 합성 요청은 조각 3 하나뿐: %s" % [(round(t, 2), i) for t, i in later])
        if exp.get("new_reading"):
            # 새 읽기: 바는 진행선 0 에서, 리더 창은 새 원문으로, 앞 세션은 스레드까지 끝났어야 한다
            fill_now = bar._fill_drawn / float(max(bar._w, 1))
            check(before_new.get("fill", 0) > 0.3 and fill_now <= 0.02,
                  "진행선이 앞 읽기 위치 %.3f 에서 0 으로 새로 시작 (지금 %.3f)" % (before_new.get("fill", 0), fill_now))
            shown_text = reader.text.get("1.0", "end-1c")
            check(shown_text == cur["text"].replace("\r\n", "\n"), "리더 창에 새 원문이 들어감")
            prev = cur.get("prev")
            check(prev is not None and prev.join(2.0), "앞 세션 스레드 종료")
            old_calls = before_new["stream"].calls if before_new.get("stream") else []
            check("abort" in old_calls, "앞 세션 스트림 abort %s" % old_calls)
            late = [k for k, _ in glue.ignored]
            check("session_end" in late, "앞 세션의 늦은 알림은 버려짐 %s" % late)
        if exp.get("panel"):
            # 설정 패널: 떠 있고, 슬라이더를 뗀 값이 엔진 속도가 되었고, 패널 글자도 그 값인가
            want = drag_sent.get("rate")
            check(bar._panel_open and bool(_u32.IsWindowVisible(bar._panel_hwnd)), "설정 패널 떠 있음")
            check(want is not None and abs(cur["s"].rate - want) < 1e-9,
                  "속도 슬라이더 → 엔진 속도 %.3f (보낸 값 %s)" % (cur["s"].rate, want))
            shown = bar._panel_canvas.itemcget(bar._rows["rate"]["value"], "text")
            check(want is not None and shown == "%.2fx" % want, "패널 속도 글자 %r" % shown)
        # 창 스타일 (보이는 창만 — 숨은 창은 볼 필요 없음)
        if _IS_WIN:
            wins = []
            if bar._visible:
                wins.append(("하단 바", bar._hwnd))
            if bar._panel_open:
                wins.append(("설정 패널", bar._panel_hwnd))
            if reader.is_visible():
                wins.append(("리더 창", reader_window._wrapper_hwnd(reader.win)))
            for label, h in wins:
                ex = ex_style(h)
                check(ex is not None and (ex & NEED_EX) == NEED_EX,
                      "%s 확장 스타일 0x%08X (NOACTIVATE|TOOLWINDOW|TOPMOST 필요)" % (label, ex or 0))
            fg = hwnd_int(fg_hwnd())
            check(fg not in our_hwnds(), "전경 창이 우리 창 아님 (전경 0x%X)" % fg)
            act = hwnd_int(_u32.GetActiveWindow())
            check(act not in our_hwnds(), "우리 스레드 활성 창이 바·리더 창 아님 (0x%X)" % act)
            if fg != hwnd_int(fg0):
                notes.append("     참고: 전경 창이 처음(0x%X)과 다름 — 사용자가 창을 바꿨을 수 있음" % hwnd_int(fg0))
        check(not focus_hits, "우리 창 FocusIn 0회 (%s)" % focus_hits)
        if exp.get("stopped"):
            done = cur["s"].join(2.0)
            check(done, "재생·합성 스레드 종료(join)")
            alive = [t.name for t in threading.enumerate() if t.name.startswith("tts-")]
            check(not alive, "남은 tts- 스레드 없음 %s" % alive)
            calls = streams[-1].calls if streams else []
            check("abort" in calls and "close" in calls, "스트림 abort·close 호출 %s" % calls)
            ends = [e for e in glue.events if e[1] == "session_end"]
            check(len(ends) == 1, "session_end 한 번 (%d)" % len(ends))
            check(glue.commands and glue.commands[-1][1] == "stop", "닫기 버튼이 stop 명령을 보냄")
        return ok

    marks_click = {}
    drag_sent = {}
    before_new = {}

    def new_reading(_name, _info):
        """(Tk 메인) 읽는 도중 새 읽기 — whisperer.py speak_text 와 같은 순서.

        previous = tts_session → stop_current_playback()(= 앞 세션 stop) → 새 TtsSession(previous=앞 세션)
        → tts_session = 새 세션(_reading_segment_idx = None) → start().
        바로 전의 바 진행선 위치를 기억해 두었다가 new_reading 확인에서 "0 에서 다시 시작했나"를 본다.
        """
        glue.pump()
        before_new["fill"] = bar._fill_drawn / float(max(bar._w, 1))
        before_new["stream"] = streams[-1] if streams else None
        prev = cur["s"]
        prev.stop()
        nxt = new_session(SECOND_TEXT)
        cur.update(nxt)
        cur["prev"] = prev
        glue.begin(cur["s"])
        cur["s"].start()
        print("[newread] t=%.2fs 앞 읽기 진행선 %.3f → 새 읽기 시작" %
              (time.monotonic() - t0_box["t0"], before_new["fill"]), flush=True)

    def drag(key, slider_value):
        """설정 패널 슬라이더를 사람이 끄는 것처럼: 지금 손잡이 자리에서 누르고 → slider_value 자리로 끌고 → 뗀다.

        Tk 안에서만 도는 가짜 이벤트다(운영체제 마우스 흉내 아님). 바가 손을 뗄 때 한 번만 setRate 를
        보내는지(확장 change 이벤트, page-ui.js:637-642)와 그 값이 엔진까지 가는지를 본다.
        """
        glue.pump()
        n_before = len(glue.commands)
        p, row = bottom_bar._PARAMS[key], bar._rows[key]
        r = bar._px(bottom_bar.SLIDER_THUMB_D) / 2.0

        def x_of(v):
            frac = (v - p["min"]) / (p["max"] - p["min"])
            return int(round(row["x0"] + r + frac * (row["x1"] - row["x0"] - 2 * r)))

        y = int(round(row["cy"]))
        pc = bar._panel_canvas
        pc.event_generate("<ButtonPress-1>", x=x_of(bar._slider_vals[key]), y=y)
        pc.event_generate("<B1-Motion>", x=x_of((bar._slider_vals[key] + slider_value) / 2.0), y=y)
        pc.event_generate("<B1-Motion>", x=x_of(slider_value), y=y)
        pc.event_generate("<ButtonRelease-1>", x=x_of(slider_value), y=y)
        sent = glue.commands[n_before:]
        if sent:
            drag_sent[key] = sent[-1][2]
        print("[drag] %-8s t=%.2fs 보낸 명령=%s" % (key, time.monotonic() - t0_box["t0"],
                                                 [(c, v) for _, c, v in sent]), flush=True)

    def click(key, info):
        """하단 바 버튼을 사람이 누른 것처럼: 캔버스에 누름·뗌 이벤트를 버튼 가운데 좌표로 넣는다.

        Tk 안에서만 도는 가짜 이벤트라 운영체제 마우스·다른 프로그램에는 영향이 없다.
        바의 원형 판정(_hit) → 활성 확인 → _activate → on_command 까지 실제 경로를 그대로 탄다.
        """
        glue.pump()
        n_before = len(glue.commands)
        bt = bar._buttons[key]
        x, y = int(round(bt.cx)), int(round(bt.cy))
        c = bar._canvas
        c.event_generate("<ButtonPress-1>", x=x, y=y)
        c.event_generate("<ButtonRelease-1>", x=x, y=y)
        t = time.monotonic() - t0_box["t0"]
        if info.get("mark"):
            marks_click[info["mark"]] = t    # 연타 첫 누름 시각 — 그 뒤 합성 요청을 확인할 때 쓴다
        sent = glue.commands[n_before:]
        print("[click] %-8s t=%.2fs 활성=%s 보낸 명령=%s" % (key, t, bt.enabled,
                                                         [(c, v) for _, c, v in sent]), flush=True)

    def finish():
        glue.pump()
        # 끝나기 전 스타일을 한 번 더: 패널·말풍선은 한 번도 안 떴을 수 있어 숨긴 창의 값을 본다(만들 때 건다)
        if _IS_WIN:
            for label, h in (("설정 패널", bar._panel_hwnd), ("말풍선", bar._tip_hwnd)):
                ex = ex_style(h)
                ok = ex is not None and (ex & (WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)) == (WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
                results.append((label + " 스타일", ok, ["%s 0x%08X" % ("OK  " if ok else "FAIL", ex or 0)]))
                print("[cp] %-14s %s  0x%08X" % (label + " 스타일", "PASS" if ok else "FAIL", ex or 0), flush=True)
        # 계획한 확인 단계가 하나라도 안 돌았으면(예외·시간 초과) 실패로 친다
        done_names = {n for n, _, _ in results}
        for _ms, kind, name, _exp in TIMELINE:
            if kind == "cp" and name not in done_names:
                results.append((name, False, ["FAIL 이 확인 단계가 실행되지 않음"]))
                print("[cp] %-14s FAIL  (실행되지 않음)" % name, flush=True)
        n_fail = sum(1 for _, ok, _ in results if not ok)
        print("[demo] 합성 요청 기록(초, 조각): %s" % [(round(t, 2), i) for t, i in synth_log], flush=True)
        print("[demo] 하단 바 명령: %s" % [(round(t - t0_box["t0"], 2), c, v) for t, c, v in glue.commands], flush=True)
        print("[demo] 알림 처리 시간(가장 오래·횟수): %s" % {k: ("%.0fms" % (v[0] * 1000), v[1])
                                                     for k, v in glue.took.items()}, flush=True)
        if shots:
            _contact_sheet(shots, os.path.join(args.shots, "ui_sheet.png"))
        print("[demo] 결과: %d단계 중 실패 %d" % (len(results), n_fail), flush=True)
        try:
            for key in ("prev", "s"):
                if cur.get(key) is not None:
                    cur[key].stop()
            bar.destroy()
            reader.destroy()
            root.destroy()
        except Exception:
            pass
        state["code"] = 0 if n_fail == 0 else 1

    state = {"code": 1}

    # ── 5) 100ms 마다 알림 처리 (whisperer.py check_gui_queue 흉내) ──
    def poll():
        try:
            glue.pump()
        finally:
            try:
                root.after(GUI_POLL_MS, poll)
            except tk.TclError:
                pass

    # ── 6) 시작 + 시간표 예약 ──
    t0_box["t0"] = time.monotonic()
    print("[demo] 준비 %.2fs (프로세스 시작 → 읽기 시작)" % (t0_box["t0"] - _T_PROC), flush=True)
    cur["s"].start()
    root.after(GUI_POLL_MS, poll)
    for ms, kind, name, exp in TIMELINE:
        if kind == "cp":
            root.after(ms, checkpoint, name, exp)
        elif kind == "click":
            root.after(ms, click, name, exp or {})
        elif kind == "drag":
            root.after(ms, drag, name, exp)
        elif kind == "newread":
            root.after(ms, new_reading, name, exp)
        else:
            root.after(ms, finish)
            root.after(ms + 200, root.quit)
    root.mainloop()
    return state["code"]


def _contact_sheet(shots, path):
    """단계별 캡처를 반으로 줄여 세로로 이어 붙인 한 장(보고용)."""
    try:
        from PIL import Image, ImageDraw
        ims = []
        for name, p in shots:
            im = Image.open(p)
            im = im.resize((max(1, im.width // 2), max(1, im.height // 2)))
            ims.append((name, im))
        w = max(im.width for _, im in ims)
        h = sum(im.height + 22 for _, im in ims)
        sheet = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(sheet)
        y = 0
        for name, im in ims:
            d.text((4, y + 4), name, fill="black")
            sheet.paste(im, (0, y + 20))
            y += im.height + 22
        sheet.save(path)
    except Exception as e:
        print("[demo] 모음 이미지 실패: %s" % e, flush=True)


if __name__ == "__main__":
    code = main(sys.argv[1:])
    print("[demo] 끝 (종료 코드 %d, 프로세스 %.2fs)" % (code, time.monotonic() - _T_PROC), flush=True)
    sys.exit(code)
