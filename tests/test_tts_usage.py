# -*- coding: utf-8 -*-
"""tts_usage 테스트 — 결제 달·세기·확장 기록·Paseo 파일·합계·받는 창구(실제 127.0.0.1 임의 포트).

기록 파일은 임시 폴더에만 쓴다(%APPDATA% 의 진짜 파일은 건드리지 않는다). Google 호출 없음.
"""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tts_usage  # noqa: E402
from messages import messages  # noqa: E402

UTC = timezone.utc


def utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class TestBillingMonth(unittest.TestCase):
    # 기대값 = Paseo billingMonth 와 같은 계산(node Intl en-CA, America/Los_Angeles)으로 2026-11-01 에 뽑은 값
    INTL_CASES = [
        ["2026-11-01T06:59:59Z", "2026-10"], ["2026-11-01T07:00:00Z", "2026-11"],
        ["2026-12-01T07:59:59Z", "2026-11"], ["2026-12-01T08:00:00Z", "2026-12"],
        ["2027-01-01T07:59:59Z", "2026-12"], ["2027-01-01T08:00:00Z", "2027-01"],
        ["2027-03-01T07:59:59Z", "2027-02"], ["2027-03-01T08:00:00Z", "2027-03"],
        ["2027-04-01T06:59:59Z", "2027-03"], ["2027-04-01T07:00:00Z", "2027-04"],
        ["2026-03-08T09:59:59Z", "2026-03"], ["2026-03-08T10:00:00Z", "2026-03"],
        ["2024-11-01T06:59:59Z", "2024-10"], ["2024-11-01T07:00:00Z", "2024-11"],
        ["2025-11-01T06:59:59Z", "2025-10"], ["2025-11-01T07:00:00Z", "2025-11"],
        ["2026-10-01T06:59:59Z", "2026-09"], ["2026-10-01T07:00:00Z", "2026-10"],
        ["2028-03-01T07:59:59Z", "2028-02"], ["2028-03-01T08:00:00Z", "2028-03"],
        ["2031-11-01T06:59:59Z", "2031-10"], ["2031-11-01T07:00:00Z", "2031-11"],
    ]

    def test_matches_intl(self):
        for when, month in self.INTL_CASES:
            self.assertEqual(tts_usage.billing_month(utc(when)), month, when)

    def test_naive_and_other_zones(self):
        self.assertEqual(tts_usage.billing_month(datetime(2026, 11, 1, 7, 0)), "2026-11")   # 시간대 없음 = UTC
        kst = timezone(__import__("datetime").timedelta(hours=9))
        self.assertEqual(tts_usage.billing_month(datetime(2026, 11, 1, 15, 59, tzinfo=kst)), "2026-10")
        self.assertEqual(tts_usage.billing_month(datetime(2026, 11, 1, 16, 0, tzinfo=kst)), "2026-11")

    def test_month_start(self):
        self.assertEqual(tts_usage.month_start_utc("2026-11"), utc("2026-11-01T07:00:00Z"))   # 그날 02:00 까지 서머타임
        self.assertEqual(tts_usage.month_start_utc("2026-12"), utc("2026-12-01T08:00:00Z"))
        self.assertEqual(tts_usage.month_start_utc("2027-03"), utc("2027-03-01T08:00:00Z"))
        self.assertEqual(tts_usage.month_start_utc("2027-04"), utc("2027-04-01T07:00:00Z"))
        for bad in ("2026-13", "2026-1", "x", None):
            self.assertIsNone(tts_usage.month_start_utc(bad))
        self.assertEqual(tts_usage.next_month("2026-12"), "2027-01")
        self.assertEqual(tts_usage.next_month("2026-11"), "2026-12")


