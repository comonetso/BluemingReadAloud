# -*- coding: utf-8 -*-
"""noeul_live.py — 크롬 확장 대신 노을로 읽어 주는 길(2026-11-18) 시험.

실제 OpenAI 는 부르지 않는다(이 PC 는 IP 허용 목록 밖 — 실제 소리는 사무실에서 확인). 대신
- 가짜 연결(FakeConn)·가짜 시계로 Paseo tts.ts liveRead 11-18 판의 순서·끝 판정·실패 구분
- 이 PC 안에 띄운 작은 웹소켓 서버로 LiveSocket 의 여는 인사·프레임·거절 응답
- 실제 포트의 UsageReceiver 로 POST /v1/tts/noeul 의 응답 모양·Origin·동시 처리
"""

import base64
import hashlib
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import noeul_live  # noqa: E402
import tts_usage  # noqa: E402

TEXT = "안녕하세요. 반갑습니다."
LOUD = (1000).to_bytes(2, "little", signed=True) * 2400      # 0.1초, 표본 1000 (> 600)
QUIET = bytes(4800)                                         # 0.1초 무음


def audio(pcm):
    return {"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode("ascii")}


def said(text):
    return {"type": "session.output_transcript.delta", "delta": text}


STARTED = {"type": "session.started"}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeConn:
    """script = [(시각, 이벤트 dict | "close" | "error_close")] — recv(timeout) 가 시계를 그 시각으로 옮기며 하나씩 준다."""

    def __init__(self, clock, script):
        self.clock = clock
        self.script = list(script)
        self.sent = []
        self.closed = False
        self.headers = None

    def opener(self, url, headers, timeout):
        self.url = url
        self.headers = headers
        return self

    def send_text(self, text):
        self.sent.append(json.loads(text))

    def recv(self, timeout):
        limit = self.clock.now + timeout
        if self.script and self.script[0][0] <= limit + 1e-9:
            at, item = self.script.pop(0)
            self.clock.now = max(self.clock.now, at)
            if item == "close":
                raise noeul_live.LiveClosed()
            if item == "error_close":
                raise noeul_live.LiveClosed(error=True)
            return json.dumps(item, ensure_ascii=False)
        # 기다릴 시간이 소수 오차만큼 작아도 시계는 앞으로 가야 한다(안 그러면 같은 자리를 끝없이 돈다 — 실제 시계는 늘 흐른다)
        self.clock.now = limit if limit > self.clock.now else self.clock.now + 1e-6
        return None

    def close(self):
        self.closed = True

    def types(self):
        return [e["type"] for e in self.sent]


class Attempts:
    """시도마다 새 가짜 연결 — scripts[n] 이 n+1 번째 시도(모자라면 아무것도 안 오는 연결). 예외 객체를 두면 그 시도의 연결이 실패."""

    def __init__(self, clock, scripts):
        self.clock = clock
        self.scripts = list(scripts)
        self.conns = []

    def opener(self, url, headers, timeout):
        n = len(self.conns)
        script = self.scripts[n] if n < len(self.scripts) else []
        if isinstance(script, Exception):
            self.conns.append(script)
            raise script
        conn = FakeConn(self.clock, script)
        self.conns.append(conn)
        return conn.opener(url, headers, timeout)


def run(*scripts, text=TEXT, key="sk-test", lang="ko", cancelled=None):
    """scripts = 시도별 이벤트 목록. 돌려주는 conn = 첫 시도의 연결, attempts.conns = 시도마다."""
    clock = FakeClock()
    attempts = Attempts(clock, scripts)
    logs = []
    kwargs = {"cancelled": (lambda: cancelled(clock.now))} if cancelled else {}
    try:
        pcm = noeul_live.read_noeul(text, key, lang, log=logs.append, opener=attempts.opener, clock=clock,
                                    close_delay=0, **kwargs)
        err = None
    except noeul_live.NoeulError as e:
        pcm, err = None, e
    run.attempts, run.clock = attempts, clock
    return pcm, attempts.conns[0] if attempts.conns else None, logs, err


# 첫 소리 앞 무음 셋(2.0~2.2) → 소리 둘(2.3·2.4) → 그 뒤 무음 0.1초마다
BASE = [(0.5, STARTED), (2.0, audio(QUIET)), (2.1, audio(QUIET)), (2.2, audio(QUIET)),
        (2.3, audio(LOUD)), (2.4, audio(LOUD))]


def quiet_after(start, until):
    out, t = [], start
    while t < until:
        out.append((round(t, 2), audio(QUIET)))
        t += 0.1
    return out


class TestReadNoeul(unittest.TestCase):
    def test_order_and_messages_follow_paseo(self):
        pcm, conn, logs, err = run(BASE + [(2.45, said("안녕하세요 반갑습니다"))] + quiet_after(2.55, 5))
        self.assertIsNone(err)
        types = conn.types()
        self.assertEqual(types[0], "session.start")
        self.assertEqual(types[-1], "session.close")
        self.assertIn("session.instructions.append", types)
        self.assertLess(types.index("session.instructions.append"), types.index("session.input_audio.append"))
        start = conn.sent[0]["session"]
        self.assertEqual(start["model"], "gpt-live-1")
        self.assertEqual(start["audio"], {"format": {"type": "audio/pcm", "rate": 24000}, "output": {"voice": "noeul"}})
        self.assertTrue(start["instructions"].startswith("너는 한국어 원문 낭독만 한다."))
        self.assertNotIn("input", start)        # 11-18 판: 읽을 글은 시작에 넣지 않는다
        read = next(e for e in conn.sent if e["type"] == "session.instructions.append")
        self.assertIsNone(read["delegation_id"])
        self.assertEqual(read["content"], "응답하지 말고 지금 바로 다음 한국어 글을 정확히 그대로 처음부터 끝까지 한 번 "
                                          "소리 내어 읽은 뒤 침묵하라: " + TEXT)
        pump = next(e for e in conn.sent if e["type"] == "session.input_audio.append")
        self.assertEqual(base64.b64decode(pump["audio"]), bytes(4800))
        self.assertEqual(conn.headers, {"Authorization": "Bearer sk-test"})
        self.assertEqual(conn.url, "wss://api.openai.com/v1/live/sessions")
        self.assertTrue(conn.closed)

    def test_done_transcript_ends_after_short_quiet(self):
        # 받아쓴 글이 원문과 같아지면 0.3초 조용 → 끝. 결과 = 첫 소리 앞 두 조각 ~ 끝 소리 뒤 두 조각(Paseo slice(first-2, last+3))
        pcm, conn, logs, err = run(BASE + [(2.45, said("안녕하세요 반갑습니다"))] + quiet_after(2.55, 5))
        self.assertIsNone(err)
        self.assertEqual(pcm, QUIET * 2 + LOUD * 2 + QUIET * 2)    # 2.55·2.65 무음까지 받고 2.7 에 끝
        self.assertEqual(logs, [])

    def test_different_transcript_waits_long_quiet_and_logs_lengths(self):
        # 첫머리는 맞고(첫머리 판정 통과) 뒤가 달라 "다 읽음"이 안 됨 → 1.5초 조용할 때까지
        pcm, conn, logs, err = run(BASE + [(2.45, said("안녕하세요 다른 말"))] + quiet_after(2.5, 6))
        self.assertIsNone(err)
        self.assertEqual(pcm, QUIET * 2 + LOUD * 2 + QUIET * 2)
        self.assertEqual(logs, [f"[노을] 원문과 다르게 읽음 — 원문 {len(TEXT)}자 · 읽은 글 10자"])
        # 1.5초 조용할 때까지 기다렸다 — 무음을 그동안 보냈다
        self.assertGreaterEqual(conn.types().count("session.input_audio.append"), 30)

    def test_extra_speech_after_done_is_cut(self):
        script = BASE + [(2.45, said("안녕하세요 반갑습니다")), (2.5, audio(QUIET)), (2.55, said("아버지가")),
                         (2.6, audio(LOUD)), (2.7, audio(LOUD))]
        pcm, conn, logs, err = run(script)
        self.assertIsNone(err)
        self.assertEqual(pcm, QUIET * 2 + LOUD * 2 + QUIET)
        self.assertEqual(logs, [f"[노을] 글을 다 읽은 뒤 덧붙인 말을 잘라냄 — 원문 {len(TEXT)}자"])

    def test_no_sound_in_30s_fails_after_three_tries(self):
        # 7초씩 두 번 다시 시도, 마지막은 남은 16초를 다 기다린다 — 합쳐 30초에 실패
        pcm, conn, logs, err = run([(0.5, STARTED)] + quiet_after(1.0, 40))
        self.assertEqual((err.code, err.status), ("no_audio", 502))
        self.assertIn("30초", err.message)
        self.assertEqual(len(run.attempts.conns), 3)
        self.assertAlmostEqual(run.clock.now, 30.0, delta=0.11)
        self.assertEqual(logs, [f"[노을] 다시 시도 2/3 — OpenAI 노을이 7초 안에 읽기를 시작하지 않음 · 원문 {len(TEXT)}자",
                                f"[노을] 다시 시도 3/3 — OpenAI 노을이 7초 안에 읽기를 시작하지 않음 · 원문 {len(TEXT)}자"])
        for c in run.attempts.conns:
            self.assertTrue(c.closed)
            self.assertEqual(c.types()[-1], "session.close")

    def test_context_injection_incomplete_is_ignored_other_error_retries(self):
        ok_script = BASE + [(2.42, {"type": "error", "error": {"code": "context_injection_incomplete"}}),
                            (2.45, said("안녕하세요 반갑습니다"))] + quiet_after(2.55, 5)
        pcm, conn, logs, err = run(ok_script)
        self.assertIsNone(err)
        rate = {"type": "error", "error": {"code": "rate_limit_exceeded"}}
        good = [(3.0, STARTED), (4.0, audio(LOUD)), (4.05, said("안녕하세요 반갑습니다"))] + quiet_after(4.1, 6)
        pcm, conn, logs, err = run(BASE + [(2.42, rate)], good)       # 서버 오류 → 새 연결로 성공
        self.assertIsNone(err)
        self.assertEqual(logs, [f"[노을] 다시 시도 2/3 — OpenAI 노을 오류 (rate_limit_exceeded) · 원문 {len(TEXT)}자"])
        self.assertEqual(pcm, LOUD + QUIET * 2)
        pcm, conn, logs, err = run([(0.5, rate)], [(1.0, rate)], [(1.5, rate)])     # 세 번 다 → 실패
        self.assertEqual((err.code, err.status), ("server", 502))
        self.assertIn("rate_limit_exceeded", err.message)

    def test_total_timeout_fails_even_with_sound(self):
        # 끝없이 소리만 오면 전체 상한(90초)에 실패 — 받은 소리가 있어도 실패다(Paseo 11-18)
        script = [(0.5, STARTED)] + [(round(1 + i * 0.1, 2), audio(LOUD)) for i in range(1000)]
        pcm, conn, logs, err = run(script)
        self.assertEqual((err.code, err.status), ("timeout", 504))

    def test_closed_connection(self):
        pcm, conn, logs, err = run(BASE + [(2.5, "close")])          # 소리를 받은 뒤 정상 닫힘 = 받은 만큼으로 끝
        self.assertIsNone(err)
        self.assertEqual(pcm, QUIET * 2 + LOUD * 2)
        self.assertEqual(len(run.attempts.conns), 1)
        pcm, conn, logs, err = run([(0.5, STARTED), (1.0, "close")])  # 소리 없이 닫힘 → 다시, 끝내 없으면 실패
        self.assertEqual(err.code, "no_audio")
        self.assertEqual(len(run.attempts.conns), 3)
        good = [(3.0, STARTED), (4.0, audio(LOUD)), (4.05, said("안녕하세요 반갑습니다"))] + quiet_after(4.1, 6)
        pcm, conn, logs, err = run(BASE + [(2.5, "error_close")], good)   # 연결 오류 → 소리를 받았어도 새 연결로
        self.assertIsNone(err)
        self.assertEqual(pcm, LOUD + QUIET * 2)
        pcm, conn, logs, err = run([(0.5, "error_close")], [(1.0, "error_close")], [(1.5, "error_close")])
        self.assertEqual((err.code, err.status), ("connect", 502))

    def test_no_key(self):
        with self.assertRaises(noeul_live.NoeulError) as ctx:
            noeul_live.read_noeul(TEXT, "", opener=lambda *a: self.fail("열면 안 된다"))
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("no_key", 503))

    def test_other_language_uses_english_instructions(self):
        pcm, conn, logs, err = run(BASE + [(2.45, said("Hello there."))] + quiet_after(2.55, 5),
                                   text="Hello there.", lang="en")
        self.assertIsNone(err)
        self.assertTrue(conn.sent[0]["session"]["instructions"].startswith("You only read English source text"))
        read = next(e for e in conn.sent if e["type"] == "session.instructions.append")
        self.assertTrue(read["content"].endswith("then fall silent: Hello there."))

    # ── 다시 시도·첫머리 판정·끊김 (Paseo 11-18 · 크롬 확장 요청 090a8be2) ──

    GOOD2 = [(7.5, STARTED), (9.0, audio(LOUD)), (9.05, said("안녕하세요 반갑습니다"))] + quiet_after(9.1, 11)

    def test_no_reply_in_7s_retries_with_new_connection(self):
        pcm, conn, logs, err = run([(0.5, STARTED)], self.GOOD2)
        self.assertIsNone(err)
        self.assertEqual(pcm, LOUD + QUIET * 2)
        self.assertEqual(len(run.attempts.conns), 2)
        self.assertTrue(conn.closed)
        self.assertEqual(conn.types()[-1], "session.close")
        self.assertEqual(logs, [f"[노을] 다시 시도 2/3 — OpenAI 노을이 7초 안에 읽기를 시작하지 않음 · 원문 {len(TEXT)}자"])

    def test_wrong_head_retries(self):
        wrong = BASE + [(2.45, said("응답하지 말고"))] + quiet_after(2.5, 5)
        pcm, conn, logs, err = run(wrong, self.GOOD2)
        self.assertIsNone(err)
        self.assertEqual(pcm, LOUD + QUIET * 2)              # 엉뚱한 첫 시도의 소리는 버렸다
        self.assertEqual(logs, [f"[노을] 원문이 아닌 말로 시작함 — 원문 {len(TEXT)}자",
                                f"[노을] 다시 시도 2/3 — OpenAI 노을이 원문이 아닌 말로 시작함 · 원문 {len(TEXT)}자"])

    def test_head_not_checked_when_text_starts_with_digits(self):
        text = "2026년 십일월"
        script = BASE + [(2.45, said("이천이십육년 십일월"))] + quiet_after(2.5, 5)
        pcm, conn, logs, err = run(script, text=text)
        self.assertIsNone(err)
        self.assertEqual(len(run.attempts.conns), 1)

    def test_last_try_does_not_check_head(self):
        wrong1 = [(0.5, STARTED), (1.0, audio(LOUD)), (1.05, said("응답하지 말고"))]
        wrong2 = [(1.5, STARTED), (2.0, audio(LOUD)), (2.05, said("응답하지 말고"))]
        wrong3 = [(2.5, STARTED), (3.0, audio(LOUD)), (3.05, said("응답하지 말고"))] + quiet_after(3.1, 6)
        pcm, conn, logs, err = run(wrong1, wrong2, wrong3)
        self.assertIsNone(err)                       # 마지막 시도는 견주지 않고 소리를 준다(표기 차이로 잘못 어긋나도 소리는 나게)
        self.assertEqual(len(run.attempts.conns), 3)
        self.assertEqual(logs[-1], f"[노을] 원문과 다르게 읽음 — 원문 {len(TEXT)}자 · 읽은 글 7자")

    def test_head_check_gives_up_1_5s_after_first_sound(self):
        late = BASE + [(2.45, said("응")), (3.85, said("답하지 말고"))] + quiet_after(4.0, 7)
        pcm, conn, logs, err = run(late)
        self.assertIsNone(err)                       # 첫 소리(2.3) 뒤 1.5초까지 한 글자뿐 → 견주지 않고 넘김
        self.assertEqual(len(run.attempts.conns), 1)

    def test_key_or_ip_refusal_is_not_retried(self):
        for code in ("ip_not_authorized", "unauthorized"):
            pcm, conn, logs, err = run(noeul_live.NoeulError(code), self.GOOD2)
            self.assertEqual(err.code, code)
            self.assertEqual(len(run.attempts.conns), 1)

    def test_connect_failure_is_retried(self):
        soon = [(0.5, STARTED), (1.0, audio(LOUD)), (1.05, said("안녕하세요 반갑습니다"))] + quiet_after(1.1, 3)
        pcm, conn, logs, err = run(noeul_live.NoeulError("connect"), soon)
        self.assertIsNone(err)
        self.assertEqual(len(run.attempts.conns), 2)

    def test_cancel_closes_live_connection_within_0_1s(self):
        pcm, conn, logs, err = run(BASE + quiet_after(2.5, 20), cancelled=lambda now: now >= 3.0)
        self.assertEqual((err.code, err.status), ("cancelled", 499))
        self.assertTrue(conn.closed)
        self.assertEqual(conn.types()[-1], "session.close")
        self.assertLessEqual(run.clock.now, 3.1 + 1e-6)
        self.assertEqual(len(run.attempts.conns), 1)

    def test_cancel_before_any_sound_is_not_retried(self):
        pcm, conn, logs, err = run([(0.5, STARTED)], self.GOOD2, cancelled=lambda now: now >= 5.0)
        self.assertEqual(err.code, "cancelled")
        self.assertEqual(len(run.attempts.conns), 1)
        self.assertLessEqual(run.clock.now, 5.1 + 1e-6)

    def test_cancel_while_waiting_for_a_slot(self):
        taken = 0
        while noeul_live._slots.acquire(blocking=False):     # 12자리를 다 채운다
            taken += 1
        try:
            self.assertEqual(taken, noeul_live.LIVE_SESSIONS_MAX)
            with self.assertRaises(noeul_live.NoeulError) as ctx:
                noeul_live.read_noeul(TEXT, "k", opener=lambda *a: self.fail("열면 안 된다"), cancelled=lambda: True)
            self.assertEqual(ctx.exception.code, "cancelled")
        finally:
            for _ in range(taken):
                noeul_live._slots.release()

    def test_timeout_formula(self):
        self.assertEqual(noeul_live.live_timeout_s("가" * 10), 90.0)
        self.assertEqual(noeul_live.live_timeout_s("가" * 400), 150.0)

    def test_read_all(self):
        self.assertTrue(noeul_live.read_all("안녕하세요 반갑습니다", TEXT))
        long = "오늘은 2026년 11월 18일이고 날씨가 아주 맑습니다"
        # 숫자를 말로 읽어 글이 달라도 끝 12글자가 같고 길이가 80% 이상이면 다 읽은 것
        self.assertTrue(noeul_live.read_all("오늘은 이천이십육년 십일월 십팔일이고 날씨가 아주 맑습니다", long))
        self.assertFalse(noeul_live.read_all("오늘은", long))


