# -*- coding: utf-8 -*-
"""노을 직접 읽기 스트리밍. 실제 OpenAI·Tk·출력 장치 없이 가짜 연결/시계/스트림으로 확인한다."""
import ast
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import noeul_live as live
import readaloud_text as text
import translation
import tts_engine as engine
import tts_usage as usage
from test_noeul_live import Attempts, FakeClock as LiveClock, STARTED, TEXT, LOUD, QUIET, audio, said
from test_tts_engine import FakeClock, _load_glue, _pump, wait_until

SR = engine.SAMPLE_RATE


def pcm(value, seconds):
    return np.full(round(seconds * SR), value, dtype=np.int16).tobytes()


def step(session):
    with session._cond:
        return session._step_locked()


def consume(session):
    action = step(session)
    if action[0] == 'write':
        with session._cond:
            session._after_write_locked(action[2])
    return action


class TestPlan(unittest.TestCase):
    def test_first_short_sentences_and_long_comma(self):
        self.assertEqual(text.stream_pieces_growing('가. 나. 다라. 그 다음 문장입니다.', 1),
                         ['가. 나. 다라.', '그 다음 문장입니다.'])
        first = '😀가나다라마바사, ' + '아' * 50 + '.'
        pieces = text.stream_pieces_growing(first, 1.5)
        self.assertEqual(pieces, ['😀가나다라마바사,', '아' * 50 + '.'])
        self.assertEqual(' '.join(pieces), first)

    def test_early_comma_and_unsplittable_sentence(self):
        sentence = '가, ' + '나' * 60
        self.assertEqual(text.stream_pieces_growing(sentence, 1), [sentence])
        huge = '한' * 401 + '.'
        self.assertEqual(text.stream_pieces_growing(huge, 1.5), [huge])
        self.assertEqual(text.stream_pieces_growing('   ', 1), [])

    def test_growth_rate_floor_ceiling_and_sentence_boundaries(self):
        sentences = [('가' * 39 + '.')] + [(str(i) + '나' * 18 + '.') for i in range(15)]
        original = ' '.join(sentences)
        p1 = text.stream_pieces_growing(original, 1)
        # Paseo 원본 함수를 Node 로 실행해 얻은 값(별도 201개 입력 대조도 수행).
        self.assertEqual([len(p) for p in p1], [40, 83, 235])
        self.assertEqual(p1, text.stream_pieces_growing(original, 1.5))
        self.assertEqual(text.stream_pieces_growing(original, 3), text.stream_pieces_growing(original, 5))
        self.assertEqual(' '.join(p1), original)
        self.assertEqual(text.stream_pieces_growing('처음 문장입니다.\n둘째 문장입니다!', 1),
                         ['처음 문장입니다.', '둘째 문장입니다!'])

    def test_start_buffer_rounding(self):
        self.assertEqual(text.stream_start_sec('가' * 40, 1), 1)
        self.assertEqual(text.stream_start_sec('가' * 40, 1.5), 2.45)
        self.assertEqual(text.stream_start_sec('가' * 47, 1.5), 2.81)
        self.assertEqual(text.stream_start_sec('가' * 15, 1.5), 1.17)
        self.assertEqual(text.stream_start_sec('가' * 40, 0.5), 1)

    def test_javascript_trim_and_comma_whitespace(self):
        plain = '가나다라마바사.'
        self.assertEqual(text.stream_pieces_growing('\ufeff' + plain + '\ufeff', 1), [plain])
        nel = '\u0085' + plain + '\u0085'
        self.assertEqual(text.stream_pieces_growing(nel, 1), [nel])
        long = '가나다라마바사, \u0085' + '아' * 50
        self.assertEqual(text.stream_pieces_growing(long, 1), ['가나다라마바사,', '\u0085' + '아' * 50])

    def test_paragraph_kept_whole_only_for_streaming(self):
        source = ('한 문장입니다. ' * 180) + '\n\n다음 문단입니다.'
        google = text.split_paragraphs_for_reading(source, 'ko-KR')
        noeul = text.split_paragraphs_for_reading(source, 'ko-KR', streaming=True)
        self.assertGreater(len(google), len(noeul))
        self.assertEqual(len(noeul), 2)
        self.assertEqual([s['para'] for s in noeul], [0, 1])
        self.assertEqual((noeul[0]['src_start'], noeul[0]['src_end']), (0, source.index('\n\n') - 1))


