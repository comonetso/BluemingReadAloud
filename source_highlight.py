# -*- coding: utf-8 -*-
"""source_highlight.py — 읽는 동안 "원문 위"에 반투명 노란 형광펜 막을 띄운다.

■ 무엇을 하나
  크롬 확장 read-aloud-hrg 는 읽는 조각(단락)을 페이지 위에 rgba(255,226,0,0.3) 으로 칠한다
  (js/events.js:374 `::highlight(readaloud-hrg-para)`). 데스크톱 앱은 다른 앱 화면에 칠할 수 없으므로
  윈도우 UI Automation(UIA)의 TextPattern 으로 "그 글이 화면 어디에 있는지"를 묻고, 그 줄 사각형 위에
  클릭이 통과하는 반투명 창(막)을 겹쳐 띄운다. 칠할 수 없는 앱이면 whisperer 가 리더 창으로 넘어간다.

■ 모듈 사이 약속 (whisperer.py 가 이 모양에 기댄다 — 바꾸지 말 것)
    hl = SourceHighlighter(root)                      # Tk 메인에서 만든다
    hl.begin(source_text, segments, on_result)        # Tk 메인. 선택이 살아 있는 "읽기 직전"에 부른다
        segments = readaloud_text.split_for_reading(...) 결과(src_start/src_end = source_text 기준 파이썬 오프셋)
        on_result(ok: bool, reason: str) 는 나중에 **Tk 메인에서** 불린다(root.after 틱으로 넘김). begin 안에서
        바로 불리는 일은 없다. 읽기(소리)는 이 결과를 기다리지 않는다.
    hl.highlight(idx)      # Tk 메인. idx 조각을 칠한다. None 이면 지운다. 화면 밖이면 보이게 스크롤한다
    hl.highlight(idx, caption)  # (2026-09-29) caption(번역문)이 있으면 노랑 대신 "짙은 회색 바탕 + 흰 글씨 +
                                # 노랑 테두리" 막으로 원문 줄 자리를 덮고 그 글을 쓴다(build_caption_bitmap)
    hl.notify_scroll()     # 어느 스레드에서 불러도 된다(플래그만 세움 — 마우스 훅 콜백에서 부름)
    hl.end()               # Tk 메인. 막을 지우고 잡은 범위를 놓는다(end 뒤에는 on_result 를 부르지 않는다)
    hl.destroy()
    hl.active              # begin 이 성공해 지금 원문 위 칠하기가 동작 중이면 True
  덧붙인 것(선택): SourceHighlighter(root, on_stop=fn) — 읽는 도중 칠하기를 멈추면(느림·범위 잃음·대상 창 닫힘)
    fn(reason) 을 Tk 메인에서 부른다. 안 넘기면 active 만 False 가 된다.

■ 흐름
  1) begin (Tk 메인): 전경 창(=사용자가 글을 고른 앱)을 기억하고, UIA 전용 스레드에 "선택 잡기"를 맡긴다.
  2) UIA 스레드: GetFocusedElement → 위로 최대 8단계에서 TextPattern 이 있는 첫 요소(VS Code 채팅은 4단계 위
     Document) → GetSelection 첫 범위 → GetText. 그 글과 source_text(클립보드 글)를 공백을 건너뛰며 순서대로
     맞추고(align_source_to_uia), 조각마다 선택 범위를 복제해 조각 시작·끝으로 줄인 범위를 미리 만들어 둔다.
  3) highlight (Tk 메인): 그 조각 범위의 GetBoundingRectangles(줄 사각형들)만 다시 받아 막 창 하나에 그린다.
  4) 틱(Tk 메인, WATCH_MS): 결과 받기 · 대상 창이 전경인지(아니면 막 숨김) · 창이 움직였는지 · 휠 알림 ·
     한 호출이 1초를 넘는지(넘으면 그 읽기 동안 칠하기 중단)를 본다.

■ ⛔ 금지 호출 — 2026-09-28 사용자 VS Code 를 얼린 호출들이다. 이 모듈에서 절대 부르지 않는다
    - IUIAutomationTextPattern.GetVisibleRanges
    - DocumentRange 전체에 대한 GetText / GetBoundingRectangles / FindText (문서 전체 범위 호출 전부)
    - 창·문서 단위 FindAll / FindFirst (TreeScope_Descendants·Subtree) — 요소 트리 훑기
  쓰는 호출은 "포커스 요소에서 위로 걷기"와 "사용자가 고른 선택 범위 안쪽"뿐이다. 모든 UIA 호출은 시간을 재고
  (_UiaWorker._call), 한 호출이 SLOW_CALL_S(1초)를 넘으면 그 읽기 동안 원문 위 칠하기를 멈추고 막을 지운다.
  UIA 자체 제한 시간(IUIAutomation2 Connection/TransactionTimeout)도 같은 1초로 걸어 멈춘 앱에 오래 묶이지 않게 한다.

■ Edge 실측으로 확인한 크로미움 UIA 동작 (2026-09-28, 내가 띄운 Edge 154 창 — scratchpad phase4\\probe1.json)
  - MoveEndpointByUnit(TextUnit_Character) 한 칸 = "글자 묶음(grapheme cluster)" 하나다. 파이썬 글자(코드 포인트)도
    UTF-16 단위도 아니다: 😀(1코드포인트·UTF-16 2) = 1칸, e+U+0301(2코드포인트) = 1칸, 👍🏽(2코드포인트·UTF-16 4) = 1칸.
    → 파이썬 오프셋을 grapheme_counts 로 "몇 번째 글자 묶음"으로 바꿔 옮긴다. 만든 범위는 GetText 로 반드시 검증하고,
      어긋나면 그 조각 글로 FindText(선택 범위 안쪽만) 해서 대신 잡는다.
  - GetText 는 블록(문단·목록 항목) 사이에 "\\n" 하나를 넣고, 그 "\\n" 도 Character 한 칸이다.
    목록 기호가 글에 들어온다: <ul> → "• ", <ol> → "1. ". 클립보드 글(selection.toString)에는 없다.
    문단 사이는 클립보드가 "\\n\\n", UIA 는 "\\n" → 그래서 공백을 무시하고 끼어든 글자는 건너뛰며 맞춘다.
  - 블록 경계(<br> 등)에서는 GetText 의 "\\n" 과 Character 칸이 어긋날 때가 있다(범위가 "\\n두 번째…"로 한 칸 앞에서
    시작) → 앞뒤 공백이 끼면 범위 안에서 FindText 로 다시 잡고, 그래도 안 되면 선택 범위 안 FindText(_trim_verify).
  - GetBoundingRectangles 는 [왼, 위, 너비, 높이] 가 줄마다 이어진 실수 배열이고, 안쪽 스크롤 상자 밖(화면 밖) 줄은
    빠진다(빈 배열). 범위 끝이 다음 문단 첫머리에 걸리면 폭 1.0 짜리 캐럿 같은 사각형이 붙는다(rects_from_uia 가 뺌).
  - 스크롤(scratchpad phase4\\probe3.json): 문단 하나 안의 범위는 TextRange.ScrollIntoView 가 아무 효과가 없고,
    GetEnclosingElement → ScrollItemPattern.ScrollIntoView 만 움직였다(가운데쯤으로). 두 문단에 걸친 범위는
    TextRange.ScrollIntoView(True) 로 움직였다(위에 맞춤). 스크롤은 비동기라 곧바로 다시 물으면 옛 사각형이다.
  - 호출 하나 0.1~8ms(조각 8개짜리 begin 전체 약 0.1초). GetCurrentPattern(TextPatternId) 뒤 QueryInterface 가 되는
    방식(GetCurrentPatternAs 는 사용자 PC VS Code 에서 실패했다 — 오케스트레이터 실측).
  - 처음 UIA 로 붙은 직후에는 크로미움 접근성 트리가 아직 없어 문서에 TextPattern 이 없을 수 있다(Edge 실측: 약 0.05~0.2초,
    그 사이 begin 은 "no_text_pattern"). 다시 시도하지 않는다 — whisperer 가 리더 창으로 넘어간다.

■ 반드시 지킬 것 (함정)
  1. UIA 호출은 전용 스레드 하나(_UiaWorker)에서만. COM 은 그 스레드에서 초기화하고(MTA), COM 객체는 그 스레드
     밖으로 내보내지 않는다. Tk 는 그 스레드에서 부르지 않는다 — 결과는 큐에 넣고 Tk 틱이 꺼내 간다.
  2. 막 창은 포커스를 뺏으면 안 되고(NOACTIVATE) 클릭이 아래 앱으로 통과해야 한다(WS_EX_TRANSPARENT|WS_EX_LAYERED).
     Tk 의 attributes("-alpha"/"-transparentcolor") 는 GWL_EXSTYLE 을 덮어써 NOACTIVATE 를 지우므로 쓰지 않는다
     (selection_button.py 함정 2와 같다). 반투명은 UpdateLayeredWindow(픽셀마다 알파)로 직접 올린다.
  3. 보이기는 ShowWindow(SW_SHOWNOACTIVATE). Tk deiconify 는 포커스를 가져간다(selection_button.py 함정 4).
  4. 좌표: 앱은 시스템 DPI 인식(ttkbootstrap → SetProcessDPIAware)이다. UIA 사각형과 막 창 위치는 같은 프로세스의
     같은 좌표계로 오가므로 맞는다(주 모니터 Edge 실측). 배율이 다른 보조 모니터는 확인하지 못했다.
  5. VS Code 채팅 목록은 화면 밖 메시지를 DOM 에서 지울 수 있다(가상 목록). 그러면 잡아 둔 범위가 죽어 호출이
     실패한다 → 그 읽기 동안 칠하기를 멈춘다(on_stop("lost")). 다시 찾으려면 문서 전체를 뒤져야 해서 하지 않는다.
"""

from __future__ import annotations

import bisect
import logging
import math
import os
import queue
import sys
import threading
import time
import unicodedata

log = logging.getLogger(__name__)

__all__ = ["SourceHighlighter", "align_source_to_uia", "TextAlignment", "grapheme_counts",
           "build_overlay_bitmap", "build_caption_bitmap", "rects_from_uia", "clip_rects", "uia_on_screen"]


# ════════════════════════════════════════════════════════════════════
#  값 — 근거가 있는 것과 임의로 정한 것([임의])을 나눠 적는다
# ════════════════════════════════════════════════════════════════════
HIGHLIGHT_RGBA = (255, 226, 0, 0.3)   # 확장 js/events.js:374 ::highlight(readaloud-hrg-para) 배경색
SLOW_CALL_S = 1.0                     # 오케스트레이터 지시: 한 호출이 1초를 넘으면 그 읽기 동안 원문 위 칠하기 중단
UIA_TIMEOUT_MS = 1000                 # 위와 같은 1초를 UIA 자체 제한 시간으로도 건다(멈춘 앱에 20초씩 묶이지 않게)
MAX_ANCESTOR_STEPS = 8                # 오케스트레이터 지시(VS Code 채팅은 포커스에서 4단계 위가 Document — 실측)

WATCH_MS = 50            # [임의] Tk 틱 주기: 결과 받기·전경/창 위치 확인·휠 알림 처리·1초 감시
SETTLE_TICKS = 6         # [임의] 휠·창 이동·자동 스크롤 뒤 사각형을 틱마다 다시 받는 횟수(≈0.3초, 부드러운 스크롤이 끝날 때까지)
REFRESH_S = 1.0          # [임의] 아무 알림이 없어도 지금 조각 사각형을 다시 받는 주기(스크롤바 끌기·키보드 스크롤·
                         #   글이 늘어나 밀리는 경우). 0 이면 끈다
RESYNC_WINDOW = 64       # [임의] 맞춤이 어긋났을 때 앞으로 건너뛰며 다시 맞출 곳을 찾는 최대 글자 수
RESYNC_ANCHOR = 3        # [임의] 다시 맞출 곳으로 인정하는 연속 일치 글자 수
MIN_MATCH_RATIO = 0.8    # [임의] 원문(공백 뺀) 글자 중 UIA 글과 맞은 비율이 이보다 낮으면 "다른 글"로 보고 포기

# UIA 오류 코드(HRESULT) — 윈도우 SDK UIAutomationCoreApi.h
UIA_E_ELEMENTNOTAVAILABLE = 0x80040201   # 요소(범위)가 사라짐 — DOM 에서 지워진 경우
UIA_E_TIMEOUT = 0x80131505               # 우리가 건 제한 시간(UIA_TIMEOUT_MS)을 넘김

# 공백처럼 건너뛰는 글자: 공백류 + 폭 없는 공백·BOM + 개체 자리표(U+FFFC, 크로미움이 그림 자리에 넣을 수 있음)
_SKIP_CHARS = frozenset("\ufeff\u200b\ufffc")


def _ignorable(c):
    """맞출 때 무시하는 글자인지(공백·줄바꿈·폭 없는 글자)."""
    return c.isspace() or c in _SKIP_CHARS


def _squash(text):
    """무시하는 글자를 모두 뺀 글(범위 검증 비교용)."""
    return "".join(c for c in text if not _ignorable(c))


