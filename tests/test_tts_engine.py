# -*- coding: utf-8 -*-
"""tts_engine 테스트 — 가짜 합성·가짜 출력 스트림·가짜 시계로 소리 없이 돌린다.

가짜 출력(FakeStream)은 write 한 블록을 기록하고, 블록 길이만큼 가짜 시계를 앞으로 민다.
→ "재생된 소리 시간 = 가짜 시계" 가 되어 3초 규칙·750ms 연타 묶기·총 시간 추정을 실제 시간 없이 정확히 잴 수 있다.
가짜 소리의 샘플 값은 (조각 번호+1)*1000 + (조각 안 블록 번호) 라서, 기록된 블록만 보고
"어느 조각의 몇 번째 블록이 나왔는지" 를 되살린다(처음부터 다시 읽으면 블록 번호가 0 으로 돌아간다).
whisperer.py 는 import 하지 않는다(트레이·키보드 훅이 뜬다). 실제 Google 호출도 하지 않는다.
"""

import os
import sys
import threading
import time
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import readaloud_text  # noqa: E402
import tts_engine  # noqa: E402
from tts_engine import TtsSession  # noqa: E402

SR = tts_engine.SAMPLE_RATE
BLOCK = tts_engine.BLOCK_SAMPLES
POLL = 0.002          # 테스트에서는 대기 주기를 짧게
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ════════════════════════════════════════════════════════════════════
# 가짜 부품
# ════════════════════════════════════════════════════════════════════

class FakeClock:
    """가짜 시계. FakeStream.write 가 재생한 만큼 앞으로 민다. 테스트가 직접 advance 할 수도 있다."""

    def __init__(self, t=0.0):
        self._t = t
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            return self._t

    def advance(self, dt):
        with self._lock:
            self._t += dt


class FakeStream:
    """가짜 출력 스트림. 소리를 내지 않고 블록을 기록한다. on_write(블록) 훅은 재생 스레드에서 불린다."""

    def __init__(self, clock, on_write=None):
        self.clock = clock
        self.on_write = on_write
        self.blocks = []
        self.lock = threading.Lock()
        self.started = self.stopped = self.aborted = self.closed = False

    def start(self):
        self.started = True

    def write(self, block):
        if self.aborted or self.closed:
            raise RuntimeError("stream aborted")
        arr = np.array(block, copy=True)
        with self.lock:
            self.blocks.append(arr)
        self.clock.advance(len(arr) / SR)
        if self.on_write is not None:
            self.on_write(arr)
        time.sleep(0)  # 다른 스레드에 차례를 준다

    def abort(self):
        self.aborted = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True

    def written(self):
        with self.lock:
            return list(self.blocks)