class TestVoiceLabel(unittest.TestCase):
    def texts(self, lang):
        return messages["voice_price"][lang], messages["voice_usage"][lang]

    def test_kind_and_short_name(self):
        self.assertEqual(tts_usage.usage_kind("ko-KR-Chirp3-HD-Zephyr"), "chirp3hd")
        self.assertEqual(tts_usage.usage_kind("ko-KR-Wavenet-A"), "wavenet")
        self.assertEqual(tts_usage.usage_kind("ko-KR-Neural2-A"), "neural2")
        self.assertEqual(tts_usage.usage_kind("ko-KR-Standard-B"), "standard")
        self.assertEqual(tts_usage.usage_kind("이상한이름"), "unknown")
        self.assertEqual(tts_usage.short_voice_name("ko-KR-Chirp3-HD-Zephyr"), "Zephyr")
        self.assertEqual(tts_usage.short_voice_name("ko-KR-Wavenet-A"), "Wavenet-A")
        self.assertEqual(tts_usage.short_voice_name("ko-KR-Neural2-A"), "Neural2-A")

    def test_label_like_paseo(self):
        # Paseo: "Zephyr · Chirp 3 HD · 100만 자 30달러 (이번 달 Paseo 12,345자)" — 괄호 안 이름만 이 앱
        price, usage = self.texts("ko")
        self.assertEqual(tts_usage.voice_label("ko-KR-Chirp3-HD-Zephyr", 12345, price, usage),
                         "Zephyr · Chirp 3 HD · 100만 자 30달러 (이번 달 PC 앱 12,345자)")
        self.assertEqual(tts_usage.voice_label("ko-KR-Wavenet-A", 0, price, usage),
                         "Wavenet-A · WaveNet · 100만 자 4달러 (이번 달 PC 앱 0자)")
        self.assertEqual(tts_usage.voice_label("ko-KR-Wavenet-B", None, price, usage),
                         "Wavenet-B · WaveNet · 100만 자 4달러")
        self.assertEqual(tts_usage.voice_label("ko-KR-Neural2-A", 5, price, usage),
                         "Neural2-A · Neural2 (이번 달 PC 앱 5자)")       # 값을 모르는 종류는 값 칸 없음
        price, usage = self.texts("en")
        self.assertEqual(tts_usage.voice_label("ko-KR-Chirp3-HD-Kore", 1234567, price, usage),
                         "Kore · Chirp 3 HD · $30 per 1M chars (this month, PC app 1,234,567 chars)")

    def test_group_digits(self):
        self.assertEqual(tts_usage.group_digits(0), "0")
        self.assertEqual(tts_usage.group_digits(999), "999")
        self.assertEqual(tts_usage.group_digits(1000), "1,000")
        self.assertEqual(tts_usage.group_digits(12345.6), "12,346")


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def path(self, name):
        return os.path.join(self.dir, "sub", name)


