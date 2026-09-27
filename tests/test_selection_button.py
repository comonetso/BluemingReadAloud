# -*- coding: utf-8 -*-
"""selection_button 단위테스트.  실행: python -m unittest discover -s tests  (프로젝트 폴더에서)

무엇을 보나
  - SelectionGestureDetector: 가짜 시계(초)·좌표로 끌기 임계값 경계, 더블/트리플클릭, 느린 두 번 클릭(시간 초과),
    멀리 떨어진 두 번 클릭, 휠/키 → hide, 점이 떠 있을 때 누름 → hide.
  - system_gesture_settings 의 값 읽기(가짜 읽기 함수로 실패·0·음수 처리).
  - 점 자리(dot_position), 원 모양 표(circle_mask), 점 그림(render_dot_bgra), contains 판정.
  - 적대 입력(AdversarialDetectorTest): 음수 좌표, 소수 경계, 시계 역행, 누름 없는 뗌, 뗌 없는 누름 두 번,
    아주 느린 트리플클릭, 트리플 중간 끊김, 더블클릭 뒤 끌기.
  - 점 누름·뗌 판정(ClickLogicTest): 점 안 누름·안 뗌 → on_click 1번, 안 누름·밖 뗌 → 0번, 연타 → 1번 등.
창을 띄우지 않는다(사용자가 이 PC 에서 앱을 쓰는 중이라 테스트가 화면에 무엇도 띄우면 안 된다).
SelectionButton 은 창 없이 판정 부분만 보려고 __new__ 로 만든 뒤 필요한 값만 채운다.
실제 창(스타일·창 모양·WindowFromPoint·캡처)은 3초 데모로 따로 쟀다(2026-09-28, 보고서 참고).
"""
import os
import sys
import unittest
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import selection_button as sb  # noqa: E402
from selection_button import SelectionGestureDetector  # noqa: E402

SHOW = "show"
HIDE = ("hide",)


def det(drag=(4, 4), dbl_time=0.5, dbl_size=(4, 4)):
    """윈도우 기본값(끌기 4px, 더블클릭 0.5초·4px)으로 감지기를 만든다."""
    return SelectionGestureDetector(drag_threshold=drag, double_click_time=dbl_time, double_click_size=dbl_size)


def click(d, x, y, t, hold=0.05):
    """누르고 hold 초 뒤 같은 자리에서 뗀다. (누름 결과, 뗌 결과)."""
    return d.on_press(x, y, t), d.on_release(x, y, t + hold)


class DragTest(unittest.TestCase):
    """끌기: 누른 곳과 뗀 곳이 임계값 "이상" 떨어지면 show."""

    def test_below_threshold_is_click(self):
        d = det()
        self.assertIsNone(d.on_press(100, 100, 1.0))
        self.assertIsNone(d.on_release(103, 100, 1.2))   # 3px < 4

    def test_exact_threshold_shows(self):
        d = det()
        d.on_press(100, 100, 1.0)
        self.assertEqual(d.on_release(104, 100, 1.2), (SHOW, 104, 100))

    def test_vertical_threshold(self):
        d = det()
        d.on_press(100, 100, 1.0)
        self.assertIsNone(d.on_release(100, 103, 1.2))
        d.on_press(100, 100, 5.0)
        self.assertEqual(d.on_release(100, 104, 5.2), (SHOW, 100, 104))

    def test_negative_direction(self):
        # 오른쪽→왼쪽, 아래→위로 끌어도 같다
        d = det()
        d.on_press(100, 100, 1.0)
        self.assertEqual(d.on_release(96, 100, 1.2), (SHOW, 96, 100))
        d.on_press(100, 100, 5.0)
        self.assertEqual(d.on_release(100, 96, 5.2), (SHOW, 100, 96))

    def test_diagonal_below_both_is_click(self):
        # 가로·세로 각각 따로 본다(3,3 은 대각선으로 4 넘지만 끌기 아님 — 윈도우 DragDetect 사각형과 같은 방식)
        d = det()
        d.on_press(100, 100, 1.0)
        self.assertIsNone(d.on_release(103, 103, 1.2))

    def test_long_drag(self):
        d = det()
        d.on_press(10, 10, 1.0)
        self.assertEqual(d.on_release(600, 240, 3.0), (SHOW, 600, 240))

    def test_custom_threshold(self):
        d = det(drag=(10, 6))
        d.on_press(0, 0, 1.0)
        self.assertIsNone(d.on_release(9, 5, 1.1))
        d.on_press(0, 0, 5.0)
        self.assertEqual(d.on_release(10, 0, 5.1), (SHOW, 10, 0))
        d.on_press(0, 0, 9.0)
        self.assertEqual(d.on_release(0, 6, 9.1), (SHOW, 0, 6))

    def test_release_without_press(self):
        # 훅이 버튼을 누른 채 시작된 경우 등 — 근거가 없으니 아무것도 안 한다
        self.assertIsNone(det().on_release(500, 500, 1.0))

    def test_release_consumes_press(self):
        d = det()
        d.on_press(0, 0, 1.0)
        d.on_release(0, 0, 1.1)
        self.assertIsNone(d.on_release(50, 0, 1.2))   # 두 번째 뗌은 누름이 없다