class TestWavAndKey(unittest.TestCase):
    def test_wav(self):
        data = noeul_live.wav_from_pcm(LOUD + QUIET)
        with wave.open(io.BytesIO(data)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()), (1, 2, 24000, 4800))
        self.assertEqual(len(data), 44 + 9600)

    def test_pcm_peak(self):
        self.assertEqual(noeul_live.pcm_peak(QUIET), 0)
        self.assertEqual(noeul_live.pcm_peak(LOUD), 1000)
        self.assertEqual(noeul_live.pcm_peak((-32768).to_bytes(2, "little", signed=True) + b"\x01"), 32768)

    def test_usage_key_id_matches_tts_usage(self):
        self.assertEqual(noeul_live.usage_key_id(" sk-abc "), tts_usage.key_mark("sk-abc")["id"])

    def test_read_paseo_key_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "google.env")
            self.assertIsNone(noeul_live.read_paseo_openai_key(path))     # 파일 없음
            cases = [
                ("﻿GOOGLE_TTS_KEY=g\nOPENAI_API_KEY=sk-plain\n", "sk-plain"),
                ("export OPENAI_API_KEY = \"sk-quoted\"  # 메모\n", "sk-quoted"),
                ("OPENAI_API_KEY='sk-single'\n", "sk-single"),
                ("OPENAI_API_KEY=sk-x # 주석\n", "sk-x"),
                ("OPENAI_API_KEY=\"sk-bad\" 꼬리\n", None),
                ("OPENAI_API_KEY=sk-1\nOPENAI_API_KEY=sk-2\n", "sk-2"),
                ("OPENAI_API_KEY=sk-1\nOPENAI_API_KEY=\n", None),
                ("GOOGLE_TTS_KEY=g\n", None),
            ]
            for content, want in cases:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.assertEqual(noeul_live.read_paseo_openai_key(path), want, content)

    def test_paseo_keys_path_follows_paseo_home(self):
        old = os.environ.get("PASEO_HOME")
        try:
            os.environ["PASEO_HOME"] = os.path.join("X:", "ph")
            self.assertEqual(noeul_live.paseo_keys_path(), os.path.join("X:", "ph", "claude-state-bar", "google.env"))
            del os.environ["PASEO_HOME"]
            self.assertTrue(noeul_live.paseo_keys_path().endswith(os.path.join(".paseo", "claude-state-bar", "google.env")))
        finally:
            if old is not None:
                os.environ["PASEO_HOME"] = old


