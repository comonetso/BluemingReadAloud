# -*- coding: utf-8 -*-
"""translation 테스트 — 판별 규칙·문장 나누기·끼워 넣기·Gemini 요청 모양. 실제 Gemini 는 부르지 않는다."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import readaloud_text  # noqa: E402
import translation as tr  # noqa: E402
from tts_engine import SegmentFailed  # noqa: E402


def bracket(texts):
    """가짜 번역: 각 글을 <> 로 감싼다."""
    return ["<" + t + ">" for t in texts]


class TestRules(unittest.TestCase):
    def test_supports_korean_voice_only(self):
        self.assertTrue(tr.supports("ko-KR"))
        self.assertTrue(tr.supports("ko"))
        self.assertFalse(tr.supports("en-US"))
        self.assertFalse(tr.supports(""))
        self.assertFalse(tr.supports(None))

    def test_korean_sentence_with_dev_terms_is_kept(self):
        # 사용자 결정의 근거가 된 예 — 한글 41% 지만 한글이 있으니 번역하지 않는다
        self.assertFalse(tr.needs_translation("React 컴포넌트에서 useState hook을 쓰면 됩니다"))
        self.assertFalse(tr.needs_translation("git push 를 하세요."))

    def test_sentence_without_hangul_is_translated(self):
        self.assertTrue(tr.needs_translation("The quick brown fox jumps over the lazy dog."))
        self.assertTrue(tr.needs_translation("Error: Cannot find module 'express'."))
        self.assertTrue(tr.needs_translation("See HTTP URL. now"))

    def test_no_letters_or_url_only_is_not_translated(self):
        for s in ["", "   ", "1234.", "---", "3.14 + 2 = 5.14", readaloud_text.URL_REPLACEMENT, "(1)"]:
            with self.subTest(s=s):
                self.assertFalse(tr.needs_translation(s))

    def test_other_scripts_without_hangul_are_translated(self):
        self.assertTrue(tr.needs_translation("こんにちは。"))


class TestSentences(unittest.TestCase):
    def spans_text(self, text):
        return [text[s:e] for s, e in tr.sentence_spans(text)]

    def test_split_on_punctuation_space_and_newline(self):
        text = "첫 문장입니다. Second one! 셋째?\n넷째 줄"
        self.assertEqual(self.spans_text(text), ["첫 문장입니다.", "Second one!", "셋째?", "넷째 줄"])

    def test_no_split_inside_versions_or_without_space(self):
        self.assertEqual(self.spans_text("v1.2.3 버전은 node.js 를 씁니다."), ["v1.2.3 버전은 node.js 를 씁니다."])

    def test_blank_and_leading_spaces(self):
        self.assertEqual(self.spans_text("  \n\n  Hello.  \n"), ["Hello."])
        self.assertEqual(tr.sentence_spans(""), [])


class TestPlan(unittest.TestCase):
    def runs(self, text):
        return [text[s:e] for s, e in tr.plan(text)]

    def test_consecutive_foreign_sentences_are_one_run(self):
        text = "설정을 바꿉니다. Then restart the app. It will reload. 끝났습니다."
        self.assertEqual(self.runs(text), ["Then restart the app. It will reload."])

    def test_runs_split_by_korean_sentence(self):
        text = "Hello.\n안녕하세요.\nWorld."
        self.assertEqual(self.runs(text), ["Hello.", "World."])

    def test_korean_only_has_no_runs(self):
        self.assertEqual(tr.plan("한국어만 있습니다. 두 번째도요."), [])

    def test_number_line_breaks_run(self):
        text = "First.\n2024.\nSecond."
        self.assertEqual(self.runs(text), ["First.", "Second."])


class TestTranslateSegment(unittest.TestCase):
    def test_inserts_translations_in_place(self):
        text = "설정을 바꿉니다. Then restart. 끝."
        self.assertEqual(tr.translate_segment(text, bracket), "설정을 바꿉니다. <Then restart.> 끝.")

    def test_no_runs_returns_text_without_calling(self):
        calls = []
        out = tr.translate_segment("한국어뿐.", lambda xs: calls.append(xs) or xs)
        self.assertEqual(out, "한국어뿐.")
        self.assertEqual(calls, [])

    def test_one_call_per_segment_with_all_runs(self):
        calls = []

        def fake(xs):
            calls.append(list(xs))
            return bracket(xs)
        out = tr.translate_segment("A one.\n가나다.\nB two.", fake)
        self.assertEqual(calls, [["A one.", "B two."]])
        self.assertEqual(out, "<A one.>\n가나다.\n<B two.>")

    def test_wrong_count_raises(self):
        with self.assertRaises(tr.TranslationError):
            tr.translate_segment("A.\n가.\nB.", lambda xs: ["하나"])
        with self.assertRaises(tr.TranslationError):
            tr.translate_segment("A.", lambda xs: "문자열")


class TestMarkAndSynthesize(unittest.TestCase):
    def test_mark_replaces_text_with_raw_only_for_targets(self):
        # 줄이 길면(SHORT_LINE_BYTES 초과) 줄마다 조각이 따로 나온다
        en = "This line is written only in English and it is long enough to stand alone."
        text = "첫째 줄입니다 그리고 이어지는 글이 조금 더 있습니다 README 를 봅니다\n" + en
        segs = readaloud_text.split_for_reading(text, "ko-KR", "ko-KR", keep_raw=True)
        plain = readaloud_text.split_for_reading(text, "ko-KR", "ko-KR")
        raw_texts = tr.mark_for_translation(segs)
        self.assertEqual(len(segs), 2)
        for s in segs:
            self.assertEqual(set(s), {"text", "src_start", "src_end"})
        self.assertEqual(segs[0]["text"], plain[0]["text"])   # 한국어 조각은 변환 뒤 글 그대로
        self.assertEqual(segs[1]["text"], en)                 # 번역 대상은 변환 전 글
        self.assertEqual(raw_texts, {en})
        self.assertEqual([(s["src_start"], s["src_end"]) for s in segs],
                         [(p["src_start"], p["src_end"]) for p in plain])  # 형광펜 위치는 그대로

    def test_short_lines_merged_into_one_segment_translate_only_foreign_part(self):
        # 짧은 줄은 한 조각으로 합쳐진다 → 조각 전체가 번역 경로로 가지만, 번역은 한글 없는 문장에만 한다
        text = "한국어 줄입니다.\nThis line is English only."
        segs = readaloud_text.split_for_reading(text, "ko-KR", "ko-KR", keep_raw=True)
        raw_texts = tr.mark_for_translation(segs)
        self.assertEqual(len(segs), 1)
        raw = segs[0]["text"]
        self.assertEqual(raw_texts, {raw})
        out = tr.translate_segment(raw, bracket)
        self.assertIn("한국어 줄입니다.", out)
        self.assertIn("<This line is English only.>", out)

    def make(self, translate, synth_fail=False):
        synth_calls = []

        def synthesize(text, rate):
            synth_calls.append((text, rate))
            if synth_fail:
                raise RuntimeError("합성 오류")
            return "소리:" + text
        wrapped = tr.make_translating_synthesize(synthesize, translate, lambda t: "변환(" + t + ")",
                                                 {"Hello world."})
        return wrapped, synth_calls

    def test_non_target_goes_straight_to_synthesize(self):
        wrapped, calls = self.make(bracket)
        self.assertEqual(wrapped("한국어.", 1.0), "소리:한국어.")
        self.assertEqual(calls, [("한국어.", 1.0)])

    def test_target_is_translated_then_prepared_once(self):
        tcalls = []

        def translate(xs):
            tcalls.append(xs)
            return bracket(xs)
        wrapped, calls = self.make(translate)
        self.assertEqual(wrapped("Hello world.", 1.0), "소리:변환(<Hello world.>)")
        self.assertEqual(wrapped("Hello world.", 1.0), "소리:변환(<Hello world.>)")
        self.assertEqual(len(tcalls), 1)     # 같은 읽기 안에서는 번역을 다시 요청하지 않는다
        self.assertEqual(len(calls), 2)

    def test_translated_of_returns_translation_after_synthesis(self):
        wrapped, _ = self.make(bracket)
        self.assertIsNone(wrapped.translated_of("Hello world."))     # 아직 번역 전
        wrapped("Hello world.", 1.0)
        self.assertEqual(wrapped.translated_of("Hello world."), "<Hello world.>")   # 변환 전 번역문(막에 쓸 글)
        self.assertIsNone(wrapped.translated_of("한국어."))             # 번역 대상이 아닌 조각

    def test_on_translated_called_once_after_translation(self):
        seen = []
        wrapped = tr.make_translating_synthesize(lambda t, r: t, bracket, lambda t: t, {"Hello world."},
                                                 on_translated=lambda t: seen.append((t, wrapped.translated_of(t))))
        wrapped("한국어.", 1.0)
        self.assertEqual(seen, [])                                   # 번역 대상이 아니면 알림 없음
        wrapped("Hello world.", 1.0)
        wrapped("Hello world.", 1.0)                                 # 두 번째는 기억한 번역 — 알림 없음
        self.assertEqual(seen, [("Hello world.", "<Hello world.>")])   # 알림 때는 이미 찾아볼 수 있다

    def test_translation_failure_becomes_segment_failed(self):
        def broken(xs):
            raise tr.TranslationError("HTTP 403")
        wrapped, calls = self.make(broken)
        with self.assertRaises(SegmentFailed) as cm:
            wrapped("Hello world.", 1.0)
        self.assertIn("HTTP 403", str(cm.exception))
        self.assertEqual(calls, [])

    def test_missing_translator_fails_the_segment(self):
        wrapped, _ = self.make(tr.MissingTranslator("인증 파일 없음"))
        with self.assertRaises(SegmentFailed) as cm:
            wrapped("Hello world.", 1.0)
        self.assertIn("인증 파일 없음", str(cm.exception))

    def test_synthesis_failure_stays_ordinary(self):
        wrapped, _ = self.make(bracket, synth_fail=True)
        with self.assertRaises(RuntimeError) as cm:
            wrapped("Hello world.", 1.0)
        self.assertNotIsInstance(cm.exception, SegmentFailed)


class FakeResponse:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.posts = []
        self.gets = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append((url, json, headers, timeout))
        if self.error:
            raise self.error
        return self.response

    def get(self, url, headers=None, timeout=None):
        self.gets.append((url, headers, timeout))
        if self.error:
            raise self.error
        return self.response


def gemini_ok(items):
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(items, ensure_ascii=False)}]}}]})


class TestGeminiTranslator(unittest.TestCase):
    def test_request_shape_and_result(self):
        session = FakeSession(gemini_ok(["안녕"]))
        t = tr.GeminiTranslator("KEY-123", session=session)
        self.assertEqual(t(["Hello"]), ["안녕"])
        url, body, headers, timeout = session.posts[0]
        self.assertEqual(url, "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent")
        self.assertEqual(headers, {"x-goog-api-key": "KEY-123"})
        self.assertNotIn("KEY-123", url)                 # 키는 URL 에 넣지 않는다(로그로 새지 않게)
        self.assertEqual(timeout, 3.0)                   # 사용자 결정 제한 시간
        self.assertEqual(json.loads(body["contents"][0]["parts"][0]["text"]), ["Hello"])
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertIn("programming terms", body["systemInstruction"]["parts"][0]["text"])

    def test_empty_key_is_rejected(self):
        for key in ("", None):
            with self.assertRaises(tr.TranslationError):
                tr.GeminiTranslator(key, session=FakeSession())

    def test_http_error_carries_server_message(self):
        resp = FakeResponse(403, {"error": {"message": "Requests to this API are blocked."}})
        t = tr.GeminiTranslator("K", session=FakeSession(resp))
        with self.assertRaises(tr.TranslationError) as cm:
            t(["Hello"])
        self.assertIn("403", str(cm.exception))
        self.assertIn("blocked", str(cm.exception))

    def test_network_error_and_bad_body(self):
        t = tr.GeminiTranslator("K", session=FakeSession(error=OSError("연결 끊김")))
        with self.assertRaises(tr.TranslationError):
            t(["Hello"])
        bad = FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]})
        t = tr.GeminiTranslator("K", session=FakeSession(bad))
        with self.assertRaises(tr.TranslationError):
            t(["Hello"])


class TestCheckGeminiKey(unittest.TestCase):
    def test_ok(self):
        session = FakeSession(FakeResponse(200, {"name": "models/gemini-3.5-flash-lite"}))
        tr.check_gemini_key("KEY-9", session=session)
        url, headers, timeout = session.gets[0]
        self.assertEqual(url, "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite")
        self.assertEqual(headers, {"x-goog-api-key": "KEY-9"})
        self.assertEqual(timeout, 3.0)

    def test_wrong_key_or_network(self):
        with self.assertRaises(tr.TranslationError) as cm:
            tr.check_gemini_key("TTS-KEY", session=FakeSession(FakeResponse(403, {"error": {"message": "denied"}})))
        self.assertIn("403", str(cm.exception))
        with self.assertRaises(tr.TranslationError):
            tr.check_gemini_key("K", session=FakeSession(error=OSError("시간 초과")))
        with self.assertRaises(tr.TranslationError):
            tr.check_gemini_key("", session=FakeSession())


if __name__ == "__main__":
    unittest.main()