def block_audio(idx, seconds):
    """조각 idx 의 가짜 소리: 값 = (idx+1)*1000 + 조각 안 블록 번호."""
    n = int(round(seconds * SR))
    return ((idx + 1) * 1000 + (np.arange(n) // BLOCK)).astype(np.int16)


def decode(block):
    """기록된 블록 → (조각 번호, 블록 번호). 무음(드레인)이면 None."""
    v = int(block[0])
    if v == 0:
        return None
    return v // 1000 - 1, v % 1000


def runs_of(blocks):
    """기록된 블록들 → [(조각, 시작 블록, 연속 블록 수)]. 처음부터 다시 읽으면 새 run 이 된다."""
    runs = []
    for b in blocks:
        d = decode(b)
        if d is None:
            continue
        seg, blk = d
        if runs and runs[-1][0] == seg and runs[-1][1] + runs[-1][2] == blk:
            runs[-1] = (seg, runs[-1][1], runs[-1][2] + 1)
        else:
            runs.append((seg, blk, 1))
    return runs


class FakeSynth:
    """가짜 합성. texts[i] 를 받으면 조각 i 의 가짜 소리를 돌려준다.

    seconds(idx, rate): 소리 길이, fail: 예외를 던질 조각, gates: {idx: Event} 열릴 때까지 멈춤(네트워크 지연 흉내),
    audio_of(idx, rate, seconds): 소리 모양을 바꾸고 싶을 때.
    """

    def __init__(self, texts, seconds=None, fail=(), gates=None, audio_of=None):
        self.index = {t: i for i, t in enumerate(texts)}
        self.seconds = seconds or (lambda idx, rate: 0.5)
        self.fail = set(fail)
        self.gates = gates or {}
        self.audio_of = audio_of or (lambda idx, rate, sec: block_audio(idx, sec))
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, text, rate):
        idx = self.index[text]
        with self.lock:
            self.calls.append((idx, rate))
        gate = self.gates.get(idx)
        if gate is not None:
            gate.wait(5)
        if idx in self.fail:
            raise RuntimeError("가짜 API 오류")
        return self.audio_of(idx, rate, self.seconds(idx, rate))

    def called(self):
        with self.lock:
            return list(self.calls)


def wait_until(pred, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.001)
    return pred()


class Harness:
    """세션 하나를 가짜 부품으로 조립한다. hooks: [(조건 함수(블록, h) → bool, 실행 함수(h))] — 한 번씩만 실행."""

    def __init__(self, texts, seconds=None, fail=(), gates=None, audio_of=None, hooks=None,
                 open_stream=None, on_event_error=None, **kwargs):
        self.texts = list(texts)
        self.clock = FakeClock()
        self.events = []
        self.ev_lock = threading.Lock()
        self.hooks = [[cond, act, False] for cond, act in (hooks or [])]
        self.stream = FakeStream(self.clock, on_write=self._on_write)
        self.synth = FakeSynth(self.texts, seconds=seconds, fail=fail, gates=gates, audio_of=audio_of)
        self.segments = [{"text": t, "src_start": None, "src_end": None} for t in self.texts]
        self.on_event_error = on_event_error
        self.session = TtsSession(
            "원문", self.segments, self.synth, open_stream or (lambda: self.stream), self._on_event,
            clock=self.clock, poll=POLL, **kwargs)

    def _on_event(self, kind, data):
        with self.ev_lock:
            self.events.append((kind, data))
        if self.on_event_error and kind == self.on_event_error:
            raise RuntimeError("받는 쪽 오류 흉내")

    def _on_write(self, block):
        for hook in self.hooks:
            cond, act, done = hook
            if not done and cond(block, self):
                hook[2] = True
                act(self)

    # 조회 도우미
    def all_events(self):
        with self.ev_lock:
            return list(self.events)

    def kinds(self):
        return [k for k, _ in self.all_events()]

    def states(self):
        return [d for k, d in self.all_events() if k == "state"]

    def segment_events(self):
        return [d for k, d in self.all_events() if k == "segment"]

    def run(self, timeout=10.0):
        self.session.start()
        ok = self.session.join(timeout)
        assert ok, "세션이 제때 끝나지 않았다"
        return runs_of(self.stream.written())


def at_block(seg, blk):
    """훅 조건: 조각 seg 의 blk 번째 블록을 막 썼을 때."""
    return lambda block, h: decode(block) == (seg, blk)


# ════════════════════════════════════════════════════════════════════
# 테스트
# ════════════════════════════════════════════════════════════════════

class EngineTestBase(unittest.TestCase):
    def tearDown(self):
        # 어떤 테스트든 끝나면 tts- 스레드가 남아 있으면 안 된다(좀비 방지)
        self.assertTrue(wait_until(lambda: not [t for t in threading.enumerate() if t.name.startswith("tts-")], 3.0),
                        "tts 스레드가 남아 있다: %r" % [t.name for t in threading.enumerate()])


class TestPlaybackOrder(EngineTestBase):
    def test_plays_segments_in_order_with_event_order(self):
        h = Harness(["첫 줄.", "둘째 줄.", "셋째 줄."], seconds=lambda i, r: 0.5)
        runs = h.run()
        self.assertEqual(runs, [(0, 0, 5), (1, 0, 5), (2, 0, 5)])
        # 끝에 드레인 무음(0.25초)을 한 번 흘리고 stop(abort 아님)으로 닫는다
        last = h.stream.written()[-1]
        self.assertEqual(len(last), int(SR * tts_engine.DRAIN_SECONDS))
        self.assertFalse(last.any())
        self.assertTrue(h.stream.started and h.stream.stopped and h.stream.closed)
        self.assertFalse(h.stream.aborted)

        events = h.all_events()
        kinds = [k for k, _ in events]
        self.assertEqual(kinds[0], "session_start")
        self.assertEqual(events[0][1]["source_text"], "원문")
        self.assertEqual(events[0][1]["segments"], h.segments)
        self.assertEqual(kinds[-1], "session_end")
        self.assertEqual(kinds.count("session_end"), 1)
        self.assertEqual(kinds.count("session_start"), 1)
        self.assertEqual(events[-2], ("state", events[-2][1]))
        self.assertEqual(events[-2][1]["state"], "STOPPED")
        self.assertEqual(h.segment_events(), [0, 1, 2])
        # 조각 k 의 segment 알림은 그 조각 소리보다 먼저 나간다(형광펜이 늦지 않게)
        keys = {"state", "elapsed", "total", "progress", "can_prev", "can_next",
                "can_mute", "muted", "rate", "volume"}
        for st in h.states():
            self.assertEqual(set(st), keys)
            self.assertIn(st["state"], ("LOADING", "PLAYING", "PAUSED", "STOPPED"))
            self.assertGreaterEqual(st["progress"], 0.0)
            self.assertLessEqual(st["progress"], 1.0)

    def test_failed_and_blank_segments_are_skipped_but_indexes_kept(self):
        texts = ["하나.", "   ", "둘.", ".", "셋."]
        h = Harness(texts, seconds=lambda i, r: 0.3, fail={2})
        runs = h.run()
        # 조각 2 는 합성 실패, 1·3 은 공백/마침표라 합성 요청도 안 한다. 4 의 소리는 여전히 "조각 4" 의 소리다
        self.assertEqual(runs, [(0, 0, 3), (4, 0, 3)])
        called = sorted({i for i, _ in h.synth.called()})
        self.assertEqual(called, [0, 2, 4])
        segs = h.segment_events()
        self.assertEqual(segs[0], 0)
        self.assertEqual(segs[-1], 4)
        self.assertEqual(segs, sorted(segs))
        self.assertNotIn(1, segs)
        self.assertNotIn(3, segs)

    def test_on_event_errors_do_not_break_playback(self):
        h = Harness(["가.", "나."], seconds=lambda i, r: 0.2, on_event_error="state")
        self.assertEqual(h.run(), [(0, 0, 2), (1, 0, 2)])
        self.assertEqual(h.kinds()[-1], "session_end")

    def test_open_stream_failure_ends_session_cleanly(self):
        def broken():
            raise RuntimeError("장치 없음")
        h = Harness(["가."], open_stream=broken)
        h.session.start()
        self.assertTrue(h.session.join(5))
        kinds = h.kinds()
        self.assertEqual(kinds[0], "session_start")
        self.assertEqual(kinds[-1], "session_end")
        self.assertEqual(h.states()[-1]["state"], "STOPPED")


class TestPauseResume(EngineTestBase):
    def test_pause_stops_writing_and_resume_continues_without_loss(self):
        h = Harness(["가.", "나."], seconds=lambda i, r: 1.0,
                    hooks=[(at_block(0, 3), lambda h: h.session.command("togglePause"))])
        h.session.start()
        self.assertTrue(wait_until(lambda: any(s["state"] == "PAUSED" for s in h.states())))
        paused = [s for s in h.states() if s["state"] == "PAUSED"][0]
        self.assertTrue(paused["can_prev"] and paused["can_next"])
        n1 = len(h.stream.written())
        t1 = h.clock()
        time.sleep(0.05)
        self.assertEqual(len(h.stream.written()), n1, "일시정지 중에 소리를 썼다")
        self.assertEqual(h.clock(), t1)
        h.session.command("togglePause")
        self.assertTrue(h.session.join(5))
        self.assertEqual(runs_of(h.stream.written()), [(0, 0, 10), (1, 0, 10)])
        names = [s["state"] for s in h.states()]
        dedup = [n for i, n in enumerate(names) if i == 0 or names[i - 1] != n]
        self.assertEqual(dedup, ["PLAYING", "PAUSED", "PLAYING", "STOPPED"])


class TestStopAndThreads(EngineTestBase):
    def test_stop_leaves_no_zombie_threads(self):
        baseline = threading.active_count()
        reached = threading.Event()
        # 6조각: 합성 스레드는 앞으로 2조각까지만 만들고 대기 → 그 대기 중에 멈춰도 빠져나와야 한다(옛 좀비 상황)
        h = Harness([f"조각{i}." for i in range(6)], seconds=lambda i, r: 5.0,
                    hooks=[(at_block(0, 5), lambda h: reached.set())])
        h.session.start()
        self.assertTrue(reached.wait(5))
        h.session.stop()
        self.assertTrue(h.session.join(2.0))
        self.assertFalse(h.session.is_alive())
        self.assertTrue(wait_until(lambda: threading.active_count() == baseline, 2.0))
        self.assertTrue(h.stream.aborted and h.stream.closed)
        self.assertEqual(h.kinds().count("session_end"), 1)
        self.assertEqual(h.kinds()[-1], "session_end")
        self.assertEqual(h.states()[-1]["state"], "STOPPED")
        # 멈춤 신호는 한 번 켜지면 꺼지지 않는다(finally 에서 clear 하던 옛 좀비 함정 방지)
        self.assertTrue(h.session._stop_event.is_set())
        h.session.stop()   # 두 번 불러도 괜찮다
        self.assertEqual(h.kinds().count("session_end"), 1)

    def test_stop_aborts_a_blocked_write(self):
        # 실제 장치의 write 는 버퍼가 빌 때까지 막힌다. stop() 이 abort 로 풀어 주지 않으면 여기서 5초 걸린다
        class BlockingStream(FakeStream):
            def __init__(self, clock):
                super().__init__(clock)
                self.unblock = threading.Event()
                self.entered = threading.Event()

            def write(self, block):
                super().write(block)
                if len(self.blocks) >= 3:
                    self.entered.set()
                    self.unblock.wait(5)

            def abort(self):
                super().abort()
                self.unblock.set()
        clock = FakeClock()
        stream = BlockingStream(clock)
        s = TtsSession("원문", [{"text": "가.", "src_start": 0, "src_end": 2}],
                       FakeSynth(["가."], seconds=lambda i, r: 5.0), lambda: stream, None, clock=clock, poll=POLL)
        s.start()
        self.assertTrue(stream.entered.wait(5))
        started = time.monotonic()
        s.stop()
        self.assertTrue(s.join(1.0))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertTrue(stream.aborted)

    def test_stop_while_synthesis_in_flight(self):
        baseline = threading.active_count()
        gate = threading.Event()
        reached = threading.Event()
        h = Harness(["가.", "나.", "다."], seconds=lambda i, r: 2.0, gates={1: gate},
                    hooks=[(at_block(0, 2), lambda h: reached.set())])
        h.session.start()
        self.assertTrue(reached.wait(5))
        h.session.command("stop")
        gate.set()   # 늦게 돌아온 합성 결과 — 멈춘 뒤라 버려져야 한다
        self.assertTrue(h.session.join(2.0))
        self.assertTrue(wait_until(lambda: threading.active_count() == baseline, 2.0))
        self.assertNotIn(1, [r[0] for r in runs_of(h.stream.written())])

    def test_new_session_waits_for_previous_player(self):
        # 앞 읽기가 스트림을 닫은 다음에야 새 스트림을 연다 (옛 스트림 close 를 일부러 느리게).
        # 옛 스트림 write 도 실제 장치처럼 천천히(블록당 10ms) — stop() 순간에 옛 읽기가 아직 재생 중이어야
        # stop() 이 abort 만 하고 바로 돌아오고, close 는 옛 재생 스레드가 나중에 한다(그걸 기다리는지 보는 것)
        class SlowCloseStream(FakeStream):
            def write(self, block):
                super().write(block)
                time.sleep(0.01)

            def close(self):
                time.sleep(0.2)
                super().close()
        old = Harness(["가."], seconds=lambda i, r: 5.0)
        old.stream = SlowCloseStream(old.clock)
        old.session._open_stream = lambda: old.stream
        old.session.start()
        self.assertTrue(wait_until(lambda: len(old.stream.written()) > 2))
        order = []
        new_clock = FakeClock()
        new_stream = FakeStream(new_clock)

        def open_new():
            order.append(("open_new", old.stream.closed))
            return new_stream
        new = TtsSession("원문2", [{"text": "나.", "src_start": 0, "src_end": 2}],
                         FakeSynth(["나."], seconds=lambda i, r: 0.2), open_new, None,
                         clock=new_clock, poll=POLL, previous=old.session)
        old.session.stop()
        new.start()
        self.assertTrue(new.join(5))
        self.assertTrue(old.session.join(5))
        self.assertEqual(order, [("open_new", True)])


class TestMoves(EngineTestBase):
    def test_rewind_within_3s_goes_to_previous_after_750ms(self):
        # 조각 1 을 1.1초 들은 때 이전 → 750ms 동안 조각 1 이 계속 나오다가 조각 0 처음부터
        h = Harness(["가.", "나.", "다."], seconds=lambda i, r: 5.0,
                    hooks=[(at_block(1, 10), lambda h: h.session.rewind())])
        runs = h.run()
        self.assertEqual(runs[0], (0, 0, 50))
        seg, start, count = runs[1]
        self.assertEqual((seg, start), (1, 0))
        self.assertTrue(18 <= count <= 20, runs)     # 11블록 + 0.75초(7~8블록)
        self.assertEqual(runs[2:], [(0, 0, 50), (1, 0, 50), (2, 0, 50)])
        self.assertEqual(h.segment_events(), [0, 1, 0, 1, 2])
        self.assertEqual([i for i, _ in h.synth.called()].count(0), 2)   # 옮긴 뒤 다시 합성

    def test_rewind_after_3s_restarts_current_immediately(self):
        h = Harness(["가.", "나.", "다."], seconds=lambda i, r: 5.0,
                    hooks=[(at_block(1, 35), lambda h: h.session.rewind())])
        runs = h.run()
        self.assertEqual(runs, [(0, 0, 50), (1, 0, 36), (1, 0, 50), (2, 0, 50)])
        self.assertEqual(h.segment_events(), [0, 1, 2])

    def test_rewind_on_first_segment_restarts_it(self):
        h = Harness(["가.", "나."], seconds=lambda i, r: 5.0,
                    hooks=[(at_block(0, 10), lambda h: h.session.command("rewind"))])
        runs = h.run()
        self.assertEqual(runs, [(0, 0, 11), (0, 0, 50), (1, 0, 50)])

    def test_forward_is_disabled_on_last_segment(self):
        h = Harness(["가.", "나."], seconds=lambda i, r: 1.0,
                    hooks=[(at_block(1, 3), lambda h: h.session.forward())])
        runs = h.run()
        self.assertEqual(runs, [(0, 0, 10), (1, 0, 10)])
        self.assertEqual(h.segment_events(), [0, 1])
        current = None
        seen_true = seen_false = False
        for kind, data in h.all_events():
            if kind == "segment":
                current = data
            elif kind == "state" and data["state"] == "PLAYING":
                if current == 0:
                    self.assertTrue(data["can_next"])
                    seen_true = True
                elif current == 1:
                    self.assertFalse(data["can_next"])
                    self.assertTrue(data["can_prev"])
                    seen_false = True
        self.assertTrue(seen_true and seen_false)

    def test_rapid_forward_presses_are_combined(self):
        # 0.6초·1.1초에 다음을 두 번(두 번째는 첫 이동이 적용되기 전) → 마지막 누름 0.75초 뒤(1.85초)에
        # 한 번만 이동하고 조각 1 은 건너뛴다. 첫 누름 기준이었다면 1.35초에 옮겨 14블록만 나왔을 것이다
        h = Harness(["가.", "나.", "다.", "라."], seconds=lambda i, r: 3.0,
                    hooks=[(at_block(0, 5), lambda h: h.session.forward()),
                           (at_block(0, 10), lambda h: h.session.command("forward"))])
        runs = h.run()
        seg, start, count = runs[0]
        self.assertEqual((seg, start), (0, 0))
        self.assertTrue(18 <= count <= 20, runs)     # 1.1초 + 0.75초 = 1.85초 → 19블록 안팎
        self.assertEqual(runs[1:], [(2, 0, 30), (3, 0, 30)])
        self.assertEqual(h.segment_events(), [0, 1, 2, 3])

    def test_double_rewind_within_delay_goes_back_two(self):
        # 조각 2 를 2.6초 들은 때 이전(→1, 대기), 3.2초 때 또 이전 → 첫 누름 시각이 새 기준이라 3초 규칙에
        # 걸리지 않고 목표만 0 으로 한 칸 더 간다(확장: 이동을 누를 때마다 ts = Date.now())
        h = Harness(["가.", "나.", "다."], seconds=lambda i, r: 5.0,
                    hooks=[(at_block(2, 25), lambda h: h.session.rewind()),
                           (at_block(2, 31), lambda h: h.session.rewind())])
        runs = h.run()
        self.assertEqual(runs[:2], [(0, 0, 50), (1, 0, 50)])
        seg, start, count = runs[2]
        self.assertEqual((seg, start), (2, 0))
        self.assertTrue(38 <= count <= 41, runs)     # 3.2초 + 0.75초
        self.assertEqual(runs[3:], [(0, 0, 50), (1, 0, 50), (2, 0, 50)])
        self.assertEqual(h.segment_events(), [0, 1, 2, 1, 0, 1, 2])

    def test_late_result_from_old_generation_is_dropped(self):
        gate = threading.Event()
        h = Harness(["가.", "나.", "다.", "라."], seconds=lambda i, r: 2.0, gates={1: gate},
                    hooks=[(at_block(0, 3), lambda h: h.session.forward()),
                           (at_block(0, 4), lambda h: h.session.forward())])
        h.session.start()
        # 이동이 적용될 때까지(조각 1 합성은 아직 네트워크에 걸려 있음)
        self.assertTrue(wait_until(lambda: h.session._cur == 2))
        gate.set()   # 이제서야 조각 1 결과가 도착 — 옛 세대라 버려져야 한다
        self.assertTrue(h.session.join(10))
        runs = runs_of(h.stream.written())
        self.assertEqual(runs[0][:2], (0, 0))
        self.assertEqual(runs[1:], [(2, 0, 20), (3, 0, 20)])
        self.assertNotIn(1, [r[0] for r in runs])
        self.assertIn(1, [i for i, _ in h.synth.called()])   # 요청은 했지만 재생하지 않음


class TestRateVolume(EngineTestBase):
    def test_rate_change_applies_from_next_segment(self):
        # 소리 값에 속도를 새긴다: (idx+1)*1000 + 속도*100
        def audio_of(idx, rate, sec):
            return np.full(int(sec * SR), (idx + 1) * 1000 + int(round(rate * 100)), dtype=np.int16)
        texts = ["가.", "나.", "다."]
        h = Harness(texts, seconds=lambda i, r: 2.0, audio_of=audio_of,
                    hooks=[(lambda b, h: int(b[0]) == 1100 and len(h.stream.written()) == 4,
                            lambda h: h.session.command("setRate", 1.5))])
        h.run()
        values = np.concatenate([b for b in h.stream.written() if b.any()])
        counts = {int(v): int(c) for v, c in zip(*np.unique(values, return_counts=True))}
        full = 2 * SR
        self.assertEqual(counts.get(1100), full, counts)   # 지금 조각은 옛 속도로 끝까지
        self.assertEqual(counts.get(2150), full, counts)   # 다음 조각부터 새 속도
        self.assertEqual(counts.get(3150), full, counts)
        self.assertNotIn(2100, counts)                      # 옛 속도로 미리 만든 조각은 버림
        self.assertNotIn(3100, counts)
        self.assertEqual(h.states()[-2]["rate"], 1.5)
        for idx, rate in h.synth.called():
            if idx == 0:
                self.assertEqual(rate, 1.0)

    def test_rate_is_clamped_to_cloud_range(self):
        self.assertEqual(tts_engine.clamp_rate(10), tts_engine.RATE_MAX)
        self.assertEqual(tts_engine.clamp_rate(0.01), tts_engine.RATE_MIN)
        self.assertEqual(tts_engine.clamp_rate("x"), 1.0)
        self.assertEqual(tts_engine.clamp_rate(float("nan")), 1.0)
        self.assertEqual(tts_engine.clamp_rate(1.23), 1.23)
        s = TtsSession("", [], lambda t, r: None, lambda: None, rate=9)
        self.assertEqual(s.rate, 4.0)

    def test_volume_and_mute_gain(self):
        def audio_of(idx, rate, sec):
            return np.full(int(sec * SR), 10000, dtype=np.int16)

        def nth(n):
            return lambda b, h: len(h.stream.written()) == n

        def unmute_and_louder(h):
            h.session.command("unmute")
            h.session.command("setVolume", 5)   # 1.0 으로 잘린다
        h = Harness(["가."], seconds=lambda i, r: 2.0, audio_of=audio_of, volume=0.5,
                    hooks=[(nth(6), lambda h: h.session.command("mute")),
                           (nth(10), unmute_and_louder)])
        h.run()
        blocks = h.stream.written()
        seg_blocks = blocks[:20]
        self.assertEqual(sum(len(b) for b in seg_blocks), 2 * SR)   # 음소거해도 시간은 흐른다(건너뛰지 않음)
        firsts = [int(b[0]) for b in seg_blocks]
        self.assertEqual(firsts[:6], [5000] * 6)      # 볼륨 0.5
        self.assertEqual(firsts[6:10], [0] * 4)       # 음소거 — 다음 블록부터 바로
        self.assertEqual(firsts[10:], [10000] * 10)   # 음소거 해제 + 볼륨 1.0
        muted_states = [s for s in h.states() if s["muted"]]
        self.assertTrue(muted_states and all(s["can_mute"] for s in h.states()))
        self.assertEqual(h.session.volume, 1.0)
        self.assertEqual(tts_engine.clamp_volume(-1), 0.0)


class TestTiming(EngineTestBase):
    def _texts(self):
        return ["가" * 10, "나" * 20, "다" * 30]

    def test_total_is_none_until_first_audio_then_estimated(self):
        gate = threading.Event()
        # 1글자에 0.1초(속도 1.0 기준) → 1초·2초·3초, 합 6초
        h = Harness(self._texts(), seconds=lambda i, r: [10, 20, 30][i] * 0.1 / r, gates={0: gate})
        h.session.start()
        self.assertTrue(wait_until(lambda: len(h.states()) >= 1))
        first = h.states()[0]
        self.assertIsNone(first["total"])            # 첫 조각 길이를 알기 전: "계산 중"
        self.assertEqual(first["elapsed"], 0.0)
        gate.set()
        self.assertTrue(h.session.join(10))
        playing = [s for s in h.states() if s["state"] == "PLAYING" and s["total"] is not None]
        self.assertTrue(playing)
        for s in playing:
            self.assertAlmostEqual(s["total"], 6.0, places=6)
        elapsed = [s["elapsed"] for s in playing]
        self.assertEqual(elapsed, sorted(elapsed))
        # 조각 1 이 시작될 때 지난 시간은 조각 0 길이(1초)
        cur = None
        for kind, data in h.all_events():
            if kind == "segment":
                cur = data
            elif kind == "state" and cur == 1:
                self.assertGreaterEqual(data["elapsed"], 1.0 - 1e-9)
                break

    def test_estimate_follows_rate_change(self):
        h = Harness(self._texts(), seconds=lambda i, r: [10, 20, 30][i] * 0.1 / r,
                    hooks=[(at_block(0, 2), lambda h: h.session.set_rate(2.0))])
        h.run()
        after = [s for s in h.states() if s["rate"] == 2.0 and s["state"] == "PLAYING"]
        self.assertTrue(after)
        # 조각 0 은 1초(이미 합성), 나머지는 속도 2배로 1초 + 1.5초 → 3.5초
        for s in after:
            self.assertAlmostEqual(s["total"], 3.5, places=6)

    def test_loading_shown_only_after_two_seconds(self):
        gate = threading.Event()
        h = Harness(["가.", "나."], seconds=lambda i, r: 0.5, gates={0: gate})
        h.session.start()
        self.assertTrue(wait_until(lambda: len(h.states()) >= 1))
        self.assertEqual(h.states()[0]["state"], "PLAYING")
        h.clock.advance(1.5)
        time.sleep(0.05)
        self.assertNotIn("LOADING", [s["state"] for s in h.states()])
        h.clock.advance(0.6)   # 2.1초 기다림
        self.assertTrue(wait_until(lambda: any(s["state"] == "LOADING" for s in h.states())))
        loading = [s for s in h.states() if s["state"] == "LOADING"][0]
        self.assertFalse(loading["can_prev"] or loading["can_next"])   # 확장: PLAYING·PAUSED 때만 이동 가능
        gate.set()
        self.assertTrue(h.session.join(10))
        names = [s["state"] for s in h.states()]
        self.assertEqual(names[names.index("LOADING") + 1], "PLAYING")


class TestGoogleSynthesize(unittest.TestCase):
    """make_google_synthesize — 가짜 texttospeech 모듈과 가짜 클라이언트로(실제 호출 없음)."""

    @staticmethod
    def fake_tts(markup_field=True):
        fields = {"text": 1, "ssml": 1}
        if markup_field:
            fields["markup"] = 1

        class SynthesisInput:
            meta = types.SimpleNamespace(fields=fields)

            def __init__(self, text=None, markup=None):
                self.text = text
                self.markup = markup

        class VoiceSelectionParams:
            def __init__(self, language_code, name):
                self.language_code = language_code
                self.name = name

        class AudioConfig:
            def __init__(self, audio_encoding, sample_rate_hertz, speaking_rate):
                self.audio_encoding = audio_encoding
                self.sample_rate_hertz = sample_rate_hertz
                self.speaking_rate = speaking_rate

        return types.SimpleNamespace(SynthesisInput=SynthesisInput, VoiceSelectionParams=VoiceSelectionParams,
                                     AudioConfig=AudioConfig,
                                     AudioEncoding=types.SimpleNamespace(LINEAR16="LINEAR16"))

    class FakeClient:
        def __init__(self, reject_markup=False, content=None):
            self.reject_markup = reject_markup
            self.requests = []
            self.content = content if content is not None else b"H" * 44 + np.array([1, 2, 3], np.int16).tobytes()

        def synthesize_speech(self, input, voice, audio_config):
            self.requests.append((input, voice, audio_config))
            if input.markup is not None and self.reject_markup:
                raise RuntimeError("400 INVALID_ARGUMENT")
            return types.SimpleNamespace(audio_content=self.content)

    def test_korean_chirp_uses_markup_first(self):
        client = self.FakeClient()
        synth = tts_engine.make_google_synthesize(client, self.fake_tts(), "ko-KR-Chirp3-HD-Callirrhoe")
        audio = synth("사과, 배.", 1.2)
        self.assertEqual(audio.tolist(), [1, 2, 3])
        self.assertEqual(len(client.requests), 1)
        inp, voice, cfg = client.requests[0]
        self.assertEqual(inp.markup, readaloud_text.pauses_markup("사과, 배.", "ko-KR", "Chirp3-HD"))
        self.assertIn("[pause short]", inp.markup)
        self.assertIsNone(inp.text)
        self.assertEqual((voice.language_code, voice.name), ("ko-KR", "ko-KR-Chirp3-HD-Callirrhoe"))
        self.assertEqual((cfg.audio_encoding, cfg.sample_rate_hertz, cfg.speaking_rate), ("LINEAR16", 24000, 1.2))

    def test_rejected_markup_falls_back_to_text(self):
        client = self.FakeClient(reject_markup=True)
        synth = tts_engine.make_google_synthesize(client, self.fake_tts(), "ko-KR-Chirp3-HD-Callirrhoe")
        self.assertEqual(synth("사과, 배.", 1.0).tolist(), [1, 2, 3])
        self.assertEqual([r[0].markup is not None for r in client.requests], [True, False])
        self.assertEqual(client.requests[1][0].text, "사과, 배.")

    def test_text_only_when_markup_not_applicable(self):
        for voice_name, text, field in [("ko-KR-Wavenet-A", "사과, 배.", True),          # Chirp3-HD 아님
                                        ("ko-KR-Chirp3-HD-Callirrhoe", "사과 배.", True),  # 쉼표·화살표 없음
                                        ("ko-KR-Chirp3-HD-Callirrhoe", "사과, 배.", False)]:  # 라이브러리에 markup 없음
            client = self.FakeClient()
            synth = tts_engine.make_google_synthesize(client, self.fake_tts(field), voice_name)
            synth(text, 1.0)
            self.assertEqual(len(client.requests), 1)
            self.assertIsNone(client.requests[0][0].markup)
            self.assertEqual(client.requests[0][0].text, text)

    def test_rate_clamped_and_header_stripped(self):
        client = self.FakeClient()
        synth = tts_engine.make_google_synthesize(client, self.fake_tts(), "ko-KR-Wavenet-A")
        synth("가.", 5.0)
        self.assertEqual(client.requests[0][2].speaking_rate, 4.0)
        empty = tts_engine.make_google_synthesize(self.FakeClient(content=b"H" * 44), self.fake_tts(), "ko-KR-Wavenet-A")
        self.assertIsNone(empty("가.", 1.0))

    def test_voice_helpers(self):
        self.assertEqual(tts_engine.voice_lang_of("ko-KR-Chirp3-HD-Callirrhoe"), "ko-KR")
        self.assertEqual(tts_engine.voice_type_of("ko-KR-Chirp3-HD-Callirrhoe"), "Chirp3-HD")
        self.assertEqual(tts_engine.voice_lang_of("en-US-Neural2-F"), "en-US")
        self.assertEqual(tts_engine.voice_type_of("ko-KR-Wavenet-A"), "Wavenet")
        self.assertEqual(tts_engine.voice_lang_of(""), "ko-KR")
        self.assertIsNone(tts_engine.voice_type_of("이상한이름"))
        self.assertTrue(tts_engine.is_silent_segment("  .  "))
        self.assertTrue(tts_engine.is_silent_segment("\n\n"))
        self.assertFalse(tts_engine.is_silent_segment(".."))
        self.assertEqual(tts_engine.count_spoken_chars(" 가 나\n다 "), 3)


class TestRobustness(EngineTestBase):
    """2026-09-28 깨 보기에서 찾은 결함의 재발 방지 (수정 전 엔진에서는 모두 실패했다)."""

    def test_session_end_is_not_delayed_by_synthesis_in_flight(self):
        # 합성 요청이 네트워크에 걸린 채(gate) 정지 → 옛 코드는 합성 스레드를 1초 기다린 뒤에야 session_end 를 보내
        # 하단 바가 1초 동안 "재생 중" 으로 남았고, 새 읽기도 1초 늦게 시작했다
        gate = threading.Event()
        reached = threading.Event()
        h = Harness(["가.", "나.", "다."], seconds=lambda i, r: 5.0, gates={1: gate},
                    hooks=[(at_block(0, 3), lambda h: reached.set())])
        h.session.start()
        self.assertTrue(reached.wait(5))
        opened = []
        new_clock = FakeClock()
        new_stream = FakeStream(new_clock)
        new = TtsSession("원문2", [{"text": "라.", "src_start": 0, "src_end": 2}],
                         FakeSynth(["라."], seconds=lambda i, r: 0.2),
                         lambda: (opened.append(time.monotonic()), new_stream)[1], None,
                         clock=new_clock, poll=POLL, previous=h.session)
        t0 = time.monotonic()
        h.session.stop()
        new.start()
        try:
            self.assertTrue(wait_until(lambda: "session_end" in h.kinds() and opened, 3))
            self.assertLess(opened[0] - t0, 0.5, "새 읽기가 옛 합성 스레드를 기다렸다")
            self.assertEqual(h.states()[-1]["state"], "STOPPED")
            self.assertTrue(h.session.is_alive())   # 합성 스레드는 아직 네트워크에 걸려 있다(좀비 아님 — 곧 끝남)
        finally:
            gate.set()
        self.assertTrue(new.join(5))
        self.assertTrue(h.session.join(5))

    def test_producer_crash_ends_session_instead_of_waiting_forever(self):
        class BoomList(list):
            """합성 스레드가 조각 1 을 볼 때만 터진다(합성 스레드 안의 예상 못 한 버그 흉내)."""
            def __getitem__(self, i):
                if i == 1 and threading.current_thread().name == "tts-producer":
                    raise IndexError("합성 스레드 버그 흉내")
                return list.__getitem__(self, i)
        h = Harness(["가.", "나.", "다."], seconds=lambda i, r: 0.5)
        h.session._blank = BoomList(h.session._blank)
        h.session.start()
        ok = h.session.join(3)
        if not ok:
            h.session.stop()
            h.session.join(3)
        self.assertTrue(ok, "합성 스레드가 죽었는데 재생 스레드가 영원히 기다린다")
        self.assertEqual(runs_of(h.stream.written()), [(0, 0, 5)])
        self.assertEqual(h.kinds()[-1], "session_end")

    def test_stop_does_not_block_while_stream_is_draining(self):
        # 정상 종료의 stream.stop()(남은 버퍼를 다 들려줄 때까지 막힘) 도중에 stop() → Tk 메인이 막히면 안 된다
        class SlowStop(FakeStream):
            def __init__(self, clock):
                super().__init__(clock)
                self.in_stop = threading.Event()

            def stop(self):
                self.in_stop.set()
                time.sleep(0.4)
                super().stop()
        clock = FakeClock()
        stream = SlowStop(clock)
        s = TtsSession("원문", [{"text": "가.", "src_start": 0, "src_end": 2}],
                       FakeSynth(["가."], seconds=lambda i, r: 0.2), lambda: stream, None, clock=clock, poll=POLL)
        s.start()
        self.assertTrue(stream.in_stop.wait(5))
        t0 = time.monotonic()
        s.stop()
        self.assertLess(time.monotonic() - t0, 0.1)
        self.assertTrue(s.join(5))
        self.assertTrue(stream.closed)

    def test_stop_right_after_stream_registration_still_aborts(self):
        # stop() 이 락을 못 잡고 그냥 돌아가도(스트림 등록 중) 재생 스레드가 멈춤 신호를 보고 abort 해야 한다
        clock = FakeClock()
        stream = FakeStream(clock)
        holder = {}

        def open_stream():
            holder["s"].stop()          # 스트림을 돌려주기 직전에 정지 — 등록 전후 경계
            return stream
        s = TtsSession("원문", [{"text": "가.", "src_start": 0, "src_end": 2}],
                       FakeSynth(["가."], seconds=lambda i, r: 5.0), open_stream, None, clock=clock, poll=POLL)
        holder["s"] = s
        s.start()
        self.assertTrue(s.join(3))
        self.assertTrue(stream.aborted and stream.closed)
        self.assertEqual(stream.written(), [])

    def test_thread_start_failure_sends_session_end_and_leaves_no_thread(self):
        h = Harness(["가."], seconds=lambda i, r: 0.2)
        orig = threading.Thread.start

        def bad_start(thread):
            if thread.name == "tts-player":
                raise RuntimeError("can't start new thread (흉내)")
            return orig(thread)
        threading.Thread.start = bad_start
        try:
            with self.assertRaises(RuntimeError):
                h.session.start()
        finally:
            threading.Thread.start = orig
        self.assertEqual(h.kinds()[-1], "session_end")
        self.assertEqual(h.states()[-1]["state"], "STOPPED")
        self.assertTrue(h.session.join(3))            # 시작 못 한 재생 스레드를 join 해도 오류가 나지 않는다
        self.assertTrue(h.session.join_playback(0))   # 다음 읽기가 기다리지 않는다

    def test_no_segments_ends_at_once(self):
        h = Harness([])
        h.session.start()
        self.assertTrue(h.session.join(3))
        self.assertEqual(h.kinds()[0], "session_start")
        self.assertEqual(h.kinds()[-1], "session_end")
        self.assertEqual(h.stream.written(), [])

    def test_all_synthesis_failed_ends_quietly(self):
        h = Harness(["가.", "나.", "다."], fail={0, 1, 2})
        h.run()
        self.assertEqual(h.stream.written(), [])      # 드레인 무음도 흘리지 않는다
        self.assertTrue(h.stream.stopped and not h.stream.aborted)
        self.assertEqual(h.kinds()[-1], "session_end")

    def test_pause_then_stop(self):
        h = Harness(["가.", "나."], seconds=lambda i, r: 1.0,
                    hooks=[(at_block(0, 3), lambda h: h.session.pause())])
        h.session.start()
        self.assertTrue(wait_until(lambda: any(s["state"] == "PAUSED" for s in h.states())))
        h.session.stop()
        self.assertTrue(h.session.join(2))
        self.assertTrue(h.stream.aborted)
        self.assertEqual(h.states()[-1]["state"], "STOPPED")

    def test_move_while_paused_stays_paused_until_resume(self):
        h = Harness(["가.", "나.", "다."], seconds=lambda i, r: 1.0,
                    hooks=[(at_block(0, 3), lambda h: h.session.pause())])
        h.session.start()
        self.assertTrue(wait_until(lambda: any(s["state"] == "PAUSED" for s in h.states())))
        h.session.forward()
        h.clock.advance(1.0)   # 750ms 대기가 지남(일시정지 중엔 쓰기가 없어 가짜 시계가 안 흐르므로 직접 민다)
        self.assertTrue(wait_until(lambda: h.session._audio_idx == 1))
        n = len(h.stream.written())
        time.sleep(0.05)
        self.assertEqual(len(h.stream.written()), n, "일시정지 중인데 이동한 조각을 재생했다")
        self.assertEqual(h.states()[-1]["state"], "PAUSED")
        h.session.resume()
        self.assertTrue(h.session.join(5))
        self.assertEqual(runs_of(h.stream.written())[1:], [(1, 0, 10), (2, 0, 10)])

    def test_rapid_moves_then_stop(self):
        h = Harness(["가.", "나.", "다.", "라."], seconds=lambda i, r: 3.0,
                    hooks=[(at_block(0, 3), lambda h: (h.session.forward(), h.session.forward(), h.session.stop()))])
        h.session.start()
        self.assertTrue(h.session.join(2))
        self.assertTrue(h.stream.aborted)
        self.assertEqual([r[0] for r in runs_of(h.stream.written())], [0])

    def test_rate_change_then_move(self):
        def audio_of(idx, rate, sec):
            return np.full(int(sec * SR), (idx + 1) * 1000 + int(round(rate * 100)), dtype=np.int16)
        h = Harness(["가.", "나.", "다."], seconds=lambda i, r: 3.0, audio_of=audio_of,
                    hooks=[(lambda b, h: len(h.stream.written()) == 3,
                            lambda h: (h.session.set_rate(2.0), h.session.forward()))])
        h.run()
        values = {int(b[0]) for b in h.stream.written() if b.any()}
        self.assertEqual(values, {1100, 2200, 3200})

    def test_volume_change_while_muted_stays_silent(self):
        def audio_of(idx, rate, sec):
            return np.full(int(sec * SR), 10000, dtype=np.int16)
        h = Harness(["가."], seconds=lambda i, r: 1.0, audio_of=audio_of,
                    hooks=[(lambda b, h: len(h.stream.written()) == 2,
                            lambda h: (h.session.set_muted(True), h.session.set_volume(0.3))),
                           (lambda b, h: len(h.stream.written()) == 5, lambda h: h.session.set_muted(False))])
        h.run()
        firsts = [int(b[0]) for b in h.stream.written()[:10]]
        self.assertEqual(firsts, [10000, 10000, 0, 0, 0, 3000, 3000, 3000, 3000, 3000])


# ════════════════════════════════════════════════════════════════════
# whisperer.py 연결부 — import 하지 않는다(트레이·전역 키보드 훅이 뜬다).
# 소스에서 필요한 함수만 AST 로 뽑아 가짜 부품(가짜 합성·가짜 스트림·가짜 바/리더)과 함께 돌린다.
# ════════════════════════════════════════════════════════════════════

_GLUE_FUNCS = ["stop_current_playback", "_make_tts_event_handler", "speak_text", "stop_tts", "_safe_ui",
               "_ensure_reading_ui", "_on_bar_command", "_on_reader_geometry_changed", "_show_reader_window",
               "_hide_reading_ui", "_handle_tts_event", "toggle_reader_window"]
_GLUE_VARS = ["_tts_state_lock"]


class _HookedGlobals(dict):
    """전역 이름 읽기를 가로챌 수 있는 이름공간. exec 로 만든 함수는 이 dict 를 전역으로 쓰고,
    dict 하위 클래스면 CPython 이 LOAD_GLOBAL 때 __getitem__ 을 부른다 → 스레드가 "전역을 읽은 직후" 에 멈춰 세울 수 있다.
    가로채기 함수는 이름공간의 "__hook__" 키에 넣는다(dict.__setitem__ 으로)."""

    def __getitem__(self, key):
        value = dict.__getitem__(self, key)
        hook = dict.get(self, "__hook__")
        if hook is not None:
            hook(key, value)
        return value


def _load_glue(ui_log):
    import ast
    src_path = os.path.join(APP_DIR, "whisperer.py")
    with open(src_path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    variables = [n for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id in _GLUE_VARS for t in n.targets)]
    missing = [f for f in _GLUE_FUNCS if f not in funcs]
    assert not missing, f"whisperer.py 에서 함수를 못 찾음: {missing}"
    module = ast.Module(body=variables + [funcs[f] for f in _GLUE_FUNCS], type_ignores=[])
    code = compile(module, src_path, "exec")

    class Bar:
        height = 48

        def __init__(self, root, on_command, get_msg):
            ui_log.append(("bar.init",))

        def show(self, work_area):
            ui_log.append(("bar.show",))

        def hide(self):
            ui_log.append(("bar.hide",))

        def update(self, st):
            ui_log.append(("bar.update", st["state"]))

    class Reader:
        def __init__(self, root, get_msg, on_geometry_changed=None):
            pass

        def start(self, source_text, segments):
            ui_log.append(("reader.start",))

        def show(self, work_area, bar_height, geometry=None):
            ui_log.append(("reader.show",))

        def highlight(self, idx):
            ui_log.append(("reader.highlight", idx))

        def end(self):
            ui_log.append(("reader.end",))

    streams = []

    def stream_factory(sample_rate=SR):
        def open_stream():
            s = FakeStream(FakeClock(), on_write=lambda b: time.sleep(0.005))   # 실제 장치처럼 천천히(블록당 5ms)
            streams.append(s)
            return s
        return open_stream

    def make_synth(client, tts, voice_name, sample_rate=SR, log=None):
        return lambda text, rate: np.full(int(SR * 10.0), 1000, dtype=np.int16)   # 조각마다 10초 소리(100블록 ≈ 0.5초)

    engine = types.SimpleNamespace(**{k: getattr(tts_engine, k) for k in dir(tts_engine) if not k.startswith("__")})
    engine.sounddevice_stream_factory = stream_factory
    engine.make_google_synthesize = make_synth
    engine.play_start_beep = lambda: None
    ns = _HookedGlobals({
        "__builtins__": __builtins__, "__name__": "whisperer_glue",
        "os": os, "sys": sys, "threading": threading, "time": time, "logging": types.SimpleNamespace(
            error=lambda *a, **k: None, warning=lambda *a, **k: None, info=lambda *a, **k: None),
        "readaloud_text": readaloud_text, "tts_engine": engine, "queue": __import__("queue"),
        "gui_queue": __import__("queue").Queue(), "log_to_console": lambda msg: None, "save_settings": lambda: None,
        "update_tray_menu": lambda: None, "root": object(), "get_msg": lambda k, *a: k,
        "BottomBar": Bar, "ReaderWindow": Reader, "bottom_bar": None, "reader_window": None,
        "google_tts": object(), "google_tts_client": object(), "tts_voice_name": "ko-KR-Chirp3-HD-Callirrhoe",
        "tts_speaking_rate": 1.0, "tts_volume": 1.0, "reader_window_enabled": True, "reader_window_geometry": None,
        "_reading_work_area": None, "_reading_segment_idx": None, "_get_english_words": lambda: None,
        "_current_work_area": lambda: (0, 0, 1920, 1040),
        "tts_playing": False, "tts_paused": False, "tts_stop_event": threading.Event(), "tts_session": None,
        "sd": types.SimpleNamespace(stop=lambda: None), "_streams": streams,
    })
    exec(code, ns)
    return ns


def _pump(ns, until, timeout=5.0):
    """check_gui_queue 대신: gui_queue 의 엔진 알림을 이 스레드(= Tk 메인 역할)에서 처리한다."""
    import queue as _q
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            while True:
                msg = ns["gui_queue"].get_nowait()
                if isinstance(msg, tuple) and msg[0] == "tts_event":
                    ns["_handle_tts_event"](*msg[1:])
                elif msg == "toggle_reader_window":
                    ns["toggle_reader_window"]()
        except _q.Empty:
            pass
        if until():
            return True
        time.sleep(0.002)
    return until()


class TestWhispererGlue(EngineTestBase):
    def tearDown(self):
        ns = getattr(self, "ns", None)
        if ns is not None:
            dict.__setitem__(ns, "__hook__", None)
            s = dict.get(ns, "tts_session")
            if s is not None:
                s.stop()
        super().tearDown()

    def test_old_session_end_cannot_clobber_new_reading(self):
        # 옛 읽기의 재생 스레드가 끝 알림에서 "내가 지금 세션인가" 를 확인한 바로 그 순간에 멈춰 세우고,
        # 그 사이 Tk 메인이 새 읽기를 시작한다. 락이 없으면 옛 스레드가 뒤늦게 tts_playing=False 로 덮어써
        # 새 읽기가 재생 중인데 "재생 안 함" 으로 보인다(플로팅 아이콘 파랑, 단축키가 중지 대신 아이콘 숨김).
        ui = []
        ns = self.ns = _load_glue(ui)
        ns["speak_text"]("첫 번째 글입니다.")
        old = dict.__getitem__(ns, "tts_session")
        self.assertTrue(_pump(ns, lambda: ns["_streams"] and ns["_streams"][0].written()))
        reached = threading.Event()
        proceed = threading.Event()

        def hook(key, value):
            if key != "tts_session" or value is not old or threading.current_thread().name != "tts-player":
                return
            frame = sys._getframe(2)
            if frame.f_code.co_name == "on_event" and frame.f_locals.get("kind") == "session_end":
                dict.__setitem__(ns, "__hook__", None)   # 한 번만
                reached.set()
                proceed.wait(0.5)   # 락이 있으면 Tk 메인이 락에서 기다리므로 여기서 시간 초과로 풀린다
        dict.__setitem__(ns, "__hook__", hook)
        ns["stop_tts"]()                      # 옛 읽기 정지 → 재생 스레드가 끝 알림을 보내다 hook 에서 멈춤
        self.assertTrue(reached.wait(3))
        ns["speak_text"]("두 번째 글입니다.")   # 그 사이 새 읽기(단축키로 새 선택을 읽은 경우)
        proceed.set()
        new = dict.__getitem__(ns, "tts_session")
        self.assertIsNot(new, old)
        self.assertTrue(old.join(3))
        self.assertTrue(new.is_alive())
        self.assertTrue(dict.__getitem__(ns, "tts_playing"), "옛 세션의 끝 알림이 새 읽기의 tts_playing 을 덮어썼다")
        # 옛 세션의 늦은 알림은 새 읽기의 하단 바를 숨기지 않는다
        _pump(ns, lambda: False, timeout=0.1)
        self.assertIs(dict.__getitem__(ns, "tts_session"), new)
        self.assertNotIn(("bar.hide",), ui)
        ns["stop_tts"]()
        self.assertTrue(_pump(ns, lambda: dict.__getitem__(ns, "tts_session") is None))
        self.assertFalse(dict.__getitem__(ns, "tts_playing"))
        self.assertIn(("bar.hide",), ui)
        self.assertTrue(new.join(3))

    def test_new_selection_while_reading_keeps_playing_state(self):
        # 가장 흔한 경우: 읽는 중에 새 글을 선택하고 단축키 → speak_text 가 안에서 옛 읽기를 멈추고 새 세션을 넣는다.
        # 옛 읽기의 끝 알림이 "확인" 을 마친 채 멈춰 있는 동안 speak_text 가 새 세션을 넣으면(대입에 락이 없으면)
        # 옛 알림이 뒤늦게 tts_playing=False 로 덮어쓴다. speak_text 쪽 락이 이것을 막는다.
        ui = []
        ns = self.ns = _load_glue(ui)
        ns["speak_text"]("첫 번째 글입니다.")
        old = dict.__getitem__(ns, "tts_session")
        self.assertTrue(_pump(ns, lambda: ns["_streams"] and ns["_streams"][0].written()))
        reached = threading.Event()
        proceed = threading.Event()

        def hook(key, value):
            if key != "tts_session" or value is not old or threading.current_thread().name != "tts-player":
                return
            frame = sys._getframe(2)
            if frame.f_code.co_name == "on_event" and frame.f_locals.get("kind") == "session_end":
                dict.__setitem__(ns, "__hook__", None)
                reached.set()
                proceed.wait(0.5)
        dict.__setitem__(ns, "__hook__", hook)
        # speak_text 는 옛 읽기를 멈춘(stop_current_playback) 뒤 모니터 작업 영역을 구하고 나서 새 세션을 넣는다.
        # 작업 영역 조회에서 "옛 끝 알림이 hook 에 걸릴 때까지" 기다리게 해 순서를 고정한다.
        dict.__setitem__(ns, "_current_work_area", lambda: (reached.wait(2), (0, 0, 1920, 1040))[1])
        ns["speak_text"]("두 번째 글입니다.")   # 옛 끝 알림이 hook 에서 멈춘 사이 새 세션을 넣으려 한다
        proceed.set()
        self.assertTrue(reached.is_set(), "옛 세션 끝 알림이 제때 오지 않았다")
        new = dict.__getitem__(ns, "tts_session")
        self.assertIsNot(new, old)
        self.assertTrue(old.join(3))
        self.assertTrue(new.is_alive())
        self.assertTrue(dict.__getitem__(ns, "tts_playing"), "옛 세션의 끝 알림이 새 읽기의 tts_playing 을 덮어썼다")
        ns["stop_tts"]()
        self.assertTrue(_pump(ns, lambda: dict.__getitem__(ns, "tts_session") is None))
        self.assertTrue(new.join(3))

    def test_normal_reading_drives_bar_and_reader(self):
        ui = []
        ns = self.ns = _load_glue(ui)
        # 60바이트 이하 짧은 줄은 다음 줄과 합쳐지므로(확장 speech.js:444) 두 조각이 되게 길게 쓴다
        ns["speak_text"]("첫 번째 줄은 이렇게 조금 길게 써서 육십 바이트를 넘깁니다.\n"
                         "두 번째 줄도 마찬가지로 조금 길게 써서 합쳐지지 않게 합니다.")
        self.assertTrue(dict.__getitem__(ns, "tts_playing"))
        self.assertTrue(_pump(ns, lambda: dict.__getitem__(ns, "tts_session") is None, timeout=10))
        self.assertFalse(dict.__getitem__(ns, "tts_playing"))
        names = [c[0] for c in ui]
        self.assertLess(names.index("bar.show"), names.index("bar.update"))
        self.assertEqual(names[-2:], ["bar.hide", "reader.end"])
        self.assertEqual([c[1] for c in ui if c[0] == "reader.highlight"], [0, 1])

    def test_thread_start_failure_does_not_leave_playing_state(self):
        ui = []
        ns = self.ns = _load_glue(ui)
        orig = threading.Thread.start

        def bad_start(thread):
            if thread.name == "tts-player":
                raise RuntimeError("can't start new thread (흉내)")
            return orig(thread)
        threading.Thread.start = bad_start
        try:
            ns["speak_text"]("글입니다.")      # 예외를 밖으로 올리지 않는다(로그만)
        finally:
            threading.Thread.start = orig
        self.assertFalse(dict.__getitem__(ns, "tts_playing"))
        self.assertTrue(_pump(ns, lambda: dict.__getitem__(ns, "tts_session") is None))
        self.assertIn(("bar.hide",), ui)

    def test_bar_close_during_hotkey_stop(self):
        # 단축키 중지(stop_tts)와 하단 바 닫기(X → "stop")가 겹쳐도 한 번만 끝나고 상태가 맞다
        ui = []
        ns = self.ns = _load_glue(ui)
        ns["speak_text"]("글입니다.\n둘째 줄.")
        self.assertTrue(_pump(ns, lambda: ("bar.show",) in ui))
        session = dict.__getitem__(ns, "tts_session")
        ns["stop_tts"]()
        ns["_on_bar_command"]("stop")
        self.assertTrue(_pump(ns, lambda: dict.__getitem__(ns, "tts_session") is None))
        self.assertTrue(session.join(3))
        self.assertFalse(dict.__getitem__(ns, "tts_playing"))
        self.assertEqual(ui[-2:], [("bar.hide",), ("reader.end",)])


class TestEnglishWordsData(unittest.TestCase):
    """확장의 js/english-words.js 복사본이 앱에 들어 있고, 저작권 고지가 남아 있고, exe 에도 들어가는가."""

    def test_word_list_file(self):
        path = os.path.join(APP_DIR, "data", "english-words.js")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            head = f.read(3000)
        self.assertIn("Copyright 2000-2018 by Kevin Atkinson", head)
        words = readaloud_text.load_english_words(path)
        self.assertGreater(len(words), 80000)
        self.assertIn("read", words)
        with open(os.path.join(APP_DIR, "BluemingReadAloud.spec"), encoding="utf-8") as f:
            self.assertIn("english-words.js", f.read())


if __name__ == "__main__":
    unittest.main()
