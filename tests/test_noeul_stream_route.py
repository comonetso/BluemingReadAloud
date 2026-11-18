"""크롬 확장 흘려받기 노을(2026-11-18 확장 요청 20321079) 시험.

실제 OpenAI 는 부르지 않는다. 만들기는 가짜(make_stream 이 tts_engine.GrowingAudio 를 돌려주고 시험이 소리를 넣는다)로,
- 48kHz 두 채널 늘리기(StreamWidener)·길이 모르는 WAV 머리
- 연결 자리 순서표(_Slots — 먼저 맡긴 문단·앞 조각부터)와 read_noeul 이 줄에서 빠지기
- tts_engine stream 이 lang·순서표를 조각마다 넘기고 실패에 code 를 붙이는지
- ExtensionStreams 의 시작 전 모음·끝까지 흘림·실패·끊김·취소·보관 시간
- 실제 포트의 UsageReceiver 로 네 길(+ OPTIONS)의 응답 모양·Origin·Access-Control-Allow-Origin
"""

import http.client
import json
import os
import socket
import struct
import sys
import threading
import time
import unittest
from array import array

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import noeul_live  # noqa: E402
import tts_engine  # noqa: E402
import tts_usage  # noqa: E402

ORIGIN = "chrome-extension://abcdefghijklmnop"
KEY = "sk-test-stream-key"


def pcm(*values):
    return array("h", values).tobytes()


def widened(samples):
    w = noeul_live.StreamWidener()
    return w.feed(array("h", samples)) + w.flush()


def wait_until(check, limit=3.0):
    end = time.monotonic() + limit
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.01)
    return check()


class FakeStreams:
    """make_stream 대신 — 문단마다 GrowingAudio 를 만들어 돌려주고 받은 인자를 적는다."""

    def __init__(self, start_sec=0.0):
        self.start_sec = start_sec
        self.calls, self.audios = [], []

    def __call__(self, key):
        def stream(text, rate, *, cancelled, wake, lang, group):
            audio = tts_engine.GrowingAudio(self.start_sec, cancelled=cancelled, wake=wake)
            self.calls.append({"key": key, "text": text, "rate": rate, "lang": lang, "group": group})
            self.audios.append(audio)
            return audio
        return stream


class Sink:
    def __init__(self, fail=False):
        self.began = threading.Event()
        self.data = bytearray()
        self.fail = fail

    def begin(self):
        self.began.set()

    def write(self, data):
        if self.fail:
            raise BrokenPipeError()
        self.data += data


def failed(code):
    error = tts_engine.SegmentFailed(noeul_live.MESSAGES.get(code, code))
    error.code = code
    return error


class TestWidenAndHeader(unittest.TestCase):
    def test_widen_values(self):
        out = array("h")
        out.frombytes(widened([0, 100, -100]))
        # 0 · (0+100)/2 · 100 · (100-100)/2 · -100(끝 — 다음 표본이 없어 그대로 두 번), 표본마다 두 채널
        self.assertEqual(list(out), [0, 0, 50, 50, 100, 100, 0, 0, -100, -100, -100, -100])

    def test_widen_same_bytes_however_split(self):
        import random
        rnd = random.Random(7)
        samples = [rnd.randint(-32768, 32767) for _ in range(997)]
        whole = widened(samples)
        for cut in (1, 2, 3, 50, 496):
            w = noeul_live.StreamWidener()
            parts = b"".join(w.feed(array("h", samples[i:i + cut])) for i in range(0, len(samples), cut))
            self.assertEqual(parts + w.flush(), whole, cut)
        self.assertEqual(len(whole), len(samples) * 2 * 2 * 2)   # 두 배 표본 · 두 채널 · 2바이트

    def test_widen_extremes_do_not_wrap(self):
        out = array("h")
        out.frombytes(widened([32767, 32767, -32768, -32768]))
        self.assertEqual(max(out), 32767)
        self.assertEqual(min(out), -32768)

    def test_header(self):
        head = noeul_live.wav_stream_header()
        self.assertEqual(len(head), 44)
        self.assertEqual(head[:4], b"RIFF")
        self.assertEqual(head[8:16], b"WAVEfmt ")
        self.assertEqual(struct.unpack("<I", head[4:8])[0], 0xFFFFFFFF)
        self.assertEqual(struct.unpack("<I", head[40:44])[0], 0xFFFFFFFF)
        fmt = struct.unpack("<IHHIIHH", head[16:36])
        self.assertEqual(fmt, (16, 1, 2, 48000, 192000, 4, 16))
        self.assertEqual(head[36:40], b"data")


