# -*- coding: utf-8 -*-
"""usage_pill 테스트 — 창은 띄우지 않고 자리 계산(pill_position)만 본다."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from usage_pill import pill_position, popup_position  # noqa: E402

WORK = (0, 0, 1920, 1040)   # 작업표시줄을 뺀 작업 영역


class TestPopupPosition(unittest.TestCase):
    PILL = (1600, 1000, 300, 30)   # 오른쪽 아래 알약 (x, y, w, h)

    def test_above_pill_right_aligned(self):
        # 창 오른쪽 끝 = 알약 오른쪽 끝(1900), 창 아래 = 알약 위 - 8
        self.assertEqual(popup_position(self.PILL, (800, 600), WORK, 8), (1100, 1000 - 8 - 600))

    def test_below_when_no_room_above(self):
        self.assertEqual(popup_position((1600, 20, 300, 30), (800, 600), WORK, 8), (1100, 58))

    def test_kept_inside(self):
        self.assertEqual(popup_position((10, 1000, 300, 30), (800, 600), WORK, 8), (0, 392))     # 왼쪽으로 넘침
        right = (1920, 0, 3840, 1040)
        self.assertEqual(popup_position((3500, 1000, 300, 30), (800, 600), right, 8), (3000, 392))  # 다른 모니터
        self.assertEqual(popup_position(self.PILL, (800, 600), None, 8), (1100, 392))            # 영역 모름


class TestPillPosition(unittest.TestCase):
    def test_default_is_bottom_right_with_margin(self):
        self.assertEqual(pill_position(None, (300, 30), WORK, 12), (1920 - 300 - 12, 1040 - 30 - 12))

    def test_saved_kept_inside(self):
        self.assertEqual(pill_position((100, 200), (300, 30), WORK, 12), (100, 200))
        self.assertEqual(pill_position((1800, 1030), (300, 30), WORK, 12), (1620, 1010))   # 오른쪽·아래로 넘침
        self.assertEqual(pill_position((-50, -9), (300, 30), WORK, 12), (0, 0))           # 왼쪽·위로 넘침

    def test_other_monitor_and_unknown_area(self):
        right = (1920, 0, 3840, 1080)   # 오른쪽 모니터
        self.assertEqual(pill_position((2000, 500), (300, 30), right, 12), (2000, 500))
        self.assertEqual(pill_position([5, 6], (300, 30), None, 12), (5, 6))
        self.assertEqual(pill_position(None, (300, 30), None, 12), (0, 0))


if __name__ == "__main__":
    unittest.main()