class TestLiveSink(unittest.TestCase):
    def read(self, scripts, sink, text_value=TEXT):
        self.clock = LiveClock()
        self.attempts = Attempts(self.clock, scripts)
        return live.read_noeul(text_value, 'sk-fake', opener=self.attempts.opener, clock=self.clock,
                               close_delay=0, sink=lambda b: sink.append((self.clock.now, b)))

    def test_delivers_before_completion_with_one_quiet_piece_each_side(self):
        got = []
        script = [(0.1, STARTED), (0.2, audio(QUIET)), (0.3, audio(QUIET)), (0.4, audio(LOUD)),
                  (0.41, said(TEXT)), (0.5, audio(LOUD)), (0.6, audio(QUIET)), (0.7, audio(QUIET))]
        self.read([script], got)
        self.assertEqual([b for _, b in got], [QUIET, LOUD, LOUD, QUIET])
        self.assertAlmostEqual(got[0][0], 0.41)
        self.assertLess(got[0][0], self.clock.now)

    def test_wrong_head_is_discarded_before_retry(self):
        got = []
        other = pcm(2000, 0.1)
        wrong = [(0.1, STARTED), (0.2, audio(other)), (0.21, said('응답하지 말고'))]
        good = [(0.3, STARTED), (0.4, audio(LOUD)), (0.41, said(TEXT)), (0.5, audio(QUIET))]
        self.read([wrong, good], got)
        self.assertEqual(len(self.attempts.conns), 2)
        self.assertTrue(got)
        self.assertNotIn(other, [b for _, b in got])

    def test_no_retry_after_audio_delivered(self):
        got = []
        script = [(0.1, STARTED), (0.2, audio(LOUD)), (0.21, said(TEXT)),
                  (0.3, {'type': 'error', 'error': {'code': 'broken'}})]
        with self.assertRaises(live.NoeulError):
            self.read([script, []], got)
        self.assertEqual(len(self.attempts.conns), 1)
        self.assertEqual([b for _, b in got], [LOUD])
        self.assertTrue(self.attempts.conns[0].closed)

    def test_head_timeout_releases_pending_audio(self):
        got = []
        self.read([[(0.1, STARTED), (1, audio(LOUD))]], got)
        self.assertTrue(got)
        self.assertAlmostEqual(got[0][0], 2.5)


class TestStreamingPlayback(unittest.TestCase):
    def session(self, count=1, rate=1):
        self.clock = FakeClock()
        return engine.TtsSession('원문', [{'text': f'문단 {i}', 'para': i} for i in range(count)],
                                 lambda *_: None, lambda: None, rate=rate, clock=self.clock, drain=0)

    def ready(self, s, index, a):
        with s._cond:
            s._put_ready_locked(index, a, 1, index)

    def test_buffer_threshold_then_wait_without_skipping(self):
        s = self.session(2)
        a = engine.GrowingAudio(1)
        self.ready(s, 0, a)
        self.ready(s, 1, np.full(2400, 2000, dtype=np.int16))
        a.append(pcm(1000, 0.9))
        self.assertEqual(step(s)[0], 'wait')
        a.append(pcm(1000, 0.1))
        self.assertEqual(consume(s)[0], 'write')
        self.assertFalse(a.done)   # 첫 조각 완료까지 기다린 것이 아님
        for _ in range(9):
            self.assertEqual(consume(s)[0], 'write')
        self.assertEqual(step(s)[0], 'wait')
        self.assertEqual((s._cur, s._target), (0, 0))
        a.append(pcm(1001, 0.1))
        self.assertEqual(int(consume(s)[1][0]), 1001)
        a.finish()
        self.assertEqual(int(consume(s)[1][0]), 2000)

    def test_exact_original_sample_threshold_at_one_and_one_point_five(self):
        for rate in (1, 1.5):
            with self.subTest(rate=rate):
                s = self.session(rate=rate)
                a = engine.GrowingAudio(text.stream_start_sec('가' * 40, rate))
                self.ready(s, 0, a)
                a.append(np.full(a.start_samples - 1, 1000, np.int16).tobytes())
                self.assertEqual(step(s)[0], 'wait')
                a.append(np.full(1, 1000, np.int16).tobytes())
                self.assertEqual(consume(s)[0], 'write')
                self.assertFalse(a.done)

    def test_short_complete_paragraph_does_not_wait_forever(self):
        s = self.session()
        a = engine.GrowingAudio(1)
        self.ready(s, 0, a)
        a.append(pcm(1000, 0.1))
        self.assertEqual(step(s)[0], 'wait')
        a.finish()
        self.assertEqual(consume(s)[0], 'write')
        self.assertEqual(step(s), ('done', 'finished'))

    def test_prefetched_failure_is_reported_only_at_its_turn(self):
        s = self.session(2)
        a = engine.GrowingAudio(1)
        a.finish(engine.SegmentFailed(live.MESSAGES['unauthorized']))
        self.ready(s, 0, np.full(2400, 1000, dtype=np.int16))
        self.ready(s, 1, a)
        self.assertEqual(consume(s)[0], 'write')
        self.assertFalse(any(k == 'segment_failed' for k, _ in s._outbox))
        self.assertEqual(step(s), ('done', 'segment_failed'))
        failed = [d for k, d in s._outbox if k == 'segment_failed']
        self.assertEqual(failed, [{'index': 1, 'message': live.MESSAGES['unauthorized'], 'provider': 'noeul'}])

    def test_move_cancels_only_jobs_outside_window_pause_keeps_them(self):
        s = self.session(4)
        jobs = [engine.GrowingAudio(1, cancelled=s._stop_event.is_set) for _ in range(3)]
        for i, a in enumerate(jobs):
            self.ready(s, i, a)
        step(s)
        s.pause()
        self.assertFalse(any(a.cancelled for a in jobs))
        s.forward()
        self.clock.advance(1)
        step(s)
        self.assertTrue(jobs[0].cancelled)
        self.assertFalse(jobs[1].cancelled or jobs[2].cancelled)
        s.stop()
        self.assertTrue(all(a.cancelled for a in jobs))

    def test_wsola_waits_preserve_state_and_flush_only_at_paragraph_end(self):
        samples = (np.sin(np.arange(SR * 3) * 2 * np.pi * 220 / SR) * 10000).astype(np.int16)
        for rate in (1, 1.5):
            with self.subTest(rate=rate):
                growing = engine.GrowingAudio(1)
                stretch = engine._StreamingStretcher(growing, rate)
                actual = []
                for part in np.array_split(samples, 15):
                    growing.append(part.tobytes())
                    while True:
                        block, _ = stretch.next_block(2400, rate)
                        if not len(block):
                            break
                        actual.append(block)
                    self.assertFalse(stretch.done)
                growing.finish()
                for _ in range(100):
                    block, _ = stretch.next_block(2400, rate)
                    if len(block):
                        actual.append(block)
                    if stretch.done:
                        break
                self.assertTrue(stretch.done)
                complete = engine._Stretcher(samples, rate)
                expected = []
                while not complete.done:
                    block, _ = complete.next_block(2400, rate)
                    if len(block):
                        expected.append(block)
                np.testing.assert_array_equal(np.concatenate(actual), np.concatenate(expected))

    def test_rate_change_applies_to_next_streaming_block(self):
        a = engine.GrowingAudio(1)
        a.append(pcm(1000, 4))
        stretch = engine._StreamingStretcher(a, 1)
        block, consumed_one = stretch.next_block(2400, 1)
        self.assertEqual((len(block), consumed_one), (2400, 2400))
        block, consumed_fast = stretch.next_block(2400, 1.5)
        self.assertEqual(len(block), 2400)
        self.assertGreater(consumed_fast, consumed_one)
        block, consumed_back = stretch.next_block(2400, 1)
        self.assertEqual((len(block), consumed_back), (2400, 2400))
        self.assertFalse(a.done)