class TestSlots(unittest.TestCase):
    def test_priority_order(self):
        slots = noeul_live._Slots(1)
        self.assertTrue(slots.acquire())
        order = []
        tickets = [slots.ticket(p) for p in [(2, 0), (1, 5), (1, 0)]]

        def run(ticket):
            self.assertTrue(slots.wait(ticket, 5))
            order.append(ticket[0])
            time.sleep(0.02)
            slots.release()

        threads = [threading.Thread(target=run, args=(t,)) for t in tickets]
        for t in threads:
            t.start()
        time.sleep(0.05)
        self.assertEqual(order, [])        # 자리가 없으니 아무도 못 얻는다
        slots.release()
        for t in threads:
            t.join(5)
        self.assertEqual(order, [(1, 0), (1, 5), (2, 0)])

    def test_drop_lets_next_in(self):
        slots = noeul_live._Slots(1)
        first, second = slots.ticket((1, 0)), slots.ticket((2, 0))
        self.assertFalse(slots.wait(second, 0.05))   # 앞 순서표가 줄에 있다
        slots.drop(first)
        self.assertTrue(slots.wait(second, 0.5))
        slots.release()

    def test_semaphore_promise(self):
        slots = noeul_live._Slots(2)
        self.assertTrue(slots.acquire(blocking=False))
        self.assertTrue(slots.acquire(blocking=False))
        self.assertFalse(slots.acquire(blocking=False))
        self.assertEqual(slots._queue, [])           # 못 얻으면 줄에서 빠진다
        slots.release()
        slots.release()
        with self.assertRaises(ValueError):
            slots.release()

    def test_read_noeul_leaves_queue_when_cancelled(self):
        held = 0
        while noeul_live._slots.acquire(blocking=False):
            held += 1
        try:
            answers = iter([False] + [True] * 100)
            with self.assertRaises(noeul_live.NoeulError) as ctx:
                noeul_live.read_noeul("안녕하세요.", "k", opener=lambda *a: self.fail("열면 안 된다"),
                                      cancelled=lambda: next(answers), priority=(1, 0))
            self.assertEqual(ctx.exception.code, "cancelled")
            self.assertEqual(noeul_live._slots._queue, [])
        finally:
            for _ in range(held):
                noeul_live._slots.release()


class TestEngineStream(unittest.TestCase):
    TEXT = "첫 문장은 조금 깁니다, 쉼표 뒤에도 이어집니다. 둘째 문장입니다. 셋째 문장도 있습니다. 넷째 문장으로 끝납니다."

    def run_stream(self, reader, **kw):
        synth = tts_engine.make_noeul_synthesize("k", reader=reader)
        audio = synth.stream(self.TEXT, 1.0, cancelled=lambda: False, wake=lambda: None, **kw)
        self.assertTrue(wait_until(lambda: audio.done))
        return audio

    def test_lang_and_priority_per_piece(self):
        seen, lock = [], threading.Lock()

        def reader(text, key, lang, *, log, cancelled, sink, **kw):
            with lock:
                seen.append((lang, kw.get("priority", "없음")))
            sink(pcm(1, 2, 3))
            return b""

        audio = self.run_stream(reader, lang="en", group=7)
        self.assertEqual({lang for lang, _ in seen}, {"en"})
        self.assertEqual(sorted(p for _, p in seen), [(7, i) for i in range(len(audio.pieces))])

    def test_no_group_no_priority(self):
        seen = []

        def reader(text, key, lang, *, log, cancelled, sink, **kw):
            seen.append((lang, "priority" in kw))
            return b""

        self.run_stream(reader)
        self.assertTrue(seen)
        self.assertEqual({s for s in seen}, {("ko", False)})

    def test_failure_carries_code(self):
        def unauthorized(*a, **kw):
            raise noeul_live.NoeulError("unauthorized")

        def broken(*a, **kw):
            raise ValueError("뜻밖")

        self.assertEqual(self.run_stream(unauthorized).error.code, "unauthorized")
        self.assertEqual(self.run_stream(broken).error.code, "internal")


