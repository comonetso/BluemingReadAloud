# -*- coding: utf-8 -*-
"""source_highlight 단위테스트.  실행: python -m unittest discover -s tests  (프로젝트 폴더에서)

무엇을 보나
  - 순수 함수: 클립보드 글 ↔ UIA 선택 글 맞춤(공백·줄바꿈·목록 기호·마크다운 기호 차이), 글자 묶음 세기,
    UIA 사각형 변환·자르기, 막 그림(겹쳐도 한 번만 칠함).
  - SourceHighlighter 전체 흐름: 가짜 UIA 객체(선택 글·줄 사각형·스크롤·지연을 흉내)와 가짜 Tk(root.after),
    가짜 Win32(전경 창·창 위치), 가짜 막 창으로 — 조각 범위 사각형, 자동 스크롤, 1초 초과 시 중단,
    콜백이 UIA 스레드가 아니라 Tk 메인(테스트 스레드)에서 불리는지, 전경이 아니면 숨김, 금지 호출을 안 부르는지.
창은 하나도 띄우지 않는다(사용자가 이 PC 를 쓰는 중). 실제 Edge 실측은 scratchpad phase4 스크립트로 따로 했다.
"""
import os
import re
import sys
import threading
import time
import types
import unicodedata
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import readaloud_text  # noqa: E402
import source_highlight as sh  # noqa: E402
from source_highlight import (SourceHighlighter, align_source_to_uia, build_overlay_bitmap,  # noqa: E402
                              clip_rects, grapheme_counts, rects_from_uia)

# 2026-09-28 Edge 실측(scratchpad phase4\probe1.json): 같은 선택의 selection.toString()(= 클립보드 글)과 UIA GetText
EDGE_SRC = ("첫 문단입니다. 😀 이모지와 e\u0301 결합 글자, 👍🏽 피부색도 섞었어요.\n\n"
            "Second paragraph in English, with bold and inline code words.\n\n"
            "목록 첫째 항목입니다\nList item two is here\n번호 목록 하나\nNumbered item two\n"
            "셋째 문단: 줄바꿈\n두 번째 줄입니다.\n\n"
            "Filler one. The quick brown fox jumps over the lazy dog, again and again, so that this paragraph "
            "wraps onto more than one line in a small window.\n\n"
            "마지막 문단입니다. The end.")
EDGE_UIA = ("첫 문단입니다. 😀 이모지와 e\u0301 결합 글자, 👍🏽 피부색도 섞었어요.\n"
            "Second paragraph in English, with bold and inline code words.\n"
            "• 목록 첫째 항목입니다\n• List item two is here\n1. 번호 목록 하나\n2. Numbered item two\n"
            "셋째 문단: 줄바꿈\n두 번째 줄입니다.\n"
            "Filler one. The quick brown fox jumps over the lazy dog, again and again, so that this paragraph "
            "wraps onto more than one line in a small window.\n"
            "마지막 문단입니다. The end.")


NL = chr(10)
LIST_MARK = re.compile(r"(?m)^(?:•|[0-9]+\.) ")   # UIA 글의 목록 기호("• ", "1. ")


def squash(s):
    return "".join(c for c in s if not (c.isspace() or c in "\ufeff\u200b\ufffc"))


# ════════════════════════════════════════════════════════════════════
#  순수 함수
# ════════════════════════════════════════════════════════════════════
class AlignTest(unittest.TestCase):
    """클립보드 글과 UIA 선택 글이 모양이 달라도 조각이 UIA 글의 올바른 자리로 가는지."""

    def check_segments(self, src, uia, lang="ko"):
        al = align_source_to_uia(src, uia)
        self.assertIsNotNone(al)
        segs = readaloud_text.split_for_reading(src, lang)
        self.assertTrue(segs)
        for seg in segs:
            if seg["src_start"] is None:
                continue
            span = al.span(seg["src_start"], seg["src_end"])
            self.assertIsNotNone(span, seg)
            a, b = span
            got = uia[a:b]
            self.assertEqual(got, got.strip(), "앞뒤 공백 없이 잡아야 한다")
            want = squash(src[seg["src_start"]:seg["src_end"]])
            self.assertEqual(squash(LIST_MARK.sub("", got)), want)
        return al, segs

    def test_edge_measured_text(self):
        al, segs = self.check_segments(EDGE_SRC, EDGE_UIA)
        self.assertEqual(al.ratio, 1.0)
        # 짧은 줄은 다음 줄과 합쳐진다: "Second ...words." + "목록 첫째 항목입니다" 가 한 조각 → 가운데 "• " 까지 포함
        k = next(s for s in segs if "목록 첫째" in EDGE_SRC[s["src_start"]:s["src_end"]])
        a, b = al.span(k["src_start"], k["src_end"])
        self.assertEqual(EDGE_UIA[a:b], "Second paragraph in English, with bold and inline code words.\n• 목록 첫째 항목입니다")
        # 목록 항목으로 시작하는 조각은 기호 "• " 뒤 글자부터 잡는다
        k = next(s for s in segs if EDGE_SRC[s["src_start"]:s["src_end"]].startswith("List item two"))
        a, b = al.span(k["src_start"], k["src_end"])
        self.assertTrue(EDGE_UIA[a:b].startswith("List item two"))
        self.assertTrue(EDGE_UIA[a:b].endswith("셋째 문단: 줄바꿈"))

    def test_markdown_marks_only_in_source(self):
        src = "**굵은 글씨** 로 쓴 문장입니다 그리고 조금 더 길게 씁니다.\n\n- 첫째 항목은 여기에 있습니다 길게\n- `code` 둘째 항목도 여기에 있어요 길게"
        uia = "굵은 글씨 로 쓴 문장입니다 그리고 조금 더 길게 씁니다.\n첫째 항목은 여기에 있습니다 길게\ncode 둘째 항목도 여기에 있어요 길게"
        al = align_source_to_uia(src, uia)
        self.assertIsNotNone(al)
        s = src.index("첫째")
        e = src.index("길게", s) + 2
        a, b = al.span(s, e)
        self.assertEqual(uia[a:b], "첫째 항목은 여기에 있습니다 길게")
        s = src.index("`code`")
        a, b = al.span(s, len(src))
        self.assertEqual(uia[a:b], "code 둘째 항목도 여기에 있어요 길게")

    def test_crlf_and_blank_lines(self):
        self.check_segments("첫 줄은 이렇게 조금 길게 써서 한 조각이 되게 합니다.\r\n\r\n둘째 줄도 마찬가지로 길게 써서 한 조각이 됩니다.",
                            "첫 줄은 이렇게 조금 길게 써서 한 조각이 되게 합니다.\n둘째 줄도 마찬가지로 길게 써서 한 조각이 됩니다.")

    def test_substituted_quote_still_aligns(self):
        src = "It's a test sentence with a quote and more words after it."
        uia = "It’s a test sentence with a quote and more words after it."
        al = align_source_to_uia(src, uia)
        self.assertIsNotNone(al)
        self.assertEqual(al.span(0, len(src)), (0, len(uia)))

    def test_different_text_is_rejected(self):
        self.assertIsNone(align_source_to_uia("전혀 다른 글입니다 여기에는 아무것도 없어요",
                                              "Completely unrelated English text lives here"))

    def test_empty_is_rejected(self):
        self.assertIsNone(align_source_to_uia("", "abc"))
        self.assertIsNone(align_source_to_uia("abc", "  \n "))

    def test_long_text_is_fast(self):
        lines = ["줄 %d 은 목록 항목입니다 hello world" % i for i in range(1500)]
        src = "\n\n".join(lines)
        uia = "\n".join("• " + x for x in lines)
        t = time.perf_counter()
        al = align_source_to_uia(src, uia)
        self.assertIsNotNone(al)
        self.assertLess(time.perf_counter() - t, 1.0)
        self.assertEqual(al.ratio, 1.0)


