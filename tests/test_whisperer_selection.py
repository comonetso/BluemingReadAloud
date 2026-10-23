# -*- coding: utf-8 -*-
"""whisperer.py 의 빨간 점 연결부 시험 — 마우스 훅이 넘기는 것, 웹페이지 판정, 텔레그램 판정 (2026-10-23).

whisperer.py 는 import 하지 않는다(트레이·전역 키보드 훅이 뜬다). 소스에서 필요한 함수·상수만 AST 로 뽑아
가짜 부품과 함께 돌린다(test_tts_engine.py 의 _load_glue 와 같은 방식).
"""
import ast
import os
import sys
import threading
import time
import types
import unittest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from selection_button import SelectionGestureDetector  # noqa: E402

_FUNCS = ["_make_selection_hook", "_is_disabled_browser_exe", "_is_telegram_exe", "_is_web_scheme", "_unless_web_page"]
_VARS = ["_BROWSER_EXES", "_TELEGRAM_EXES"]


def _load(extra=None):
    src_path = os.path.join(APP_DIR, "whisperer.py")
    with open(src_path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    variables = [n for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id in _VARS for t in n.targets)]
    missing = [f for f in _FUNCS if f not in funcs]
    assert not missing, f"whisperer.py 에서 함수를 못 찾음: {missing}"
    module = ast.Module(body=variables + [funcs[f] for f in _FUNCS], type_ignores=[])
    ns = {"__builtins__": __builtins__, "__name__": "whisperer_selection",
          "threading": threading, "time": time,
          "logging": types.SimpleNamespace(debug=lambda *a, **k: None),
          "_ensure_source_highlighter": lambda: None}
    if extra:
        ns.update(extra)
    exec(compile(module, src_path, "exec"), ns)
    return ns


LEFT = types.SimpleNamespace(name="left")
RIGHT = types.SimpleNamespace(name="right")


class HookTest(unittest.TestCase):
    """_make_selection_hook: 끌기·더블클릭 → "show", 한 번 클릭 → "click"(텔레그램 "선택" 용), 다음 입력 → "hide"."""

    def make(self, enabled=True, own=False, on_dot=False):
        ns = _load()
        self.posts = []
        self.t = [100.0]
        det = SelectionGestureDetector(drag_threshold=(4, 4), double_click_time=0.5, double_click_size=(4, 4))
        self.own = own
        self.on_click, self.on_scroll, self.on_key = ns["_make_selection_hook"](
            det, contains=lambda x, y: on_dot, is_own_window=lambda x, y: self.own,
            post=self.posts.append, is_enabled=lambda: enabled, clock=lambda: self.t[0])

    def click(self, x, y, button=LEFT, up=None):
        self.on_click(x, y, button, True)
        ux, uy = up if up else (x, y)
        self.on_click(ux, uy, button, False)

    def test_single_click_posts_click(self):
        self.make()
        self.click(10, 20)
        self.assertEqual(self.posts, [("selection_button", "click", 10, 20)])

    def test_next_press_after_click_hides(self):
        # 한 번 클릭 뒤엔 점이 떴을 수 있다(텔레그램) → 다음 누름에서 "숨김"
        self.make()
        self.click(10, 20)
        self.t[0] += 2.0
        self.on_click(300, 300, LEFT, True)
        self.assertEqual(self.posts[-1], ("selection_button", "hide"))

    def test_key_after_click_hides_once(self):
        self.make()
        self.click(10, 20)
        self.on_key()
        self.on_key()
        self.assertEqual(self.posts.count(("selection_button", "hide")), 1)

    def test_drag_posts_show_only(self):
        self.make()
        self.click(10, 20, up=(80, 20))
        self.assertEqual(self.posts, [("selection_button", "show", 80, 20)])

    def test_double_click_posts_click_then_show(self):
        self.make()
        self.click(10, 20)
        self.t[0] += 0.1
        self.click(10, 20)
        self.assertEqual(self.posts, [("selection_button", "click", 10, 20), ("selection_button", "hide"),
                                      ("selection_button", "show", 10, 20)])

    def test_own_window_click_posts_nothing(self):
        self.make(own=True)
        self.click(10, 20)
        self.click(10, 20, up=(90, 20))
        self.assertEqual(self.posts, [])

    def test_click_on_dot_posts_nothing(self):
        self.make(on_dot=True)
        self.click(10, 20)
        self.assertEqual(self.posts, [])

    def test_disabled_posts_nothing(self):
        self.make(enabled=False)
        self.click(10, 20)
        self.assertEqual(self.posts, [])

    def test_right_click_is_not_click(self):
        # 우클릭(메뉴 열기)은 "click" 이 아니다 — 메뉴의 "선택" 을 누르는 왼쪽 클릭이 "click" 이다
        self.make()
        self.click(10, 20, button=RIGHT)
        self.assertNotIn("click", [p[1] for p in self.posts])