class MultiClickTest(unittest.TestCase):
    """더블·트리플클릭의 뗌에서 show. 누름과 누름 사이 시간·거리로 이어짐을 판단."""

    def test_single_click_does_not_show(self):
        d = det()
        self.assertEqual(click(d, 100, 100, 1.0), (None, None))

    def test_double_click_shows_on_second_release(self):
        d = det()
        self.assertEqual(click(d, 100, 100, 1.0), (None, None))
        p, r = click(d, 101, 100, 1.25)
        self.assertIsNone(p)
        self.assertEqual(r, (SHOW, 101, 100))

    def test_double_click_time_boundary_inclusive(self):
        d = det()
        click(d, 100, 100, 1.0)
        self.assertEqual(click(d, 100, 100, 1.5)[1], (SHOW, 100, 100))   # 정확히 0.5초 = 이어짐

    def test_slow_second_click_is_single(self):
        d = det()
        click(d, 100, 100, 1.0)
        self.assertEqual(click(d, 100, 100, 1.51), (None, None))   # 0.51초 > 0.5

    def test_far_second_click_is_single(self):
        d = det()
        click(d, 100, 100, 1.0)
        self.assertEqual(click(d, 103, 100, 1.1), (None, None))    # 가로 3 > 4/2
        d2 = det()
        click(d2, 100, 100, 1.0)
        self.assertEqual(click(d2, 100, 97, 1.1), (None, None))    # 세로 3 > 4/2

    def test_double_click_size_boundary_inclusive(self):
        d = det()
        click(d, 100, 100, 1.0)
        self.assertEqual(click(d, 102, 98, 1.1)[1], (SHOW, 102, 98))   # 가로·세로 정확히 2 = 이어짐

    def test_triple_click(self):
        d = det()
        self.assertEqual(click(d, 50, 50, 1.0), (None, None))
        self.assertEqual(click(d, 50, 50, 1.2), (None, (SHOW, 50, 50)))
        # 세 번째 누름: 점이 떠 있으니 숨기고, 뗌에서 다시 띄운다
        self.assertEqual(click(d, 50, 50, 1.4), (HIDE, (SHOW, 50, 50)))

    def test_quadruple_click_still_shows(self):
        # 크로미움은 네 번째부터도 문단 선택(클릭 수 3 유지)이라 선택이 남는다 → 계속 show
        d = det()
        for i in range(3):
            click(d, 50, 50, 1.0 + 0.2 * i)
        self.assertEqual(click(d, 50, 50, 1.6)[1], (SHOW, 50, 50))

    def test_triple_chain_compares_with_previous_press(self):
        # 각 누름을 "바로 앞 누름"과 비교한다: 0→2→4 는 첫 누름과 4 떨어졌지만 트리플로 센다
        d = det()
        click(d, 0, 0, 1.0)
        self.assertEqual(click(d, 2, 0, 1.2)[1], (SHOW, 2, 0))
        self.assertEqual(click(d, 4, 0, 1.4)[1], (SHOW, 4, 0))

    def test_double_click_timed_between_presses(self):
        # 윈도우처럼 "누름~누름" 시간을 잰다: 첫 클릭을 오래 누르고 있었으면 이어지지 않는다
        d = det()
        d.on_press(10, 10, 1.0)
        d.on_release(10, 10, 1.45)
        self.assertEqual(click(d, 10, 10, 1.55), (None, None))   # 누름 사이 0.55초

    def test_click_after_slow_pair_restarts_count(self):
        d = det()
        click(d, 10, 10, 1.0)
        click(d, 10, 10, 2.0)                                     # 느림 → 새 첫 클릭
        self.assertEqual(click(d, 10, 10, 2.3)[1], (SHOW, 10, 10))  # 이것과 이어져 더블

    def test_clock_going_backwards_is_not_double(self):
        d = det()
        click(d, 10, 10, 5.0)
        self.assertEqual(click(d, 10, 10, 4.9), (None, None))

    def test_double_click_then_drag_shows(self):
        # 더블클릭 뒤 끌기(단어 단위로 넓히기) — 끌기로도 show
        d = det()
        click(d, 10, 10, 1.0)
        d.on_press(10, 10, 1.2)
        self.assertEqual(d.on_release(200, 10, 1.8), (SHOW, 200, 10))

    def test_custom_double_click_settings(self):
        d = det(dbl_time=0.9, dbl_size=(10, 10))
        click(d, 0, 0, 1.0)
        self.assertEqual(click(d, 5, -5, 1.85)[1], (SHOW, 5, -5))