class GraphemeTest(unittest.TestCase):
    """크로미움 UIA Character 한 칸 = 글자 묶음(Edge 실측)을 파이썬에서 세는지."""

    def count(self, s):
        return grapheme_counts(s)[-1]

    def test_edge_measured_units(self):
        self.assertEqual(self.count("e\u0301"), 1)
        self.assertEqual(self.count("👍🏽"), 1)
        self.assertEqual(self.count("😀"), 1)
        # 실측: 선택 시작에서 38칸 옮기면 "Sec" 가 나왔다(😀·é·👍🏽 가 각 1칸, "\n" 도 1칸)
        cum = grapheme_counts(EDGE_UIA)
        self.assertEqual(cum[EDGE_UIA.index("Second")], 38)
        self.assertEqual(cum[EDGE_UIA.index("\n")], 37)

    def test_other_clusters(self):
        self.assertEqual(self.count("\r\n"), 1)
        self.assertEqual(self.count("👨\u200d👩\u200d👧"), 1)
        self.assertEqual(self.count("🇰🇷🇯🇵"), 2)
        self.assertEqual(self.count("각"), 1)     # 풀어 쓴 한글 자모 → 한 글자
        self.assertEqual(self.count("한글abc"), 5)
        self.assertEqual(self.count("❤️"), 1)
        self.assertEqual(self.count("a\n\u0301"), 3)               # 줄바꿈 뒤 결합 부호는 따로(GB4)

    def test_floor_ceil(self):
        s = "a e\u0301b"
        cum = grapheme_counts(s)
        self.assertEqual(sh._g_floor(cum, s.index("\u0301")), 2)   # é 묶음 안 → é 의 시작
        self.assertEqual(sh._g_ceil(cum, s.index("\u0301")), 3)    # 묶음 한가운데 끝 → 묶음 끝까지


class TrimVerifyTest(unittest.TestCase):
    """범위 앞뒤에 줄바꿈이 끼면(크로미움 블록 경계 어긋남) 그 칸을 잘라 낸다."""

    def worker(self):
        w = object.__new__(sh._UiaWorker)
        w._U, w._clock, w.call_since = U, time.monotonic, None
        return w

    def test_trims_leading_newline_and_trailing_space(self):
        doc = FakeDoc(NL.join(["a", "hello world ", "b"]))
        r = FakeRange(doc, 1, 15)                       # 줄바꿈 + "hello world " + 줄바꿈
        self.assertEqual(doc.text(r.s, r.e), NL + "hello world " + NL)
        got = self.worker()._trim_verify(r, "hello world", "helloworld")
        self.assertIsNotNone(got)
        self.assertEqual(doc.text(got.s, got.e), "hello world")
        self.assertEqual(doc.count("FindText"), 1, "범위 안에서만 다시 찾는다")

    def test_exact_range_is_kept_without_findtext(self):
        doc = FakeDoc(NL.join(["a", "hello world", "b"]))
        r = FakeRange(doc, 2, 13)
        self.assertIs(self.worker()._trim_verify(r, "hello world", "helloworld"), r)
        self.assertEqual(doc.count("FindText"), 0)

    def test_rejects_different_text(self):
        doc = FakeDoc(NL.join(["a", "hello world", "b"]))
        self.assertIsNone(self.worker()._trim_verify(FakeRange(doc, 0, 7), "hello", "hello"))


class RectTest(unittest.TestCase):
    def test_rects_from_uia_rounds_outward(self):
        self.assertEqual(rects_from_uia((10.4, 20.6, 30.2, 10.0, 5, 5, 0, 3)), [(10, 20, 41, 31)])
        # Edge 실측: 범위 끝이 다음 문단 첫머리에 걸리면 폭 1.0 짜리 캐럿 같은 사각형이 따라온다 → 뺀다
        self.assertEqual(rects_from_uia((113.0, 571.0, 685.0, 31.0, 113.0, 627.0, 1.0, 31.0)), [(113, 571, 798, 602)])
        self.assertEqual(rects_from_uia(None), [])
        self.assertEqual(rects_from_uia(()), [])

    def test_clip(self):
        self.assertEqual(clip_rects([(0, 0, 100, 20), (0, 90, 100, 110), (0, 200, 10, 210)], (10, 10, 50, 100)),
                         [(10, 10, 50, 20), (10, 90, 50, 100)])
        self.assertEqual(clip_rects([(1, 2, 3, 4)], None), [(1, 2, 3, 4)])

    def test_bitmap_paints_overlap_once(self):
        px = sh.PREMULT_PIXEL
        self.assertEqual(px, bytes((0, 68, 77, 77)))          # rgba(255,226,0,0.3) 미리 곱한 BGRA
        left, top, w, h, bits = build_overlay_bitmap([(10, 10, 14, 12), (12, 10, 16, 12), (10, 14, 12, 15)])
        self.assertEqual((left, top, w, h), (10, 10, 6, 5))
        self.assertEqual(len(bits), w * h * 4)

        def pixel(x, y):
            o = ((y - top) * w + (x - left)) * 4
            return bits[o:o + 4]
        self.assertEqual(pixel(13, 10), px)                     # 겹친 곳도 같은 값(두 번 칠해 진해지지 않음)
        self.assertEqual(pixel(15, 11), px)
        self.assertEqual(pixel(12, 12), bytes(4))               # 줄 사이 틈은 투명
        self.assertEqual(pixel(11, 14), px)
        self.assertEqual(pixel(13, 14), bytes(4))