class StreamsCase(unittest.TestCase):
    start_sec = 0.0

    def setUp(self):
        self.key = KEY
        self.logs = []
        self.now = [100.0]
        self.fake = FakeStreams(self.start_sec)
        self.streams = noeul_live.ExtensionStreams(key_reader=lambda: self.key, make_stream=self.fake,
                                                   log=self.logs.append, clock=lambda: self.now[0])

    def make(self, **body):
        payload = {"v": 1, "text": "안녕하세요. 노을입니다.", "lang": "ko", "rate": 1.5}
        payload.update(body)
        status, answer, headers = self.streams.create(payload)
        self.assertEqual(status, 200, answer)
        return answer["id"], self.fake.audios[-1]

    def open(self, job_id, sink, closed=lambda: False):
        box = {}
        thread = threading.Thread(target=lambda: box.update(r=self.streams.stream(job_id, closed, sink.begin,
                                                                                  sink.write)))
        thread.start()
        return thread, box


class TestCreate(StreamsCase):
    def test_checks(self):
        bad = [({"v": 2}, "v"), ({"v": True}, "v"), ({"text": "  "}, "text"), ({"text": 3}, "text"),
               ({"lang": "xx"}, "lang"), ({"rate": "1"}, "rate"), ({"rate": True}, "rate"), ({"rate": 0}, "rate"),
               ({"rate": -1}, "rate"), ({"rate": float("inf")}, "rate")]
        for change, field in bad:
            payload = {"v": 1, "text": "안녕", "lang": "ko", "rate": 1}
            payload.update(change)
            status, answer, _ = self.streams.create(payload)
            self.assertEqual((status, answer["code"]), (400, "bad_request"), change)
            self.assertIn(field, answer["error"])
        self.assertEqual(self.fake.calls, [])

    def test_no_key(self):
        self.key = ""
        status, answer, _ = self.streams.create({"v": 1, "text": "안녕", "lang": "ko"})
        self.assertEqual((status, answer["code"]), (503, "no_key"))
        self.assertEqual(answer["error"], noeul_live.MESSAGES["no_key"])

    def test_ok_and_args(self):
        status, answer, headers = self.streams.create({"v": 1, "text": "Hello.", "lang": "en"})
        self.assertEqual(status, 200)
        self.assertTrue(answer["ok"])
        self.assertGreaterEqual(len(answer["id"]), 20)
        self.assertEqual(headers, {"X-Usage-Key": noeul_live.usage_key_id(KEY)})
        call = self.fake.calls[0]
        self.assertEqual((call["key"], call["text"], call["lang"], call["rate"]), (KEY, "Hello.", "en", 1.0))
        second = self.streams.create({"v": 1, "text": "Again.", "lang": "en"})[1]["id"]
        self.assertNotEqual(second, answer["id"])
        self.assertLess(self.fake.calls[0]["group"], self.fake.calls[1]["group"])   # 먼저 맡긴 문단이 앞 순서표