# ════════════════════════════════════════════════════════════════════
#  글자 묶음(grapheme cluster) 세기 — 크로미움 UIA 의 Character 한 칸
# ════════════════════════════════════════════════════════════════════
def _is_ext_pict(cp):
    """그림 문자(이모지)인지 대강 가른다(UAX #29 Extended_Pictographic 근사 — ZWJ 이모지 잇기에만 쓴다)."""
    return (cp in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x24C2, 0x3030, 0x303D, 0x3297, 0x3299)
            or 0x2194 <= cp <= 0x21AA or 0x231A <= cp <= 0x23FF or 0x25AA <= cp <= 0x25FE
            or 0x2600 <= cp <= 0x27BF or 0x2934 <= cp <= 0x2935 or 0x2B05 <= cp <= 0x2B55
            or (0x1F000 <= cp <= 0x1FAFF and not 0x1F1E6 <= cp <= 0x1F1FF and not 0x1F3FB <= cp <= 0x1F3FF)
            or 0x1FC00 <= cp <= 0x1FFFD)


def _gcb(ch):
    """글자 하나의 경계 분류(UAX #29 Grapheme_Cluster_Break 의 필요한 만큼만)."""
    cp = ord(ch)
    if cp == 0x0D:
        return "CR"
    if cp == 0x0A:
        return "LF"
    if cp == 0x200D:
        return "ZWJ"
    if 0x1F1E6 <= cp <= 0x1F1FF:
        return "RI"                       # 국기 글자(두 개씩 짝)
    if 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F or cp == 0x200C or 0xFF9E <= cp <= 0xFF9F:
        return "Extend"                   # 피부색·태그·ZWNJ·반각 탁음
    if 0x1100 <= cp <= 0x115F or 0xA960 <= cp <= 0xA97C:
        return "L"                        # 한글 첫소리 자모
    if 0x1160 <= cp <= 0x11A7 or 0xD7B0 <= cp <= 0xD7C6:
        return "V"
    if 0x11A8 <= cp <= 0x11FF or 0xD7CB <= cp <= 0xD7FB:
        return "T"
    if 0xAC00 <= cp <= 0xD7A3:
        return "LV" if (cp - 0xAC00) % 28 == 0 else "LVT"
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me"):
        return "Extend"                   # 결합 부호(é 의 U+0301), 이체 선택자(FE0F) 등
    if cat == "Mc":
        return "SpacingMark"
    if cat in ("Cc", "Zl", "Zp", "Cf"):
        return "Control"
    if _is_ext_pict(cp):
        return "ExtPict"
    return "Other"


def grapheme_counts(text):
    """cum[i] = text[:i] 안에서 시작하는 글자 묶음 수 (길이 len(text)+1).

    왜: 크로미움 UIA 는 Character 한 칸을 글자 묶음으로 센다(모듈 머리말 실측). 파이썬 오프셋 i 를 "UIA 몇 칸"으로
    바꿀 때 쓴다. 함정: 유니코드 규칙을 필요한 만큼만 옮긴 근사다(인도계 문자 결합 규칙 GB9c 등은 없음) → 만든
    범위는 늘 GetText 로 검증하고 어긋나면 FindText 로 대신 잡는다(_UiaWorker._build_ranges).
    근거: UAX #29 GB3~GB13, Edge 실측(😀·e+U+0301·👍🏽 각 1칸, "\\n" 1칸).
    """
    n = len(text)
    cum = [0] * (n + 1)
    count = 0
    prev = None
    pict_zwj = False      # 바로 앞이 "그림문자 Extend* ZWJ" 로 끝났는가(GB11)
    in_pict = False       # 지금 "그림문자 Extend*" 안인가
    ri_run = 0            # 이어진 국기 글자 수(GB12/13)
    for i, ch in enumerate(text):
        cur = _gcb(ch)
        if prev is None:
            brk = True
        elif prev == "CR" and cur == "LF":
            brk = False                                            # GB3
        elif prev in ("Control", "CR", "LF") or cur in ("Control", "CR", "LF"):
            brk = True                                             # GB4, GB5
        elif prev == "L" and cur in ("L", "V", "LV", "LVT"):
            brk = False                                            # GB6
        elif prev in ("LV", "V") and cur in ("V", "T"):
            brk = False                                            # GB7
        elif prev in ("LVT", "T") and cur == "T":
            brk = False                                            # GB8
        elif cur in ("Extend", "ZWJ", "SpacingMark"):
            brk = False                                            # GB9, GB9a
        elif prev == "ZWJ" and cur == "ExtPict" and pict_zwj:
            brk = False                                            # GB11
        elif prev == "RI" and cur == "RI" and ri_run % 2 == 1:
            brk = False                                            # GB12, GB13
        else:
            brk = True
        if brk:
            count += 1
        cum[i + 1] = count
        # 다음 글자를 위한 상태
        pict_zwj = in_pict and cur == "ZWJ"
        if cur == "ExtPict":
            in_pict = True
        elif cur != "Extend":
            in_pict = False
        ri_run = ri_run + 1 if cur == "RI" else 0
        prev = cur
    return cum


def _g_floor(cum, i):
    """파이썬 오프셋 i 의 글자가 속한 글자 묶음 번호(시작점용)."""
    if i >= len(cum) - 1:
        return cum[-1]
    return cum[i + 1] - 1


def _g_ceil(cum, i):
    """파이썬 오프셋 i 앞에서 시작한 글자 묶음 수(끝점용 — 묶음 한가운데면 그 묶음 끝까지 넣는다)."""
    return cum[min(i, len(cum) - 1)]


# ════════════════════════════════════════════════════════════════════
#  원문(클립보드 글) ↔ UIA 선택 글 맞추기
# ════════════════════════════════════════════════════════════════════
class TextAlignment:
    """원문 글자(공백 뺀) → UIA 글 위치 대응표. span() 이 조각 구간을 UIA 글 구간으로 바꾼다."""

    def __init__(self, a_idx, b_idx, amap, ratio):
        self.a_idx = a_idx      # 공백 뺀 원문 글자 k 의 원문 오프셋
        self.b_idx = b_idx      # 공백 뺀 UIA 글자 k 의 UIA 글 오프셋
        self.amap = amap        # 원문 글자 k → UIA 글자 번호(-1 = 짝 없음)
        self.ratio = ratio      # 짝을 찾은 원문 글자 비율

    def span(self, src_start, src_end):
        """원문 [src_start, src_end) → UIA 글 [a, b) (앞뒤 공백 없음). 짝 있는 글자가 하나도 없으면 None.

        첫 짝~마지막 짝까지를 잡는다(순서가 늘 앞으로만 가므로 가운데 짝 없는 글자도 그 사이에 든다).
        """
        if src_start is None or src_end is None or src_end <= src_start:
            return None
        lo = bisect.bisect_left(self.a_idx, src_start)
        hi = bisect.bisect_left(self.a_idx, src_end)
        first = last = -1
        for k in range(lo, hi):
            j = self.amap[k]
            if j >= 0:
                if first < 0:
                    first = j
                last = j
        if first < 0:
            return None
        return self.b_idx[first], self.b_idx[last] + 1


def align_source_to_uia(source_text, uia_text, window=RESYNC_WINDOW, anchor=RESYNC_ANCHOR):
    """클립보드 원문과 UIA 선택 글을 공백을 무시하고 앞에서부터 순서대로 맞춘다. 못 맞추면 None.

    왜: 둘은 같은 선택인데 모양이 다르다(Edge 실측) — 문단 사이 "\\n\\n" 대 "\\n", UIA 에만 있는 목록 기호 "• "·"1. ".
    VS Code 가 복사할 때 마크다운 기호(**, `, - 등)를 원문 쪽에 붙일 가능성도 있다(확인 못 함).
    방법: 확장 alignSegmentsToSource(page-ui-host.js:711-720)처럼 공백은 건너뛰고 같은 글자를 순서대로 짝짓는다.
    확장은 어긋나면 바로 포기하지만, 여기서는 목록 기호 같은 "한쪽에만 있는 글자"를 건너뛰어야 해서
    어긋난 자리에서 앞쪽 window 글자 안에 anchor 글자가 다시 일치하는 곳을 찾아 짧게 건너뛴 쪽으로 다시 맞춘다.
    (difflib 은 2만 자에서 5.8초가 걸려 쓰지 않았다 — 이 방식은 글 길이에 비례.)
    둘 다 못 찾으면 한 글자씩 "다른 글자"로 보고 넘어간다. 전체 짝 비율이 MIN_MATCH_RATIO 보다 낮으면 None.
    """
    a_chars, a_idx = [], []
    for i, c in enumerate(source_text or ""):
        if not _ignorable(c):
            a_chars.append(c)
            a_idx.append(i)
    b_chars, b_idx = [], []
    for i, c in enumerate(uia_text or ""):
        if not _ignorable(c):
            b_chars.append(c)
            b_idx.append(i)
    a, b = "".join(a_chars), "".join(b_chars)
    na, nb = len(a), len(b)
    if na == 0 or nb == 0:
        return None
    amap = [-1] * na
    i = j = matched = 0
    while i < na and j < nb:
        if a[i] == b[j]:
            amap[i] = j
            matched += 1
            i += 1
            j += 1
            continue
        ka = min(anchor, na - i)
        kb = min(anchor, nb - j)
        pb = b.find(a[i:i + ka], j + 1, j + 1 + window + ka)   # UIA 쪽에만 있는 글자(목록 기호 등) 건너뛰기
        pa = a.find(b[j:j + kb], i + 1, i + 1 + window + kb)   # 원문 쪽에만 있는 글자 건너뛰기
        if pb >= 0 and (pa < 0 or pb - j <= pa - i):
            j = pb
        elif pa >= 0:
            i = pa
        else:
            i += 1          # 서로 다른 글자(예: ' 대 ’) — 양쪽 한 칸씩
            j += 1
    ratio = matched / na
    if ratio < MIN_MATCH_RATIO:
        return None
    return TextAlignment(a_idx, b_idx, amap, ratio)


# ════════════════════════════════════════════════════════════════════
#  사각형 도우미 (순수 함수 — 테스트 대상)
# ════════════════════════════════════════════════════════════════════
def rects_from_uia(arr):
    """GetBoundingRectangles 결과([왼, 위, 너비, 높이] 가 이어진 실수 배열) → [(왼, 위, 오른, 아래)] 정수.

    바깥쪽으로 반올림한다(내림·올림) — 글자 끝이 막 밖으로 삐져나오지 않게.
    폭이 1px 이하인 것은 뺀다: 크로미움은 범위 끝이 다음 문단 첫머리와 같은 자리로 잡히면 그 줄 첫머리에 폭 1.0 짜리
    "캐럿 같은" 사각형을 준다(Edge 실측 [113, 627, 1.0, 31]) — 글자 하나는 그보다 넓다. 높이 0 도 뺀다.
    """
    out = []
    if not arr:
        return out
    vals = list(arr)
    for k in range(0, len(vals) - 3, 4):
        x, y, w, h = vals[k:k + 4]
        if w <= 1 or h <= 0:
            continue
        out.append((int(math.floor(x)), int(math.floor(y)), int(math.ceil(x + w)), int(math.ceil(y + h))))
    return out


def uia_on_screen(arr, view):
    """GetBoundingRectangles 원시 배열에 화면(view = 문서 영역 (왼, 위, 오른, 아래)) 안에 걸친 사각형이 하나라도 있는가.

    무엇을: "이 글자(범위)가 지금 화면에 보이나"만 가른다(자동 스크롤 판단용 — 그리기용 rects_from_uia 와 다르다).
    왜 따로 두나: 그리기에서는 폭 1px 캐럿 같은 사각형을 빼지만, 여기서는 그것도 "화면 안에 있다"는 증거로 친다.
      크로미움은 범위 끝이 문단 사이 "\\n" 에 걸리면 마지막 글자 자리로 [줄 끝, 1px] + [다음 문단 첫머리, 1px] 만 준다
      (Edge 실측 2026-09-28 phase4\\edge_runclear_.json: [797, 571, 1.0, 31.0, 113, 627, 1.0, 31.0]). 이것을 "안 보임"으로
      읽으면 다 보이는 조각인데도 스크롤해 버린다(앞 판의 h3 가 그랬다 — 사용자 화면을 괜히 움직임).
    함정: 화면 밖 줄은 크로미움이 아예 빼고 주지만(빈 배열), 좌표가 화면 밖으로 오는 앱이 있을 수 있어 view 와 겹치는지도 본다.
      view 가 None 이면 사각형이 있기만 하면 보인다고 친다.
    """
    if not arr:
        return False
    vals = list(arr)
    for k in range(0, len(vals) - 3, 4):
        x, y, w, h = vals[k:k + 4]
        if h <= 0:
            continue
        if view is None:
            return True
        vl, vt, vr, vb = view
        if x <= vr and x + max(w, 0) >= vl and y < vb and y + h > vt:
            return True
    return False