class HideTest(unittest.TestCase):
    """점이 떠 있을 때 누름 → hide. 휠·키·다른 버튼 → hide."""

    def _shown(self):
        d = det()
        d.on_press(0, 0, 1.0)
        self.assertEqual(d.on_release(100, 0, 1.5), (SHOW, 100, 0))
        return d

    def test_press_hides_when_shown(self):
        d = self._shown()
        self.assertEqual(d.on_press(300, 300, 3.0), HIDE)

    def test_press_hides_only_once(self):
        d = self._shown()
        self.assertEqual(click(d, 300, 300, 3.0), (HIDE, None))
        self.assertEqual(click(d, 300, 300, 9.0), (None, None))   # 이미 숨겼다

    def test_press_does_not_hide_when_not_shown(self):
        self.assertIsNone(det().on_press(0, 0, 1.0))

    def test_other_input_always_hides(self):
        d = det()
        self.assertEqual(d.on_other_input(), HIDE)   # 안 떠 있어도 hide (여러 번 불러도 괜찮은 동작)
        d = self._shown()
        self.assertEqual(d.on_other_input(), HIDE)
        self.assertIsNone(d.on_press(0, 0, 5.0))      # 휠/키로 이미 숨겼으니 누름은 None

    def test_other_input_does_not_cancel_drag(self):
        # 끌면서 휠로 스크롤해 길게 고르는 경우 — 휠이 끌기를 끊지 않는다
        d = det()
        d.on_press(0, 0, 1.0)
        self.assertEqual(d.on_other_input(), HIDE)
        self.assertEqual(d.on_release(0, 400, 2.0), (SHOW, 0, 400))

    def test_other_input_keeps_click_chain(self):
        d = det()
        click(d, 10, 10, 1.0)
        d.on_other_input()
        self.assertEqual(click(d, 10, 10, 1.2)[1], (SHOW, 10, 10))


class SystemSettingsTest(unittest.TestCase):
    def test_reads_values(self):
        metrics = {sb.SM_CXDRAG: 6, sb.SM_CYDRAG: 7, sb.SM_CXDOUBLECLK: 8, sb.SM_CYDOUBLECLK: 9}
        got = sb._read_gesture_settings(metrics.get, lambda: 700)
        self.assertEqual(got, {"drag_threshold": (6, 7), "double_click_time": 0.7, "double_click_size": (8, 9)})

    def test_zero_means_failure(self):
        got = sb._read_gesture_settings(lambda i: 0, lambda: 0)
        self.assertEqual(got, {"drag_threshold": (4, 4), "double_click_time": 0.5, "double_click_size": (4, 4)})

    def test_exceptions_and_none(self):
        def boom(*a):
            raise OSError("no user32")
        self.assertEqual(sb._read_gesture_settings(boom, boom)["drag_threshold"], (4, 4))
        self.assertEqual(sb._read_gesture_settings(None, None)["double_click_time"], 0.5)

    def test_negative_drag_uses_magnitude(self):
        got = sb._read_gesture_settings(lambda i: -5, lambda: 500)
        self.assertEqual(got["drag_threshold"], (5, 5))

    def test_real_system_call_shape(self):
        # GetSystemMetrics/GetDoubleClickTime 을 읽기만 한다(창·입력 없음)
        got = sb.system_gesture_settings()
        self.assertEqual(set(got), {"drag_threshold", "double_click_time", "double_click_size"})
        self.assertTrue(all(v > 0 for v in got["drag_threshold"] + got["double_click_size"]))
        self.assertGreater(got["double_click_time"], 0)
        SelectionGestureDetector(**got)   # 그대로 넘길 수 있다