class TestParagraphWorkers(unittest.TestCase):
    def tearDown(self):
        for a in getattr(self, 'jobs', []):
            a.cancel()
            for worker in a.workers:
                if worker.ident is not None:
                    worker.join(3)
                    self.assertFalse(worker.is_alive())

    def job(self, synth, value, rate=1):
        a = synth.stream(value, rate, cancelled=lambda: False, wake=lambda: None)
        self.jobs = getattr(self, 'jobs', []) + [a]
        return a

    def test_out_of_order_connections_are_drained_in_order_before_first_done(self):
        value = '처음 읽을 문장입니다. 두 번째 문장입니다. 세 번째 문장입니다.'
        pieces = text.stream_pieces_growing(value, 1.5)
        hold = threading.Event()
        called = []

        def reader(t, key, lang, *, sink, cancelled, **kwargs):
            index = pieces.index(t)
            called.append(index)
            sink(pcm((index + 1) * 1000, 0.1))
            if index == 0:
                while not hold.wait(0.01):
                    if cancelled():
                        raise live.NoeulError('cancelled')
            return b'unused'

        counted = []
        a = self.job(engine.make_noeul_synthesize('k', reader=reader, on_sent=counted.append), value, 1.5)
        self.assertTrue(wait_until(lambda: len(called) == len(pieces) and len(a) == 2400))
        self.assertFalse(a.done)
        self.assertEqual(set(a.read(0, len(a))), {1000})
        hold.set()
        self.assertTrue(wait_until(lambda: a.done))
        expected = np.concatenate([np.full(2400, (i + 1) * 1000, np.int16) for i in range(len(pieces))])
        np.testing.assert_array_equal(a.read(0, len(a)), expected)
        self.assertCountEqual(counted, pieces)

    def test_eight_workers_and_failure_cancel_other_connections(self):
        value = ' '.join('가' * 301 + str(i) + '.' for i in range(11))
        active, peak = 0, 0
        lock = threading.Lock()
        release = threading.Event()

        def reader(t, key, lang, *, sink, cancelled, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(active, peak)
            try:
                while not release.wait(0.01):
                    if cancelled():
                        raise live.NoeulError('cancelled')
                if t.endswith('0.'):
                    raise live.NoeulError('unauthorized')
                while not cancelled():
                    time.sleep(0.001)
                raise live.NoeulError('cancelled')
            finally:
                with lock:
                    active -= 1

        counted = []
        a = self.job(engine.make_noeul_synthesize('k', reader=reader, on_sent=counted.append), value)
        self.assertTrue(wait_until(lambda: active == 8))
        self.assertEqual(peak, 8)
        release.set()
        self.assertTrue(wait_until(lambda: a.done and active == 0))
        self.assertEqual(str(a.error), live.MESSAGES['unauthorized'])
        self.assertEqual(counted, [])

    def test_translation_preserves_stream_plan_and_caption(self):
        calls = []

        def synth(*_):
            self.fail('완성 배열 경로를 부르면 안 됨')

        result = object()
        synth.stream = lambda t, r, **kw: calls.append((t, r, kw)) or result
        wrapped = translation.make_translating_synthesize(synth, lambda ts: ['번역된 문장입니다.' for _ in ts],
                                                          lambda t: t + ' 변환', {'Hello world.'})
        cancelled, wake = lambda: False, lambda: None
        self.assertIs(wrapped.stream('Hello world.', 1.5, cancelled=cancelled, wake=wake), result)
        self.assertEqual(calls, [('번역된 문장입니다. 변환', 1.5, {'cancelled': cancelled, 'wake': wake})])
        self.assertEqual(wrapped.translated_of('Hello world.'), '번역된 문장입니다.')

    def test_real_counter_counts_success_once_and_extension_does_not_count(self):
        attempts_seen = []

        def reader(t, key, lang, **kwargs):
            clock = LiveClock()
            wrong = [(0.1, STARTED), (0.2, audio(LOUD)), (0.21, said('응답하지 말고'))]
            good = [(0.3, STARTED), (0.4, audio(LOUD)), (0.41, said(t)), (0.5, audio(QUIET))]
            attempts = Attempts(clock, [wrong, good])
            attempts_seen.append(attempts)
            return live.read_noeul(t, key, lang, opener=attempts.opener, clock=clock, close_delay=0, **kwargs)

        now = datetime(2026, 11, 18, tzinfo=timezone.utc)
        mark = usage.key_mark('fake-openai-key')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'usage.json'
            counter = usage.UsageCounter(str(path))
            synth = engine.make_noeul_synthesize('fake-openai-key', reader=reader,
                on_sent=lambda sent: self.assertTrue(counter.count('openai', sent, now=now, key=mark)))
            a = self.job(synth, TEXT)
            self.assertTrue(wait_until(lambda: a.done))
            before = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(before['months']['2026-11']['openai'], len(TEXT))
            self.assertEqual(before['keys'][mark['id']]['months']['2026-11']['openai'], len(TEXT))
            self.assertEqual(len(attempts_seen[0].conns), 2)   # 버린 연결은 세지 않음

            def refused(*args, **kwargs):
                raise live.NoeulError('unauthorized')

            bad = self.job(engine.make_noeul_synthesize('fake-openai-key', reader=refused,
                            on_sent=lambda sent: counter.count('openai', sent, now=now, key=mark)), TEXT)
            self.assertTrue(wait_until(lambda: bad.done))
            self.assertIsInstance(bad.error, engine.SegmentFailed)
            response = live.handle_extension_request({'v': 1, 'text': TEXT},
                        key_reader=lambda: 'fake-openai-key', reader=reader)
            self.assertEqual(response[0], 200)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), before)

    def test_ip_key_and_exhausted_retry_errors_use_shared_messages(self):
        for code in ('ip_not_authorized', 'unauthorized'):
            with self.subTest(code=code):
                def reader(*args, **kwargs):
                    raise live.NoeulError(code)
                a = self.job(engine.make_noeul_synthesize('k', reader=reader), TEXT)
                self.assertTrue(wait_until(lambda: a.done))
                self.assertEqual(str(a.error), live.MESSAGES[code])
        attempts_seen = []

        def silent(t, key, lang, **kwargs):
            clock = LiveClock()
            attempts = Attempts(clock, [[], [], []])
            attempts_seen.append(attempts)
            return live.read_noeul(t, key, lang, opener=attempts.opener, clock=clock, close_delay=0, **kwargs)

        counted = []
        a = self.job(engine.make_noeul_synthesize('k', reader=silent, on_sent=counted.append), TEXT)
        self.assertTrue(wait_until(lambda: a.done))
        self.assertEqual(str(a.error), live.MESSAGES['no_audio'])
        self.assertEqual(len(attempts_seen[0].conns), 3)
        self.assertEqual(counted, [])