class PureTest(unittest.TestCase):
    def setUp(self):
        self.ns = _load()

    def test_web_scheme(self):
        f = self.ns["_is_web_scheme"]
        for s in ("http", "https", "HTTPS"):
            self.assertTrue(f(s), s)
        for s in ("chrome-extension", "chrome", "aside", "about", "file", "whale", "", None):
            self.assertFalse(f(s), s)

    def test_telegram_exe(self):
        f = self.ns["_is_telegram_exe"]
        self.assertTrue(f("Telegram.exe"))
        self.assertTrue(f("telegram.exe"))
        for s in ("chrome.exe", "Aside.exe", "", None):
            self.assertFalse(f(s), s)

    def test_browser_exe_unchanged(self):
        f = self.ns["_is_disabled_browser_exe"]
        for s in ("Aside.exe", "whale.exe", "CHROME.EXE"):
            self.assertTrue(f(s), s)
        for s in ("msedgewebview2.exe", "Telegram.exe", None):
            self.assertFalse(f(s), s)


class FakeHL:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.asked = answer, error, 0

    def query_page_scheme(self, on_done):
        self.asked += 1
        if self.error:
            raise self.error
        on_done(self.answer)


class UnlessWebPageTest(unittest.TestCase):
    """_unless_web_page: 웹페이지(http·https)만 on_web, 그 밖·모름은 proceed(2026-10-23 사용자 결정)."""

    def run_case(self, browser, hl):
        ns = _load({"_ensure_source_highlighter": lambda: hl})
        got = []
        ns["_unless_web_page"](browser, lambda s: got.append(("proceed", s)), lambda s: got.append(("web", s)))
        return got

    def test_not_a_browser_proceeds_without_asking(self):
        hl = FakeHL("https")
        self.assertEqual(self.run_case(None, hl), [("proceed", None)])
        self.assertEqual(hl.asked, 0)

    def test_web_page_rests(self):
        self.assertEqual(self.run_case("Aside.exe", FakeHL("https")), [("web", "https")])
        self.assertEqual(self.run_case("Aside.exe", FakeHL("http")), [("web", "http")])

    def test_internal_pages_proceed(self):
        for scheme in ("chrome-extension", "chrome", "aside", "file", "about"):
            self.assertEqual(self.run_case("Aside.exe", FakeHL(scheme)), [("proceed", scheme)], scheme)

    def test_unknown_proceeds(self):
        self.assertEqual(self.run_case("Aside.exe", FakeHL(None)), [("proceed", None)])

    def test_no_highlighter_proceeds(self):
        self.assertEqual(self.run_case("Aside.exe", None), [("proceed", None)])

    def test_query_error_proceeds(self):
        self.assertEqual(self.run_case("Aside.exe", FakeHL(error=RuntimeError("x"))), [("proceed", None)])


if __name__ == "__main__":
    unittest.main()