class TestHandleExtensionRequest(unittest.TestCase):
    def handle(self, payload, key="sk-k", reader=None, cancelled=None, log=None):
        self.calls = []

        def default_reader(text, key, lang, log=None, cancelled=None):
            self.calls.append((text, key, lang, cancelled))
            return LOUD
        return noeul_live.handle_extension_request(payload, cancelled, key_reader=lambda: key,
                                                   reader=reader or default_reader, log=log)

    def test_cancelled_is_passed_to_reader_and_reported(self):
        probe = lambda: False
        status, *_ = self.handle({"v": 1, "text": "가"}, cancelled=probe)
        self.assertEqual(status, 200)
        self.assertIs(self.calls[0][3], probe)
        logs = []

        def reader(*a, **k):
            raise noeul_live.NoeulError("cancelled")
        status, ctype, raw, headers = self.handle({"v": 1, "text": "가나"}, reader=reader, log=logs.append)
        self.assertEqual((status, self.body(raw)["code"]), (499, "cancelled"))
        self.assertTrue(logs[0].startswith("[노을] 크롬 확장 요청 2자 — 확장이 끊어 노을 연결을 닫음"))

    def body(self, raw):
        return json.loads(raw.decode("utf-8"))

    def test_success_returns_wav_and_key_id(self):
        text = "이미 다듬은 글 — 다시 다듬지 않는다 (README)"
        status, ctype, raw, headers = self.handle({"v": 1, "text": text, "lang": "ko"})
        self.assertEqual((status, ctype), (200, "audio/wav"))
        self.assertEqual(raw, noeul_live.wav_from_pcm(LOUD))
        self.assertEqual(headers, {"X-Usage-Key": noeul_live.usage_key_id("sk-k")})
        self.assertEqual(self.calls, [(text, "sk-k", "ko", None)])

    def test_bad_requests(self):
        for payload in ([], {"text": "가"}, {"v": True, "text": "가"}, {"v": 2, "text": "가"}, {"v": 1},
                        {"v": 1, "text": "  "}, {"v": 1, "text": 3}, {"v": 1, "text": "가", "lang": "xx"}):
            status, ctype, raw, headers = self.handle(payload)
            self.assertEqual((status, ctype), (400, "application/json"), payload)
            self.assertEqual(self.body(raw)["code"], "bad_request")
        self.assertEqual(self.calls, [])
        status, *_ = self.handle({"v": 1, "text": "가"})      # lang 없으면 한국어
        self.assertEqual(status, 200)
        self.assertEqual(self.calls[0][2], "ko")

    def test_no_key(self):
        status, ctype, raw, headers = self.handle({"v": 1, "text": "가"}, key=None)
        self.assertEqual(status, 503)
        self.assertEqual(self.body(raw), {"ok": False, "code": "no_key", "error": noeul_live.MESSAGES["no_key"]})

    def test_noeul_errors_pass_through(self):
        for code, status in (("ip_not_authorized", 401), ("unauthorized", 401), ("timeout", 504),
                             ("no_audio", 502), ("connect", 502)):
            def reader(*a, **k):
                raise noeul_live.NoeulError(code)
            got_status, ctype, raw, headers = self.handle({"v": 1, "text": "가"}, reader=reader)
            self.assertEqual(got_status, status)
            self.assertEqual(self.body(raw)["code"], code)
            self.assertEqual(self.body(raw)["error"], noeul_live.MESSAGES[code])

    def test_unexpected_error_is_internal(self):
        def reader(*a, **k):
            raise RuntimeError("x")
        status, ctype, raw, headers = self.handle({"v": 1, "text": "가"}, reader=reader)
        self.assertEqual((status, self.body(raw)["code"]), (500, "internal"))