@unittest.skipUnless(sys.platform == "win32", "번역문 막은 Windows GDI 로 그린다")
class CaptionBitmapTest(unittest.TestCase):
    """번역문 막(2026-09-29): 원문 줄 자리를 덮고, 짙은 회색 바탕 + 옅은 회색 글씨 + 노랑 테두리, 넘치면 아래로 늘린다."""

    RECTS = [(100, 200, 500, 220), (100, 220, 380, 240)]   # 두 줄, 줄 높이 20, 둘째 줄이 더 짧다

    @staticmethod
    def pixel(result, x, y):
        left, top, w, h, bits = result
        o = ((y - top) * w + (x - left)) * 4
        b, g, r, a = bits[o:o + 4]
        return (r, g, b, a)

    def test_covers_box_with_border_and_opaque_background(self):
        edge = sh.CAPTION_BORDER_PX + sh.CAPTION_PAD_PX
        res = sh.build_caption_bitmap(self.RECTS, "짧은 번역문")
        left, top, w, h, bits = res
        # 줄마다 너비가 달라도 상자 전체(100~500 × 200~240)를 덮고, 테두리+여백만큼 바깥으로 크다
        self.assertEqual((left, top, w, h), (100 - edge, 200 - edge, 400 + 2 * edge, 40 + 2 * edge))
        self.assertEqual(len(bits), w * h * 4)
        self.assertTrue(all(bits[i] == 255 for i in range(3, len(bits), 4)), "전부 불투명 — 원문이 비치지 않게")
        self.assertEqual(self.pixel(res, left, top), sh.CAPTION_BORDER + (255,))            # 모서리 = 노랑 테두리
        self.assertEqual(self.pixel(res, 490, 235), sh.CAPTION_BG + (255,))                # 글 없는 안쪽 = 짙은 회색
        self.assertEqual(sh.CAPTION_BG, (0x38, 0x38, 0x38))
        self.assertEqual(sh.CAPTION_FG, (0xCC, 0xCC, 0xCC))   # 옅은 회색(사용자 "흰색은 너무 밝다")

    def test_draws_text_in_first_line(self):
        res = sh.build_caption_bitmap(self.RECTS, "가나다라마바사")
        # ClearType 은 가장자리에 색을 섞으므로 "바탕보다 확실히 밝은 픽셀" 을 센다
        bright = sum(1 for y in range(200, 220) for x in range(100, 250)
                     if sum(self.pixel(res, x, y)[:3]) > sum(sh.CAPTION_BG) + 200)
        self.assertGreater(bright, 20, "첫 줄 자리에 글자가 있어야 한다")
        empty = sum(1 for y in range(222, 238) for x in range(100, 250)
                    if sum(self.pixel(res, x, y)[:3]) > sum(sh.CAPTION_BG) + 200)
        self.assertEqual(empty, 0, "한 줄짜리 글이면 둘째 줄 자리는 비어 있다")

    def test_long_text_grows_downward_only(self):
        short = sh.build_caption_bitmap(self.RECTS, "짧다")
        long = sh.build_caption_bitmap(self.RECTS, "아주 긴 번역문입니다 " * 12)
        self.assertEqual(short[:3], long[:3], "위치·너비는 원문 자리 그대로")
        self.assertGreater(long[3], short[3], "넘치면 막을 아래로 늘린다")
        self.assertEqual((long[3] - short[3]) % 20, 0, "늘어나는 만큼은 원문 줄 높이 단위")

    def test_clip_crops_after_drawing_at_original_size(self):
        # 2026-09-29 결함: 잘린 사각형으로 글꼴을 정해 글씨가 작아졌다. 이제 원래 크기로 그리고 보이는 영역만 자른다
        text = "번역문 줄이 여러 개가 되도록 조금 길게 씁니다 " * 3
        full = sh.build_caption_bitmap(self.RECTS, text)
        clip = (100, 212, 450, 236)                       # 첫 줄 일부만 보이고 오른쪽도 잘린 상황
        cut = sh.build_caption_bitmap(self.RECTS, text, clip)
        left, top, w, h, bits = cut
        self.assertEqual((left, top, left + w, top + h), clip, "보이는 영역만 남는다")
        # 잘린 그림은 원래 크기로 그린 그림의 그 부분과 픽셀까지 같다(= 글꼴·줄바꿈이 원래 크기 기준)
        fl, ft, fw, fh, fbits = full
        for y in (0, h // 2, h - 1):
            row_full = fbits[((top - ft + y) * fw + (left - fl)) * 4:((top - ft + y) * fw + (left - fl) + w) * 4]
            self.assertEqual(bits[y * w * 4:(y + 1) * w * 4], row_full)

    def test_clip_outside_returns_none(self):
        self.assertIsNone(sh.build_caption_bitmap(self.RECTS, "가나다", (0, 0, 50, 50)))

    def test_font_fits_line_height(self):
        gdi = sh._GdiText()
        try:
            size = gdi.fit(20)
            self.assertLessEqual(gdi.height(), 20)
            gdi.set_size(size + 1)
            self.assertGreater(gdi.height(), 20, "줄 높이 안에 들어가는 가장 큰 글꼴")
            self.assertGreater(gdi.width("가나다"), gdi.width("가"))
        finally:
            gdi.close()

    def test_wrap_keeps_newlines_and_breaks_long_words(self):
        measure = lambda s: 10 * len(s)      # noqa: E731 — 글자당 10px 가짜 자
        lines = sh._wrap_caption("첫 줄\n\n" + "가" * 40 + "\n둘 셋 넷 다섯 여섯 일곱", measure, 50)
        self.assertEqual(lines[0], "첫 줄")
        self.assertTrue(all(measure(ln) <= 50 for ln in lines))
        self.assertEqual("".join(lines[1:9]), "가" * 40)          # 공백 없는 긴 덩어리는 글자 단위로
        self.assertEqual(lines[9:], ["둘 셋 넷", "다섯 여섯", "일곱"])   # 공백에서 끊는다(딱 50px 은 들어간다)

    def test_emoji_length_for_gdi(self):
        self.assertEqual(sh._u16len("가😀"), 3)


# ════════════════════════════════════════════════════════════════════
#  가짜 UIA — 크로미움처럼 "글자 묶음 한 칸"으로 움직이는 텍스트 범위
# ════════════════════════════════════════════════════════════════════
U = types.SimpleNamespace(
    UIA_IsTextPatternAvailablePropertyId=30040, UIA_TextPatternId=10014, IUIAutomationTextPattern="ITextPattern",
    UIA_ScrollItemPatternId=10017, IUIAutomationScrollItemPattern="IScrollItem",
    TextPatternRangeEndpoint_Start=0, TextPatternRangeEndpoint_End=1, TextUnit_Character=0)
UIA_E_ELEMENTNOTAVAILABLE_SIGNED = 0x80040201 - (1 << 32)
Rect = types.SimpleNamespace


class FakeCOMError(Exception):
    def __init__(self, hresult):
        super().__init__(hresult)
        self.hresult = hresult


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            return self.t

    def advance(self, dt):
        with self._lock:
            self.t += dt


def split_units(text, split_marks=False):
    """가짜 문서의 한 칸 = 글자 + 뒤따르는 결합 부호·피부색(크로미움 글자 묶음 흉내). split_marks 면 결합 부호도 따로."""
    units = []
    for ch in text:
        cp = ord(ch)
        joins = (unicodedata.category(ch) == "Mn" and not split_marks) or 0x1F3FB <= cp <= 0x1F3FF
        if units and joins and units[-1] != "\n":
            units[-1] += ch
        else:
            units.append(ch)
    return units


class FakeDoc:
    """UIA 글(units)과 화면 배치: 한 줄 = "\\n" 사이, 글자 폭 CW, 줄 높이 LH, 보이는 줄 VIS 개(scroll 부터)."""
    X0, Y0, CW, LH, VIS = 60, 110, 10, 20, 12

    def __init__(self, text, sel_start=0, sel_end=None, split_marks=False, pid=4242):
        self.units = split_units(text, split_marks)
        self.sel = (sel_start, len(self.units) if sel_end is None else sel_end)
        self.scroll = 0
        self.pid = pid
        self.calls = []
        self.forbidden = []
        self.hook = None           # hook(이름) — 호출 직전에 불린다(지연·오류 흉내)
        self.lock = threading.Lock()
        self.pos = []
        line = col = 0
        for u in self.units:
            self.pos.append((line, col))
            if u == "\n":
                line += 1
                col = 0
            else:
                col += 1
        self.lines = line + 1

    def note(self, name):
        with self.lock:
            self.calls.append(name)
        if self.hook:
            self.hook(name)

    def count(self, name):
        with self.lock:
            return self.calls.count(name)

    def rects(self, s, e):
        by_line = {}
        for k in range(s, e):
            if self.units[k] == "\n":
                continue
            line, col = self.pos[k]
            lo, hi = by_line.get(line, (col, col))
            by_line[line] = (min(lo, col), max(hi, col))
        out = []
        for line in sorted(by_line):
            if not (self.scroll <= line < self.scroll + self.VIS):
                continue            # 화면 밖 줄은 빠진다(크로미움 실측과 같음)
            lo, hi = by_line[line]
            out += [self.X0 + lo * self.CW, self.Y0 + (line - self.scroll) * self.LH, (hi - lo + 1) * self.CW, self.LH]
        return tuple(float(v) for v in out)

    def expected_rects(self, s, e):
        return rects_from_uia(self.rects(s, e))

    def text(self, s, e):
        return "".join(self.units[s:e])

    def offset_to_unit(self, s, off):
        acc = 0
        for k in range(s, len(self.units) + 1):
            if acc == off:
                return k
            if k == len(self.units):
                break
            acc += len(self.units[k])
        return None


class FakeRange:
    def __init__(self, doc, s, e):
        self.doc, self.s, self.e = doc, s, e

    def Clone(self):
        self.doc.note("Clone")
        return FakeRange(self.doc, self.s, self.e)

    def GetText(self, n):
        self.doc.note("GetText")
        t = self.doc.text(self.s, self.e)
        return t if n is None or n < 0 else t[:n]

    def MoveEndpointByUnit(self, ep, unit, count):
        self.doc.note("MoveEndpointByUnit")
        cur = self.s if ep == 0 else self.e
        new = max(0, min(len(self.doc.units), cur + count))
        if ep == 0:
            self.s = new
            self.e = max(self.e, new)
        else:
            self.e = new
            self.s = min(self.s, new)
        return new - cur

    def MoveEndpointByRange(self, ep, other, other_ep):
        self.doc.note("MoveEndpointByRange")
        v = other.s if other_ep == 0 else other.e
        if ep == 0:
            self.s = v
            self.e = max(self.e, v)
        else:
            self.e = v
            self.s = min(self.s, v)

    def GetBoundingRectangles(self):
        self.doc.note("GetBoundingRectangles")
        return self.doc.rects(self.s, self.e)

    def ScrollIntoView(self, top):
        """크로미움 흉내(Edge 실측): 한 줄(블록) 안 범위는 아무 효과 없음, 여러 줄에 걸치면 첫 줄을 위에 맞춤."""
        self.doc.note("ScrollIntoView")
        first = self.doc.pos[self.s][0] if self.s < len(self.doc.units) else self.doc.lines - 1
        last = self.doc.pos[max(self.s, self.e - 1)][0] if self.e > 0 else first
        if last > first:
            self.doc.scroll = max(0, min(first, self.doc.lines - self.doc.VIS))

    def GetEnclosingElement(self):
        self.doc.note("GetEnclosingElement")
        line = self.doc.pos[self.s][0] if self.s < len(self.doc.units) else self.doc.lines - 1
        return FakeLineElement(self.doc, line)

    def FindText(self, text, backward, ignore_case):
        self.doc.note("FindText")
        hay = self.doc.text(self.s, self.e)
        off = hay.find(text)
        if off < 0:
            return None
        a = self.doc.offset_to_unit(self.s, off)
        b = self.doc.offset_to_unit(self.s, off + len(text))
        if a is None or b is None:
            return None
        return FakeRange(self.doc, a, b)

    # ⛔ 금지 호출 — 부르면 기록
    def GetVisibleRanges(self):
        self.doc.forbidden.append("GetVisibleRanges")


class FakeScrollItem:
    """ScrollItemPattern 흉내(Edge 실측): 그 줄을 화면 가운데쯤으로."""

    def __init__(self, doc, line):
        self.doc, self.line = doc, line

    def QueryInterface(self, iface):
        assert iface == U.IUIAutomationScrollItemPattern
        return self

    def ScrollIntoView(self):
        self.doc.note("ScrollItem")
        self.doc.scroll = max(0, min(self.line - self.doc.VIS // 2, self.doc.lines - self.doc.VIS))


class FakeLineElement:
    """GetEnclosingElement 가 돌려주는 줄(문단) 요소."""

    def __init__(self, doc, line):
        self.doc, self.line = doc, line

    def GetCurrentPattern(self, pid):
        self.doc.note("GetCurrentPattern")
        return FakeScrollItem(self.doc, self.line) if pid == U.UIA_ScrollItemPatternId else None


class FakeArray:
    def __init__(self, items):
        self.items = items

    @property
    def Length(self):
        return len(self.items)

    def GetElement(self, i):
        return self.items[i]


class FakePattern:
    def __init__(self, doc):
        self.doc = doc

    def QueryInterface(self, iface):
        assert iface == U.IUIAutomationTextPattern
        return self

    def GetSelection(self):
        self.doc.note("GetSelection")
        s, e = self.doc.sel
        return FakeArray([FakeRange(self.doc, s, e)])

    @property
    def DocumentRange(self):
        self.doc.forbidden.append("DocumentRange")
        return FakeRange(self.doc, 0, len(self.doc.units))

    def GetVisibleRanges(self):
        self.doc.forbidden.append("GetVisibleRanges")


class FakeElement:
    def __init__(self, doc, parent=None, has_text=False, pid=None):
        self.doc, self.parent, self.has_text = doc, parent, has_text
        self.CurrentProcessId = doc.pid if pid is None else pid
        self.CurrentBoundingRectangle = Rect(left=50, top=100, right=950, bottom=700)

    def GetCurrentPropertyValue(self, pid):
        self.doc.note("GetCurrentPropertyValue")
        assert pid == U.UIA_IsTextPatternAvailablePropertyId
        return self.has_text

    def GetCurrentPattern(self, pid):
        self.doc.note("GetCurrentPattern")
        return FakePattern(self.doc) if self.has_text else None

    def FindAll(self, *a):
        self.doc.forbidden.append("FindAll")

    def FindFirst(self, *a):
        self.doc.forbidden.append("FindFirst")


class FakeWalker:
    def __init__(self, doc):
        self.doc = doc

    def GetParentElement(self, el):
        self.doc.note("GetParentElement")
        return el.parent


class FakeUIA:
    def __init__(self, doc, depth=4, focus_pid=None):
        self.doc = doc
        top = FakeElement(doc, None, has_text=True)       # 문서(TextPattern)
        el = top
        for _ in range(depth):                              # 그 아래 포커스까지 depth 단계
            el = FakeElement(doc, el, pid=focus_pid)
        self.focused = el
        self.ControlViewWalker = FakeWalker(doc)
        self.doc_element = top

    def GetFocusedElement(self):
        self.doc.note("GetFocusedElement")
        return self.focused


class FakeRoot:
    """root.after 흉내 — 테스트 스레드가 run_pending 으로 돌린다(= Tk 메인)."""

    def __init__(self):
        self.pending = {}
        self.n = 0

    def after(self, ms, fn):
        self.n += 1
        self.pending[self.n] = fn
        return self.n

    def after_cancel(self, i):
        self.pending.pop(i, None)

    def run_pending(self):
        items, self.pending = self.pending, {}
        for fn in items.values():
            fn()


class FakeEnv:
    own_pid = 1

    def __init__(self):
        self.fg = 777
        self.rect = (0, 0, 1000, 800)
        self.alive = True
        self.iconic = False
        self.target_pid = 4242

    def foreground_root(self):
        return self.fg

    def window_rect(self, h):
        return self.rect

    def is_window(self, h):
        return self.alive

    def is_iconic(self, h):
        return self.iconic

    def pid_of(self, h):
        return self.target_pid if h == 777 else 999


class FakeOverlay:
    def __init__(self):
        self.shows = []
        self.captions = []      # show 마다 받은 번역문(없으면 None) — shows 와 같은 순서
        self.caption_srcs = []  # 번역문 막 크기 계산용 원래(잘리기 전) 사각형
        self.clips = []         # 번역문 막을 마지막에 자를 보이는 영역
        self.fail = False       # True 면 그리기 실패 흉내(False 를 돌려준다)
        self.visible = False
        self.destroyed = False

    def show(self, rects, caption=None, caption_src=None, clip=None):
        self.shows.append(list(rects))
        self.captions.append(caption)
        self.caption_srcs.append(list(caption_src) if caption_src else None)
        self.clips.append(clip)
        if self.fail:
            self.visible = False
            return False
        self.visible = True
        return True

    def hide(self):
        self.visible = False

    def destroy(self):
        self.destroyed = True


# 가짜 문서 글: 30줄(보이는 줄 12개). 줄 0 에 결합 부호·피부색, 줄 3·4 는 목록 항목
LINES = ["문단 %02d번째 줄입니다. 이 줄은 읽기 조각 하나가 됩니다. Line %02d." % (i, i) for i in range(30)]
LINES[0] = "문단 00번째 줄입니다. e\u0301 결합과 👍🏽 피부색이 섞인 조각 하나가 됩니다. Line 00."
DOC_SRC = "\n\n".join(LINES)
DOC_UIA = "\n".join(("• " + x) if i in (3, 4) else x for i, x in enumerate(LINES))


def wait(root, cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        root.run_pending()
        if cond():
            return True
        time.sleep(0.002)
    root.run_pending()
    return cond()


class HighlighterTest(unittest.TestCase):
    """SourceHighlighter 전체 흐름(가짜 UIA·Tk·Win32·막)."""

    def make(self, uia_text=DOC_UIA, src=DOC_SRC, depth=4, split_marks=False, focus_pid=None):
        self.doc = FakeDoc(uia_text, split_marks=split_marks)
        self.uia = FakeUIA(self.doc, depth=depth, focus_pid=focus_pid)
        self.clock = FakeClock()
        self.root = FakeRoot()
        self.env = FakeEnv()
        self.overlays = []
        self.stops = []
        self.results = []
        self.factory_threads = []

        def factory():
            self.factory_threads.append(threading.current_thread())
            return self.uia, U

        def make_overlay(root):
            ov = FakeOverlay()
            self.overlays.append(ov)
            return ov

        self.hl = SourceHighlighter(self.root, on_stop=lambda r: self.stops.append((r, threading.current_thread())),
                                    uia_factory=factory, overlay_factory=make_overlay, win_env=self.env,
                                    clock=self.clock)
        self.addCleanup(self.hl.destroy)
        self.src = src
        self.segs = readaloud_text.split_for_reading(src, "ko")
        return self.hl

    def begin(self):
        self.hl.begin(self.src, self.segs, lambda ok, why: self.results.append((ok, why, threading.current_thread())))
        self.assertTrue(wait(self.root, lambda: self.results), "on_result 가 와야 한다")
        return self.results[-1]

    def seg_units(self, idx):
        """조각 idx 가 가짜 문서에서 차지하는 칸 [s, e) — 기대값 계산용(모듈과 따로 셈)."""
        seg = self.segs[idx]
        text = squash(self.src[seg["src_start"]:seg["src_end"]])
        joined = "".join(self.doc.units)
        # 조각 글 첫머리를 UIA 글에서 찾고, 거기서부터 공백·목록 기호(•)를 건너뛰며 한 글자씩 따라가 끝을 정한다
        i = joined.index(self.src[seg["src_start"]:seg["src_end"]].strip()[:10])
        start_off, k = i, 0
        while k < len(text):
            c = joined[i]
            if c == text[k]:
                k += 1
            else:
                self.assertTrue(c.isspace() or c == "•", "기대값 계산 실패: %r" % c)
            i += 1
        s = self.doc.offset_to_unit(0, start_off)
        e = self.doc.offset_to_unit(0, i)
        self.assertEqual(squash(self.doc.text(s, e)).replace("•", ""), text)
        return s, e

    def last_show(self):
        return self.overlays[-1].shows[-1] if self.overlays and self.overlays[-1].shows else None

    # ── 기본 흐름 ──
    def test_begin_ok_callback_on_main_thread(self):
        self.make()
        ok, why, th = self.begin()
        self.assertEqual((ok, why), (True, "ok"))
        self.assertIs(th, threading.current_thread(), "on_result 는 Tk 메인(테스트 스레드)에서")
        self.assertIsNot(self.factory_threads[0], threading.current_thread(), "UIA 는 전용 스레드에서 만든다")
        self.assertTrue(self.hl.active)
        self.assertEqual(self.doc.forbidden, [])

    def test_highlight_draws_segment_line_rects(self):
        self.make()
        self.begin()
        for idx in (0, 1, 3):
            self.hl.highlight(idx)
            s, e = self.seg_units(idx)
            want = self.doc.expected_rects(s, e)
            self.assertTrue(wait(self.root, lambda: self.last_show() == want), (idx, self.last_show(), want))
        self.assertEqual(self.doc.count("ScrollIntoView") + self.doc.count("ScrollItem"), 0,
                         "이미 보이는 조각은 스크롤하지 않는다")
        self.assertTrue(self.overlays[-1].visible)
        self.assertEqual(len(self.overlays), 1, "막 창은 하나")
        self.assertEqual(self.doc.forbidden, [])

    def test_caption_reaches_overlay_and_changes_without_rescroll(self):
        self.make()
        self.begin()
        self.hl.highlight(0, "번역문 하나")
        s, e = self.seg_units(0)
        want = self.doc.expected_rects(s, e)
        self.assertTrue(wait(self.root, lambda: self.last_show() == want))
        self.assertEqual(self.overlays[-1].captions[-1], "번역문 하나")
        asked = self.doc.count("GetBoundingRectangles")
        self.hl.highlight(0, "번역문 둘")                  # 같은 조각에 번역문만 바뀜 → 다시 묻지 않고 다시 그린다
        self.assertEqual(self.overlays[-1].captions[-1], "번역문 둘")
        self.assertEqual(self.doc.count("GetBoundingRectangles"), asked)
        self.hl.highlight(1)                                # 번역 안 된 조각 → 노랑(번역문 없음)
        s1, e1 = self.seg_units(1)
        self.assertTrue(wait(self.root, lambda: self.last_show() == self.doc.expected_rects(s1, e1)))
        self.assertIsNone(self.overlays[-1].captions[-1])

    def test_caption_gets_raw_rects_and_visible_bounds(self):
        # 번역문 막은 크기를 원래(잘리기 전) 사각형으로 정하고, 보이는 영역은 따로 넘겨 마지막에 자르게 한다
        self.make()
        self.begin()
        self.hl.highlight(0, "번역문")
        s, e = self.seg_units(0)
        want = self.doc.expected_rects(s, e)
        self.assertTrue(wait(self.root, lambda: self.last_show() == want))
        ov = self.overlays[-1]
        self.assertEqual(ov.caption_srcs[-1], want)
        self.assertIsNotNone(ov.clips[-1])
        self.hl.highlight(1)                                  # 번역문 없는 조각은 예전처럼 사각형만
        s1, e1 = self.seg_units(1)
        self.assertTrue(wait(self.root, lambda: self.last_show() == self.doc.expected_rects(s1, e1)))
        self.assertIsNone(ov.caption_srcs[-1])
        self.assertIsNone(ov.clips[-1])

    def test_failed_draw_is_not_recorded_as_visible(self):
        # 막 창이 그리기에 실패하면(UpdateLayeredWindow 등) "보임" 으로 기록하지 않는다 — 진단 로그가 거짓말하지 않게
        self.make()
        self.begin()
        self.hl.highlight(0)
        s, e = self.seg_units(0)
        self.assertTrue(wait(self.root, lambda: self.last_show() == self.doc.expected_rects(s, e)))
        self.assertTrue(self.hl._overlay_visible)
        self.overlays[-1].fail = True
        self.hl.highlight(1)
        self.assertTrue(wait(self.root, lambda: len(self.overlays[-1].shows) >= 2 and not self.hl._overlay_visible))

    def two_line_segment(self):
        """두 줄짜리 조각이 있는 문서로 begin 하고, 그 조각 번호를 돌려준다(test_partly_visible_segment_scrolls 와 같은 문서)."""
        lines = LINES[:]
        lines[11] = "긴 줄 시작. " + "가나다라마 " * 3
        src = "\n\n".join(lines[:11]) + "\n\n" + lines[11] + "\n" + "이어지는 둘째 줄 " * 3 + "\n\n" + "\n\n".join(lines[12:])
        uia = "\n".join(lines[:11]) + "\n" + lines[11] + "\n" + "이어지는 둘째 줄 " * 3 + "\n" + "\n".join(lines[12:])
        self.make(uia_text=uia.replace("  ", " "), src=src)
        self.begin()
        return next(i for i, sg in enumerate(self.segs) if "긴 줄 시작" in src[sg["src_start"]:sg["src_end"]])

    def test_partial_paragraph_uses_yellow_instead_of_caption(self):
        # 2026-09-29 사용자 결정: 스크롤로 문단 일부만 보이면 번역문 막 대신 노랑(보이는 줄만으로는 막 폭을 알 수 없다)
        idx = self.two_line_segment()
        self.hl.highlight(idx, "번역문")
        ov = lambda: self.overlays[-1]                     # noqa: E731
        self.assertTrue(wait(self.root, lambda: len(self.last_show() or []) == 2 and ov().captions[-1] == "번역문"),
                        "다 보이면 번역문 막")
        self.doc.scroll = 12                               # 첫 줄이 화면 위로 나감 → 한 줄만 보임
        self.hl.notify_scroll()
        self.assertTrue(wait(self.root, lambda: len(self.last_show() or []) == 1 and ov().visible and ov().captions[-1] is None),
                        "일부만 보이면 노랑")
        self.doc.scroll = 11                               # 다시 다 보임
        self.hl.notify_scroll()
        self.assertTrue(wait(self.root, lambda: len(self.last_show() or []) == 2 and ov().captions[-1] == "번역문"),
                        "다시 다 보이면 번역문 막")

    def test_overlay_kept_while_not_covered_even_without_focus(self):
        # 2026-09-29 사용자 결정: 다른 앱이 앞 창이어도 막 자리가 가려지지 않았으면 유지, 덮이면 숨김
        self.make()
        self.begin()
        self.hl.highlight(0)
        s, e = self.seg_units(0)
        self.assertTrue(wait(self.root, lambda: self.last_show() == self.doc.expected_rects(s, e)))
        ov = self.overlays[-1]
        self.env.root_at = lambda x, y: 777                # 막 자리 맨 위는 여전히 대상 창
        self.env.fg = 555                                  # 다른 앱이 앞 창이 됨
        wait(self.root, lambda: False, timeout=0.2)
        self.assertTrue(ov.visible, "가려지지 않았으면 유지")
        self.env.root_at = lambda x, y: 555                # 다른 창이 막 자리를 덮음
        self.assertTrue(wait(self.root, lambda: not ov.visible), "덮이면 숨김")
        self.env.root_at = lambda x, y: 777                # 덮던 창이 비킴
        self.assertTrue(wait(self.root, lambda: ov.visible), "비키면 다시 보임")
        self.env.iconic = True                             # 대상 창 최소화
        self.assertTrue(wait(self.root, lambda: not ov.visible), "최소화하면 숨김")

    def test_line_count_and_probe_points(self):
        self.assertEqual(sh._line_count([(0, 0, 10, 20), (12, 0, 30, 20), (0, 20, 5, 40)]), 2)   # 같은 줄 두 사각형
        self.assertEqual(sh._line_count([]), 0)
        pts = sh._probe_points((100, 200, 300, 260))
        self.assertEqual(pts[0], (200, 230))
        self.assertTrue(all(100 <= x < 300 and 200 <= y < 260 for x, y in pts))

    def test_caption_given_before_begin_result_is_kept(self):
        self.make()
        self.hl.begin(self.src, self.segs, lambda ok, why: self.results.append((ok, why)))
        self.hl.highlight(0, "먼저 온 번역문")              # 결과 전에 온 highlight 는 번역문까지 기억한다
        self.assertTrue(wait(self.root, lambda: self.overlays and self.overlays[-1].captions))
        self.assertEqual(self.overlays[-1].captions[-1], "먼저 온 번역문")

    def test_segment_with_list_marker_starts_after_marker(self):
        self.make()
        self.begin()
        idx = next(i for i, s in enumerate(self.segs) if "문단 03" in self.src[s["src_start"]:s["src_end"]])
        self.hl.highlight(idx)
        s, e = self.seg_units(idx)
        self.assertTrue(self.doc.text(s, e).startswith("문단 03"))
        want = self.doc.expected_rects(s, e)
        self.assertTrue(wait(self.root, lambda: self.last_show() == want))
        self.assertEqual(want[0][0], FakeDoc.X0 + 2 * FakeDoc.CW, "막은 '• ' 두 칸 뒤에서 시작")

    def test_offscreen_segment_scrolls_into_view_once(self):
        """한 줄짜리 조각: 범위 ScrollIntoView 는 효과가 없고(크로미움) 감싼 요소의 ScrollItem 이 가운데로 옮긴다."""
        self.make()
        self.begin()
        idx = 20                                  # 20번째 줄은 처음엔 화면 밖(보이는 줄 0~11)
        s, e = self.seg_units(idx)
        self.assertEqual(self.doc.expected_rects(s, e), [])
        self.hl.highlight(idx)
        self.assertTrue(wait(self.root, lambda: self.doc.count("ScrollItem") == 1))
        want = lambda: self.doc.expected_rects(s, e)   # noqa: E731
        self.assertTrue(wait(self.root, lambda: want() and self.last_show() == want()))
        self.assertEqual(self.doc.scroll, 20 - FakeDoc.VIS // 2)
        self.hl.highlight(idx)                     # 같은 번호를 또 받아도 다시 스크롤하지 않는다
        wait(self.root, lambda: False, timeout=0.1)
        self.assertEqual(self.doc.count("ScrollItem"), 1)
        self.assertEqual(self.doc.count("ScrollIntoView"), 1)

    def test_partly_visible_segment_scrolls(self):
        """조각의 끝 글자가 화면 밖이면 스크롤한다(확장: 문단 전체가 들어오게)."""
        lines = LINES[:]
        lines[11] = "긴 줄 시작. " + "가나다라마 " * 3
        src = "\n\n".join(lines[:11]) + "\n\n" + lines[11] + "\n" + "이어지는 둘째 줄 " * 3 + "\n\n" + "\n\n".join(lines[12:])
        uia = "\n".join(lines[:11]) + "\n" + lines[11] + "\n" + "이어지는 둘째 줄 " * 3 + "\n" + "\n".join(lines[12:])
        self.make(uia_text=uia.replace("  ", " "), src=src)
        self.begin()
        idx = next(i for i, sg in enumerate(self.segs) if "긴 줄 시작" in src[sg["src_start"]:sg["src_end"]])
        self.hl.highlight(idx)
        self.assertTrue(wait(self.root, lambda: self.doc.count("ScrollIntoView") == 1))
        s, e = self.seg_units(idx)
        self.assertTrue(wait(self.root, lambda: self.last_show() == self.doc.expected_rects(s, e)))
        self.assertEqual(len(self.last_show()), 2, "두 줄 모두 보인다")
        self.assertEqual(self.doc.scroll, 11, "여러 줄 범위는 범위 ScrollIntoView(True)로 위에 맞춘다")

    def test_highlight_before_begin_result_is_remembered(self):
        self.make()
        gate = threading.Event()
        self.doc.hook = lambda name: gate.wait(2) if name == "GetSelection" else None
        self.hl.begin(self.src, self.segs, lambda ok, why: self.results.append((ok, why)))
        self.hl.highlight(1)                      # 결과 전에 온 highlight
        wait(self.root, lambda: False, timeout=0.05)
        self.assertEqual(self.results, [])
        gate.set()
        s, e = self.seg_units(1)
        want = self.doc.expected_rects(s, e)
        self.assertTrue(wait(self.root, lambda: self.last_show() == want))

    def test_highlight_none_clears(self):
        self.make()
        self.begin()
        self.hl.highlight(0)
        self.assertTrue(wait(self.root, lambda: self.overlays and self.overlays[-1].visible))
        self.hl.highlight(None)
        self.assertFalse(self.overlays[-1].visible)

    def test_grapheme_drift_falls_back_to_findtext(self):
        """가짜 문서가 결합 부호를 따로 센다(우리 셈과 다름) → 검증 실패 → FindText 로 대신 잡아 그대로 칠한다."""
        self.make(split_marks=True)
        ok, why, _ = self.begin()
        self.assertTrue(ok, why)
        self.assertGreater(self.doc.count("FindText"), 0)
        for idx in (0, 1, 2):
            self.hl.highlight(idx)
            s, e = self.seg_units(idx)
            want = self.doc.expected_rects(s, e)
            self.assertTrue(wait(self.root, lambda: self.last_show() == want), idx)

    # ── 전경·창 이동·휠 ──
    def test_not_foreground_hides_and_comes_back(self):
        self.make()
        self.begin()
        self.hl.highlight(0)
        self.assertTrue(wait(self.root, lambda: self.overlays and self.overlays[-1].visible))
        self.env.fg = 555                          # 다른 창으로 전환
        self.assertTrue(wait(self.root, lambda: not self.overlays[-1].visible))
        n = self.doc.count("GetBoundingRectangles")
        wait(self.root, lambda: False, timeout=0.1)
        self.assertEqual(self.doc.count("GetBoundingRectangles"), n, "전경이 아니면 묻지도 않는다")
        self.env.fg = 777                          # 돌아옴
        self.assertTrue(wait(self.root, lambda: self.overlays[-1].visible))

    def test_switched_away_during_begin_never_paints_other_window(self):
        """begin 이 도는 사이 다른 창으로 옮겨 가면, 결과가 와도 그 창 위에 한 번도 칠하지 않는다."""
        self.make()

        def hook(name):
            if name == "GetSelection":
                self.env.fg = 555
        self.doc.hook = hook
        self.hl.begin(self.src, self.segs, lambda ok, why: self.results.append((ok, why)))
        self.hl.highlight(0)                        # 결과 전에 온 highlight
        self.assertTrue(wait(self.root, lambda: self.results))
        self.assertEqual(self.results[0], (True, "ok"))
        self.doc.hook = None
        wait(self.root, lambda: False, timeout=0.1)
        self.assertTrue(all(not ov.shows for ov in self.overlays))
        self.env.fg = 777
        self.assertTrue(wait(self.root, lambda: self.overlays and self.overlays[-1].visible))

    def test_minimized_hides(self):
        self.make()
        self.begin()
        self.hl.highlight(0)
        self.assertTrue(wait(self.root, lambda: self.overlays and self.overlays[-1].visible))
        self.env.iconic = True
        self.assertTrue(wait(self.root, lambda: not self.overlays[-1].visible))

    def test_scroll_notify_from_other_thread_requeries(self):
        self.make()
        self.begin()
        self.hl.highlight(5)
        s, e = self.seg_units(5)
        self.assertTrue(wait(self.root, lambda: self.last_show() == self.doc.expected_rects(s, e)))
        self.doc.scroll = 3                         # 사용자가 휠로 3줄 내림
        t = threading.Thread(target=self.hl.notify_scroll)
        t.start()
        t.join()
        want = self.doc.expected_rects(s, e)
        self.assertTrue(wait(self.root, lambda: self.last_show() == want))
        self.assertEqual(want[0][1], FakeDoc.Y0 + 2 * FakeDoc.LH)

    def test_scroll_hides_overlay_until_quiet_then_redraws_once(self):
        # 2026-09-29 사용자 결정 "스크롤 중엔 숨기기": 휠이 오면 숨기고, 묻지 않다가, 조용해지면 한 번 물어 새 자리에 그린다
        self.make()
        self.begin()
        self.hl.highlight(5)
        s, e = self.seg_units(5)
        self.assertTrue(wait(self.root, lambda: self.last_show() == self.doc.expected_rects(s, e)))
        self.assertTrue(self.overlays[-1].visible)
        wait(self.root, lambda: False, timeout=0.1)          # 앞 요청이 다 돌아오게
        asked = self.doc.count("GetBoundingRectangles")
        self.doc.scroll = 3
        self.hl.notify_scroll()
        self.assertTrue(wait(self.root, lambda: not self.overlays[-1].visible), "휠이 오면 막을 숨긴다")
        self.assertEqual(self.doc.count("GetBoundingRectangles"), asked, "스크롤 중에는 묻지 않는다")
        want = self.doc.expected_rects(s, e)
        self.assertTrue(wait(self.root, lambda: self.overlays[-1].visible and self.last_show() == want),
                        "멈추면 새 자리에 다시 그린다")
        self.assertEqual(self.doc.count("GetBoundingRectangles"), asked + 1, "멈춘 뒤 한 번만 묻는다")

    def test_window_move_requeries(self):
        self.make()
        self.begin()
        self.hl.highlight(2)
        s, e = self.seg_units(2)
        self.assertTrue(wait(self.root, lambda: self.last_show() == self.doc.expected_rects(s, e)))
        n = self.doc.count("GetBoundingRectangles")
        self.env.rect = (10, 0, 1010, 800)
        self.assertTrue(wait(self.root, lambda: self.doc.count("GetBoundingRectangles") > n))

    def test_rects_clipped_to_window(self):
        self.make()
        self.env.rect = (0, 0, 200, 800)            # 창이 좁아 줄 오른쪽이 창 밖
        self.begin()
        self.hl.highlight(0)
        self.assertTrue(wait(self.root, lambda: self.last_show() is not None))
        self.assertTrue(all(r[2] <= 200 for r in self.last_show()))

    # ── 1초 초과·범위 잃음·대상 닫힘 ──
    def test_slow_call_during_reading_stops_painting(self):
        self.make()
        self.begin()
        self.hl.highlight(0)
        self.assertTrue(wait(self.root, lambda: self.overlays and self.overlays[-1].visible))
        self.doc.hook = lambda name: self.clock.advance(1.5) if name == "GetBoundingRectangles" else None
        self.hl.highlight(1)
        self.assertTrue(wait(self.root, lambda: self.stops))
        self.assertEqual(self.stops[0][0], "slow")
        self.assertIs(self.stops[0][1], threading.current_thread(), "on_stop 도 Tk 메인에서")
        self.assertFalse(self.hl.active)
        self.assertFalse(self.overlays[-1].visible)
        self.doc.hook = None
        n = len(self.doc.calls)
        self.hl.highlight(2)                        # 그 읽기 동안은 더 묻지 않는다
        self.hl.notify_scroll()
        wait(self.root, lambda: False, timeout=0.1)
        self.assertEqual(len(self.doc.calls), n)

    def test_slow_call_during_begin_fails(self):
        self.make()
        self.doc.hook = lambda name: self.clock.advance(1.2) if name == "GetSelection" else None
        ok, why, _ = self.begin()
        self.assertEqual((ok, why), (False, "slow"))
        self.assertFalse(self.hl.active)

    def test_stuck_call_is_caught_by_tk_watchdog(self):
        """호출이 돌아오지 않아도(멈춘 앱) Tk 틱이 1초 넘김을 보고 중단한다. 그 사이 새 begin 은 uia_busy."""
        self.make()
        self.begin()
        self.hl.highlight(0)
        self.assertTrue(wait(self.root, lambda: self.overlays and self.overlays[-1].visible))
        gate = threading.Event()
        self.doc.hook = lambda name: gate.wait(3) if name == "GetBoundingRectangles" else None
        self.hl.highlight(1)
        self.assertTrue(wait(self.root, lambda: self.hl._worker.call_since is not None))
        self.clock.advance(1.1)
        self.assertTrue(wait(self.root, lambda: self.stops))
        self.assertEqual(self.stops[0][0], "slow")
        self.assertFalse(self.overlays[-1].visible)
        self.results.clear()
        self.hl.begin(self.src, self.segs, lambda ok, why: self.results.append((ok, why)))
        self.assertTrue(wait(self.root, lambda: self.results))
        self.assertEqual(self.results[0], (False, "uia_busy"))
        self.doc.hook = None
        gate.set()

    def test_lost_range_stops(self):
        self.make()
        self.begin()

        def hook(name):
            if name == "GetBoundingRectangles":
                raise FakeCOMError(UIA_E_ELEMENTNOTAVAILABLE_SIGNED)
        self.doc.hook = hook
        self.hl.highlight(0)
        self.assertTrue(wait(self.root, lambda: self.stops))
        self.assertEqual(self.stops[0][0], "lost")
        self.assertFalse(self.hl.active)

    def test_target_closed_stops(self):
        self.make()
        self.begin()
        self.env.alive = False
        self.assertTrue(wait(self.root, lambda: self.stops))
        self.assertEqual(self.stops[0][0], "target_closed")

    # ── begin 실패 ──
    def test_text_mismatch(self):
        self.make(uia_text="Completely different text that the user did not copy at all.\nAnother line here.")
        self.assertEqual(self.begin()[:2], (False, "text_mismatch"))

    def test_text_pattern_depth_limit(self):
        self.make(depth=8)                         # 포커스에서 8단계 위 → 찾는다
        self.assertEqual(self.begin()[:2], (True, "ok"))
        self.hl.destroy()
        self.make(depth=9)                         # 9단계 위 → 못 찾는다
        self.assertEqual(self.begin()[:2], (False, "no_text_pattern"))

    def test_own_window_does_not_touch_uia(self):
        self.make()
        self.env.target_pid = FakeEnv.own_pid
        self.assertEqual(self.begin()[:2], (False, "own_window"))
        self.assertEqual(self.doc.count("GetFocusedElement"), 0)

    def test_focus_changed(self):
        self.make(focus_pid=31337)
        self.assertEqual(self.begin()[:2], (False, "focus_changed"))

    def test_empty_selection(self):
        self.make()
        self.doc.sel = (5, 5)
        self.assertEqual(self.begin()[:2], (False, "empty_selection"))

    # ── end ──
    def test_end_hides_and_ignores_late_results(self):
        self.make()
        self.begin()
        self.hl.highlight(0)
        self.assertTrue(wait(self.root, lambda: self.overlays and self.overlays[-1].visible))
        gate = threading.Event()
        self.doc.hook = lambda name: gate.wait(2) if name == "GetBoundingRectangles" else None
        self.hl.highlight(1)
        self.hl.end()
        self.assertFalse(self.overlays[-1].visible)
        self.assertFalse(self.hl.active)
        shows = len(self.overlays[-1].shows)
        gate.set()
        wait(self.root, lambda: False, timeout=0.1)
        self.assertEqual(len(self.overlays[-1].shows), shows, "end 뒤 늦게 온 결과로 다시 그리지 않는다")
        self.assertEqual(self.stops, [])

    def test_end_before_result_suppresses_on_result(self):
        self.make()
        gate = threading.Event()
        self.doc.hook = lambda name: gate.wait(2) if name == "GetSelection" else None
        self.hl.begin(self.src, self.segs, lambda ok, why: self.results.append((ok, why)))
        self.hl.end()
        gate.set()
        wait(self.root, lambda: False, timeout=0.15)
        self.assertEqual(self.results, [])

    def test_no_forbidden_calls_in_full_flow(self):
        self.make()
        self.begin()
        for idx in (0, 20, 3):
            self.hl.highlight(idx)
            wait(self.root, lambda: False, timeout=0.05)
        self.hl.notify_scroll()
        wait(self.root, lambda: False, timeout=0.1)
        self.hl.end()
        self.assertEqual(self.doc.forbidden, [])


if __name__ == "__main__":
    unittest.main()