class TestUsageCounter(TempDirCase):
    NOV = utc("2026-11-02T00:00:00Z")

    def read(self, name="tts-usage.json"):
        with open(self.path(name), encoding="utf-8") as f:
            return json.load(f)

    def test_counts_code_points_like_paseo(self):
        c = tts_usage.UsageCounter(self.path("tts-usage.json"))
        self.assertTrue(c.count("chirp3hd", "가나 다\n😀", now=self.NOV))   # 공백·줄바꿈 포함, 이모지 1자 = 6
        self.assertTrue(c.count("chirp3hd", "abc", now=self.NOV))
        self.assertTrue(c.count("wavenet", "가", now=self.NOV))
        self.assertEqual(self.read(), {"v": 1, "months": {"2026-11": {"chirp3hd": 9, "wavenet": 1}}})
        self.assertEqual(c.month_counts("2026-11"), {"chirp3hd": 9, "wavenet": 1})
        self.assertEqual(c.month_counts("2026-10"), {})
        self.assertFalse(os.path.exists(self.path("tts-usage.json") + ".tmp"))

    def test_month_boundary_and_keep_13(self):
        c = tts_usage.UsageCounter(self.path("tts-usage.json"))
        c.count("chirp3hd", "가", now=utc("2026-11-01T06:59:59Z"))
        c.count("chirp3hd", "나", now=utc("2026-11-01T07:00:00Z"))
        self.assertEqual(self.read()["months"], {"2026-10": {"chirp3hd": 1}, "2026-11": {"chirp3hd": 1}})
        for i in range(14):   # 2027-01 … 2028-02
            year, mon = 2027 + i // 12, i % 12 + 1
            c.count("wavenet", "x", now=datetime(year, mon, 15, tzinfo=UTC))
        months = sorted(self.read()["months"])
        self.assertEqual(len(months), 13)
        self.assertEqual(months[0], "2027-02")

    def test_broken_file_starts_over_and_empty_text_noop(self):
        os.makedirs(os.path.dirname(self.path("tts-usage.json")))
        with open(self.path("tts-usage.json"), "w", encoding="utf-8") as f:
            f.write("{깨짐")
        c = tts_usage.UsageCounter(self.path("tts-usage.json"))
        self.assertTrue(c.count("chirp3hd", "", now=self.NOV))
        self.assertTrue(c.count("chirp3hd", "가나", now=self.NOV))
        self.assertEqual(self.read(), {"v": 1, "months": {"2026-11": {"chirp3hd": 2}}})

    def test_threads_do_not_lose_counts(self):
        c = tts_usage.UsageCounter(self.path("tts-usage.json"))
        threads = [threading.Thread(target=lambda: [c.count("chirp3hd", "가나다", now=self.NOV) for _ in range(10)])
                   for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(c.month_counts("2026-11"), {"chirp3hd": 150})

    def test_write_failure_returns_false(self):
        logs = []
        blocker = os.path.join(self.dir, "file")
        with open(blocker, "w") as f:
            f.write("x")
        c = tts_usage.UsageCounter(os.path.join(blocker, "tts-usage.json"), log=logs.append)   # 파일 아래 폴더 = 못 씀
        self.assertFalse(c.count("chirp3hd", "가", now=self.NOV))
        self.assertTrue(logs and logs[0].startswith("[사용량]"))


class TestExtensionReports(TempDirCase):
    NOV = utc("2026-11-02T00:00:00Z")

    def reports(self):
        return tts_usage.ExtensionReports(self.path("tts-usage-extension.json"))

    def payload(self, source="abcdefgh", label="Aside", months=None):
        return {"v": 1, "source": source, "label": label,
                "months": months if months is not None else {"2026-11": {"chirp3hd": 10, "wavenet": 2}}}

    def test_accept_replaces_not_adds(self):
        r = self.reports()
        self.assertEqual(r.accept(self.payload(), now=self.NOV), (True, "abcdefgh"))
        self.assertEqual(r.accept(self.payload(months={"2026-11": {"chirp3hd": 15}}), now=self.NOV), (True, "abcdefgh"))
        rows = r.month_by_source("2026-11")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["counts"], {"chirp3hd": 15})       # 누적값을 받으므로 바꿔 넣는다
        self.assertEqual(rows[0]["label"], "Aside")
        self.assertEqual(rows[0]["updatedAt"], "2026-11-02T00:00:00Z")

    def test_sources_summed_separately_and_sorted(self):
        r = self.reports()
        r.accept(self.payload("zzzzzzzz", "Whale"), now=self.NOV)
        r.accept(self.payload("abcdefgh", "Aside"), now=self.NOV)
        r.accept(self.payload("11111111", "", {"2026-10": {"chirp3hd": 3}}), now=self.NOV)
        self.assertEqual([x["label"] for x in r.month_by_source("2026-11")], ["Aside", "Whale"])
        self.assertEqual([x["source"] for x in r.month_by_source("2026-10")], ["11111111"])

    def test_rejects_bad_payloads(self):
        r = self.reports()
        bad = [
            None, [], {"v": 2, "source": "abcdefgh", "months": {}},
            self.payload(source="short"), self.payload(source="has space!"), self.payload(source=123),
            self.payload(months={"2026-11": {"chirp3hd": -1}}),
            self.payload(months={"2026-11": {"chirp3hd": True}}),
            self.payload(months={"2026-11": {"chirp3hd": "10"}}),
            self.payload(months={"2026-11": {"chirp3hd": 10 ** 11}}),
            self.payload(months={"2026-11": {"Chirp3HD": 1}}),
            self.payload(months={"26-11": {"chirp3hd": 1}}),
            self.payload(months={"2026-11": [1]}),
            self.payload(months="x"),
        ]
        for p in bad:
            ok, _why = r.accept(p, now=self.NOV)
            self.assertFalse(ok, p)
        self.assertEqual(r.month_by_source("2026-11"), [])

    def test_label_cleaned_and_sources_capped(self):
        r = self.reports()
        r.accept(self.payload(label="A\x00side\n" + "x" * 50), now=self.NOV)
        self.assertEqual(r.month_by_source("2026-11")[0]["label"], "Aside" + "x" * 27)
        for i in range(tts_usage.EXTENSION_MAX_SOURCES + 3):
            r.accept(self.payload(source=f"src{i:05d}"), now=datetime(2026, 11, 3, 0, 0, i, tzinfo=UTC))
        rows = r.month_by_source("2026-11")
        self.assertEqual(len(rows), tts_usage.EXTENSION_MAX_SOURCES)
        self.assertNotIn("abcdefgh", [x["source"] for x in rows])    # 가장 오래 소식 없는 것부터 버림

    def test_keeps_only_13_months(self):
        r = self.reports()
        months = {f"{2025 + i // 12}-{i % 12 + 1:02d}": {"chirp3hd": i} for i in range(15)}
        r.accept(self.payload(months=months), now=self.NOV)
        with open(self.path("tts-usage-extension.json"), encoding="utf-8") as f:
            saved = json.load(f)["sources"]["abcdefgh"]["months"]
        self.assertEqual(len(saved), 13)
        self.assertNotIn("2025-01", saved)