class DotPositionTest(unittest.TestCase):
    def test_right_of_release_point_vertically_centered(self):
        # 22px·GAP 4 (배율 1): 왼쪽 = x + 4, 세로 가운데 = y
        self.assertEqual(sb.dot_position(100, 200, 22, 4, (0, 0, 1920, 1080)), (104, 189))
        # 홀수 크기(배율 1.4 → 31px): 가운데 칸 = top + 15 = y
        left, top = sb.dot_position(100, 200, 31, 6, (0, 0, 1920, 1080))
        self.assertEqual((left, top + 31 // 2), (106, 200))

    def test_clamped_into_work_area(self):
        area = (0, 0, 1920, 1040)   # 작업표시줄 제외
        # 오른쪽 아래 끝: 끌어넣으면 (1898, 1018) 인데 그러면 커서(1919,1039)를 덮는다 → 커서 왼쪽 1919-4-22 = 1893
        self.assertEqual(sb.dot_position(1919, 1039, 22, 4, area), (1919 - 4 - 22, 1040 - 22))
        # 작업 영역 밖(왼쪽 위)에서 뗌: 끌어넣은 자리가 커서를 덮지 않으므로 그대로
        self.assertEqual(sb.dot_position(-50, -50, 22, 4, area), (0, 0))

    def test_second_monitor_work_area(self):
        area = (-1920, 0, 0, 1080)   # 왼쪽 보조 모니터
        # 오른쪽 끝(-5)에서 뗌: 끌어넣으면 (-22, 0) 이 커서를 덮는다 → 커서 왼쪽 -5-4-22 = -31
        self.assertEqual(sb.dot_position(-5, 5, 22, 4, area), (-31, 0))

    def test_never_under_cursor_near_right_edge(self):
        """3차 검증 verifyDot.md ④-1: 최대화 창의 세로 스크롤바(화면 오른쪽 끝 약 20px)를 끌고 놓으면
        점이 마우스 밑에 떠서 다음 클릭이 스크롤바 대신 점을 눌렀다 → 끌어넣은 결과가 커서를 덮으면 커서 왼쪽으로.
        오른쪽 끝에서 size 픽셀 안쪽 모든 x 와 여러 y 에서 "점 창 사각형이 커서 픽셀을 덮지 않는다" 를 확인한다."""
        for size, gap, area in ((31, 6, (0, 0, 2560, 1384)), (22, 4, (0, 0, 1920, 1040)),
                                (31, 6, (-2560, 0, 0, 1384))):
            l, t, r, b = area
            for x in range(r - size - gap - 2, r):
                for y in (t, t + 3, (t + b) // 2, b - 3, b - 1):
                    left, top = sb.dot_position(x, y, size, gap, area)
                    covers = left <= x < left + size and top <= y < top + size
                    self.assertFalse(covers, (size, gap, area, x, y, left, top))
                    self.assertGreaterEqual(left, l)
                    self.assertLessEqual(left + size, r)
                    self.assertGreaterEqual(top, t)
                    self.assertLessEqual(top + size, b)

    def test_flip_only_when_covering(self):
        # 오른쪽 끝에서 size+gap 보다 멀리 떨어진 곳: 끌어넣기도 뒤집기도 없음 (x+gap)
        area = (0, 0, 2560, 1384)
        self.assertEqual(sb.dot_position(2560 - 31 - 6 - 1, 700, 31, 6, area), (2560 - 31 - 1, 685))
        # 끌어넣기는 됐지만 커서를 덮지 않는 경우(x+gap 이 작업 영역을 조금 넘음): 끌어넣은 자리 그대로
        #   x=2527: x+6=2533 > 2560-31=2529 → left=2529, 커서 2527 < 2529 이라 덮지 않음
        self.assertEqual(sb.dot_position(2527, 700, 31, 6, area), (2529, 685))
        # x=2529: left=2529 가 커서 2529 를 덮음 → 2529-6-31 = 2492
        self.assertEqual(sb.dot_position(2529, 700, 31, 6, area), (2492, 685))
        # 아래 끝만 끌어넣은 경우(가로는 x+gap 그대로라 커서 오른쪽): 뒤집지 않음
        self.assertEqual(sb.dot_position(1000, 1383, 31, 6, area), (1006, 1353))
        # 소수 좌표: 커서 픽셀은 floor
        self.assertEqual(sb.dot_position(2559.9, 700.5, 31, 6, area), (2559 - 6 - 31, 685))

    def test_no_area(self):
        self.assertEqual(sb.dot_position(10.7, 20.2, 22, 4, None), (14, 9))

    def test_measured_layout_this_pc(self):
        """2026-09-28 이 PC 실측값 그대로(배율 140% → 점 창 31px, 간격 6px, 모니터 두 대).

        주 모니터 작업 영역 (0,0,2560,1384), 왼쪽 모니터 (-2560,0,0,1384). 실제 창(GetWindowRect)도 이 자리였다
        (3차 실측 때의 값. 그 뒤 "커서를 덮으면 왼쪽으로" 보정으로 오른쪽 끝 두 경우는 계산값을 바꿨다 — 새 자리는 실측 안 함).
        함정: 왼쪽 모니터 오른쪽 끝(-1)에서 떼면 x+6 = 5 는 주 모니터다 → "뗀 곳의 모니터" 안으로 끌어넣어
        점이 모니터 경계에 걸쳐 두 모니터로 쪼개져 보이지 않게 한다(보정 뒤에도 왼쪽 모니터 안에 남는다).
        """
        prim = (0, 0, 2560, 1384)
        left = (-2560, 0, 0, 1384)
        self.assertEqual(sb.dot_position(2350, 1342, 31, 6, prim), (2356, 1327))    # 보통: x+6, 세로 가운데 = y
        # 오른쪽 아래 끝: 끌어넣은 (2529, 1353) 은 커서를 덮는다 → 커서 왼쪽 2559-6-31 = 2522 (2026-09-28 보정)
        self.assertEqual(sb.dot_position(2559, 1383, 31, 6, prim), (2522, 1353))
        # 왼쪽 모니터 오른쪽 끝·위: 끌어넣은 (-31, 0) 은 커서(-1,5)를 덮는다 → -1-6-31 = -38
        self.assertEqual(sb.dot_position(-1, 5, 31, 6, left), (-38, 0))
        self.assertEqual(sb.dot_position(-2560, 1383, 31, 6, left), (-2554, 1353))  # 왼쪽 모니터 왼쪽 아래


class ShapeTest(unittest.TestCase):
    def test_circle_mask_symmetric(self):
        for size in (22, 31):
            m = sb.circle_mask(size)
            self.assertEqual(len(m), size)
            self.assertTrue(all(len(r) == size for r in m))
            for y in range(size):
                for x in range(size):
                    self.assertEqual(m[y][x], m[size - 1 - y][x])
                    self.assertEqual(m[y][x], m[y][size - 1 - x])
            self.assertTrue(m[size // 2][size // 2])
            self.assertFalse(m[0][0])
            self.assertTrue(m[size // 2][0])   # 가운데 줄 양 끝은 원 안

    def test_render_dot(self):
        size = 22
        mask = sb.circle_mask(size)
        data = sb.render_dot_bgra(size, 12, mask)
        self.assertEqual(len(data), size * size * 4)

        def px(x, y):
            i = (y * size + x) * 4
            return tuple(data[i:i + 4])

        self.assertEqual(px(11, 11), (0x30, 0x3B, 0xFF, 255))   # 가운데 = #ff3b30 불투명(B,G,R,A)
        self.assertEqual(px(0, 0)[3], 0)                        # 원 밖 모서리 = 투명(클릭 통과)
        self.assertEqual(px(1, 11)[3], sb.RING_ALPHA)           # 점 밖·클릭 영역 안 = 알파 1
        for x in range(size):                                   # 미리 곱한 알파: 색 ≤ 알파
            b, g, r, a = px(x, 11)
            self.assertTrue(max(b, g, r) <= a)

    def test_hover_dot_is_bigger(self):
        size = 31
        mask = sb.circle_mask(size)
        normal = sb.render_dot_bgra(size, 12 * 1.4, mask)
        hover = sb.render_dot_bgra(size, 12 * 1.25 * 1.4, mask)

        def opaque(data):
            return sum(1 for i in range(3, len(data), 4) if data[i] == 255)

        self.assertGreater(opaque(hover), opaque(normal))
        # 확장 비율 그대로: 넓이 비 ≈ 1.25² ≈ 1.56
        self.assertAlmostEqual(opaque(hover) / opaque(normal), 1.5625, delta=0.2)


class ContainsTest(unittest.TestCase):
    """창을 만들지 않고 contains 판정만 본다(__new__ 로 필요한 값만 채움)."""

    def _button(self, pos, size=22):
        b = sb.SelectionButton.__new__(sb.SelectionButton)
        b._size = size
        b._mask = sb.circle_mask(size)
        b._pos = pos
        return b

    def test_hidden_contains_nothing(self):
        self.assertFalse(self._button(None).contains(10, 10))

    def test_inside_outside(self):
        b = self._button((100, 200))
        self.assertTrue(b.contains(111, 211))      # 가운데
        self.assertTrue(b.contains(100.9, 211))    # 왼쪽 끝 칸(소수 좌표는 내림)
        self.assertFalse(b.contains(100, 200))     # 원 밖 모서리
        self.assertFalse(b.contains(99, 211))      # 창 밖
        self.assertFalse(b.contains(122, 211))     # 창 밖(오른쪽)
        self.assertFalse(b.contains("x", 211))     # 이상한 값 → False

    def test_matches_mask_everywhere(self):
        b = self._button((0, 0), size=31)
        for y in range(31):
            for x in range(31):
                self.assertEqual(b.contains(x, y), b._mask[y][x])

    def test_msg_fallback(self):
        b = sb.SelectionButton.__new__(sb.SelectionButton)
        b._get_msg = lambda key, *a: "[Missing message: %s]" % key
        self.assertEqual(b._msg("selection_button_title"), "선택한 글 읽기")
        b._get_msg = lambda key, *a: "Read the selected text"
        self.assertEqual(b._msg("selection_button_title"), "Read the selected text")


class AdversarialDetectorTest(unittest.TestCase):
    """감지 로직을 일부러 이상한 입력으로 흔든다(2026-09-28 반증 담당 추가).

    훅은 실제로 이런 걸 줄 수 있다: 왼쪽 모니터의 음수 좌표, 훅이 뗌을 놓친 누름(관리자 권한 창 위에서 떼는 등),
    사람이 아주 느리게 누르는 트리플클릭. 각 테스트의 기대값은 "윈도우·크로미움이 그 입력을 어떻게 받느냐"에 맞췄다.
    """

    def test_negative_coordinates_drag(self):
        # 왼쪽 모니터(-2560..0). 절댓값 차이만 보므로 음수여도 같다
        d = det()
        d.on_press(-100, 50, 1.0)
        self.assertIsNone(d.on_release(-103, 50, 1.1))            # 3px
        d.on_press(-100, 50, 5.0)
        self.assertEqual(d.on_release(-104, 50, 5.1), (SHOW, -104, 50))
        d.on_press(-2, 0, 9.0)                                    # 모니터 경계를 넘는 끌기(-2 → +2)
        self.assertEqual(d.on_release(2, 0, 9.1), (SHOW, 2, 0))

    def test_negative_coordinates_double_click(self):
        d = det()
        click(d, -1500, 700, 1.0)
        self.assertEqual(click(d, -1502, 702, 1.2)[1], (SHOW, -1502, 702))   # 가로·세로 2 = 이어짐
        d2 = det()
        click(d2, -1500, 700, 1.0)
        self.assertEqual(click(d2, -1503, 700, 1.2), (None, None))           # 3 > 2 = 새 첫 클릭

    def test_fractional_threshold_boundary(self):
        # 소수 좌표(훅은 정수를 주지만 약속상 숫자면 된다): 3.999 는 끌기 아님, 4.0 은 끌기
        d = det()
        d.on_press(0.0, 0.0, 1.0)
        self.assertIsNone(d.on_release(3.999, 0.0, 1.1))
        d.on_press(0.5, 0.5, 2.0)
        self.assertEqual(d.on_release(4.5, 0.5, 2.1), (SHOW, 4.5, 0.5))

    def test_both_axes_exactly_below_and_at(self):
        d = det()
        d.on_press(10, 10, 1.0)
        self.assertIsNone(d.on_release(13, 7, 1.1))               # 가로 3·세로 3 → 끌기 아님
        d.on_press(10, 10, 5.0)
        self.assertEqual(d.on_release(6, 6, 5.1), (SHOW, 6, 6))   # 가로 4(왼쪽 방향) → 끌기

    def test_clock_backwards_mid_triple(self):
        # 시계가 거꾸로 가면 그 누름은 새 첫 클릭. 그 뒤로는 새 기준에서 다시 센다
        d = det()
        click(d, 10, 10, 5.0)
        self.assertEqual(click(d, 10, 10, 5.2)[1], (SHOW, 10, 10))   # 더블
        self.assertEqual(click(d, 10, 10, 4.0), (HIDE, None))        # 역행 → 한 번 클릭(떠 있던 점은 숨김)
        self.assertEqual(click(d, 10, 10, 4.3)[1], (SHOW, 10, 10))   # 4.0 기준 0.3초 → 더블

    def test_same_timestamp_counts_as_continuous(self):
        # dt = 0 (같은 시각 두 누름) — 0 ≤ dt 이므로 이어진 것으로 센다(시계 해상도가 거친 경우)
        d = det()
        click(d, 10, 10, 1.0, hold=0.0)
        self.assertEqual(click(d, 10, 10, 1.0, hold=0.0)[1], (SHOW, 10, 10))

    def test_release_without_press_does_not_touch_shown_state(self):
        d = det()
        d.on_press(0, 0, 1.0)
        d.on_release(100, 0, 1.2)                                  # show
        self.assertIsNone(d.on_release(200, 0, 1.3))              # 누름 없는 뗌
        self.assertEqual(d.on_press(300, 0, 3.0), HIDE)           # 여전히 떠 있다고 보고 누름에서 숨김

    def test_two_presses_without_release_quick_same_spot(self):
        # 첫 뗌을 훅이 놓쳤다. 같은 자리 0.2초 뒤 누름 = 실제로는 더블클릭(앱은 단어를 골랐다) → 뗌에서 show
        d = det()
        self.assertIsNone(d.on_press(50, 50, 1.0))
        self.assertIsNone(d.on_press(50, 50, 1.2))
        self.assertEqual(d.on_release(50, 50, 1.25), (SHOW, 50, 50))

    def test_two_presses_without_release_far_or_slow(self):
        # 놓친 뗌 뒤의 누름이 멀거나 느리면 한 번 클릭 → 뗌에서 아무것도 안 함(두 번째 누름 기준으로 끌기를 잰다)
        d = det()
        d.on_press(50, 50, 1.0)
        d.on_press(500, 500, 1.2)
        self.assertIsNone(d.on_release(501, 500, 1.3))
        d2 = det()
        d2.on_press(50, 50, 1.0)
        d2.on_press(50, 50, 3.0)
        self.assertIsNone(d2.on_release(50, 50, 3.1))

    def test_press_without_release_then_drag_measured_from_new_press(self):
        d = det()
        d.on_press(0, 0, 1.0)            # 뗌 놓침
        d.on_press(100, 100, 5.0)
        self.assertIsNone(d.on_release(102, 100, 5.1))            # 새 누름 기준 2px → 끌기 아님(옛 누름 기준이면 102px)

    def test_very_slow_triple_click_each_gap_at_limit(self):
        # 누름 사이가 매번 정확히 0.5초 — 각 누름이 "바로 앞 누름"과 이어지므로 트리플(전체 1초 걸려도)
        d = det()
        self.assertEqual(click(d, 20, 20, 1.0, hold=0.1), (None, None))
        self.assertEqual(click(d, 20, 20, 1.5, hold=0.1), (None, (SHOW, 20, 20)))
        self.assertEqual(click(d, 20, 20, 2.0, hold=0.1), (HIDE, (SHOW, 20, 20)))

    def test_triple_click_with_late_third(self):
        # 1→2 는 더블, 2→3 은 0.51초 → 세 번째는 한 번 클릭(앱은 선택을 푼다) → 누름에서 숨기고 뗌에서 안 띄움
        d = det()
        click(d, 20, 20, 1.0)
        self.assertEqual(click(d, 20, 20, 1.3)[1], (SHOW, 20, 20))
        self.assertEqual(click(d, 20, 20, 1.81), (HIDE, None))

    def test_double_click_then_drag_back_near_start(self):
        # 더블클릭의 두 번째 누름은 끌기 거리와 상관없이 show(뗀 자리가 누른 자리 근처여도)
        d = det()
        click(d, 10, 10, 1.0)
        d.on_press(10, 10, 1.2)
        self.assertEqual(d.on_release(11, 10, 2.5), (SHOW, 11, 10))

    def test_huge_values(self):
        d = det()
        d.on_press(10 ** 9, -10 ** 9, 1e9)
        self.assertEqual(d.on_release(10 ** 9 + 4, -10 ** 9, 1e9 + 1), (SHOW, 10 ** 9 + 4, -10 ** 9))


_Ev = namedtuple("_Ev", "x y")


class ClickLogicTest(unittest.TestCase):
    """점 누름·뗌 → on_click 판정(_on_press/_on_release)을 창 없이 본다.

    SelectionButton 을 __new__ 로 만들고 진짜 hide() 를 쓴다. 창 대신 가짜 win(winfo_id 0 → 틀 핸들 없음 →
    Tk withdraw 경로)을 넣어 화면에는 아무것도 안 뜬다. 좌표는 점 창 안 좌표(Tk event.x/y).
    실제 창에서는 Tk event_generate 로 같은 경우를 확인했다(2026-09-28 3초 데모: 안→안 1번, 안→밖 0번, 연타 4번 → 1번).
    """

    class _FakeWin:
        """창 없는 대역. hide() 가 부르는 winfo_id/withdraw 만 있다."""
        def winfo_id(self):
            return 0

        def withdraw(self):
            pass

    def _button(self, size=22):
        import threading
        b = sb.SelectionButton.__new__(sb.SelectionButton)
        b._size = size
        b._mask = sb.circle_mask(size)
        b._visible = True
        b._pressed = False
        b._hover = False
        b._destroyed = False
        b._hwnd = None
        b._pos = (100, 100)
        b._owner_thread = threading.current_thread()
        b.win = self._FakeWin()
        b.calls = []
        b._on_click = lambda: b.calls.append(1)
        return b

    def _click(self, b, press, release):
        b._on_press(_Ev(*press))
        b._on_release(_Ev(*release))

    def test_press_and_release_inside(self):
        b = self._button()
        self._click(b, (11, 11), (12, 11))
        self.assertEqual(b.calls, [1])
        self.assertFalse(b._visible)                  # 누르면 숨는다(확장 read() 도 먼저 hide)

    def test_release_outside_does_nothing(self):
        b = self._button()
        self._click(b, (11, 11), (40, 11))            # 누른 채 밖으로 끌고 나가서 뗌(Tk 암묵적 잡기 → 창 밖 좌표)
        self.assertEqual(b.calls, [])
        self.assertTrue(b._visible)
        self._click(b, (11, 11), (-3, 11))            # 왼쪽 밖(음수)
        self.assertEqual(b.calls, [])

    def test_press_outside_circle_release_inside(self):
        b = self._button()
        self._click(b, (0, 0), (11, 11))              # 원 밖 모서리(실제로는 창 모양 밖이라 오지도 않는다)
        self.assertEqual(b.calls, [])

    def test_ring_counts_as_dot(self):
        # 눈에 보이는 12px 점 밖이지만 22px 클릭 영역 안(알파 1) — 확장 버튼도 22px 전체가 눌린다
        b = self._button()
        self._click(b, (1, 11), (1, 11))
        self.assertEqual(b.calls, [1])

    def test_rapid_clicks_call_once(self):
        b = self._button()
        for _ in range(4):
            self._click(b, (11, 11), (11, 11))
        self.assertEqual(b.calls, [1])                # 첫 클릭에 숨었으므로 나머지는 무시

    def test_hidden_between_press_and_release(self):
        # 누른 사이에 키 입력 등으로 숨김 → 뗌은 무시
        b = self._button()
        b._on_press(_Ev(11, 11))
        b.hide()
        b._visible = True                             # 그 사이 다른 자리에 다시 떴다고 해도(show_at 은 누름 상태를 지운다)
        b._on_release(_Ev(11, 11))
        self.assertEqual(b.calls, [])

    def test_release_without_press_and_hidden_press(self):
        b = self._button()
        b._on_release(_Ev(11, 11))
        self.assertEqual(b.calls, [])
        b._visible = False
        self._click(b, (11, 11), (11, 11))
        self.assertEqual(b.calls, [])

    def test_on_click_exception_still_hides(self):
        b = self._button()

        def boom():
            raise RuntimeError("읽기 실패")
        b._on_click = boom
        with self.assertLogs(sb.log, level="ERROR"):
            self._click(b, (11, 11), (11, 11))
        self.assertFalse(b._visible)

    def test_bad_event_coordinates(self):
        b = self._button()
        b._on_press(_Ev("??", None))
        self.assertFalse(b._pressed)


if __name__ == "__main__":
    unittest.main()