class TestGatherThenStream(StreamsCase):
    start_sec = 0.2      # 시작 전 모음 4800 표본

    def test_waits_for_start_then_streams_to_end(self):
        job_id, audio = self.make()
        audio.append(pcm(*([5] * 2400)))
        sink = Sink()
        thread, box = self.open(job_id, sink)
        time.sleep(0.3)
        self.assertFalse(sink.began.is_set())         # 아직 모음이 모자란다
        audio.append(pcm(*([7] * 2400)))
        self.assertTrue(sink.began.wait(2))
        audio.append(pcm(1, 2, 3))
        self.assertEqual(self.streams.result(job_id)[1], {"ok": True, "done": False})
        audio.finish()
        thread.join(3)
        self.assertIsNone(box["r"])
        self.assertEqual(bytes(sink.data), noeul_live.wav_stream_header() + widened([5] * 2400 + [7] * 2400 + [1, 2, 3]))
        self.assertEqual(self.streams.result(job_id), (200, {"ok": True, "done": True}))
        self.assertTrue(any("크롬 확장 흘림" in line and "첫 소리까지" in line for line in self.logs))
        status, answer = self.streams.stream(job_id, lambda: False, Sink().begin, Sink().write)   # 한 id 한 번만
        self.assertEqual((status, answer["code"]), (404, "not_found"))


class TestStreamEnds(StreamsCase):
    def test_failure_before_stream(self):
        job_id, audio = self.make()
        audio.finish(failed("unauthorized"))
        status, answer = self.streams.stream(job_id, lambda: False, Sink().begin, Sink().write)
        self.assertEqual((status, answer["code"]), (401, "unauthorized"))
        self.assertEqual(self.streams.result(job_id)[1]["code"], "unauthorized")

    def test_failure_after_some_sound(self):
        job_id, audio = self.make()
        audio.append(pcm(1, 2, 3, 4))
        sink = Sink()
        thread, box = self.open(job_id, sink)
        self.assertTrue(sink.began.wait(2))
        audio.finish(failed("server"))                 # 엔진 순서: 실패를 적고 나머지 연결을 닫는다
        audio.cancel()
        thread.join(3)
        self.assertEqual(bytes(sink.data), noeul_live.wav_stream_header() + widened([1, 2, 3, 4]))
        self.assertEqual(self.streams.result(job_id)[1],
                         {"ok": False, "code": "server", "error": noeul_live.MESSAGES["server"]})

    def test_closed_while_streaming(self):
        job_id, audio = self.make()
        audio.append(pcm(1, 2))
        gone = threading.Event()
        sink = Sink()
        thread, box = self.open(job_id, sink, closed=gone.is_set)
        self.assertTrue(sink.began.wait(2))
        gone.set()
        thread.join(3)
        self.assertTrue(audio.cancelled)
        self.assertEqual(self.streams.result(job_id)[1]["code"], "cancelled")

    def test_write_error(self):
        job_id, audio = self.make()
        audio.append(pcm(1, 2))
        self.assertIsNone(self.streams.stream(job_id, lambda: False, Sink().begin, Sink(fail=True).write))
        self.assertTrue(audio.cancelled)
        self.assertEqual(self.streams.result(job_id)[1]["code"], "cancelled")

    def test_delete_before_open(self):
        job_id, audio = self.make()
        self.assertEqual(self.streams.delete(job_id), (200, {"ok": True}))
        self.assertTrue(audio.cancelled)
        self.assertEqual(self.streams.result(job_id)[1]["code"], "cancelled")
        status, answer = self.streams.stream(job_id, lambda: False, Sink().begin, Sink().write)
        self.assertEqual((status, answer["code"]), (499, "cancelled"))

    def test_delete_while_streaming(self):
        job_id, audio = self.make()
        audio.append(pcm(1, 2))
        sink = Sink()
        thread, box = self.open(job_id, sink)
        self.assertTrue(sink.began.wait(2))
        self.streams.delete(job_id)
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.streams.result(job_id)[1]["code"], "cancelled")

    def test_unknown_ids(self):
        self.assertEqual(self.streams.result("nope")[0], 404)
        self.assertEqual(self.streams.delete("nope")[0], 404)
        self.assertEqual(self.streams.stream("nope", lambda: False, Sink().begin, Sink().write)[0], 404)

    def test_keep_time(self):
        job_id, audio = self.make()
        self.now[0] += noeul_live.STREAM_KEEP_S - 1
        self.assertEqual(self.streams.result(job_id)[1], {"ok": True, "done": False})
        self.now[0] += 1                                # 맡긴 뒤 10분 — 안 열렸으니 취소
        self.assertEqual(self.streams.result(job_id)[1]["code"], "expired")
        self.assertTrue(audio.cancelled)
        status, answer = self.streams.stream(job_id, lambda: False, Sink().begin, Sink().write)
        self.assertEqual((status, answer["code"]), (410, "expired"))
        self.now[0] += noeul_live.STREAM_KEEP_S         # 끝난 뒤 10분 — 장부에서 지운다
        self.assertEqual(self.streams.result(job_id)[0], 404)


