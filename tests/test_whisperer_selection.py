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

_FUNCS = ["_make_selection_hook", "_is_disabled_browser_exe", "_is_telegram_exe", "_is_web_scheme", "_unless_web_page",
           "_show_dot_if_telegram_selected", "_handle_selection_button_msg", "_wait_clipboard_text"]
_VARS = ["_BROWSER_EXES", "_TELEGRAM_EXES", "TELEGRAM_MENU_RETRY_MS", "TELEGRAM_MENU_RETRY_MAX_S",
         "COPY_WAIT_S", "COPY_POLL_S"]


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

    def test_right_press_posts_spot(self):
        # 2026-10-24: 우클릭 누름은 자리를 넘긴다(텔레그램 "선택" 뒤 그 자리 메시지를 보려고). 가운데 버튼은 안 넘긴다
        self.make()
        self.click(10, 20, button=RIGHT)
        self.click(50, 60, button=types.SimpleNamespace(name="middle"))
        self.assertEqual([p for p in self.posts if p[1] == "rpress"], [("selection_button", "rpress", 10, 20)])


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


class FakeTG:
    """query_telegram_selected 에 차례로 답한다(답이 떨어지면 마지막 답을 되풀이)."""

    def __init__(self, answers):
        self.answers, self.asked, self.right_clicks = list(answers), 0, []

    def query_telegram_selected(self, x, y, on_done, right_click=None):
        self.asked += 1
        self.right_clicks.append(right_click)
        on_done(self.answers[min(self.asked, len(self.answers)) - 1])


class FakeRoot:
    def __init__(self):
        self.pending = []

    def after(self, ms, fn):
        self.pending.append((ms, fn))


class TelegramDotTest(unittest.TestCase):
    """_show_dot_if_telegram_selected: "menu" 가 한 번 나오면 그 뒤 False 도 한도까지 다시 묻는다(2026-10-24)."""

    def run_case(self, answers, right_click=None):
        hl = self.hl = FakeTG(answers)
        clock_ms = [100000]
        root = FakeRoot()
        shown = []
        ns = _load({
            "_ensure_source_highlighter": lambda: hl,
            "time": types.SimpleNamespace(monotonic=lambda: clock_ms[0] / 1000.0),
            "logging": types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None),
            "_dot_query_gen": 0,
            "_safe_ui": lambda label, fn, *a: fn(*a),
            "root": root,
            "selection_button": types.SimpleNamespace(show_at=lambda x, y: shown.append((x, y))),
            "selection_button_enabled": True,
        })
        ns["_show_dot_if_telegram_selected"](10, 20, right_click)
        while root.pending:
            ms, fn = root.pending.pop(0)
            clock_ms[0] += ms
            fn()
        return hl.asked, shown

    def test_menu_then_false_then_selected_shows_dot(self):
        # 10-23 설치본 로그 모양: 메뉴를 누른 뒤 포커스는 메시지로 돌아왔지만 선택 표시가 아직 → 한 번 더 물어 선택됨
        self.assertEqual(self.run_case(["menu", False, True]), (3, [(10, 20)]))

    def test_plain_false_does_not_retry(self):
        # 메뉴와 무관한 클릭(그냥 메시지 누름)은 다시 묻지 않는다
        self.assertEqual(self.run_case([False]), (1, []))

    def test_menu_then_false_stops_at_limit(self):
        asked, shown = self.run_case(["menu", False])
        self.assertEqual(shown, [])
        self.assertLessEqual(asked, 12, "TELEGRAM_MENU_RETRY_MAX_S(1초) 를 넘겨 묻지 않는다")
        self.assertGreaterEqual(asked, 9)

    def test_menu_then_unknown_stops(self):
        # None = 느림·실패 → 그만(다른 앱을 얼리지 않는 규칙)
        self.assertEqual(self.run_case(["menu", None]), (2, []))

    def test_selected_at_once(self):
        self.assertEqual(self.run_case([True]), (1, [(10, 20)]))

    def test_right_click_spot_passed_on_every_try(self):
        # 2026-10-24: 우클릭 자리는 다시 물을 때마다 같이 넘긴다. 점 자리는 그대로 뗀 자리
        self.assertEqual(self.run_case(["menu", False, True], right_click=(3, 4)), (3, [(10, 20)]))
        self.assertEqual(self.hl.right_clicks, [(3, 4)] * 3)


class FakeEnd:
    """query_selection_end 에 answer 로 답한다. later=True 면 on_done 을 쥐고 있다가 시험이 부른다."""

    def __init__(self, answer=None, later=False, scheme=None):
        self.answer, self.later, self.scheme, self.asked, self.pending = answer, later, scheme, 0, []

    def query_selection_end(self, on_done):
        self.asked += 1
        if self.later:
            self.pending.append(on_done)
        else:
            on_done(self.answer)

    def query_page_scheme(self, on_done):
        on_done(self.scheme)