# ════════════════════════════════════════════════════════════════════
# LiveSocket — 이 PC 안의 작은 웹소켓 서버와 실제로 주고받기
# ════════════════════════════════════════════════════════════════════

def _server_frame(op, payload, fin=True):
    n = len(payload)
    first = (0x80 if fin else 0) | op
    if n < 126:
        head = bytes([first, n])
    elif n < 65536:
        head = bytes([first, 126]) + n.to_bytes(2, "big")
    else:
        head = bytes([first, 127]) + n.to_bytes(8, "big")
    return head + payload


def _read_client_frame(conn, buf):
    while True:
        if len(buf) >= 2:
            n, at = buf[1] & 0x7F, 2
            if n == 126 and len(buf) >= 4:
                n, at = int.from_bytes(buf[2:4], "big"), 4
            elif n == 127 and len(buf) >= 10:
                n, at = int.from_bytes(buf[2:10], "big"), 10
            if n < 126 or at > 2:
                masked = bool(buf[1] & 0x80)
                end = at + (4 if masked else 0) + n
                if len(buf) >= end:
                    op = buf[0] & 0x0F
                    payload = bytes(buf[end - n: end])
                    if masked:
                        mask = buf[at: at + 4]
                        payload = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
                    del buf[:end]
                    return op, masked, payload
        data = conn.recv(65536)
        if not data:
            return None, None, None
        buf += data