class TestPaseoUsage(TempDirCase):
    def write(self, data):
        os.makedirs(os.path.dirname(self.path("tts-usage-all.json")), exist_ok=True)
        with open(self.path("tts-usage-all.json"), "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def read(self, month="2026-11"):
        return tts_usage.read_paseo_usage(month, self.path("tts-usage-all.json"))

    def test_states(self):
        self.assertEqual(self.read(), {"state": "missing"})
        self.write("{깨짐")
        self.assertEqual(self.read()["state"], "broken")
        self.write({"v": 1, "month": "2026-11", "total": {"chirp3hd": "x"}})
        self.assertEqual(self.read()["state"], "broken")
        self.write({"v": 1, "updatedAt": "2026-10-31T23:55:00.000Z", "month": "2026-10", "total": {"chirp3hd": 5}})
        self.assertEqual(self.read(), {"state": "other_month", "month": "2026-10", "updatedAt": "2026-10-31T23:55:00.000Z"})

    def test_ok_shape_from_paseo(self):
        # Paseo tts.ts exportUsageAll 이 쓰는 모양 그대로(openai 칸·stale 포함)
        self.write({"v": 1, "updatedAt": "2026-11-01T07:30:00.000Z", "month": "2026-11",
                    "sources": {"PC": {"chirp3hd": 100, "wavenet": 0, "openai": 7},
                                "DBServer-Gabia": {"chirp3hd": 20, "wavenet": 3, "openai": 0}},
                    "total": {"chirp3hd": 120, "wavenet": 3, "openai": 7}, "stale": ["Calladmin-Gabia"]})
        got = self.read()
        self.assertEqual(got["state"], "ok")
        self.assertEqual(got["total"], {"chirp3hd": 120, "wavenet": 3, "openai": 7})
        self.assertEqual(sorted(got["sources"]), ["DBServer-Gabia", "PC"])
        self.assertEqual(got["stale"], ["Calladmin-Gabia"])
        self.assertEqual(got["updatedAt"], "2026-11-01T07:30:00.000Z")


class TestSummarize(unittest.TestCase):
    def test_sums_three_places(self):
        paseo = {"state": "ok", "total": {"chirp3hd": 900_000, "wavenet": 10, "openai": 50}}
        ext = [{"counts": {"chirp3hd": 50_000}}, {"counts": {"chirp3hd": 100_000, "wavenet": 5}}]
        s = tts_usage.summarize({"chirp3hd": 60_000, "wavenet": 1}, paseo, ext, "2026-11")
        chirp, wave = s["kinds"]
        self.assertEqual([k["kind"] for k in s["kinds"]], ["chirp3hd", "wavenet"])   # openai 는 넣지 않는다
        self.assertEqual((chirp["paseo"], chirp["app"], chirp["extension"], chirp["total"]), (900_000, 60_000, 150_000, 1_110_000))
        self.assertEqual((chirp["free"], chirp["left"], chirp["over"]), (1_000_000, 0, 110_000))
        self.assertAlmostEqual(chirp["cost"], 3.3)      # 11만 자 × 30달러 / 100만
        self.assertEqual((wave["total"], wave["left"], wave["over"], wave["cost"]), (16, 3_999_984, 0, 0))

    def test_paseo_unknown_left_out(self):
        s = tts_usage.summarize({"chirp3hd": 5}, {"state": "missing"}, [], "2026-11")
        chirp = s["kinds"][0]
        self.assertIsNone(chirp["paseo"])
        self.assertEqual((chirp["total"], chirp["left"]), (5, 999_995))

    def test_other_kinds_only_when_used(self):
        s = tts_usage.summarize({"neural2": 3, "standard": 0}, {"state": "missing"}, [], "2026-11")
        self.assertEqual([k["kind"] for k in s["kinds"]], ["chirp3hd", "wavenet", "neural2"])
        n2 = s["kinds"][2]
        self.assertEqual((n2["free"], n2["left"], n2["over"], n2["cost"]), (None, None, None, None))


class TestPillText(unittest.TestCase):
    def texts(self, lang="ko"):
        return {k: messages["pill_" + k][lang] for k in ("under", "over", "plain", "no_paseo")}

    def test_under_over_plain(self):
        paseo = {"state": "ok", "total": {"chirp3hd": 18_000}}
        s = tts_usage.summarize({"chirp3hd": 944}, paseo, [], "2026-11")
        row = tts_usage.pill_row(s, "chirp3hd")
        self.assertEqual(tts_usage.pill_text(row, True, self.texts()), ("Chirp 3 HD 18,944 / 1,000,000자", False))
        s = tts_usage.summarize({"chirp3hd": 1_110_000}, {"state": "missing"}, [], "2026-11")
        self.assertEqual(tts_usage.pill_text(tts_usage.pill_row(s, "chirp3hd"), False, self.texts()),
                         ("Chirp 3 HD 1,110,000자 · 110,000자 넘음 · 약 3.30달러 · Paseo 빠짐", True))
        self.assertEqual(tts_usage.pill_text(tts_usage.pill_row(s, "wavenet"), True, self.texts("en")),
                         ("WaveNet 0 / 4,000,000 chars", False))
        # 무료분을 모르는 종류(목록 밖 저장값 Neural2)는 글자만
        row = tts_usage.pill_row(tts_usage.summarize({}, {"state": "missing"}, [], "2026-11"), "neural2")
        self.assertEqual(tts_usage.pill_text(row, True, self.texts()), ("neural2 0자", False))


class TestUsageReceiver(TempDirCase):
    def setUp(self):
        super().setUp()
        self.reports = tts_usage.ExtensionReports(self.path("tts-usage-extension.json"))
        self.got = []
        self.rejected = []
        self.receiver = tts_usage.UsageReceiver(self.reports, port=0,
                                                on_report=lambda s, l, m: self.got.append((s, l)),
                                                on_reject=self.rejected.append)
        self.assertTrue(self.receiver.start())
        self.base = f"http://127.0.0.1:{self.receiver.port}"

    def tearDown(self):
        self.receiver.stop()
        super().tearDown()

    def call(self, method, path, body=None, origin="chrome-extension://abcdefghijklmnop", raw=None):
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if origin:
            req.add_header("Origin", origin)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
        except (ConnectionError, urllib.error.URLError) as e:
            # 너무 큰 본문은 서버가 읽지 않고 413 으로 답한 뒤 닫는다 — 보내는 중이던 쪽에선 연결 끊김으로 보일 수 있다
            return "closed", str(e)

    def test_accepts_extension_post(self):
        body = {"v": 1, "source": "abcdefgh", "label": "Aside", "months": {tts_usage.billing_month(): {"chirp3hd": 42}}}
        self.assertEqual(self.call("POST", "/v1/tts-usage", body), (200, {"ok": True}))
        self.assertEqual(self.got, [("abcdefgh", "Aside")])
        self.assertEqual(self.reports.month_by_source()[0]["counts"], {"chirp3hd": 42})

    def test_rejects(self):
        body = {"v": 1, "source": "abcdefgh", "months": {"2026-11": {"chirp3hd": 1}}}
        self.assertEqual(self.call("POST", "/v1/tts-usage", body, origin=None)[0], 403)              # Origin 없음
        self.assertEqual(self.call("POST", "/v1/tts-usage", body, origin="https://evil.example")[0], 403)
        self.assertEqual(self.call("POST", "/v1/tts-usage", raw=b"{not json")[0], 400)
        self.assertEqual(self.call("POST", "/v1/tts-usage", {"v": 1, "source": "x", "months": {}})[0], 400)
        self.assertIn(self.call("POST", "/v1/tts-usage", raw=b" " * (tts_usage.RECEIVER_MAX_BYTES + 1))[0], (413, "closed"))
        self.assertEqual(self.call("POST", "/v1/other", body)[0], 404)
        self.assertEqual(self.got, [])
        self.assertEqual(self.reports.month_by_source("2026-11"), [])
        # 거절 까닭이 이름만으로 알려진다(콘솔 한 줄 — 크롬 확장 몫이 0 인 원인 찾기)
        # 차례는 보지 않는다 — 요청마다 다른 스레드라 부하가 크면 섞일 수 있다(전체 시험에서 한 번 갈림). 큰 본문(size)은
        # 연결이 끊긴 쪽으로 끝날 수 있어 꼭 있으라고는 하지 않는다
        for reason in ("origin_missing", "origin_other", "json", "source", "path"):
            self.assertIn(reason, self.rejected)
        self.assertTrue(set(self.rejected) <= {"origin_missing", "origin_other", "json", "source", "size", "path"})

    def test_health(self):
        self.assertEqual(self.call("GET", "/v1/health", origin=None), (200, {"ok": True}))
        self.assertEqual(self.call("GET", "/x", origin=None)[0], 404)

    def test_port_in_use_returns_false(self):
        other = tts_usage.UsageReceiver(self.reports, port=self.receiver.port, log=lambda m: None)
        self.assertFalse(other.start())
        self.assertFalse(other.running)


if __name__ == "__main__":
    unittest.main()