class TestRoutes(unittest.TestCase):
    def setUp(self):
        self.fake = FakeStreams()
        self.logs = []
        self.streams = noeul_live.ExtensionStreams(key_reader=lambda: KEY, make_stream=self.fake, log=self.logs.append)
        self.receiver = tts_usage.UsageReceiver(None, port=0, log=self.logs.append, noeul_stream=self.streams)
        self.assertTrue(self.receiver.start())

    def tearDown(self):
        self.receiver.stop()

    def call(self, method, path, body=None, origin=ORIGIN, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.receiver.port, timeout=5)
        sent = dict(headers or {})
        if origin:
            sent["Origin"] = origin
        raw = None
        if body is not None:
            raw = json.dumps(body).encode("utf-8")
            sent["Content-Type"] = "application/json"
        conn.request(method, path, body=raw, headers=sent)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, data

    def post(self, **body):
        payload = {"v": 1, "text": "안녕하세요.", "lang": "ko", "rate": 1}
        payload.update(body)
        return self.call("POST", "/v1/tts/noeul/stream", payload)

    def test_post_answer(self):
        status, headers, data = self.post()
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["ok"])
        self.assertEqual(headers["x-usage-key"], noeul_live.usage_key_id(KEY))
        self.assertEqual(headers["access-control-allow-origin"], ORIGIN)
        self.assertIn("X-Usage-Key", headers["access-control-expose-headers"])

    def test_post_refusals(self):
        status, headers, data = self.call("POST", "/v1/tts/noeul/stream", {"v": 1, "text": "안녕"}, origin=None)
        self.assertEqual((status, json.loads(data)["code"]), (403, "origin"))
        status, headers, data = self.post(text="")
        self.assertEqual((status, json.loads(data)["code"]), (400, "bad_request"))
        self.assertEqual(headers["access-control-allow-origin"], ORIGIN)   # 거절 본문도 확장이 읽게
        self.assertEqual(self.fake.calls, [])

    def test_stream_result_and_once(self):
        job_id = json.loads(self.post()[2])["id"]
        audio = self.fake.audios[0]
        audio.append(pcm(10, 20, 30))
        audio.finish()
        status, headers, data = self.call("GET", f"/v1/tts/noeul/stream/{job_id}", headers={"Range": "bytes=0-"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "audio/wav")
        self.assertEqual(headers["access-control-allow-origin"], ORIGIN)
        self.assertNotIn("content-length", headers)
        self.assertEqual(data, noeul_live.wav_stream_header() + widened([10, 20, 30]))
        status, _, data = self.call("GET", f"/v1/tts/noeul/stream/{job_id}/result")
        self.assertEqual((status, json.loads(data)), (200, {"ok": True, "done": True}))
        status, _, data = self.call("GET", f"/v1/tts/noeul/stream/{job_id}")
        self.assertEqual((status, json.loads(data)["code"]), (404, "not_found"))

    def test_stream_without_origin(self):
        # 확장 오디오 요소의 GET 엔 Origin 이 안 붙는다(정정 요청 46919744 실측) — id 로 받는다
        job_id = json.loads(self.post()[2])["id"]
        self.fake.audios[0].append(pcm(1, 2))
        self.fake.audios[0].finish()
        status, headers, data = self.call("GET", f"/v1/tts/noeul/stream/{job_id}", origin=None,
                                          headers={"Range": "bytes=0-"})
        self.assertEqual(status, 200)
        self.assertNotIn("access-control-allow-origin", headers)
        self.assertEqual(data, noeul_live.wav_stream_header() + widened([1, 2]))
        status, _, data = self.call("GET", f"/v1/tts/noeul/stream/{job_id}/result", origin=None)
        self.assertEqual((status, json.loads(data)), (200, {"ok": True, "done": True}))
        other = json.loads(self.post()[2])["id"]
        status, _, data = self.call("DELETE", f"/v1/tts/noeul/stream/{other}", origin="null")
        self.assertEqual((status, json.loads(data)), (200, {"ok": True}))

    def test_web_origin_refused(self):
        job_id = json.loads(self.post()[2])["id"]
        for method, path in [("GET", f"/v1/tts/noeul/stream/{job_id}"), ("GET", f"/v1/tts/noeul/stream/{job_id}/result"),
                             ("DELETE", f"/v1/tts/noeul/stream/{job_id}")]:
            status, _, data = self.call(method, path, origin="https://example.com")
            self.assertEqual((status, json.loads(data)["code"]), (403, "origin"), (method, path))
        self.assertFalse(self.fake.audios[0].cancelled)
        status, _, data = self.call("GET", f"/v1/tts/noeul/stream/{job_id}/result")   # 거절된 GET 은 열지 않았다
        self.assertEqual(json.loads(data), {"ok": True, "done": False})
        status, _, data = self.call("POST", "/v1/tts/noeul/stream", {"v": 1, "text": "안녕"}, origin="null")
        self.assertEqual((status, json.loads(data)["code"]), (403, "origin"))           # 맡기기는 확장 출처만

    def test_delete_and_options(self):
        job_id = json.loads(self.post()[2])["id"]
        status, headers, data = self.call("DELETE", f"/v1/tts/noeul/stream/{job_id}")
        self.assertEqual((status, json.loads(data)), (200, {"ok": True}))
        self.assertEqual(headers["access-control-allow-origin"], ORIGIN)
        self.assertTrue(self.fake.audios[0].cancelled)
        self.assertEqual(self.call("DELETE", "/v1/tts/noeul/stream/nope")[0], 404)
        status, headers, _ = self.call("OPTIONS", "/v1/tts/noeul/stream")
        self.assertEqual(status, 204)
        self.assertIn("DELETE", headers["access-control-allow-methods"])
        self.assertEqual(self.call("OPTIONS", "/v1/tts/noeul/stream", origin=None)[0], 404)

    def test_client_close_cancels(self):
        job_id = json.loads(self.post()[2])["id"]
        audio = self.fake.audios[0]
        audio.append(pcm(*([3] * 100)))
        sock = socket.create_connection(("127.0.0.1", self.receiver.port), timeout=5)
        sock.sendall((f"GET /v1/tts/noeul/stream/{job_id} HTTP/1.1\r\nHost: 127.0.0.1\r\nOrigin: {ORIGIN}\r\n"
                      "Range: bytes=0-\r\n\r\n").encode("ascii"))
        self.assertIn(b"200", sock.recv(64))
        sock.close()                                    # 확장이 멈춤·건너뛰기로 src 를 지움
        self.assertTrue(wait_until(lambda: audio.cancelled, 2.0))
        self.assertTrue(wait_until(lambda: self.streams.result(job_id)[1].get("code") == "cancelled", 2.0))


if __name__ == "__main__":
    unittest.main()