class TinyServer:
    """한 번만 받는 웹소켓 서버. reply = None 이면 101 로 열고 act(conn, buf, 기록) 실행, 문자열이면 그 HTTP 응답."""

    def __init__(self, act=None, reply=None, together=b""):
        self.together = together      # 101 응답과 한 번에 보낼 바이트(같은 묶음으로 오는 첫 메시지)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.act = act
        self.reply = reply
        self.request = {}
        self.got = []
        self.error = None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            conn, _ = self.sock.accept()
            conn.settimeout(5)
            buf = bytearray()
            while b"\r\n\r\n" not in buf:
                buf += conn.recv(65536)
            end = buf.index(b"\r\n\r\n")
            lines = bytes(buf[:end]).decode("latin-1").split("\r\n")
            del buf[: end + 4]
            self.request = {"line": lines[0]}
            for line in lines[1:]:
                name, _, value = line.partition(":")
                self.request[name.strip().lower()] = value.strip()
            if self.reply is not None:
                conn.sendall(self.reply.encode("utf-8"))
                conn.close()
                return
            accept = base64.b64encode(hashlib.sha1((self.request["sec-websocket-key"] + noeul_live._WS_GUID)
                                                   .encode("ascii")).digest()).decode("ascii")
            conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                          f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode("ascii") + self.together)
            self.act(conn, buf, self.got)
            conn.close()
        except Exception as e:     # 시험 실패를 본문에서 보이게
            self.error = e
        finally:
            self.sock.close()