class HeldConnections:
    """실제 read_noeul 의 연결 자리·취소 루프를 통과하는 가짜 웹소켓. 네트워크를 열지 않는다."""
    def __init__(self):
        self.lock = threading.Lock()
        self.conns = []
        self.active = self.peak = 0

    def opener(self, *args):
        owner = self

        class Conn:
            def __init__(self):
                self.started = self.closed = self.session_closed = False
                self.sent = []
                self.text = None

            def send_text(self, value):
                event = json.loads(value)
                self.sent.append(event['type'])
                if event['type'] == 'session.instructions.append':
                    self.text = event['content'].partition(': ')[2]
                if event['type'] == 'session.close' and not self.session_closed:
                    self.session_closed = True
                    with owner.lock:
                        owner.active -= 1

            def recv(self, timeout):
                if not self.started:
                    self.started = True
                    return json.dumps(STARTED)
                time.sleep(min(timeout, 0.01))
                return None

            def close(self):
                self.closed = True

        conn = Conn()
        with self.lock:
            self.conns.append(conn)
            self.active += 1
            self.peak = max(self.peak, self.active)
        return conn


class TestLiveCancellation(unittest.TestCase):
    def test_move_into_translating_paragraph_keeps_one_connection(self):
        entered, translated, finish = threading.Event(), threading.Event(), threading.Event()
        calls = []
        jobs = []

        def translator(sources):
            entered.set()
            translated.wait(3)
            return ['번역된 문단입니다.' for _ in sources]

        def reader(t, key, lang, *, sink, cancelled, **kwargs):
            calls.append(t)
            sink(pcm(1000, 0.1))
            if t == '번역된 문단입니다.':
                while not finish.wait(0.01):
                    if cancelled():
                        raise live.NoeulError('cancelled')
            return b'ignored'

        base = engine.make_noeul_synthesize('fake', reader=reader)
        original = base.stream

        def remember(*args, **kwargs):
            a = original(*args, **kwargs)
            jobs.append(a)
            return a

        base.stream = remember
        synth = translation.make_translating_synthesize(base, translator, lambda t: t, {'Hello world.'})
        s = engine.TtsSession('원문', [{'text': '첫 문단입니다.', 'para': 0},
                              {'text': 'Hello world.', 'para': 1}], synth,
                              lambda: types.SimpleNamespace(start=lambda: None, stop=lambda: None,
                              abort=lambda: None, close=lambda: None, write=lambda b: None), move_delay=0, drain=0)
        try:
            s.pause()
            s.start()
            self.assertTrue(entered.wait(3))
            s.forward()
            self.assertTrue(wait_until(lambda: s._cur == 1))
            translated.set()
            self.assertTrue(wait_until(lambda: s._audio_idx == 1))
            self.assertEqual(calls.count('번역된 문단입니다.'), 1)
            self.assertFalse(jobs[-1].cancelled)
        finally:
            finish.set()
            translated.set()
            s.stop()
            s.join(3)
            for a in jobs:
                for worker in a.workers:
                    worker.join(3)

    def test_move_closes_old_live_connection_and_rate_does_not_replan(self):
        held = HeldConnections()
        jobs = []

        def reader(t, key, lang, **kwargs):
            return live.read_noeul(t, key, lang, opener=held.opener, close_delay=0, **kwargs)

        synth = engine.make_noeul_synthesize('fake', reader=reader)
        base = synth.stream

        def remember(*args, **kwargs):
            a = base(*args, **kwargs)
            jobs.append(a)
            return a

        synth.stream = remember
        values = ['첫째 문단입니다.', '둘째 문단입니다.', '셋째 문단입니다.']
        session = engine.TtsSession('원문', [{'text': t, 'para': i} for i, t in enumerate(values)], synth,
                                    lambda: types.SimpleNamespace(start=lambda: None, stop=lambda: None,
                                    abort=lambda: None, close=lambda: None, write=lambda b: None),
                                    move_delay=0, drain=0)
        try:
            session.start()
            self.assertTrue(wait_until(lambda: len(held.conns) == 3 and all(c.text for c in held.conns)))
            session.set_rate(1.5)
            self.assertEqual(session.rate, 1.5)
            self.assertEqual([j.plan_rate for j in jobs], [1, 1, 1])
            session.forward()
            old = next(c for c in held.conns if c.text == values[0])
            self.assertTrue(wait_until(lambda: old.closed))
            self.assertTrue(old.session_closed)
            self.assertFalse(any(c.session_closed for c in held.conns if c is not old))
            self.assertEqual(len(jobs), 3)   # 겹치는 문단은 다시 열지 않고 계획도 바꾸지 않는다.
        finally:
            session.stop()
            session.join(3)
            for job in jobs:
                for worker in job.workers:
                    worker.join(3)
            self.assertTrue(all(c.closed for c in held.conns))

    def test_global_twelve_slots_shared_with_extension_pause_and_stop(self):
        held = HeldConnections()
        ext_cancel = threading.Event()
        ext_errors = []

        def reader(t, key, lang, **kwargs):
            return live.read_noeul(t, key, lang, opener=held.opener, close_delay=0, **kwargs)

        def extension():
            try:
                reader(TEXT, 'fake', 'ko', cancelled=ext_cancel.is_set)
            except live.NoeulError as e:
                ext_errors.append(e.code)

        ext = threading.Thread(target=extension, daemon=True)
        ext.start()
        self.assertTrue(wait_until(lambda: held.active == 1))
        value = ' '.join('가' * 301 + str(i) + '.' for i in range(11))
        counted = []
        synth = engine.make_noeul_synthesize('fake', reader=reader, on_sent=counted.append)
        jobs = []
        base_stream = synth.stream

        def remember(*args, **kwargs):
            job = base_stream(*args, **kwargs)
            jobs.append(job)
            return job

        synth.stream = remember
        session = engine.TtsSession('원문', [{'text': value, 'para': i} for i in range(2)], synth,
                                    lambda: types.SimpleNamespace(start=lambda: None, stop=lambda: None,
                                    abort=lambda: None, close=lambda: None, write=lambda b: None), drain=0)
        try:
            session.start()
            self.assertTrue(wait_until(lambda: held.active == 12 and len(jobs) == 2))
            self.assertEqual(held.peak, live.LIVE_SESSIONS_MAX)
            session.pause()
            time.sleep(0.05)
            self.assertFalse(any(c.session_closed for c in held.conns))
            session.stop()
            ext_cancel.set()
            self.assertTrue(session.join(3))
            ext.join(3)
            self.assertFalse(ext.is_alive())
            self.assertTrue(wait_until(lambda: held.active == 0 and all(c.closed for c in held.conns)))
            self.assertTrue(all('session.close' in c.sent for c in held.conns))
            self.assertEqual(ext_errors, ['cancelled'])
            self.assertEqual(counted, [])
        finally:
            session.stop()
            ext_cancel.set()
            ext.join(3)
            for job in jobs:
                for worker in job.workers:
                    worker.join(3)

    def test_move_during_translation_prevents_late_connection(self):
        entered, release = threading.Event(), threading.Event()
        readers = []

        def translator(sources):
            entered.set()
            release.wait(3)
            return ['번역된 첫 문단입니다.' for _ in sources]

        def reader(t, key, lang, *, sink, cancelled, **kwargs):
            readers.append(t)
            sink(pcm(1000, 0.1))
            return b'ignored'

        synth = translation.make_translating_synthesize(
            engine.make_noeul_synthesize('fake', reader=reader), translator, lambda t: t, {'Hello world.'})
        events = []
        session = engine.TtsSession('원문', [{'text': 'Hello world.', 'para': 0},
                                    {'text': '다음 문단입니다.', 'para': 1}], synth,
                                    lambda: types.SimpleNamespace(start=lambda: None, stop=lambda: None,
                                    abort=lambda: None, close=lambda: None, write=lambda b: None),
                                    lambda k, d: events.append((k, d)), move_delay=0, drain=0)
        try:
            session.start()
            self.assertTrue(entered.wait(3))
            session.forward()
            self.assertTrue(wait_until(lambda: session._cur == 1))
            release.set()
            self.assertTrue(session.join(3))
            self.assertEqual(readers, ['다음 문단입니다.'])
        finally:
            release.set()
            session.stop()
            session.join(3)