class KeyboardDotTest(unittest.TestCase):
    """("keyboard",) — 선택 끝 글자 옆, 모르면 마우스 옆에 바로 띄운다(2026-10-28: 예전엔 "show" 로 되넘겨 다시 묻고 안 띄움)."""

    CURSOR = (500, 600)

    def run_case(self, hl, exe="Notepad.exe", browser=None, between=None):
        self.hl = hl
        self.shown, self.telegram = [], []
        ns = _load({
            "_ensure_source_highlighter": lambda: hl,
            "source_highlight_enabled": True,
            "selection_button_enabled": True,
            "selection_button": types.SimpleNamespace(show_at=lambda x, y: self.shown.append((x, y))),
            "disable_in_browsers": True,
            "_no_dot_foreground": lambda: False,
            "_no_dot_window_at": lambda x, y: False,
            "_nonclient_at": lambda x, y: False,
            "_foreground_disabled_browser": lambda: browser,
            "_foreground_exe_name": lambda: exe,
            "_cursor_pos": lambda: self.CURSOR,
            "_safe_ui": lambda label, fn, *a: fn(*a),
            "_hide_selection_button": lambda: None,
            "_dot_query_gen": 0,
            "_tg_right_click": None,
        })
        ns["_show_dot_if_telegram_selected"] = lambda x, y, rc=None: self.telegram.append((x, y))
        handle = ns["_handle_selection_button_msg"]
        handle("keyboard")
        if between:
            handle(*between)                     # 결과를 기다리는 사이 들어온 다른 명령
        for on_done in hl.pending:
            on_done(hl.answer)
        return self.shown

    def test_end_known_shows_next_to_it(self):
        self.assertEqual(self.run_case(FakeEnd((300, 40))), [(300, 40)])
        self.assertEqual(self.hl.asked, 1)

    def test_end_unknown_shows_next_to_cursor_without_asking_again(self):
        # 메모장 Ctrl+A: 끝 글자가 파일 끝 줄바꿈이라 위치를 모른다 → 마우스 옆(2026-09-28 규칙)
        self.assertEqual(self.run_case(FakeEnd(None)), [self.CURSOR])
        self.assertEqual(self.hl.asked, 1)

    def test_nothing_selected_shows_nothing(self):
        self.assertEqual(self.run_case(FakeEnd("none")), [])

    def test_key_while_waiting_drops_late_answer(self):
        self.assertEqual(self.run_case(FakeEnd((300, 40), later=True), between=("hide",)), [])

    def test_telegram_goes_to_selected_message_check(self):
        self.assertEqual(self.run_case(FakeEnd((300, 40)), exe="Telegram.exe"), [])
        self.assertEqual(self.telegram, [(300, 40)])

    def test_web_page_shows_nothing(self):
        self.assertEqual(self.run_case(FakeEnd((300, 40), scheme="https"), browser="Aside.exe"), [])
        self.assertEqual(self.hl.asked, 0)


class WaitClipboardTest(unittest.TestCase):
    """_wait_clipboard_text: 글이 들어오면 바로, 비면 COPY_WAIT_S 까지(2026-10-28 — 예전엔 0.5초 고정)."""

    def run_case(self, answers):
        ns = _load()
        t = [0.0]
        self.reads = 0

        def paste():
            self.reads += 1
            a = answers[min(self.reads, len(answers)) - 1]
            if isinstance(a, Exception):
                raise a
            return a

        def sleep(s):
            t[0] += s

        got = ns["_wait_clipboard_text"](paste, clock=lambda: t[0], sleep=sleep)
        return got, t[0]

    def test_returns_as_soon_as_text_arrives(self):
        got, took = self.run_case(["", "", "고른 글"])
        self.assertEqual(got, "고른 글")
        self.assertAlmostEqual(took, 0.06)

    def test_empty_waits_full_limit(self):
        got, took = self.run_case([""])
        self.assertEqual(got, "")
        self.assertGreaterEqual(took, 0.5)
        self.assertLess(took, 0.55)

    def test_blank_only_waits_full_limit(self):
        got, took = self.run_case(["  \n"])
        self.assertEqual(got, "  \n")
        self.assertGreaterEqual(took, 0.5)

    def test_read_error_retries(self):
        got, _ = self.run_case([RuntimeError("열려 있음"), "고른 글"])
        self.assertEqual(got, "고른 글")

    def test_last_read_error_is_raised(self):
        with self.assertRaises(RuntimeError):
            self.run_case([RuntimeError("열려 있음")])


if __name__ == "__main__":
    unittest.main()