class TestLiveSocket(unittest.TestCase):
    def test_frames_both_ways(self):
        long_text = "가" * 100             # 300바이트 — 길이 확장(126) 프레임

        def act(conn, buf, got):
            conn.sendall(_server_frame(1, "짧은 글".encode("utf-8")))
            conn.sendall(_server_frame(1, long_text.encode("utf-8")))
            conn.sendall(_server_frame(1, "앞".encode("utf-8"), fin=False) + _server_frame(0, "뒤".encode("utf-8")))
            conn.sendall(_server_frame(9, b"ping!"))
            got.append(_read_client_frame(conn, buf))      # pong
            got.append(_read_client_frame(conn, buf))      # 클라이언트 글
            conn.sendall(_server_frame(8, b""))

        server = TinyServer(act)
        ws = noeul_live.LiveSocket(f"ws://127.0.0.1:{server.port}/v1/live/sessions", {"Authorization": "Bearer sk-z"}, 5)
        self.assertEqual(ws.recv(2), "짧은 글")
        self.assertEqual(ws.recv(2), long_text)
        self.assertEqual(ws.recv(2), "앞뒤")
        sent = ("보낸 글 " + "나" * 50000).encode("utf-8")    # 64KB 넘는 길이(127) 프레임
        ws.send_text(sent.decode("utf-8"))
        with self.assertRaises(noeul_live.LiveClosed) as ctx:
            for _ in range(10):
                ws.recv(2)
        self.assertFalse(ctx.exception.error)
        ws.close()
        server.thread.join(5)
        self.assertIsNone(server.error)
        self.assertEqual(server.request["line"], "GET /v1/live/sessions HTTP/1.1")
        self.assertEqual(server.request["authorization"], "Bearer sk-z")
        self.assertEqual(server.request["upgrade"], "websocket")
        # 핑 응답과 보낸 글은 어느 쪽이 먼저 갈지 그때그때 다르다 — 종류별로 본다(긴 글은 길이·앞뒤만 비교해 출력이 짧게)
        got = {op: (masked, payload) for op, masked, payload in server.got}
        self.assertEqual(sorted(got), [1, 10])
        self.assertEqual(got[10], (True, b"ping!"))
        self.assertTrue(got[1][0])
        self.assertEqual((len(got[1][1]), got[1][1][:16], got[1][1][-16:]), (len(sent), sent[:16], sent[-16:]))
        self.assertTrue(got[1][1] == sent)

    def test_message_in_same_packet_as_101(self):
        # 여는 인사와 첫 메시지가 한 묶음으로 와도 첫 메시지를 놓치지 않는다(11-18 시험 중 찾은 결함)
        done = threading.Event()
        server = TinyServer(lambda conn, buf, got: done.wait(5),
                            together=_server_frame(1, b'{"type":"session.started"}'))
        ws = noeul_live.LiveSocket(f"ws://127.0.0.1:{server.port}/x", {}, 5)
        self.assertEqual(ws.recv(1), '{"type":"session.started"}')
        done.set()
        ws.close()
        server.thread.join(5)

    def test_recv_returns_none_on_quiet(self):
        done = threading.Event()

        def act(conn, buf, got):
            done.wait(5)

        server = TinyServer(act)
        ws = noeul_live.LiveSocket(f"ws://127.0.0.1:{server.port}/x", {}, 5)
        self.assertIsNone(ws.recv(0.05))
        done.set()
        ws.close()
        server.thread.join(5)

    def refused(self, status_line, body):
        reply = f"{status_line}\r\nContent-Type: application/json\r\nContent-Length: {len(body.encode())}\r\n\r\n{body}"
        server = TinyServer(reply=reply)
        with self.assertRaises(noeul_live.NoeulError) as ctx:
            noeul_live.LiveSocket(f"ws://127.0.0.1:{server.port}/v1/live/sessions", {"Authorization": "Bearer k"}, 5)
        server.thread.join(5)
        return ctx.exception

    def test_ip_not_authorized(self):
        e = self.refused("HTTP/1.1 401 Unauthorized",
                         json.dumps({"error": {"code": "ip_not_authorized", "message": "IP not allowed"}}))
        self.assertEqual((e.code, e.status), ("ip_not_authorized", 401))

    def test_other_401_is_unauthorized(self):
        e = self.refused("HTTP/1.1 401 Unauthorized", json.dumps({"error": {"code": "invalid_api_key"}}))
        self.assertEqual((e.code, e.status), ("unauthorized", 401))
        self.assertIn("invalid_api_key", e.message)

    def test_other_status_is_connect(self):
        e = self.refused("HTTP/1.1 500 Internal Server Error", "oops")
        self.assertEqual((e.code, e.status), ("connect", 502))
        self.assertIn("HTTP 500", e.message)

    def test_wrong_accept_is_connect(self):
        server = TinyServer(reply="HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: wrong\r\n\r\n")
        with self.assertRaises(noeul_live.NoeulError) as ctx:
            noeul_live.LiveSocket(f"ws://127.0.0.1:{server.port}/x", {}, 5)
        self.assertEqual(ctx.exception.code, "connect")
        server.thread.join(5)

    def test_unreachable_is_connect(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()                  # 아무도 안 듣는 포트
        with self.assertRaises(noeul_live.NoeulError) as ctx:
            noeul_live.LiveSocket(f"ws://127.0.0.1:{port}/x", {}, 2)
        self.assertEqual(ctx.exception.code, "connect")


# ════════════════════════════════════════════════════════════════════
# 받는 창구 — POST /v1/tts/noeul
# ════════════════════════════════════════════════════════════════════

class TestReceiverNoeulPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reports = tts_usage.ExtensionReports(os.path.join(self.tmp.name, "tts-usage-extension.json"))
        self.logs = []
        self.handler = lambda payload: (200, "audio/wav", noeul_live.wav_from_pcm(LOUD), {"X-Usage-Key": "abcdef012345"})
        self.cancelled_fns = []

        def noeul(payload, cancelled):
            self.cancelled_fns.append(cancelled)
            return self.handler(payload)
        self.receiver = tts_usage.UsageReceiver(self.reports, port=0, log=self.logs.append, noeul=noeul)
        self.assertTrue(self.receiver.start())
        self.base = f"http://127.0.0.1:{self.receiver.port}"

    def tearDown(self):
        self.receiver.stop()
        self.tmp.cleanup()

    def post(self, body=None, origin="chrome-extension://abcdefghijklmnop", raw=None, path=tts_usage.NOEUL_PATH,
             base=None):
        data = raw if raw is not None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request((base or self.base) + path, data=data, method="POST")
        if origin:
            req.add_header("Origin", origin)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_success(self):
        status, headers, raw = self.post({"v": 1, "text": "가", "lang": "ko"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "audio/wav")
        self.assertEqual(headers["X-Usage-Key"], "abcdef012345")
        self.assertEqual(raw, noeul_live.wav_from_pcm(LOUD))

    def test_handler_error_json(self):
        self.handler = lambda payload: (401, "application/json", noeul_live.error_body("ip_not_authorized"), {})
        status, headers, raw = self.post({"v": 1, "text": "가"})
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(raw)["code"], "ip_not_authorized")

    def test_origin_size_json_refused(self):
        status, headers, raw = self.post({"v": 1, "text": "가"}, origin=None)
        self.assertEqual((status, json.loads(raw)["code"]), (403, "origin"))
        status, headers, raw = self.post({"v": 1, "text": "가"}, origin="https://evil.example")
        self.assertEqual((status, json.loads(raw)["code"]), (403, "origin"))
        status, headers, raw = self.post(raw=b"{not json")
        self.assertEqual((status, json.loads(raw)["code"]), (400, "bad_request"))
        self.assertEqual(self.logs, ["[노을] 크롬 확장 요청 거절: origin_missing",
                                     "[노을] 크롬 확장 요청 거절: origin_other",
                                     "[노을] 크롬 확장 요청 거절: json"])

    def test_handler_crash_is_internal(self):
        def boom(payload):
            raise RuntimeError("x")
        self.handler = boom
        status, headers, raw = self.post({"v": 1, "text": "가"})
        self.assertEqual((status, json.loads(raw)["code"]), (500, "internal"))

    def test_twelve_requests_run_at_once(self):
        # 확장은 다음 조각 여러 개를 동시에 맡긴다(요청 090a8be2 — 상한 12) — 12개가 동시에 처리기 안에 있어야 모두 통과
        n = noeul_live.LIVE_SESSIONS_MAX
        barrier = threading.Barrier(n, timeout=10)

        def together(payload):
            barrier.wait()
            return 200, "audio/wav", noeul_live.wav_from_pcm(LOUD), {}
        self.handler = together
        results = []
        lock = threading.Lock()

        def one():
            status = self.post({"v": 1, "text": "가"})[0]
            with lock:
                results.append(status)
        threads = [threading.Thread(target=one) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        self.assertEqual(results, [200] * n)

    def test_open_request_is_not_cancelled(self):
        seen = []
        self.handler = lambda payload: (seen.append(self.cancelled_fns[-1]()) or (200, "audio/wav", b"x", {}))
        status, headers, raw = self.post({"v": 1, "text": "가"})
        self.assertEqual((status, seen), (200, [False]))

    def test_closed_request_is_seen_as_cancelled(self):
        # 확장이 멈춤·건너뛰기로 요청 연결을 닫으면 처리기의 cancelled() 가 참이 된다 → 노을 연결을 닫을 수 있다
        entered, seen = threading.Event(), threading.Event()

        def wait_for_cancel(payload):
            entered.set()
            for _ in range(200):
                if self.cancelled_fns[-1]():
                    seen.set()
                    break
                time.sleep(0.02)
            return 200, "audio/wav", b"", {}
        self.handler = wait_for_cancel
        body = json.dumps({"v": 1, "text": "가"}).encode("utf-8")
        s = socket.create_connection(("127.0.0.1", self.receiver.port))
        s.sendall(b"POST /v1/tts/noeul HTTP/1.1\r\nHost: 127.0.0.1\r\nOrigin: chrome-extension://abcdefghijklmnop\r\n"
                  b"Content-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        self.assertTrue(entered.wait(5))
        s.close()
        self.assertTrue(seen.wait(6))

    def test_peer_closed(self):
        a, b = socket.socketpair()
        try:
            self.assertFalse(tts_usage.peer_closed(b))
            a.close()
            deadline = time.monotonic() + 2
            while not tts_usage.peer_closed(b) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(tts_usage.peer_closed(b))
        finally:
            b.close()

    def test_usage_path_still_works(self):
        status, headers, raw = self.post({"v": 1, "source": "src-abcdef12", "months": {}}, path=tts_usage.RECEIVER_PATH)
        self.assertEqual(status, 200)

    def test_without_handler_noeul_path_is_404(self):
        bare = tts_usage.UsageReceiver(self.reports, port=0)
        self.assertTrue(bare.start())
        try:
            status, headers, raw = self.post({"v": 1, "text": "가"}, base=f"http://127.0.0.1:{bare.port}")
            self.assertEqual((status, json.loads(raw)), (404, {"ok": False, "reason": "path"}))
        finally:
            bare.stop()


if __name__ == "__main__":
    unittest.main()