class TestAppNoeul(unittest.TestCase):
    def setUp(self):
        self.ui = []
        self.ns = _load_glue(self.ui)
        self.ns['tts_voice_name'] = engine.NOEUL_VOICE
        self.ns['google_tts_client'] = self.ns['google_tts'] = None
        self.ns['openai_api_key'] = None   # 인증 창의 OpenAI 키(2026-11-18 — Paseo 키 파일 대신)

    def tearDown(self):
        for name in ('tts_session', 'tts_preview_session'):
            s = self.ns.get(name)
            if s is not None:
                s.stop()
                self.assertTrue(s.join(3))

    def fake_factory(self, reader):
        self.ns['tts_engine'].make_noeul_synthesize = lambda key, **kw: engine.make_noeul_synthesize(
            key, reader=reader, **kw)

    def test_speak_noeul_without_google_preserves_paragraphs_and_key_count(self):
        def reader(t, key, lang, *, sink, **kw):
            sink(pcm(1000, 0.2))
            return b'ignored'
        self.fake_factory(reader)
        with patch.dict(self.ns, openai_api_key='fake-openai-key'):
            self.ns['speak_text']('첫 문단입니다.\n\n두 번째 문단입니다.')
            s = self.ns['tts_session']
            self.assertIsNotNone(s)
            self.assertTrue(_pump(self.ns, lambda: not s.is_alive()))
        self.assertEqual([v['para'] for v in s.segments], [0, 1])
        self.assertTrue(self.ns['_counted'])
        for voice, sent, mark in self.ns['_counted']:
            self.assertEqual(voice, engine.NOEUL_VOICE)
            self.assertEqual(mark, usage.key_mark('fake-openai-key'))
        self.assertTrue(any(u[0] == 'reader.highlight' for u in self.ui))

    def test_missing_key_stops_and_warns_instead_of_skipping(self):
        self.fake_factory(live.read_noeul)   # no_key 는 opener 이전에 끝난다.
        with patch.dict(self.ns, openai_api_key=None):
            self.ns['speak_text']('읽을 문단입니다.')
            s = self.ns['tts_session']
            self.assertIsNotNone(s)
            self.assertTrue(_pump(self.ns, lambda: not s.is_alive()))
        failed = [u[1] for u in self.ui if u[0] == 'notify_failed']
        self.assertEqual(failed[0]['message'], live.MESSAGES['no_key'])
        self.assertEqual(self.ns['_counted'], [])

    def test_voice_id_and_bilingual_label(self):
        self.assertEqual(engine.voice_lang_of(engine.NOEUL_VOICE), 'ko-KR')
        self.assertEqual(usage.usage_kind(engine.NOEUL_VOICE), 'openai')
        self.assertEqual(usage.voice_label(engine.NOEUL_VOICE, 12, '{}', '이번 달 PC 앱 {}자'),
                         '노을 · OpenAI 라이브 · 분당 0.05달러 (이번 달 PC 앱 12자)')
        self.assertIn('$0.05 per minute', usage.voice_label(engine.NOEUL_VOICE, language='en'))

    def extract(self, *names):
        path = Path(__file__).resolve().parents[1] / 'whisperer.py'
        nodes = ast.parse(path.read_text(encoding='utf-8')).body
        module = ast.Module(body=[n for n in nodes if isinstance(n, ast.FunctionDef) and n.name in names],
                            type_ignores=[])
        exec(compile(module, str(path), 'exec'), self.ns)

    def test_noeul_preview_streams_without_google_and_counts(self):
        def reader(t, key, lang, *, sink, **kwargs):
            sink(pcm(1000, 0.1))
            return b'ignored'
        self.fake_factory(reader)
        self.extract('_start_noeul_preview')
        self.ns['tts_preview_session'] = None
        with patch.dict(self.ns, openai_api_key='fake-preview'):
            self.ns['_start_noeul_preview']('미리 들을 문장입니다.', 1.5)
            s = self.ns['tts_preview_session']
            self.assertTrue(s.join(3))
        self.assertEqual(s.rate, 1.5)
        self.assertEqual(self.ns['_counted'][0][2], usage.key_mark('fake-preview'))
        self.assertTrue(any(np.any(b) for stream in self.ns['_streams'] for b in stream.written()))
        self.assertEqual(self.ui, [])  # 본문 하단 바·형광펜은 열지 않음

    def test_preview_failure_is_queued_for_gui_and_is_not_counted(self):
        self.fake_factory(live.read_noeul)
        self.extract('_start_noeul_preview')
        self.ns['tts_preview_session'] = None
        with patch.dict(self.ns, openai_api_key=None):
            self.ns['_start_noeul_preview']('미리 들을 문장입니다.', 1)
            s = self.ns['tts_preview_session']
            self.assertTrue(s.join(3))
        message = self.ns['gui_queue'].get_nowait()
        self.assertEqual(message, ('tts_preview_failed', s, {'index': 0,
                         'message': live.MESSAGES['no_key'], 'provider': 'noeul'}))
        self.assertEqual(self.ns['_counted'], [])

    def test_noeul_warning_uses_shared_reason_and_gui_thread_callback(self):
        callbacks, warnings = [], []
        self.ns['root'] = types.SimpleNamespace(after=lambda delay, fn: callbacks.append(fn))
        self.ns['messagebox'] = types.SimpleNamespace(showwarning=lambda *args: warnings.append(args))
        self.extract('_notify_segment_failed')
        self.ns['_notify_segment_failed']({'index': 0, 'message': live.MESSAGES['ip_not_authorized'],
                                          'provider': 'noeul'})
        self.assertEqual(warnings, [])
        callbacks[0]()
        self.assertEqual(warnings, [('dialog_tts_title', live.MESSAGES['ip_not_authorized'])])

    def test_reading_provider_filters_voices_and_remembers_google_voice(self):
        # 2026-11-18 리규형님: 목록엔 읽기 공급자의 목소리만. OpenAI 로 갔다 돌아오면 마지막 Google 목소리(Paseo voice.google)
        path = Path(__file__).resolve().parents[1] / 'whisperer.py'
        nodes = ast.parse(path.read_text(encoding='utf-8')).body
        selected = [n for n in nodes if isinstance(n, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in ('KOREAN_VOICES', 'DEFAULT_VOICE', 'TTS_PROVIDERS')
            for target in n.targets)]
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), self.ns)
        self.extract('_voice_provider', '_voices_for', '_set_tts_provider')
        voices = self.ns['_voices_for']
        self.assertEqual(voices('openai'), [engine.NOEUL_VOICE])
        self.assertEqual(len(voices('google')), 8)
        self.assertNotIn(engine.NOEUL_VOICE, voices('google'))
        self.ns.update(tts_provider='google', tts_voice_name='ko-KR-Chirp3-HD-Kore', tts_google_voice='ko-KR-Chirp3-HD-Kore')
        self.ns['_set_tts_provider']('openai')
        self.assertEqual((self.ns['tts_provider'], self.ns['tts_voice_name']), ('openai', engine.NOEUL_VOICE))
        self.ns['_set_tts_provider']('google')
        self.assertEqual((self.ns['tts_provider'], self.ns['tts_voice_name']), ('google', 'ko-KR-Chirp3-HD-Kore'))
        self.ns['_set_tts_provider']('bogus')
        self.assertEqual(self.ns['tts_provider'], 'google')

    def test_voice_list_default_and_actual_settings_roundtrip(self):
        path = Path(__file__).resolve().parents[1] / 'whisperer.py'
        nodes = ast.parse(path.read_text(encoding='utf-8')).body
        selected = [n for n in nodes if isinstance(n, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in ('KOREAN_VOICES', 'DEFAULT_VOICE') for target in n.targets)]
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), self.ns)
        self.assertEqual(self.ns['KOREAN_VOICES'][-1], engine.NOEUL_VOICE)
        self.assertEqual(self.ns['DEFAULT_VOICE'], 'ko-KR-Chirp3-HD-Zephyr')
        self.extract('save_settings', 'load_settings', '_voice_provider', '_voices_for', '_set_tts_provider')
        self.ns.update(current_language='ko', google_tts_api_key=None, gemini_api_key=None, openai_api_key='fake-openai-key',
            anthropic_api_key='fake-claude-key', tts_provider='openai', translate_provider='anthropic', tts_google_voice='ko-KR-Chirp3-HD-Kore', TTS_PROVIDERS=('google', 'openai'),
            tts_hotkey_modifiers={'ctrl': True}, tts_hotkey_key='D', tts_voice_name=engine.NOEUL_VOICE,
            tts_speaking_rate=1.5, tts_rate_step=0.1, reader_window_geometry=None, bottom_bar_monitor='foreground',
            selection_button_enabled=True, disable_in_browsers=True, usage_pill_visible=False,
            usage_pill_position=None, _mask_keys=lambda value: value, json=json, print=lambda *args: None)
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / 'settings.json'
            self.ns['os'] = types.SimpleNamespace(path=types.SimpleNamespace(exists=lambda name: settings_path.exists()),
                                                  fsync=os.fsync)
            self.ns['open'] = lambda name, *args, **kwargs: open(settings_path, *args, **kwargs)
            self.ns['save_settings']()
            saved = json.loads(settings_path.read_text(encoding='utf-8'))
            self.assertEqual(saved['tts_settings']['voice_name'], engine.NOEUL_VOICE)
            self.assertEqual(saved['openai_api_key'], 'fake-openai-key')   # OpenAI 키도 설정 파일에
            self.ns['tts_voice_name'] = self.ns['DEFAULT_VOICE']
            self.assertEqual((saved['tts_provider'], saved['translate_provider'], saved['anthropic_api_key'], saved['tts_settings']['google_voice']), ('openai', 'anthropic', 'fake-claude-key', 'ko-KR-Chirp3-HD-Kore'))
            self.ns['openai_api_key'] = None
            self.ns.update(tts_provider='google', translate_provider='google', anthropic_api_key=None, tts_google_voice='ko-KR-Chirp3-HD-Zephyr')
            self.ns['load_settings']()
            self.assertEqual(self.ns['tts_voice_name'], engine.NOEUL_VOICE)
            self.assertEqual(self.ns['tts_speaking_rate'], 1.5)
            self.assertEqual(self.ns['openai_api_key'], 'fake-openai-key')   # 불러오기도 OpenAI 키를 되살린다
            self.assertEqual((self.ns['tts_provider'], self.ns['translate_provider'], self.ns['anthropic_api_key'], self.ns['tts_google_voice']), ('openai', 'anthropic', 'fake-claude-key', 'ko-KR-Chirp3-HD-Kore'))   # 공급자(11-18)


if __name__ == '__main__':
    unittest.main()