def clip_rects(rects, bounds):
    """사각형들을 bounds(왼, 위, 오른, 아래) 안으로 자른다. 잘라서 비는 것은 뺀다. bounds 가 None 이면 그대로.

    왜: 대상 창·문서 영역 밖(다른 창 위, 브라우저 툴바 위)에 칠하지 않게.
    """
    if not bounds:
        return list(rects)
    bl, bt, br, bb = bounds
    out = []
    for l, t, r, b in rects:
        l2, t2, r2, b2 = max(l, bl), max(t, bt), min(r, br), min(b, bb)
        if r2 > l2 and b2 > t2:
            out.append((l2, t2, r2, b2))
    return out


def _intersect(a, b):
    """두 사각형의 겹친 부분. 하나가 None 이면 다른 하나. 안 겹치면 빈 사각형(왼=오른)."""
    if not a:
        return b
    if not b:
        return a
    l, t, r, bt = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return (l, t, max(l, r), max(t, bt))


def _premultiplied_bgra(rgba):
    """CSS rgba → UpdateLayeredWindow 용 "미리 곱한" BGRA 한 픽셀(bytes 4)."""
    r, g, b, a = rgba
    alpha = int(a * 255 + 0.5)      # 0.3 → 77 (round(76.5) 는 짝수 쪽 76 이라 쓰지 않는다)
    return bytes((b * alpha // 255, g * alpha // 255, r * alpha // 255, alpha))


PREMULT_PIXEL = _premultiplied_bgra(HIGHLIGHT_RGBA)   # (0, 68, 77, 77)


def build_overlay_bitmap(rects, pixel=PREMULT_PIXEL):
    """줄 사각형들을 감싸는 그림 한 장. (왼, 위, 너비, 높이, BGRA bytes, 위→아래 줄 순서).

    왜 창 하나에 그리나: 줄마다 창을 두면 겹치는 곳(굵은 글씨 경계 등 한 줄이 여러 사각형으로 올 때)이 두 번 칠해져
    진해진다. 한 그림에 칠하면 겹쳐도 같은 값이라 확장(CSS 형광펜)처럼 고르게 보인다. 사각형 밖은 알파 0(투명).
    """
    left = min(r[0] for r in rects)
    top = min(r[1] for r in rects)
    w = max(r[2] for r in rects) - left
    h = max(r[3] for r in rects) - top
    buf = bytearray(w * h * 4)
    for l, t, r, b in rects:
        row = pixel * (r - l)
        x0 = (l - left) * 4
        for y in range(t - top, b - top):
            off = y * w * 4 + x0
            buf[off:off + len(row)] = row
    return left, top, w, h, bytes(buf)


# ── 번역문 막 (2026-09-29 사용자 결정: 번역된 조각은 원문 줄 자리를 덮고 번역문을 쓴다. 넘치면 막을 아래로 늘린다.
#    바탕은 짙은 회색에 흰 글씨. 설정 창 체크로 끌 수 있다 — whisperer translation_overlay_enabled) ──
CAPTION_BG = (0x38, 0x38, 0x38)    # 리더 창 TEXT_BG "#383838"(확장 설정 패널 배경)과 같은 짙은 회색
# 글자는 옅은 회색(2026-09-29 사용자 "흰색은 너무 밝다 — 옅은 회색으로"). 리더 창 HEADER_FG_DIM "#CCCCCC" 와 같은 값
# (= VS Code 다크 테마 기본 글자색)
CAPTION_FG = (0xCC, 0xCC, 0xCC)
CAPTION_BORDER = HIGHLIGHT_RGBA[:3]  # 형광펜과 같은 노랑(불투명) — "지금 읽는 자리" 표시
CAPTION_BORDER_PX = 2              # [임의] 테두리 두께(화면 px)
CAPTION_PAD_PX = 2                 # [임의] 테두리와 글자 사이(화면 px). 막은 원문 줄 상자보다 이 둘만큼 바깥으로 크다
CAPTION_FONT_FACE = "Malgun Gothic"  # 리더 창 FONT_FAMILIES 첫째. 없으면 윈도우가 비슷한 글꼴로 바꿔 준다
CAPTION_MIN_FONT_PX = 6            # [임의] 줄 높이가 아주 작아도 글꼴을 이보다 줄이지 않는다
# 글자는 윈도우 GDI 로 ClearType 을 켜고 그린다. 처음(Pillow, 흑백 부드럽게만)에는 옆의 VS Code 글자(ClearType)보다
# 거칠고 흐려 "깨져 보인다"(2026-09-29 사용자). 막이 불투명이라 GDI 글자(알파를 0 으로 씀)를 쓰고 알파만 255 로 채우면 된다.
_FW_NORMAL = 400
_DEFAULT_CHARSET = 1
_CLEARTYPE_QUALITY = 5
_BK_TRANSPARENT = 1


def _u16len(s):
    """GDI 에 넘길 글 길이(UTF-16 단위) — 이모지 같은 BMP 밖 글자는 2칸이다."""
    return len(s.encode("utf-16-le")) // 2


def _bgra_opaque(rgb):
    return bytes((rgb[2], rgb[1], rgb[0], 255))


def _wrap_caption(text, measure, max_w):
    """번역문 → 막 너비(max_w)에 맞춘 줄 목록. measure(글) = 그 글의 너비(px).

    줄바꿈은 지키고, 공백에서 끊고, 공백 없이 긴 덩어리는 글자 단위로 끊는다.
    """
    lines = []
    for para in (text or "").split("\n"):
        para = " ".join(para.split())
        if not para:
            continue
        cur = ""
        for word in para.split(" "):
            cand = word if not cur else cur + " " + word
            if measure(cand) <= max_w:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            cur = word
            while len(cur) > 1 and measure(cur) > max_w:
                cut = 1
                while cut < len(cur) and measure(cur[:cut + 1]) <= max_w:
                    cut += 1
                lines.append(cur[:cut])
                cur = cur[cut:]
        if cur:
            lines.append(cur)
    return lines or [""]


class _GdiText:
    """메모리 DC + ClearType 글꼴 — 글자 재기·그리기. build_caption_bitmap 안에서만 만들고 close 로 다 놓는다."""

    def __init__(self):
        self.dc = _g32.CreateCompatibleDC(None)
        if not self.dc:
            raise OSError("CreateCompatibleDC 실패")
        self.font = None
        self._old_font = None
        self.size = None

    def set_size(self, px):
        font = _g32.CreateFontW(-int(px), 0, 0, 0, _FW_NORMAL, 0, 0, 0, _DEFAULT_CHARSET, 0, 0,
                                _CLEARTYPE_QUALITY, 0, CAPTION_FONT_FACE)
        if not font:
            raise OSError("CreateFontW 실패")
        old = _g32.SelectObject(self.dc, font)
        if self._old_font is None:
            self._old_font = old
        if self.font:
            _g32.DeleteObject(self.font)
        self.font = font
        self.size = int(px)

    def height(self):
        """글꼴 한 줄 높이(ascent+descent, px)."""
        tm = _TEXTMETRICW()
        if not _g32.GetTextMetricsW(self.dc, ctypes.byref(tm)):
            raise OSError("GetTextMetricsW 실패")
        return tm.tmHeight

    def width(self, s):
        size = wintypes.SIZE()
        if not _g32.GetTextExtentPoint32W(self.dc, s, _u16len(s), ctypes.byref(size)):
            raise OSError("GetTextExtentPoint32W 실패")
        return size.cx

    def fit(self, line_h):
        """원문 줄 높이(line_h) 안에 글꼴 한 줄이 들어가는 가장 큰 크기로 — "글자 크기는 원문 줄 높이에 맞춘다"."""
        size = max(CAPTION_MIN_FONT_PX, int(line_h))
        while True:
            self.set_size(size)
            if size <= CAPTION_MIN_FONT_PX or self.height() <= line_h:
                return size
            size -= 1

    def close(self):
        if self._old_font:
            _g32.SelectObject(self.dc, self._old_font)
        if self.font:
            _g32.DeleteObject(self.font)
        _g32.DeleteDC(self.dc)
        self.font = self._old_font = None


def _bbox(rects):
    """사각형 목록을 감싼 상자 (왼, 위, 오른, 아래). 비었으면 None — 진단 로그용."""
    if not rects:
        return None
    return (min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects))


def _line_count(rects):
    """줄 사각형 목록의 줄 수 — 세로 구간이 겹치는 사각형은 한 줄로 친다(굵은 글씨 등으로 한 줄이 여러 사각형일 때)."""
    n, end = 0, None
    for top, bottom in sorted((r[1], r[3]) for r in rects or ()):
        if end is None or top >= end:
            n += 1
            end = bottom
        else:
            end = max(end, bottom)
    return n


def _probe_points(box, inset=2):
    """막 영역 (왼, 위, 오른, 아래) 의 가운데와 네 모서리(안쪽으로 inset) — "막 자리가 가려졌나" 볼 점 다섯 개."""
    l, t, r, b = box
    x0, x1 = min(l + inset, r - 1), max(r - 1 - inset, l)
    y0, y1 = min(t + inset, b - 1), max(b - 1 - inset, t)
    return [((l + r) // 2, (t + b) // 2), (x0, y0), (x1, y0), (x0, y1), (x1, y1)]


def _crop_bgra(left, top, w, h, bits, clip):
    """(왼, 위, 너비, 높이, BGRA) 그림을 clip((왼, 위, 오른, 아래) 화면 좌표)과 겹치는 부분만 잘라 같은 모양으로.

    clip 이 None 이면 그대로. 겹치는 곳이 없으면 None.
    """
    if not clip:
        return left, top, w, h, bits
    x0, y0 = max(left, clip[0]), max(top, clip[1])
    x1, y1 = min(left + w, clip[2]), min(top + h, clip[3])
    if x1 <= x0 or y1 <= y0:
        return None
    if (x0, y0, x1, y1) == (left, top, left + w, top + h):
        return left, top, w, h, bits
    a, b = (x0 - left) * 4, (x1 - left) * 4
    rows = [bits[(y * w) * 4 + a:(y * w) * 4 + b] for y in range(y0 - top, y1 - top)]
    return x0, y0, x1 - x0, y1 - y0, b"".join(rows)


def build_caption_bitmap(rects, text, clip=None):
    """번역문 막 그림 한 장. (왼, 위, 너비, 높이, BGRA bytes) — build_overlay_bitmap 과 같은 모양. 보일 곳이 없으면 None.

    rects 는 **잘리기 전** 원래 줄 사각형이다(UIA 가 준 그대로). clip(문서·창의 보이는 영역)은 다 그린 뒤에만 쓴다.
    (2026-09-29 실사용 결함 — 처음엔 clip_rects 로 잘린 사각형을 받아 글꼴·폭을 계산해서, 문단이 일부만 보이면 글씨가
     원문의 절반만 하고 막이 좁아졌다. Codex 분석 docs/codex_rescue/260929_211454_response_highlight-overlay-vanish.md)

    - 자리: 원문 줄 사각형들을 감싼 상자를 테두리+여백만큼 바깥으로 넓힌 곳. 줄마다 너비가 달라도 상자 전체를 덮는다
      (계단 모양으로 남은 원문 글자가 번역문과 겹쳐 보이지 않게).
    - 글자 크기: 원문 줄 높이(사각형 높이의 가운데 값)에 맞춘다. 줄 간격도 원문 줄 높이.
    - 번역문이 원문 상자에 다 안 들어가면 막을 아래로 늘린다(사용자 결정). 위·왼쪽·오른쪽은 원문 자리 그대로.
    - 전부 불투명(알파 255) — 반투명이면 아래 원문 글자가 비쳐 번역문과 겹친다. 그래서 미리 곱하기가 필요 없다.
    - 글자는 GDI(ClearType)로 그린다(위 CAPTION_* 설명). Tk 메인에서만 부른다(_Overlay.show).
    Windows 가 아니거나 GDI 가 실패하면 예외 — 부르는 쪽(_Overlay.show)이 노랑 형광펜으로 되돌린다.
    """
    if not _IS_WIN:
        raise OSError("번역문 막은 Windows 에서만 그린다")
    left = min(r[0] for r in rects)
    top = min(r[1] for r in rects)
    right = max(r[2] for r in rects)
    bottom = max(r[3] for r in rects)
    heights = sorted(r[3] - r[1] for r in rects)
    line_h = max(1, heights[len(heights) // 2])
    inner_w = max(1, right - left)
    edge = CAPTION_BORDER_PX + CAPTION_PAD_PX
    gdi = _GdiText()
    bmp = old_bmp = None
    try:
        gdi.fit(line_h)
        lines = _wrap_caption(text, gdi.width, inner_w)
        inner_h = max(bottom - top, len(lines) * line_h)
        w, h = inner_w + 2 * edge, inner_h + 2 * edge

        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h          # 위→아래
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bits = ctypes.c_void_p()
        bmp = _g32.CreateDIBSection(gdi.dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        if not bmp or not bits.value:
            raise OSError("CreateDIBSection 실패")
        old_bmp = _g32.SelectObject(gdi.dc, bmp)

        # 바탕: 전체를 테두리색으로 칠하고 안쪽을 짙은 회색으로
        b = CAPTION_BORDER_PX
        buf = bytearray(_bgra_opaque(CAPTION_BORDER) * (w * h))
        inner_row = _bgra_opaque(CAPTION_BG) * (w - 2 * b)
        for y in range(b, h - b):
            off = (y * w + b) * 4
            buf[off:off + len(inner_row)] = inner_row
        ctypes.memmove(bits.value, bytes(buf), len(buf))

        _g32.SetBkMode(gdi.dc, _BK_TRANSPARENT)
        _g32.SetTextColor(gdi.dc, CAPTION_FG[0] | (CAPTION_FG[1] << 8) | (CAPTION_FG[2] << 16))
        dy = max(0, (line_h - gdi.height()) // 2)
        for i, line in enumerate(lines):
            if line:
                _g32.TextOutW(gdi.dc, edge, edge + i * line_h + dy, line, _u16len(line))
        _g32.GdiFlush()                      # GDI 는 모아서 그린다 — 비트를 읽기 전에 다 그리게

        out = bytearray(ctypes.string_at(bits.value, w * h * 4))
        out[3::4] = b"\xff" * (w * h)        # GDI 글자는 알파를 0 으로 쓴다 → 막 전체를 불투명으로
        # 다 그린 뒤 보이는 영역만 남긴다 — 문단 일부가 화면 밖이어도 글꼴·줄바꿈은 원래 크기 그대로
        return _crop_bgra(left - edge, top - edge, w, h, bytes(out), clip)
    finally:
        if old_bmp:
            _g32.SelectObject(gdi.dc, old_bmp)
        if bmp:
            _g32.DeleteObject(bmp)
        gdi.close()


# ════════════════════════════════════════════════════════════════════
#  UIA 전용 스레드
# ════════════════════════════════════════════════════════════════════
class _SlowCall(Exception):
    """UIA 호출 하나가 SLOW_CALL_S 를 넘었거나 UIA 제한 시간에 걸림."""


class _Lost(Exception):
    """잡아 둔 요소·범위가 사라짐(UIA_E_ELEMENTNOTAVAILABLE)."""


class _Fail(Exception):
    """begin 실패(이유 문자열)."""


def _hresult(exc):
    """COMError·OSError 에서 HRESULT 를 부호 없는 32비트로. 없으면 None."""
    hr = getattr(exc, "hresult", None)
    if hr is None and getattr(exc, "args", None):
        hr = exc.args[0] if isinstance(exc.args[0], int) else None
    return None if hr is None else hr & 0xFFFFFFFF


def _create_uia():
    """(UIA 스레드에서) comtypes 로 IUIAutomation 을 만든다. (uia, 상수 모듈 U) 를 돌려준다.

    - COM 은 이 스레드를 MTA 로 초기화한다(UIA 클라이언트 권장). comtypes 는 "처음 import 한 스레드"를 import 순간
      초기화하는데 기본이 STA 라서, 처음 import 라면 sys.coinit_flags 를 잠깐 MTA(0)로 두고 import 한다.
      이미 다른 곳에서 import 됐다면 이 스레드를 직접 초기화한다(이미 초기화된 스레드면 그대로 쓴다).
    - comtypes.gen.UIAutomationClient 가 없으면(빌드본 등) UIAutomationCore.dll 에서 만든다.
    - IUIAutomation2 가 되면 Connection/TransactionTimeout 을 UIA_TIMEOUT_MS 로 건다(멈춘 앱에 오래 묶이지 않게).
    """
    if "comtypes" not in sys.modules:
        had = hasattr(sys, "coinit_flags")
        old = getattr(sys, "coinit_flags", None)
        sys.coinit_flags = 0      # COINIT_MULTITHREADED
        try:
            import comtypes  # noqa: F401
        finally:
            if had:
                sys.coinit_flags = old
            else:
                del sys.coinit_flags
    else:
        import comtypes
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            pass                  # 이 스레드가 이미 다른 방식으로 초기화됨 — 그대로 쓴다
    import comtypes.client
    try:
        from comtypes.gen import UIAutomationClient as U
    except ImportError:
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as U
    cls = getattr(U, "CUIAutomation8", None) or U.CUIAutomation
    uia = None
    if hasattr(U, "IUIAutomation2"):
        try:
            uia = comtypes.client.CreateObject(cls, interface=U.IUIAutomation2)
            uia.ConnectionTimeout = UIA_TIMEOUT_MS
            uia.TransactionTimeout = UIA_TIMEOUT_MS
        except Exception as exc:
            log.debug("IUIAutomation2 제한 시간 설정 실패(제한 시간 없이 진행): %s", exc)
            uia = None
    if uia is None:
        uia = comtypes.client.CreateObject(cls, interface=U.IUIAutomation)
    return uia, U


class _Session:
    """한 번의 읽기 동안 UIA 스레드가 쥐고 있는 것들(COM 객체는 이 스레드 밖으로 나가지 않는다)."""

    def __init__(self, gen, doc, sel, ranges):
        self.gen = gen
        self.doc = doc          # TextPattern 을 가진 요소(문서)
        self.sel = sel          # 사용자 선택 범위
        self.ranges = ranges    # 조각별 범위(없으면 None)


class _UiaWorker:
    """UIA 호출을 도맡는 스레드 하나. 요청 큐를 하나씩 처리하고 결과를 post(튜플)로 돌려준다.

    요청: ("begin", gen, source_text, spans, target_pid, own_pid) / ("rects", gen, idx, reveal) / ("end", gen) / ("quit",)
    결과: ("begin_ok", gen, info) / ("begin_fail", gen, reason) / ("rects", gen, idx, rects, doc_rect, scrolled)
          / ("slow", gen, 설명) / ("lost", gen, 설명) / ("error", gen, 설명)
    - current_gen 보다 오래된 요청은 건너뛴다(Tk 쪽이 end·새 begin 으로 무효로 만든 것).
    - call_since: 지금 진행 중인 UIA 호출이 시작된 시각(없으면 None). Tk 틱이 읽어 "1초 넘게 안 돌아옴"을 잡는다.
    """

    def __init__(self, uia_factory, clock, post):
        self._factory = uia_factory
        self._clock = clock
        self._post = post
        self._q = queue.Queue()
        self._uia = None
        self._U = None
        self._uia_error = None
        self._sess = None
        self.current_gen = 0
        self.call_since = None
        self.thread = threading.Thread(target=self._run, name="SourceHighlightUIA", daemon=True)
        self.thread.start()

    # ── Tk 쪽에서 부르는 것 ──
    def submit(self, req):
        self._q.put(req)

    def stuck(self, now):
        """지금 UIA 호출 하나가 SLOW_CALL_S 넘게 안 돌아오고 있는지."""
        since = self.call_since
        return since is not None and now - since > SLOW_CALL_S

    # ── 스레드 ──
    def _run(self):
        # 미리 UIA 객체를 만들어 둔다(다른 앱에 묻는 호출은 아니다). 첫 begin 이 comtypes import 를 기다리지 않게.
        self._get_uia(quiet=True)
        while True:
            req = self._q.get()
            kind = req[0]
            if kind == "quit":
                # COM 객체는 만든 이 스레드에서 놓는다(참조를 남기면 나중에 Tk 메인이 워커 객체를 치울 때 다른 스레드에서
                # Release 가 불린다 — 약속 "COM 객체는 이 스레드 밖으로 내보내지 않는다" 위반)
                self._sess = None
                self._uia = None
                return
            if kind == "end":
                if self._sess is not None and self._sess.gen <= req[1]:
                    self._sess = None
                continue
            if kind == "caret":
                self._caret(req[1])          # 읽기 세션과 무관한 한 번짜리 조회(req[1] = 토큰) — 세대 검사 없음
                continue
            gen = req[1]
            if gen < self.current_gen:
                continue                  # 이미 무효가 된 요청
            try:
                if kind == "begin":
                    self._begin(*req[1:])
                elif kind == "rects":
                    self._rects(*req[1:])
            except _SlowCall as exc:
                self._sess = None
                self._post(("slow", gen, str(exc)))
            except _Lost as exc:
                self._sess = None
                self._post(("lost", gen, str(exc)))
            except _Fail as exc:
                self._sess = None
                self._post(("begin_fail", gen, str(exc)))
            except Exception as exc:     # 예상 못 한 COM 오류 등 — 그 읽기는 칠하기 포기
                log.debug("원문 형광펜 UIA 오류(%s): %r", kind, exc)
                self._sess = None
                self._post(("error", gen, "%s: %r" % (kind, exc)))
            finally:
                self.call_since = None

    def _get_uia(self, quiet=False):
        if self._uia is None and self._uia_error is None:
            try:
                self._uia, self._U = self._factory()
            except Exception as exc:
                self._uia_error = repr(exc)
                if not quiet:
                    log.info("원문 형광펜: UI Automation 을 쓸 수 없음 — %s", exc)
        return self._uia

    def _call(self, label, fn, *args):
        """UIA 호출 하나를 시간을 재며 부른다. SLOW_CALL_S 초과·UIA 제한 시간 → _SlowCall, 요소 사라짐 → _Lost."""
        t0 = self._clock()
        self.call_since = t0
        try:
            result = fn(*args)
        except Exception as exc:
            hr = _hresult(exc)
            if hr == UIA_E_TIMEOUT:
                raise _SlowCall("%s: UIA 제한 시간" % label)
            if hr == UIA_E_ELEMENTNOTAVAILABLE:
                raise _Lost(label)
            if self._clock() - t0 > SLOW_CALL_S:
                raise _SlowCall("%s: %.2fs 뒤 실패" % (label, self._clock() - t0))
            raise
        finally:
            self.call_since = None
        dt = self._clock() - t0
        if dt > SLOW_CALL_S:
            raise _SlowCall("%s: %.2fs" % (label, dt))
        return result

    # ── begin: 선택 잡기 + 조각 범위 만들기 ──
    def _begin(self, gen, source_text, spans, target_pid, own_pid):
        self._sess = None
        uia = self._get_uia()
        if uia is None:
            raise _Fail("uia_unavailable")
        U = self._U
        call = self._call
        focused = call("GetFocusedElement", uia.GetFocusedElement)
        if not focused:
            raise _Fail("no_focus")
        pid = call("CurrentProcessId", lambda: focused.CurrentProcessId)
        if own_pid is not None and pid == own_pid:
            raise _Fail("own_window")
        if target_pid is not None and pid != target_pid:
            raise _Fail("focus_changed")      # begin 뒤 사이에 다른 앱으로 포커스가 옮겨 감
        doc, sel, uia_text, why = self._find_selection(focused)
        if doc is None:
            raise _Fail(why)
        alignment = align_source_to_uia(source_text, uia_text)
        if alignment is None:
            raise _Fail("text_mismatch")
        uia_spans = [alignment.span(s, e) for s, e in spans]
        if not any(uia_spans):
            raise _Fail("no_segments")
        ranges = self._build_ranges(sel, uia_text, uia_spans)
        mapped = [i for i, r in enumerate(ranges) if r is not None]
        if not mapped:
            raise _Fail("range_failed")
        self._sess = _Session(gen, doc, sel, ranges)
        self._post(("begin_ok", gen, {"mapped": mapped, "segments": len(ranges),
                                      "ratio": round(alignment.ratio, 3), "uia_chars": len(uia_text)}))
        self._release_selection(doc, sel)

    def _caret(self, token):
        """(UIA 스레드) 지금 포커스 문서의 선택 "끝 글자 하나" 화면 위치를 묻고 ("caret", 토큰, 결과) 를 돌려준다.

        쓰임: Ctrl+A·Shift+화살표처럼 키보드로 고른 뒤 빨간 점 자리(확장은 선택 마지막 줄 끝 옆 — selection-button.js:116-131).
        결과: (x, y) 끝 글자 오른쪽 가장자리·세로 가운데 / "none" 고른 글이 없다(커서만) / None 모름(부르는 쪽이 마우스 옆에 띄운다).
        ⚠️ 끝 글자 하나짜리 범위만 묻는다 — 선택 전체의 글·사각형은 묻지 않는다(Ctrl+A 면 문서 전체라 VS Code 가 얼 수 있다).
        어떤 예외든(느린 호출 포함) 이 조회만 포기한다 — 원문 형광펜 세션(_sess)은 건드리지 않는다. 결과는 항상 돌려준다.
        """
        result = None
        try:
            if self._get_uia() is not None:
                result = self._selection_end_point()
        except Exception as exc:
            log.debug("선택 끝 위치 조회 실패: %r", exc)
            result = None
        finally:
            self.call_since = None
        self._post(("caret", token, result))

    def _selection_end_point(self):
        """포커스부터 위로 TextPattern 문서를 찾아(_find_selection 과 같은 걸음) 마지막 선택 범위의 끝 글자 위치. 호출 약 10번."""
        U = self._U
        call = self._call
        S, E, CH = U.TextPatternRangeEndpoint_Start, U.TextPatternRangeEndpoint_End, U.TextUnit_Character
        focused = call("GetFocusedElement", self._uia.GetFocusedElement)
        if not focused:
            return None
        walker = call("ControlViewWalker", lambda: self._uia.ControlViewWalker)
        el = focused
        for step in range(MAX_ANCESTOR_STEPS + 1):
            if call("IsTextPatternAvailable", el.GetCurrentPropertyValue, U.UIA_IsTextPatternAvailablePropertyId):
                unk = call("GetCurrentPattern", el.GetCurrentPattern, U.UIA_TextPatternId)
                tp = call("QueryInterface", unk.QueryInterface, U.IUIAutomationTextPattern) if unk else None
                if tp:
                    arr = call("GetSelection", tp.GetSelection)
                    n = call("Length", lambda: arr.Length) if arr else 0
                    if not n:
                        return "none"
                    sel = call("GetElement", arr.GetElement, n - 1)
                    if call("CompareEndpoints", sel.CompareEndpoints, S, sel, E) == 0:
                        return "none"                              # 선택이 비었다(커서만)
                    r = call("Clone", sel.Clone)
                    call("MoveEndpointByRange", r.MoveEndpointByRange, S, r, E)       # 선택 끝에 접고
                    if call("MoveEndpointByUnit", r.MoveEndpointByUnit, S, CH, -1) != -1:  # 끝 글자 하나로 넓힌다
                        return None
                    rects = call("GetBoundingRectangles", r.GetBoundingRectangles)
                    vals = list(rects) if rects else []
                    if len(vals) < 4:
                        return None                                # 끝 글자가 화면 밖(Ctrl+A 는 대개 이 경우) → 마우스 옆
                    x, y, w, h = vals[-4:]
                    return (int(round(x + w)), int(round(y + h / 2.0)))
            if step == MAX_ANCESTOR_STEPS:
                break
            parent = call("GetParentElement", walker.GetParentElement, el)
            if not parent:
                break
            el = parent
        return None

    def _release_selection(self, doc, sel):
        """선택을 푼다 — 확장 releaseSelection(js/page-ui.js:412-427) 과 같은 규칙.

        왜: 파란 선택 색이 형광펜 막 위에 겹쳐 형광펜이 잘 안 보인다(2026-09-28 사용자 요청 "형광펜을 그릴 때 기존 선택은
            해제해야"). 확장도 형광펜이 뜨면 선택을 푼다("the selection's own color is drawn above highlights").
        규칙(확장 그대로): 칠하기를 시작할 때 한 번, **지금 선택의 시작·끝이 잡아 둔 선택(sel)과 똑같을 때만** 푼다.
            사용자가 그사이 다른 곳을 새로 골랐으면 건드리지 않는다.
        방법: UIA 에는 "선택 모두 풀기"(removeAllRanges)가 없다 → 선택 끝에 접은 빈 범위(커서)를 Select 해서 푼다.
            잡아 둔 조각 범위들(_Session.ranges)은 문서 범위라 선택을 풀어도 그대로 쓸 수 있다.
        실패해도 칠하기는 계속한다(선택 색만 남을 뿐). 단 느린 호출·요소 사라짐은 다른 호출과 똑같이 올려 보내
            칠하기를 멈춘다(VS Code 를 얼리지 않는 규칙 — 머리말).
        호출 수: 패턴 2 + 선택 조회 3 + 비교 2 + 복제·접기·선택 3 = 약 10번(각각 한 자리짜리 — 전체 범위 호출 없음).
        """
        U = self._U
        call = self._call
        S, E = U.TextPatternRangeEndpoint_Start, U.TextPatternRangeEndpoint_End
        try:
            unk = call("GetCurrentPattern", doc.GetCurrentPattern, U.UIA_TextPatternId)
            tp = call("QueryInterface", unk.QueryInterface, U.IUIAutomationTextPattern) if unk else None
            if not tp:
                return
            arr = call("GetSelection", tp.GetSelection)
            if not arr or not call("Length", lambda: arr.Length):
                return                                   # 이미 선택이 없다
            cur = call("GetElement", arr.GetElement, 0)
            same = (call("CompareEndpoints", cur.CompareEndpoints, S, sel, S) == 0
                    and call("CompareEndpoints", cur.CompareEndpoints, E, sel, E) == 0)
            if not same:
                return                                   # 사용자가 다른 곳을 새로 골랐다 — 그대로 둔다
            caret = call("Clone", sel.Clone)
            call("MoveEndpointByRange", caret.MoveEndpointByRange, S, caret, E)   # 선택 끝에 접기
            call("Select", caret.Select)
        except (_SlowCall, _Lost):
            raise
        except Exception as exc:
            log.debug("원문 형광펜: 선택 풀기 실패(선택 색만 남음): %r", exc)

    def _find_selection(self, focused):
        """포커스 요소부터 위로 최대 MAX_ANCESTOR_STEPS 단계에서 TextPattern 이 있고 선택 글이 비지 않은 첫 요소.

        돌려줌: (문서 요소, 선택 범위, 선택 글, 실패 이유). 걷기만 한다 — 트리 훑기(FindAll)는 금지(머리말).
        TextPattern 이 있는데 선택이 비었으면(예: 입력칸) 더 위로 올라가 본다.
        """
        U = self._U
        call = self._call
        walker = call("ControlViewWalker", lambda: self._uia.ControlViewWalker)
        el = focused
        why = "no_text_pattern"
        for step in range(MAX_ANCESTOR_STEPS + 1):
            if call("IsTextPatternAvailable", el.GetCurrentPropertyValue, U.UIA_IsTextPatternAvailablePropertyId):
                unk = call("GetCurrentPattern", el.GetCurrentPattern, U.UIA_TextPatternId)
                tp = call("QueryInterface", unk.QueryInterface, U.IUIAutomationTextPattern) if unk else None
                if tp:
                    arr = call("GetSelection", tp.GetSelection)
                    n = call("Length", lambda: arr.Length) if arr else 0
                    if n:
                        sel = call("GetElement", arr.GetElement, 0)
                        text = call("GetText", sel.GetText, -1) if sel else ""
                        if text and _squash(text):
                            return el, sel, text, None
                        why = "empty_selection"
                    elif why == "no_text_pattern":
                        why = "no_selection"
            if step == MAX_ANCESTOR_STEPS:
                break
            parent = call("GetParentElement", walker.GetParentElement, el)
            if not parent:
                break
            el = parent
        return None, None, None, why

    def _build_ranges(self, sel, uia_text, uia_spans):
        """조각마다 선택 범위를 복제해 [시작, 끝) 글자 묶음으로 줄인 범위를 만든다(앞 조각에서 이어서 옮긴다).

        만든 범위는 GetText 로 기대 글과 같은지 확인하고(공백 무시), 다르면 그 조각 글로 FindText 한다
        — 검색 범위는 "마지막으로 맞은 조각 끝 ~ 선택 끝"뿐이다(문서 전체 금지). 둘 다 안 되면 그 조각은 None.
        """
        U = self._U
        call = self._call
        S, E, CH = U.TextPatternRangeEndpoint_Start, U.TextPatternRangeEndpoint_End, U.TextUnit_Character
        cum = grapheme_counts(uia_text)
        base = call("Clone", sel.Clone)                                  # 선택 시작에 접힌 커서
        call("MoveEndpointByRange", base.MoveEndpointByRange, E, base, S)
        pos = 0
        good_end = call("Clone", base.Clone)                             # 마지막으로 맞은 조각 끝
        ranges = []
        for span in uia_spans:
            if span is None:
                ranges.append(None)
                continue
            a, b = span
            ga, gb = _g_floor(cum, a), _g_ceil(cum, b)
            expected = _squash(uia_text[a:b])
            rng = None
            if ga >= pos and gb > ga:
                r = call("Clone", base.Clone)
                moved = call("MoveEndpointByUnit", r.MoveEndpointByUnit, S, CH, ga - pos) if ga > pos else 0
                if moved == ga - pos:
                    call("MoveEndpointByRange", r.MoveEndpointByRange, E, r, S)
                    base, pos = call("Clone", r.Clone), ga
                    moved2 = call("MoveEndpointByUnit", r.MoveEndpointByUnit, E, CH, gb - ga)
                    if moved2 == gb - ga:
                        rng = self._trim_verify(r, uia_text[a:b], expected)
            if rng is None:
                rng = self._find_in_selection(good_end, sel, uia_text[a:b].strip(), expected)
            if rng is not None:
                good_end = call("Clone", rng.Clone)
                call("MoveEndpointByRange", good_end.MoveEndpointByRange, S, good_end, E)
            ranges.append(rng)
        return ranges

    def _trim_verify(self, r, raw, expected):
        """범위 r 의 글이 기대 글과 같으면 r(또는 앞뒤 공백을 뺀 범위)을, 아니면 None 을 돌려준다.

        왜: 크로미움은 블록 경계(<br>·목록 사이)에서 GetText 의 "\\n" 과 Character 칸이 어긋날 때가 있다
        (Edge 실측 2026-09-28: "셋째 문단: 줄바꿈<br>두 번째…" 조각이 "\\n두 번째…" 로 한 칸 앞에서 시작했고,
        시작을 한 칸 옮기면 "\\n" 이 아니라 "두" 까지 건너뛰었다 — 칸 수로는 못 고친다).
        공백만 무시하고 넘어가면 막이 앞 줄 끝(줄바꿈 자리)까지 칠해질 수 있어, 앞뒤에 공백이 끼면
        그 범위 "안에서만" 기대 글(앞뒤 공백 뺀 것)을 FindText 로 다시 잡는다.
        """
        call = self._call
        got = call("GetText", r.GetText, -1) or ""
        if _squash(got) != expected:
            return None
        if got == got.strip():
            return r
        found = call("FindText", r.FindText, raw.strip(), False, False)
        if not found:
            return None
        got = call("GetText", found.GetText, -1) or ""
        return found if got == got.strip() and _squash(got) == expected else None

    def _find_in_selection(self, start_at, sel, text, expected):
        """start_at(접힌 범위) ~ 선택 끝 안에서 text 를 FindText 로 찾아 검증한다. 못 찾으면 None."""
        if not text:
            return None
        U = self._U
        call = self._call
        E = U.TextPatternRangeEndpoint_End
        area = call("Clone", start_at.Clone)
        call("MoveEndpointByRange", area.MoveEndpointByRange, E, sel, E)
        found = call("FindText", area.FindText, text, False, False)
        if found and _squash(call("GetText", found.GetText, -1) or "") == expected:
            return found
        return None

    # ── rects: 지금 조각 사각형(필요하면 먼저 보이게 스크롤) ──
    def _rects(self, gen, idx, reveal):
        s = self._sess
        if s is None or s.gen != gen:
            # 쥐고 있던 범위가 없다(앞 오류로 버림 등) — 답을 안 하면 Tk 쪽이 "보낸 요청 대기"에 영영 묶인다
            self._post(("lost", gen, "no session"))
            return
        r = s.ranges[idx] if 0 <= idx < len(s.ranges) else None
        if r is None:
            self._post(("rects", gen, idx, [], None, False))
            return
        call = self._call
        arr = call("GetBoundingRectangles", r.GetBoundingRectangles)
        rects = rects_from_uia(arr)
        # 문서 영역(= 보이는 화면)을 먼저 받는다: 자르기에도 쓰고, "보이나" 판단(_needs_reveal)에도 쓴다
        dr = call("CurrentBoundingRectangle", lambda: s.doc.CurrentBoundingRectangle)
        doc_rect = (dr.left, dr.top, dr.right, dr.bottom) if dr is not None else None
        scrolled = False
        if reveal and self._needs_reveal(r, arr, doc_rect):
            # 확장 revealRanges(page-ui.js:436-483): 이미 다 보이면 안 움직인다.
            # 스크롤은 비동기라 사각형은 Tk 쪽이 몇 틱 동안 다시 받는다(SETTLE_TICKS).
            self._reveal(r)
            scrolled = True
        self._post(("rects", gen, idx, rects, doc_rect, scrolled))

    def _reveal(self, r):
        """조각이 보이게 스크롤한다 — 두 가지를 차례로 부른다(Edge 154 실측 2026-09-28, scratchpad phase4\\probe3.json).

        1) 조각 첫 글자를 감싼 요소(GetEnclosingElement — 보통 그 문단의 Text 요소)의 ScrollItemPattern.ScrollIntoView.
           실측: 문단 하나 안에 든 범위는 TextRange.ScrollIntoView(True/False)·앞으로 한 칸 넓히기·문단으로 넓히기가
           전부 아무 효과가 없었고, 이것만 움직였다(그 문단을 화면 가운데쯤으로 — 확장의 "가운데 맞춤"과 비슷).
           그 요소에 패턴이 없으면 부모 하나까지만 본다(트리 훑기 아님).
        2) 범위 자체의 TextRange.ScrollIntoView(True). 실측: 두 문단에 걸친 범위는 이것으로 움직였다(위에 맞춤).
           한 문단 안 범위에는 효과가 없으므로 1)의 결과를 덮지 않는다.
        함정: VS Code 채팅 목록(monaco 가상 목록)에서 이 스크롤이 먹히는지는 확인하지 못했다(사용자 VS Code 조회 금지).
        """
        U = self._U
        call = self._call
        S, E, CH = U.TextPatternRangeEndpoint_Start, U.TextPatternRangeEndpoint_End, U.TextUnit_Character
        head = call("Clone", r.Clone)
        call("MoveEndpointByRange", head.MoveEndpointByRange, E, head, S)
        call("MoveEndpointByUnit", head.MoveEndpointByUnit, E, CH, 1)
        el = call("GetEnclosingElement", head.GetEnclosingElement)
        for _ in range(2):
            if not el:
                break
            unk = call("GetCurrentPattern", el.GetCurrentPattern, U.UIA_ScrollItemPatternId)
            sip = call("QueryInterface", unk.QueryInterface, U.IUIAutomationScrollItemPattern) if unk else None
            if sip:
                call("ScrollItem.ScrollIntoView", sip.ScrollIntoView)
                break
            el = call("GetParentElement", self._uia.ControlViewWalker.GetParentElement, el)
        call("ScrollIntoView", r.ScrollIntoView, True)

    def _needs_reveal(self, r, arr, view):
        """조각의 첫 글자·마지막 글자가 둘 다 화면(view)에 있으면 False(스크롤 안 함). 범위 사각형이 아예 없으면 True.

        arr = 조각 범위의 GetBoundingRectangles 원시 배열, view = 문서 영역(없으면 None).
        함정(2026-09-28 반증): 예전에는 그리기용 rects_from_uia(폭 1px 이하 뺌)로 판단해서, 범위 끝이 문단 사이 "\\n" 에
          걸린 조각(크로미움이 끝 글자 자리로 1px 사각형만 줌)을 "끝이 안 보임"으로 읽고 다 보이는데도 스크롤했다.
          → 보이나 판단은 uia_on_screen(1px 사각형도 화면 안 증거로 침)으로 한다.
        """
        if not uia_on_screen(arr, view):
            return True
        U = self._U
        call = self._call
        S, E, CH = U.TextPatternRangeEndpoint_Start, U.TextPatternRangeEndpoint_End, U.TextUnit_Character
        head = call("Clone", r.Clone)
        call("MoveEndpointByRange", head.MoveEndpointByRange, E, head, S)
        call("MoveEndpointByUnit", head.MoveEndpointByUnit, E, CH, 1)
        if not uia_on_screen(call("GetBoundingRectangles", head.GetBoundingRectangles), view):
            return True
        tail = call("Clone", r.Clone)
        call("MoveEndpointByRange", tail.MoveEndpointByRange, S, tail, E)
        call("MoveEndpointByUnit", tail.MoveEndpointByUnit, S, CH, -1)
        return not uia_on_screen(call("GetBoundingRectangles", tail.GetBoundingRectangles), view)


# ════════════════════════════════════════════════════════════════════
#  Win32 — 이 모듈 전용 WinDLL(공용 ctypes.windll 에 형 선언을 걸면 whisperer.py 호출 방식까지 바뀐다)
# ════════════════════════════════════════════════════════════════════
_IS_WIN = sys.platform == "win32"

GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
GA_ROOT = 2
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_NOOWNERZORDER = 0x0200
HWND_TOPMOST = -1
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _g32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _LONG_PTR = ctypes.c_ssize_t
    _GetWindowLongPtr = getattr(_u32, "GetWindowLongPtrW", _u32.GetWindowLongW)
    _SetWindowLongPtr = getattr(_u32, "SetWindowLongPtrW", _u32.SetWindowLongW)
    _GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
    _GetWindowLongPtr.restype = _LONG_PTR
    _SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, _LONG_PTR]
    _SetWindowLongPtr.restype = _LONG_PTR

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

    _u32.GetForegroundWindow.argtypes = []
    _u32.GetForegroundWindow.restype = wintypes.HWND
    _u32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _u32.GetAncestor.restype = wintypes.HWND
    _u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _u32.GetWindowRect.restype = wintypes.BOOL
    _u32.IsWindow.argtypes = [wintypes.HWND]
    _u32.IsWindow.restype = wintypes.BOOL
    _u32.IsIconic.argtypes = [wintypes.HWND]
    _u32.IsIconic.restype = wintypes.BOOL
    _u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _u32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _u32.GetParent.argtypes = [wintypes.HWND]
    _u32.GetParent.restype = wintypes.HWND
    _u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _u32.ShowWindow.restype = wintypes.BOOL
    _u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _u32.SetWindowPos.restype = wintypes.BOOL
    _u32.WindowFromPoint.argtypes = [wintypes.POINT]
    _u32.WindowFromPoint.restype = wintypes.HWND
    _u32.GetDC.argtypes = [wintypes.HWND]
    _u32.GetDC.restype = wintypes.HDC
    _u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _u32.ReleaseDC.restype = ctypes.c_int
    _u32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                         ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                         ctypes.POINTER(wintypes.POINT), wintypes.DWORD,
                                         ctypes.POINTER(_BLENDFUNCTION), wintypes.DWORD]
    _u32.UpdateLayeredWindow.restype = wintypes.BOOL
    _g32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    _g32.CreateCompatibleDC.restype = wintypes.HDC
    _g32.DeleteDC.argtypes = [wintypes.HDC]
    _g32.DeleteDC.restype = wintypes.BOOL
    _g32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(_BITMAPINFO), wintypes.UINT,
                                      ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    _g32.CreateDIBSection.restype = wintypes.HBITMAP
    _g32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    _g32.SelectObject.restype = wintypes.HGDIOBJ
    _g32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    _g32.DeleteObject.restype = wintypes.BOOL

    # 번역문 막 글자(build_caption_bitmap, 2026-09-29) — GDI + ClearType
    class _TEXTMETRICW(ctypes.Structure):
        _fields_ = [("tmHeight", wintypes.LONG), ("tmAscent", wintypes.LONG), ("tmDescent", wintypes.LONG),
                    ("tmInternalLeading", wintypes.LONG), ("tmExternalLeading", wintypes.LONG),
                    ("tmAveCharWidth", wintypes.LONG), ("tmMaxCharWidth", wintypes.LONG),
                    ("tmWeight", wintypes.LONG), ("tmOverhang", wintypes.LONG),
                    ("tmDigitizedAspectX", wintypes.LONG), ("tmDigitizedAspectY", wintypes.LONG),
                    ("tmFirstChar", wintypes.WCHAR), ("tmLastChar", wintypes.WCHAR),
                    ("tmDefaultChar", wintypes.WCHAR), ("tmBreakChar", wintypes.WCHAR),
                    ("tmItalic", wintypes.BYTE), ("tmUnderlined", wintypes.BYTE), ("tmStruckOut", wintypes.BYTE),
                    ("tmPitchAndFamily", wintypes.BYTE), ("tmCharSet", wintypes.BYTE)]

    _g32.CreateFontW.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR]
    _g32.CreateFontW.restype = wintypes.HFONT
    _g32.GetTextMetricsW.argtypes = [wintypes.HDC, ctypes.POINTER(_TEXTMETRICW)]
    _g32.GetTextMetricsW.restype = wintypes.BOOL
    _g32.GetTextExtentPoint32W.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.SIZE)]
    _g32.GetTextExtentPoint32W.restype = wintypes.BOOL
    _g32.TextOutW.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int]
    _g32.TextOutW.restype = wintypes.BOOL
    _g32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    _g32.SetTextColor.restype = wintypes.COLORREF
    _g32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
    _g32.SetBkMode.restype = ctypes.c_int
    _g32.GdiFlush.argtypes = []
    _g32.GdiFlush.restype = wintypes.BOOL


class _Win32Env:
    """Tk 메인에서 쓰는 가벼운 Win32 조회(UIA 아님). 테스트는 같은 이름의 가짜로 바꿔 끼운다."""

    own_pid = os.getpid()

    def foreground_root(self):
        """지금 전경 창의 최상위 창 핸들(int) 또는 None."""
        fg = _u32.GetForegroundWindow()
        if not fg:
            return None
        root = _u32.GetAncestor(fg, GA_ROOT)
        return int(root or fg)

    def window_rect(self, hwnd):
        r = wintypes.RECT()
        if not _u32.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
        return (r.left, r.top, r.right, r.bottom)

    def is_window(self, hwnd):
        return bool(_u32.IsWindow(hwnd))

    def is_iconic(self, hwnd):
        return bool(_u32.IsIconic(hwnd))

    def pid_of(self, hwnd):
        pid = wintypes.DWORD()
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def root_at(self, x, y):
        """화면 점 (x, y) 에서 맨 위에 있는 창의 최상위 창 핸들(int) 또는 None — "막 자리가 가려졌나" 판정용.

        WindowFromPoint 는 숨긴 창을 건너뛴다. 막 창(클릭 통과)이 잡히더라도 부르는 쪽이 이 앱 창은 가림으로 치지 않는다.
        """
        h = _u32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
        if not h:
            return None
        root = _u32.GetAncestor(h, GA_ROOT)
        return int(root or h)


def _no_autostyle(cls):
    """ttkbootstrap 이 tk 위젯 생성자를 바꿔치기했으면 {"autostyle": False} (selection_button.py 와 같은 판정)."""
    init = getattr(cls, "__init__", None)
    if getattr(init, "__name__", "") == "__init__wrapper":
        return {"autostyle": False}
    return {}


def _ulw(hwnd, left, top, w, h, bgra):
    """UpdateLayeredWindow 로 창 위치·크기·그림을 한 번에 바꾼다(깜빡임 없음). 성공하면 True.

    selection_button._update_layered 와 같은 순서(화면 DC → 메모리 DC → 32비트 DIB(위→아래) → ULW → 뒷정리)에
    위치(pptDst)·크기(psize)를 함께 넘긴다. 이 창에는 SetLayeredWindowAttributes 를 부르지 않는다(섞으면 ULW 실패).
    """
    screen = mem = bmp = old = None
    try:
        screen = _u32.GetDC(None)
        mem = _g32.CreateCompatibleDC(screen)
        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        bits = ctypes.c_void_p()
        bmp = _g32.CreateDIBSection(mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        if not bmp or not bits.value:
            return False
        ctypes.memmove(bits.value, bgra, len(bgra))
        old = _g32.SelectObject(mem, bmp)
        dst = wintypes.POINT(left, top)
        size = wintypes.SIZE(w, h)
        src = wintypes.POINT(0, 0)
        blend = _BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        return bool(_u32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(dst), ctypes.byref(size), mem,
                                             ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA))
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


class _Overlay:
    """원문 위 형광펜 막 창 하나(Tk Toplevel 틀 + Win32 층 창). 모든 메서드는 Tk 메인에서만.

    - 스타일: LAYERED(픽셀마다 알파) | TRANSPARENT(클릭이 아래 앱으로 통과) | NOACTIVATE(포커스 안 뺏음)
      | TOOLWINDOW(작업표시줄·Alt+Tab 제외), APPWINDOW 끔, 소유자 없음, 항상 위(HWND_TOPMOST).
    - 그림: 줄 사각형들을 감싼 그림 한 장(build_overlay_bitmap)을 UpdateLayeredWindow 로 위치·크기와 함께 올린다.
    - 같은 사각형이면 다시 그리지 않는다.
    """

    def __init__(self, root):
        self._root = root
        self._win = None
        self._styled = None
        self._shown = False
        self._drawn = None
        self._destroyed = False

    def _hwnd(self):
        """틀 핸들(없으면 만든다). Tk 가 틀을 새로 만들었으면 스타일을 다시 건다."""
        import tkinter as tk
        if self._destroyed:
            return None
        if self._win is None:
            win = tk.Toplevel(self._root, **_no_autostyle(tk.Toplevel))
            # ⚠ 처음 화면에 붙기 전에 건다(매핑 뒤에 바꾸면 Tk 가 틀을 새로 만든다 — selection_button.py 함정 3)
            win.withdraw()
            win.overrideredirect(True)
            try:
                win.attributes("-topmost", True)
            except tk.TclError:
                pass
            win.configure(background="#ffe200", borderwidth=0, highlightthickness=0)
            win.title("BluemingReadAloud highlight")
            win.update_idletasks()
            self._win = win
        try:
            hwnd = int(_u32.GetParent(self._win.winfo_id()) or 0)
        except Exception:
            return None
        if not hwnd:
            return None
        if self._styled != hwnd:
            ex = _GetWindowLongPtr(hwnd, GWL_EXSTYLE)
            want = (ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            _SetWindowLongPtr(hwnd, GWLP_HWNDPARENT, 0)
            if want != ex:
                _SetWindowLongPtr(hwnd, GWL_EXSTYLE, want)
            _u32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                              SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOOWNERZORDER)
            self._styled = hwnd
            self._drawn = None
        return hwnd

    @property
    def hwnd(self):
        return self._styled

    def show(self, rects, caption=None, caption_src=None, clip=None):
        """rects(화면 좌표 (왼, 위, 오른, 아래) 목록 — 보이는 영역으로 자른 것)를 칠해 보인다. 비었으면 숨긴다.

        caption(번역문)이 있으면 노랑 대신 번역문 막(build_caption_bitmap)으로 그린다. 그때 크기 계산은 caption_src
        (잘리기 전 원래 사각형 — 없으면 rects)로 하고 clip(보이는 영역)으로 마지막에 자른다. 그리다 실패하면 노랑으로.
        돌려주는 값: 실제로 보이게 했으면 True, 아니면 False(부르는 쪽이 "보임" 기록을 이것으로 정한다).
        """
        if self._destroyed:
            return False
        if not rects:
            self.hide()
            return False
        hwnd = self._hwnd()
        if not hwnd:
            return False
        key = (tuple(rects), caption, tuple(caption_src) if caption_src else None, clip)
        if key != self._drawn:
            bitmap = None
            if caption:
                try:
                    bitmap = build_caption_bitmap(caption_src or rects, caption, clip)
                except Exception:
                    log.exception("번역문 막 그리기 실패 — 노랑 형광펜으로 칠한다")
            if bitmap is None:
                bitmap = build_overlay_bitmap(rects)
            left, top, w, h, bits = bitmap
            if not _ulw(hwnd, left, top, w, h, bits):
                log.warning("원문 형광펜: UpdateLayeredWindow 실패 — 막을 숨긴다")
                self.hide()
                return False
            self._drawn = key
        if not self._shown:
            _u32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            self._shown = True
        _u32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                          SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
        return True

    def hide(self):
        if self._shown and self._styled:
            _u32.ShowWindow(self._styled, SW_HIDE)
        self._shown = False

    def destroy(self):
        self.hide()
        self._destroyed = True
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None


# ════════════════════════════════════════════════════════════════════
#  공개 클래스
# ════════════════════════════════════════════════════════════════════
class SourceHighlighter:
    """읽는 조각을 원문(다른 앱 화면) 위에 반투명 노랑으로 칠한다. 약속은 모듈 머리말 참고.

    테스트용 인자(평소엔 넘기지 않는다): uia_factory(UIA 객체 만들기), overlay_factory(막 창), win_env(Win32 조회),
    clock(초 단위 시계).
    """

    def __init__(self, root, on_stop=None, *, uia_factory=None, overlay_factory=None, win_env=None, clock=None):
        self._root = root
        self._on_stop = on_stop
        self._clock = clock or time.monotonic
        self._win = win_env if win_env is not None else (_Win32Env() if _IS_WIN else None)
        self._overlay_factory = overlay_factory or _Overlay
        self._overlay = None
        self._results = queue.SimpleQueue()
        self._worker = None
        if self._win is not None:
            self._worker = _UiaWorker(uia_factory or _create_uia, self._clock, self._results.put)
        self._owner_thread = threading.current_thread()
        self._destroyed = False
        self._tick_id = None
        self._gen = 0
        self._state = "idle"           # idle | pending(begin 결과 기다림) | active
        self._on_result = None
        self._scroll_flag = False      # notify_scroll 이 아무 스레드에서나 세운다(대입 하나라 안전)
        # 막이 지금 보이는가 — 보임↔숨김이 바뀔 때만 이유를 로그에 남긴다(2026-09-29 "형광펜이 가끔 사라진다" 진단용.
        # 틱은 50ms 라 매번 찍으면 로그가 넘친다)
        self._overlay_visible = False
        self._hidden_reason = None     # 마지막으로 숨긴 이유 — 숨긴 채로 이유가 바뀔 때도 남긴다
        self._last_rects_note = None   # 마지막으로 기록한 위치 결과 요약(조각, 사각형 수, 스크롤함) — 바뀔 때만 남긴다
        self._caret_token = 0          # query_selection_end 요청 번호
        self._caret_waiting = {}       # 요청 번호 → on_done (결과가 오면 Tk 틱이 부른다)
        self._reset_view()

    def _reset_view(self):
        """한 읽기 동안의 화면 쪽 상태를 처음으로."""
        self._target_root = None
        self._target_pid = None
        self._mapped = set()
        self._want_idx = None          # 마지막으로 highlight 로 받은 번호(begin 결과 전에 와도 기억)
        self._want_caption = None      # 그 번호와 함께 받은 번역문(없으면 None — 노랑 형광펜)
        self._current_idx = None       # 지금 칠하는 번호
        self._current_caption = None   # 지금 칠하는 번호의 번역문
        self._fg_ok = None             # 대상 창이 전경인지(None = 아직 모름)
        self._last_win_rect = None
        self._doc_rect = None
        self._raw_rects = []
        self._inflight = False
        self._need_query = False
        self._reveal_pending = False
        self._settle_left = 0
        # 휠 뒤 "스크롤 중" 으로 막을 숨겨 두는 남은 틱. 0 이 되면(마지막 휠에서 SETTLE_TICKS 뒤) 한 번 물어 다시 그린다.
        # 2026-09-29 사용자 결정 "스크롤 중엔 숨기기" — 막은 다른 창이라 원문 스크롤보다 늦게 따라가 밀려 보였다.
        self._scroll_hold = 0
        self._next_refresh = None
        # 조각 번호 → 지금까지 받은 가장 많은 줄 수. 지금 보이는 줄이 이보다 적거나 경계에 잘리면 "문단 일부만 보임"
        # → 번역문 막 대신 노랑(2026-09-29 사용자 결정). 윈도우는 화면 밖 줄 위치를 안 줘서 문단 전체 크기를 따로 모른다.
        # 창 크기가 바뀌면(줄바꿈이 달라짐) 비운다.
        self._full_lines = {}
        self._partial_noted = False    # "일부만 보여 노랑" 을 로그에 남겼나(바뀔 때만 남긴다)
        # 마지막으로 그린 막 영역(보이는 부분). 대상 창이 앞 창이 아닐 때 "막 자리가 가려졌나" 를 이 자리로 본다
        self._shown_box = None

    # ── 약속된 메서드 ───────────────────────────────────────────────────

    @property
    def active(self):
        """begin 이 성공해 지금 원문 위 칠하기가 동작 중이면 True."""
        return self._state == "active"

    def begin(self, source_text, segments, on_result):
        """지금 전경 앱의 선택을 잡아 조각 위치를 맞춘다. 결과는 나중에 on_result(ok, reason) (Tk 메인).

        앞 읽기가 남아 있으면 먼저 정리한다(그 읽기의 on_result 는 부르지 않는다).
        함정: 그래서 highlight 는 begin "뒤에" 불러야 한다(begin 앞에 부른 번호는 지워진다). begin 결과가 오기 전에
        부른 highlight 는 기억했다가 결과가 오면 칠한다.
        UIA 는 부르지 않는다 — 전경 창만 Win32 로 확인하고 UIA 스레드에 맡긴다.
        """
        self._check_thread("begin")
        self._finish_session(notify_worker=True)
        self._gen += 1
        gen = self._gen
        self._on_result = on_result
        self._state = "pending"
        spans = []
        for seg in segments or ():
            try:
                spans.append((seg.get("src_start"), seg.get("src_end")))
            except AttributeError:
                spans.append((None, None))
        fail = None
        root_hwnd = pid = None
        # 원문 위치가 있는 조각이 하나도 없으면(조각 0개·전부 src_start None) UIA 를 아예 부르지 않는다.
        # 예전에는 선택 잡기·맞추기까지 다 하고 나서야 "no_segments" 로 실패했다 — 쓸데없이 사용자 앱에 묻는 호출이었다.
        has_span = any(s is not None and e is not None and e > s for s, e in spans)
        if self._destroyed:
            fail = "destroyed"
        elif self._win is None or self._worker is None:
            fail = "not_windows"
        elif not has_span:
            fail = "no_segments"
        else:
            root_hwnd = self._win.foreground_root()
            if not root_hwnd:
                fail = "no_foreground"
            else:
                pid = self._win.pid_of(root_hwnd)
                if pid == self._win.own_pid:
                    fail = "own_window"
                elif self._worker.stuck(self._clock()):
                    fail = "uia_busy"        # 앞 읽기의 호출이 아직 안 돌아옴 — 새로 쌓지 않는다
        if fail:
            self._results.put(("begin_fail", gen, fail))
        else:
            self._target_root, self._target_pid = root_hwnd, pid
            self._worker.current_gen = gen
            self._worker.submit(("begin", gen, source_text or "", spans, pid, self._win.own_pid))
        self._schedule_tick()

    def highlight(self, idx, caption=None):
        """idx 조각을 칠한다. None 이면 지운다. 조각이 바뀔 때만 화면 밖이면 보이게 스크롤한다(확장 revealRanges).

        caption(번역문, 2026-09-29)이 있으면 그 조각은 번역문 막으로 덮는다(build_caption_bitmap). 같은 번호에 번역문만
        달라지면 다시 묻지 않고(스크롤 없이) 받아 둔 사각형으로 다시 그린다.
        """
        self._check_thread("highlight")
        if idx is None:
            self._want_idx = None
            self._want_caption = None
            self._current_idx = None
            self._current_caption = None
            self._raw_rects = []
            self._hide_overlay("지우기 요청(highlight None)")
            return
        self._want_idx = idx
        self._want_caption = caption or None
        if self._state != "active":
            return
        if idx == self._current_idx:
            if self._want_caption != self._current_caption:
                self._current_caption = self._want_caption
                self._redraw()
            return
        self._select(idx)

    def notify_scroll(self):
        """휠이 굴렀다(어느 스레드에서 불러도 된다). 다음 틱부터 몇 번 사각형을 다시 받는다 — 연달아 와도 묶인다."""
        self._scroll_flag = True

    def query_selection_end(self, on_done):
        """(Tk 메인) 지금 전경 앱 선택의 "끝 글자" 화면 위치를 묻는다 — 키보드로 고른 뒤(Ctrl+A 등) 빨간 점 자리용.

        결과는 나중에 Tk 메인에서 on_done(pos): (x, y) / "none"(고른 글 없음 — 점을 띄우지 말 것) / None(모름 — 마우스 옆에).
        읽기 세션(begin~end)과 무관하게 언제든 부를 수 있다. UIA 는 전용 스레드에서만 묻는다(_UiaWorker._caret).
        앞 호출이 1초 넘게 안 돌아와 워커가 막혀 있으면 묻지 않고 곧바로 None(VS Code 가 느릴 때 더 쌓지 않는다).
        """
        self._check_thread("query_selection_end")
        if self._destroyed or self._worker is None or self._worker.stuck(self._clock()):
            self._root.after(0, on_done, None)
            return
        self._caret_token += 1
        token = self._caret_token
        self._caret_waiting[token] = on_done
        self._worker.submit(("caret", token))
        self._schedule_tick()

    def end(self):
        """막을 지우고 잡은 범위를 놓는다. end 뒤에는 on_result·on_stop 을 부르지 않는다."""
        self._check_thread("end")
        self._finish_session(notify_worker=True)

    def destroy(self):
        """앱 종료 때. 두 번 불러도 된다."""
        if self._destroyed:
            return
        self._finish_session(notify_worker=True)
        self._destroyed = True
        if self._tick_id is not None:
            try:
                self._root.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None
        if self._worker is not None:
            self._worker.submit(("quit",))
        if self._overlay is not None:
            self._overlay.destroy()
            self._overlay = None

    # ── 세션 정리 ──────────────────────────────────────────────────────

    def _finish_session(self, notify_worker):
        """지금 읽기를 끝낸다(결과 무효화 + 막 숨김 + UIA 스레드에 범위 놓기)."""
        if self._state != "idle":
            self._gen += 1                                 # 오는 중인 결과를 버리게
            if self._worker is not None:
                self._worker.current_gen = self._gen
                if notify_worker:
                    self._worker.submit(("end", self._gen))
        self._state = "idle"
        self._on_result = None
        self._hide_overlay("읽기 끝")
        self._reset_view()

    def _stop(self, reason):
        """읽는 도중 칠하기를 멈춘다(느림·범위 잃음·대상 창 닫힘). begin 결과 전이면 on_result(False)."""
        was = self._state
        cb = self._on_result
        self._finish_session(notify_worker=True)
        if was == "pending" and cb is not None:
            self._deliver(cb, False, reason)
        elif was == "active" and self._on_stop is not None:
            try:
                self._on_stop(reason)
            except Exception:
                log.exception("원문 형광펜 on_stop 실패")
        log.info("원문 형광펜 중단: %s", reason)

    @staticmethod
    def _deliver(cb, ok, reason):
        try:
            cb(ok, reason)
        except Exception:
            log.exception("원문 형광펜 on_result 실패")

    # ── Tk 틱 ─────────────────────────────────────────────────────────

    def _schedule_tick(self):
        if self._tick_id is None and not self._destroyed:
            self._tick_id = self._root.after(WATCH_MS, self._tick)

    def _tick(self):
        """WATCH_MS 마다(Tk 메인): 결과 받기 → 1초 감시 → 전경·창 이동·휠 → 사각형 다시 받기."""
        self._tick_id = None
        if self._destroyed:
            return
        self._drain()
        if self._state == "idle":
            if not self._results.empty() or self._caret_waiting:
                self._schedule_tick()            # 읽기가 없어도 선택 끝 위치 결과는 받아야 한다
            return
        now = self._clock()
        if self._worker is not None and self._worker.stuck(now):
            self._stop("slow")                 # 호출 하나가 1초 넘게 안 돌아온다 — 그 읽기 동안 중단
            return
        if self._state == "active":
            self._watch(now)
        if self._state != "idle":
            self._schedule_tick()

    def _drain(self):
        while True:
            try:
                msg = self._results.get_nowait()
            except queue.Empty:
                return
            self._handle(msg)

    def _handle(self, msg):
        kind, gen = msg[0], msg[1]
        if kind == "caret":                      # query_selection_end 결과 — 읽기 세대와 무관(msg[1] = 요청 번호)
            cb = self._caret_waiting.pop(gen, None)
            if cb is not None:
                try:
                    cb(msg[2])
                except Exception:
                    log.exception("선택 끝 위치 on_done 실패")
            return
        if kind == "rects" and gen == self._gen:
            self._inflight = False
        if gen != self._gen or self._state == "idle":
            return                               # 끝났거나 새 읽기로 바뀐 뒤 도착한 결과
        if kind == "begin_ok" and self._state == "pending":
            info = msg[2]
            self._state = "active"
            self._mapped = set(info.get("mapped", ()))
            self._last_win_rect = self._win.window_rect(self._target_root)
            # 첫 그리기 전에 전경 여부를 바로 정한다(그 사이 다른 창으로 옮겼으면 그 창 위에 한 틱이라도 칠하지 않게)
            self._fg_ok = (self._win.foreground_root() == self._target_root
                           and not self._win.is_iconic(self._target_root))
            self._next_refresh = self._clock() + REFRESH_S if REFRESH_S else None
            cb, gen0 = self._on_result, self._gen
            if cb is not None:
                self._deliver(cb, True, "ok")
            # 결과 전에 받아 둔 번호를 칠한다. ⚠ on_result 안에서 highlight(idx) 를 이미 불렀으면(whisperer 가 그렇게 한다 —
            # _on_source_highlight_result) 같은 번호로 _select 를 또 부르지 않는다: 또 부르면 "보이게 스크롤" 요청이 두 번 나가
            # 첫 스크롤이 끝나기 전(비동기) 두 번째가 옛 위치를 보고 한 번 더 스크롤할 수 있다(2026-09-28 반증).
            if (self._state == "active" and self._gen == gen0 and self._want_idx is not None
                    and self._want_idx != self._current_idx):
                self._select(self._want_idx)
        elif kind == "begin_fail" and self._state == "pending":
            cb = self._on_result
            self._finish_session(notify_worker=False)
            if cb is not None:
                self._deliver(cb, False, msg[2])
        elif kind in ("slow", "lost", "error"):
            log.info("원문 형광펜 %s: %s", kind, msg[2])
            self._stop(kind)
        elif kind == "rects" and self._state == "active":
            _, _, idx, rects, doc_rect, scrolled = msg
            note = (idx, len(rects or ()), bool(scrolled), _bbox(rects), doc_rect)
            if note != self._last_rects_note:
                # 진단용: 위치 요청 결과가 바뀔 때만. 사각형 0개가 이어지면 "범위가 죽었거나 화면 밖",
                # 문서 영역과 동떨어진 좌표면 "범위가 엉뚱한 곳을 가리킴" 이다(Codex 분석 260929_211454).
                # 좌표만 남긴다 — 글 내용은 남기지 않는다.
                log.info("원문 형광펜 위치 받음: 조각 %s, 줄 사각형 %d개%s · 감싼 상자 %s · 문서 영역 %s",
                         idx + 1 if isinstance(idx, int) else "?", note[1],
                         ", 보이게 스크롤함" if scrolled else "", note[3], doc_rect)
                self._last_rects_note = note
            if idx == self._current_idx:
                self._doc_rect = doc_rect
                if scrolled:
                    # 이 사각형은 스크롤 "전" 자리다(스크롤은 비동기 — Edge 실측). 그대로 그리면 글이 이미 움직인 뒤라
                    # 막이 엉뚱한 줄 위에 한 번 번쩍인다. 비워서 숨기고, 다음 틱부터 SETTLE_TICKS 동안 새로 받아 그린다.
                    self._raw_rects = []
                    self._settle_left = SETTLE_TICKS
                else:
                    self._raw_rects = rects
                    n = _line_count(rects)
                    if n > self._full_lines.get(idx, 0):
                        self._full_lines[idx] = n
                self._redraw()
            self._flush_query()

    def _watch(self, now):
        """대상 창 확인(가벼운 Win32 만): 닫힘 → 중단, 전경 아님·최소화 → 막 숨김, 움직임·휠 → 다시 받기."""
        root = self._target_root
        if not self._win.is_window(root):
            self._stop("target_closed")
            return
        fg_ok = self._visible_ok(root)
        if fg_ok != self._fg_ok:
            self._fg_ok = fg_ok
            if fg_ok:
                self._need_query = True          # 돌아오면 새로 받아 그린다(그 사이 스크롤됐을 수 있다)
            else:
                self._hide_overlay("막 자리가 다른 창에 가려짐·대상 창 최소화")
        rect = self._win.window_rect(root)
        if rect != self._last_win_rect:
            if self._last_win_rect is not None and rect is not None and (
                    rect[2] - rect[0], rect[3] - rect[1]) != (
                    self._last_win_rect[2] - self._last_win_rect[0], self._last_win_rect[3] - self._last_win_rect[1]):
                self._full_lines.clear()          # 창 크기가 바뀌면 줄바꿈이 달라진다 — 줄 수를 새로 센다
            self._last_win_rect = rect
            self._settle_left = SETTLE_TICKS
        if self._scroll_flag:
            # 휠: 따라가지 않고 숨긴다. 휠이 이어지면 계속 숨긴 채로(남은 틱을 다시 채움), 멈추면 새 자리에 한 번 그린다
            self._scroll_flag = False
            self._scroll_hold = SETTLE_TICKS
            self._hide_overlay("스크롤 중 — 멈추면 새 자리에 다시 그림")
        if self._scroll_hold > 0:
            self._scroll_hold -= 1
            if self._scroll_hold == 0:
                self._need_query = True          # 스크롤이 멈췄다 → 새 자리를 한 번 받아 그린다
        if self._settle_left > 0:
            self._settle_left -= 1
            self._need_query = True
        if self._next_refresh is not None and now >= self._next_refresh:
            self._next_refresh = now + REFRESH_S
            self._need_query = True
        self._flush_query()

    def _visible_ok(self, root):
        """막을 보여도 되나. 대상 창이 최소화가 아니고, 전경이거나 — 전경이 아니어도 막 자리가 가려지지 않았으면 True.

        2026-09-29 사용자 결정 "막 자리가 안 가려지면 유지": 예전엔 대상 창이 전경일 때만 보여서, 다른 앱을 누르면
        VS Code 가 그대로 보이는데도 막이 사라졌다. 막은 항상 맨 위 창이라 다른 창이 그 자리를 덮으면 그 위에 뜨므로,
        막 자리 다섯 점(_probe_points)의 맨 위 창이 모두 대상 창(또는 이 앱의 창 — 막·하단 바)일 때만 유지한다.
        가벼운 Win32 조회(WindowFromPoint)만 쓴다 — UIA 아님. 조회 수단이 없는 환경이면 예전처럼 전경일 때만.
        """
        if self._win.is_iconic(root):
            return False
        if self._win.foreground_root() == root:
            return True
        root_at = getattr(self._win, "root_at", None)
        box = self._shown_box
        if root_at is None or not box:
            return False
        for x, y in _probe_points(box):
            h = root_at(x, y)
            if h == root:
                continue
            if h and self._win.pid_of(h) == self._win.own_pid:
                continue
            return False
        return True

    # ── 사각형 받기·그리기 ────────────────────────────────────────────

    def _select(self, idx):
        """칠할 조각을 idx 로 바꾸고 사각형을 (보이게 스크롤하며) 받으러 보낸다."""
        self._current_idx = idx
        self._current_caption = self._want_caption if idx == self._want_idx else None
        if idx not in self._mapped:
            self._raw_rects = []
            self._hide_overlay(f"조각 {idx + 1} 은 원문에서 자리를 못 찾음")   # 원문에 맞추지 못한 조각 — 칠하지 않는다
            return
        self._reveal_pending = True
        self._need_query = True
        self._flush_query()

    def _flush_query(self):
        """보낼 요청이 있고, 보낸 것이 안 돌아온 게 없고, 대상 창이 전경이면 UIA 스레드에 사각형을 묻는다."""
        if (self._state != "active" or not self._need_query or self._inflight
                or self._current_idx not in self._mapped or self._fg_ok is False
                or self._scroll_hold > 0):      # 스크롤 중에는 묻지 않는다(요청은 남겨 두었다가 멈춘 뒤 보낸다)
            return
        self._need_query = False
        reveal, self._reveal_pending = self._reveal_pending, False
        self._inflight = True
        self._worker.submit(("rects", self._gen, self._current_idx, reveal))

    def _redraw(self):
        """받아 둔 사각형을 대상 창·문서 영역으로 잘라 막에 그린다. 전경이 아니면 숨긴 채로 둔다."""
        if self._fg_ok is False or self._state != "active":
            self._hide_overlay("막 자리가 다른 창에 가려짐·대상 창 최소화" if self._fg_ok is False
                               else "칠하기 동작 중 아님")
            return
        if self._scroll_hold > 0:
            # 휠 전에 보낸 요청의 결과가 스크롤 중에 돌아왔다 — 옛 자리라 그리지 않는다(멈춘 뒤 새로 받는다)
            self._hide_overlay("스크롤 중 — 멈추면 새 자리에 다시 그림")
            return
        bounds = _intersect(self._doc_rect, self._last_win_rect)
        rects = clip_rects(self._raw_rects, bounds)
        if not rects:
            n = self._current_idx + 1 if isinstance(self._current_idx, int) else "?"
            if self._raw_rects:
                reason = f"조각 {n} 이 보이는 영역 밖"
            elif self._settle_left > 0:
                reason = "스크롤·창 이동 직후 — 새 위치를 기다림"
            else:
                reason = f"조각 {n} 의 사각형이 비었음(화면 밖이거나 원문 앱이 그 부분을 다시 그림)"
            self._hide_overlay(reason)
            return
        if self._overlay is None:
            self._overlay = self._overlay_factory(self._root)
        caption = self._current_caption
        if caption:
            # 문단 일부만 보이면(화면 밖 줄이 빠졌거나 보이는 영역 경계에 잘림) 번역문 막 대신 노랑 — 2026-09-29 사용자 결정.
            # 보이는 줄만으로 막을 그리면 폭이 그 줄 폭(마지막 짧은 줄이면 75px)이 돼 세로로 길쭉해졌다(실측 로그).
            partial = (_line_count(self._raw_rects) < self._full_lines.get(self._current_idx, 0)
                       or _bbox(rects) != _bbox(self._raw_rects))
            if partial != self._partial_noted:
                log.info("원문 형광펜: %s", "문단 일부만 보임 — 번역문 막 대신 노랑" if partial
                         else "문단이 다 보임 — 번역문 막으로")
                self._partial_noted = partial
            if partial:
                caption = None
        try:
            if caption:
                # 번역문 막: 크기는 잘리기 전 원래 사각형으로, 보이는 영역(bounds)은 마지막에 자르기만
                ok = self._overlay.show(rects, caption, self._raw_rects, bounds)
            else:
                ok = self._overlay.show(rects)
        except Exception:
            log.exception("원문 형광펜 막 그리기 실패")
            ok = False
        if ok is False:
            # 막 창이 그리기에 실패했다(UpdateLayeredWindow 등) — "보임" 으로 기록하지 않는다
            self._hide_overlay("막 그리기 실패")
            return
        if not self._overlay_visible:
            log.info("원문 형광펜 보임: 조각 %s%s · 막 영역 %s · 보이는 영역 %s",
                     self._current_idx + 1 if isinstance(self._current_idx, int) else "?",
                     " (번역문 막)" if caption else "", _bbox(rects), bounds)
        self._overlay_visible = True
        self._hidden_reason = None
        self._shown_box = _bbox(rects)

    def _hide_overlay(self, reason=""):
        """막을 숨긴다. 보이던 막이 숨겨질 때, 또는 숨긴 채로 이유가 바뀔 때만 로그에 남긴다
        (진단용 — "형광펜이 사라졌다가 다시 안 나타난다". 틱마다 같은 이유를 반복해 찍지 않는다)."""
        reason = reason or "이유 미상"
        if self._overlay_visible:
            log.info("원문 형광펜 숨김: %s", reason)
        elif reason != self._hidden_reason and self._state == "active":
            log.info("원문 형광펜 숨긴 채 — 이유 바뀜: %s", reason)
        self._hidden_reason = reason
        self._overlay_visible = False
        if self._overlay is not None:
            try:
                self._overlay.hide()
            except Exception:
                log.debug("막 숨기기 실패", exc_info=True)

    def _check_thread(self, name):
        """Tk 메인이 아닌 곳에서 부르면 경고 로그만(reader_window.py·selection_button.py 와 같은 방식)."""
        if threading.current_thread() is not self._owner_thread:
            log.warning("SourceHighlighter.%s 가 Tk 메인 스레드가 아닌 곳에서 불림 — gui_queue 로 넘겨야 한다", name)
