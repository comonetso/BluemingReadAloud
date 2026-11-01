# tts_usage.py - 읽기(Google Cloud TTS) 이번 달 사용량 세기 · 세 곳(Paseo·이 앱·크롬 확장) 요금 브리지
#
# 왜 (2026-11-01 리규형님 지시 — Claude State Bar 대화에서, peer_mail 188410e0):
#   Paseo 상태바 플러그인 · 이 앱 · 크롬 읽기 확장 셋이 같은 Google 결제 계정(프로젝트 yeogiaen)의 Cloud TTS 를 쓴다.
#   무료분은 결제 계정 단위라 셋이 나눠 쓴다(Chirp 3 HD 월 100만 자, 넘으면 100만 자당 30달러 — 10월 약 8.6만 원).
#   리규형님 계획: Chirp 3 HD(Zephyr)로 쓰다가 무료분을 다 쓰기 전에 WaveNet A(100만 자당 4달러)로 바꾼다.
#   그 판단에 세 곳 합계가 필요해 이 앱이 한 화면에 모아 보인다(설정 창 "읽기 사용량" — whisperer.show_usage_dialog).
#
# 세는 법 = Paseo 와 같게(server/presentation/tts.ts countUsage, 11-01):
#   - 성공한 요청(예외 없이 돌아온 synthesize_speech)에 실제로 보낸 input 의 text 또는 markup 글자 수.
#     공백·줄바꿈·쉼 표지까지, 코드 포인트로 센다(Python len — 이모지 1자). 실패한 요청은 안 센다.
#     markup 이 400 으로 거절돼 평문으로 다시 보낸 경우는 평문만 센다. 미리 듣기도 센다.
#   - 종류 키: chirp3hd · wavenet (그 밖의 목소리는 종류 이름 소문자 — neural2·standard. 섞이지 않게 따로 쌓기만 한다)
#   - 달 키: Google 결제 달 = 미국 태평양 시간 "YYYY-MM"(billing_month). 2026-11 은 한국 시각 11-01 16:00 부터.
#   - 기록 모양: {"v":1,"months":{"2026-11":{"chirp3hd":12345,"wavenet":0}}} — 13달만 남김, 임시 파일에 쓰고 이름 바꾸기.
#
# 세 곳 모으기:
#   - Paseo 몫: Paseo PC 데몬이 5분마다 내보내는 파일(PC·서버 셋·직원 데몬 합) — PASEO_USAGE_ALL_PATH. 읽기만 한다.
#   - 크롬 확장 몫: 확장이 셀 때마다 자기 누적값을 이 앱의 받는 창구로 보낸다(UsageReceiver, 127.0.0.1:51888 TCP,
#     POST /v1/tts-usage). 규격은 크롬 확장 대화와 peer_mail 423b8e9a 로 맞췄다. 확장은 Aside·웨일·크롬에 따로 깔릴 수
#     있어 설치마다 source 가 다르고, 이 앱이 source 별로 더한다.
#   - 이 앱 몫: 개발 모드와 설치본이 같은 키(같은 결제 계정)를 쓰므로 한 파일에 같이 센다 → 작업 폴더가 아니라 %APPDATA%.
#
# ⚠️ 여기 숫자는 세 곳이 스스로 센 값이다. 이 기능을 넣기 전에 쓴 양·다른 프로그램이 같은 키로 쓴 양은 빠진다.
#    실제 청구는 Google Cloud 결제 화면이 정본이다.

import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone

from tts_engine import voice_type_of

USAGE_KEEP_MONTHS = 13            # 지난해 같은 달까지 (Paseo USAGE_KEEP_MONTHS 와 같게)

# 종류별 이름·100만 자 값(달러)·월 무료분(자) — Google 공식 가격표 cloud.google.com/text-to-speech/pricing
# (2026-11-01 Claude State Bar 확인 값: Chirp 3 HD 무료 100만·30달러 / WaveNet 무료 400만·4달러)
KIND_NAME = {"chirp3hd": "Chirp 3 HD", "wavenet": "WaveNet"}
KIND_PRICE = {"chirp3hd": 30, "wavenet": 4}
KIND_FREE = {"chirp3hd": 1_000_000, "wavenet": 4_000_000}
SHOWN_KINDS = ("chirp3hd", "wavenet")   # 요금 화면에 늘 보이는 종류(그 밖은 값이 있을 때만)
IGNORED_KINDS = ("openai",)             # Paseo 합계에 있는 OpenAI 몫 — Google 무료분과 무관해 화면에 안 넣는다

# 받는 창구 — 단일 실행 확인 UDP(prevent_multiple_instances)와 같은 번호. TCP 라 부딪히지 않는다(2026-11-01 Claude 가 정함)
RECEIVER_HOST = "127.0.0.1"
RECEIVER_PORT = 51888
RECEIVER_PATH = "/v1/tts-usage"
RECEIVER_MAX_BYTES = 16 * 1024
EXTENSION_MAX_SOURCES = 20        # 확장 설치가 이보다 많으면 가장 오래 소식 없는 것부터 버린다(Claude 가 정함)
_COUNT_MAX = 10 ** 10             # 한 칸 값 상한 — 이보다 크면 잘못 보낸 값으로 보고 받지 않는다

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_KIND_RE = re.compile(r"^[a-z0-9]{1,16}$")
_SOURCE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_UTC = timezone.utc


def app_data_dir():
    """이 앱 사용량 파일을 두는 폴더 — %APPDATA%\\BluemingReadAloud (개발 모드·설치본이 같이 쓴다)."""
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(base, "BluemingReadAloud")


APP_USAGE_PATH = os.path.join(app_data_dir(), "tts-usage.json")
EXTENSION_USAGE_PATH = os.path.join(app_data_dir(), "tts-usage-extension.json")
# Paseo 가 내보내는 세 곳 합계용 파일(제안 위치 그대로 — Paseo tts.ts USAGE_ALL_FILE)
PASEO_USAGE_ALL_PATH = os.path.join(os.path.expanduser("~"), ".paseo", "claude-state-bar", "tts-usage-all.json")


# ════════════════════════════════════════════════════════════════════
# 결제 달 — 미국 태평양 시간
# ════════════════════════════════════════════════════════════════════

def _first_sunday(year, month):
    d = datetime(year, month, 1).weekday()   # 월=0 … 일=6
    return 1 + (6 - d) % 7


def _pacific_dst_utc(year):
    """그해 태평양 서머타임 구간(UTC). 2007 년부터의 미국 규칙:
    3월 둘째 일요일 02:00 PST(= 10:00 UTC) 시작 · 11월 첫째 일요일 02:00 PDT(= 09:00 UTC) 끝.
    시간대 자료(tzdata)는 Windows 파이썬에 없어(zoneinfo 가 못 찾음) 규칙을 직접 쓴다. 미국이 규칙을 바꾸면 여기를 고친다.
    """
    start = datetime(year, 3, _first_sunday(year, 3) + 7, 10, tzinfo=_UTC)
    end = datetime(year, 11, _first_sunday(year, 11), 9, tzinfo=_UTC)
    return start, end


def _pacific_offset(now_utc):
    start, end = _pacific_dst_utc(now_utc.year)
    return timedelta(hours=-7) if start <= now_utc < end else timedelta(hours=-8)


def _as_utc(now):
    if now is None:
        return datetime.now(_UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=_UTC)
    return now.astimezone(_UTC)


def billing_month(now=None):
    """Google 결제 달 "2026-11" — 미국 태평양 시간으로 나뉜다(Paseo speech.ts billingMonth 와 같은 값).
    now: datetime(시간대 없으면 UTC 로 본다). 없으면 지금."""
    utc = _as_utc(now)
    local = utc + _pacific_offset(utc)
    return f"{local.year:04d}-{local.month:02d}"


def month_start_utc(month):
    """결제 달 "YYYY-MM" 이 시작하는 순간(UTC) — 태평양 시간 그달 1일 0시. 형식이 틀리면 None."""
    if not isinstance(month, str) or not _MONTH_RE.match(month):
        return None
    year, mon = int(month[:4]), int(month[5:])
    if not 1 <= mon <= 12:
        return None
    guess = datetime(year, mon, 1, 8, tzinfo=_UTC)        # 0시 PST = 08:00 UTC 로 먼저 잡고
    if _pacific_offset(guess) == timedelta(hours=-7):     # 그 순간이 서머타임이면 0시 PDT = 07:00 UTC
        guess = datetime(year, mon, 1, 7, tzinfo=_UTC)
    return guess


def next_month(month):
    year, mon = int(month[:4]), int(month[5:])
    return f"{year + (mon == 12):04d}-{mon % 12 + 1:02d}"


# ════════════════════════════════════════════════════════════════════
# 목소리 → 종류 · 단추 글
# ════════════════════════════════════════════════════════════════════

def usage_kind(voice_name):
    """사용량 종류 키. "ko-KR-Chirp3-HD-Zephyr" → "chirp3hd", "ko-KR-Wavenet-A" → "wavenet",
    그 밖은 종류 이름 소문자("ko-KR-Neural2-A" → "neural2"). 종류를 모르면 "unknown"."""
    vt = voice_type_of(voice_name)
    if vt == "Chirp3-HD":
        return "chirp3hd"
    if vt == "Wavenet":
        return "wavenet"
    kind = re.sub(r"[^a-z0-9]", "", str(vt or "").lower())[:16]
    return kind or "unknown"


def short_voice_name(voice_name):
    """단추에 쓰는 짧은 이름 — Paseo 와 같게. Chirp 3 HD 는 끝 이름("Zephyr"), 그 밖은 언어 코드를 뗀 이름("Wavenet-A")."""
    name = str(voice_name or "")
    if voice_type_of(name) == "Chirp3-HD":
        return name.rsplit("-", 1)[-1]
    m = re.match(r"^[a-z]{2,3}-[A-Z]{2}-(.+)$", name)
    return m.group(1) if m else name


def group_digits(n):
    """세 자리 쉼표 — 12345 → "12,345" (Paseo groupDigits 와 같게 반올림)."""
    return f"{int(round(n)):,}"


def voice_label(voice_name, used=None, price_text="{}", usage_text="{}"):
    """설정 창 목소리 칸 글 — "Zephyr · Chirp 3 HD · 100만 자 30달러 (이번 달 PC 앱 12,345자)" (Paseo speechProviders.tsx voiceLabel).
    price_text·usage_text 는 messages.py 문구("100만 자 {}달러", "이번 달 PC 앱 {}자"). used 가 None 이면 괄호를 뺀다.
    같은 종류 목소리는 같은 숫자다(무료분이 종류마다 따로라)."""
    kind = usage_kind(voice_name)
    name = KIND_NAME.get(kind) or voice_type_of(voice_name) or kind
    price = KIND_PRICE.get(kind)
    label = f"{short_voice_name(voice_name)} · {name}"
    if price:
        label += " · " + price_text.format(price)
    if used is not None:
        label += " (" + usage_text.format(group_digits(used)) + ")"
    return label


# ════════════════════════════════════════════════════════════════════
# 기록 파일 — 읽기·원자적으로 쓰기
# ════════════════════════════════════════════════════════════════════

def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return False   # 깨짐·못 읽음


def _write_json(path, data):
    """임시 파일에 쓰고 이름을 바꾼다 — 쓰는 도중에 읽어도 반쪽 파일을 보지 않게(Paseo 와 같게)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def _clean_counts(raw):
    """{"chirp3hd": 12, ...} 에서 올바른 칸만(키 형식·0 이상 정수). 아니면 None."""
    if not isinstance(raw, dict):
        return None
    out = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not _KIND_RE.match(k):
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not 0 <= v <= _COUNT_MAX:
            return None
        out[k] = int(v)
    return out


def _clean_months(raw):
    """{"2026-11": {...}} 에서 최근 13달만. 하나라도 틀린 모양이면 None(통째로 받지 않음)."""
    if not isinstance(raw, dict):
        return None
    out = {}
    for month, counts in raw.items():
        if not isinstance(month, str) or not _MONTH_RE.match(month):
            return None
        clean = _clean_counts(counts)
        if clean is None:
            return None
        out[month] = clean
    for old in sorted(out)[:-USAGE_KEEP_MONTHS]:
        del out[old]
    return out


def _read_months(path):
    data = _read_json(path)
    if isinstance(data, dict) and data.get("v") == 1:
        months = _clean_months(data.get("months"))
        if months is not None:
            return months
    return {}


class UsageCounter:
    """이 앱이 보낸 글자 수를 이번 달에 더한다. 합성 스레드·미리 듣기 스레드가 같이 부르므로 락으로 차례를 지킨다.
    세기에 실패해도 읽기에는 영향이 없다(예외를 밖으로 내지 않는다)."""

    def __init__(self, path=APP_USAGE_PATH, log=None):
        self.path = path
        self._lock = threading.Lock()
        self._log = log or (lambda msg: None)

    def count(self, kind, sent, now=None):
        chars = len(sent or "")
        if chars <= 0:
            return True
        try:
            with self._lock:
                months = _read_months(self.path)
                month = billing_month(now)
                m = months.setdefault(month, {})
                m[kind] = int(m.get(kind, 0)) + chars
                for old in sorted(months)[:-USAGE_KEEP_MONTHS]:
                    del months[old]
                _write_json(self.path, {"v": 1, "months": months})
            return True
        except Exception as e:
            self._log(f"[사용량] 기록 실패(읽기는 그대로): {e}")
            return False

    def month_counts(self, month=None):
        """그달 종류별 글자 수 {"chirp3hd": N, ...}. 기록이 없으면 {}."""
        with self._lock:
            return dict(_read_months(self.path).get(month or billing_month(), {}))


# ════════════════════════════════════════════════════════════════════
# 크롬 확장이 보낸 값
# ════════════════════════════════════════════════════════════════════

def _clean_label(raw):
    if not isinstance(raw, str):
        return ""
    return "".join(ch for ch in raw if ch.isprintable())[:32].strip()


class ExtensionReports:
    """확장 설치(source)마다 마지막으로 받은 누적 기록을 둔다 — 받을 때마다 그 source 몫을 통째로 바꾼다.
    그래서 몇 번 받아도 같고, 한 번 놓쳐도 다음에 따라잡는다. 파일 모양:
    {"v":1,"sources":{"<source>":{"label":"Aside","updatedAt":"<ISO>","months":{"2026-11":{...}}}}}"""

    def __init__(self, path=EXTENSION_USAGE_PATH):
        self.path = path
        self._lock = threading.Lock()

    def _read(self):
        data = _read_json(self.path)
        sources = data.get("sources") if isinstance(data, dict) and data.get("v") == 1 else None
        out = {}
        if isinstance(sources, dict):
            for sid, item in sources.items():
                if not isinstance(sid, str) or not _SOURCE_RE.match(sid) or not isinstance(item, dict):
                    continue
                months = _clean_months(item.get("months"))
                if months is None:
                    continue
                out[sid] = {"label": _clean_label(item.get("label")),
                            "updatedAt": item.get("updatedAt") if isinstance(item.get("updatedAt"), str) else "",
                            "months": months}
        return out

    def accept(self, payload, now=None):
        """확장이 보낸 본문(dict)을 확인하고 저장한다. 반환 (True, source) 또는 (False, 거절 까닭)."""
        if not isinstance(payload, dict) or payload.get("v") != 1:
            return False, "v"
        source = payload.get("source")
        if not isinstance(source, str) or not _SOURCE_RE.match(source):
            return False, "source"
        months = _clean_months(payload.get("months"))
        if months is None:
            return False, "months"
        stamp = _as_utc(now).isoformat().replace("+00:00", "Z")
        with self._lock:
            sources = self._read()
            sources[source] = {"label": _clean_label(payload.get("label")), "updatedAt": stamp, "months": months}
            if len(sources) > EXTENSION_MAX_SOURCES:
                for sid in sorted(sources, key=lambda s: sources[s]["updatedAt"])[:len(sources) - EXTENSION_MAX_SOURCES]:
                    del sources[sid]
            _write_json(self.path, {"v": 1, "sources": sources})
        return True, source

    def month_by_source(self, month=None):
        """그달 값이 있는 설치 목록 [{"source","label","updatedAt","counts"}] — 받은 차례 아닌 이름 차례."""
        month = month or billing_month()
        with self._lock:
            sources = self._read()
        rows = []
        for sid, item in sources.items():
            if month in item["months"]:
                rows.append({"source": sid, "label": item["label"], "updatedAt": item["updatedAt"],
                             "counts": dict(item["months"][month])})
        return sorted(rows, key=lambda r: (r["label"] or r["source"], r["source"]))


# ════════════════════════════════════════════════════════════════════
# Paseo 몫 — Paseo PC 데몬이 내보낸 파일
# ════════════════════════════════════════════════════════════════════

def read_paseo_usage(month=None, path=PASEO_USAGE_ALL_PATH):
    """Paseo 합계 파일을 읽는다. 반환 dict 의 state:
    "ok"(이번 달 값 — total·sources·stale·updatedAt) · "missing"(파일 없음) · "broken"(못 읽음·모양 틀림) ·
    "other_month"(다른 달 파일 — Paseo 데몬이 이번 달에 아직 안 내보냄. 지난달 값을 이번 달로 보이지 않는다)."""
    month = month or billing_month()
    data = _read_json(path)
    if data is None:
        return {"state": "missing"}
    if not isinstance(data, dict) or data.get("v") != 1 or not isinstance(data.get("month"), str):
        return {"state": "broken"}
    updated = data.get("updatedAt") if isinstance(data.get("updatedAt"), str) else ""
    if data["month"] != month:
        return {"state": "other_month", "month": data["month"], "updatedAt": updated}
    total = _clean_counts(data.get("total"))
    if total is None:
        return {"state": "broken"}
    sources = {}
    if isinstance(data.get("sources"), dict):
        for host, counts in data["sources"].items():
            clean = _clean_counts(counts)
            if isinstance(host, str) and clean is not None:
                sources[host] = clean
    stale = [h for h in data.get("stale", []) if isinstance(h, str)] if isinstance(data.get("stale"), list) else []
    return {"state": "ok", "total": total, "sources": sources, "stale": stale, "updatedAt": updated}


# ════════════════════════════════════════════════════════════════════
# 세 곳 합계 — 요금 화면이 그대로 그린다
# ════════════════════════════════════════════════════════════════════

def summarize(app_counts, paseo, extension_rows, month):
    """세 곳 값을 종류별로 합친다. paseo 는 read_paseo_usage 결과(state 가 "ok" 가 아니면 합계에서 빠진다).
    반환 {"month", "kinds": [{"kind","name","price","free","paseo","app","extension","total","left","over","cost"}]}.
    paseo 칸은 Paseo 값을 모르면 None. left = 남은 무료분, over = 넘친 글자, cost = 넘친 만큼의 값(달러, 가격을 알 때만)."""
    paseo_total = paseo.get("total") if paseo.get("state") == "ok" else None
    ext_total = {}
    for row in extension_rows:
        for k, v in row["counts"].items():
            ext_total[k] = ext_total.get(k, 0) + v
    extra = set(app_counts) | set(ext_total) | set(paseo_total or {})
    kinds = list(SHOWN_KINDS) + sorted(k for k in extra
                                       if k not in SHOWN_KINDS and k not in IGNORED_KINDS
                                       and (app_counts.get(k) or ext_total.get(k) or (paseo_total or {}).get(k)))
    rows = []
    for kind in kinds:
        p = None if paseo_total is None else int(paseo_total.get(kind, 0))
        a = int(app_counts.get(kind, 0))
        e = int(ext_total.get(kind, 0))
        total = (p or 0) + a + e
        free = KIND_FREE.get(kind)
        price = KIND_PRICE.get(kind)
        over = max(0, total - free) if free is not None else None
        rows.append({"kind": kind, "name": KIND_NAME.get(kind, kind), "price": price, "free": free,
                     "paseo": p, "app": a, "extension": e, "total": total,
                     "left": max(0, free - total) if free is not None else None, "over": over,
                     "cost": over * price / 1_000_000 if over is not None and price is not None else None})
    return {"month": month, "kinds": rows}


def pill_text(row, paseo_known, texts):
    """사용량 알약 글 (2026-11-01 리규형님 버튼 "글자·무료분, 넘으면 달러"). row = summarize 의 kinds 한 줄.
    texts = {"under": "{} {} / {}자", "over": "{} {}자 · {}자 넘음 · 약 {}달러", "plain": "{} {}자", "no_paseo": " · Paseo 빠짐"}
    (messages.py pill_*). 반환 (글, 경고 여부) — 경고 = 무료분을 넘음(빨강)."""
    name, total = row["name"], group_digits(row["total"])
    if row["free"] is None:
        text, alert = texts["plain"].format(name, total), False
    elif row["over"]:
        cost = f"{row['cost']:.2f}" if row["cost"] is not None else "?"
        text, alert = texts["over"].format(name, total, group_digits(row["over"]), cost), True
    else:
        text, alert = texts["under"].format(name, total, group_digits(row["free"])), False
    if not paseo_known:
        text += texts["no_paseo"]
    return text, alert


def pill_row(summary, kind):
    """summarize 결과에서 그 종류 줄. 없으면(그 종류를 아무도 안 씀) 0 으로 채운 줄."""
    for row in summary["kinds"]:
        if row["kind"] == kind:
            return row
    free, price = KIND_FREE.get(kind), KIND_PRICE.get(kind)
    return {"kind": kind, "name": KIND_NAME.get(kind, kind), "price": price, "free": free, "paseo": None,
            "app": 0, "extension": 0, "total": 0, "left": free, "over": 0 if free is not None else None,
            "cost": 0.0 if free is not None and price is not None else None}


# ════════════════════════════════════════════════════════════════════
# 받는 창구 — 크롬 확장이 자기 누적값을 보낸다 (127.0.0.1 에만 열림)
# ════════════════════════════════════════════════════════════════════

class UsageReceiver:
    """POST http://127.0.0.1:51888/v1/tts-usage 로 확장 기록을 받는다(GET /v1/health 는 살아 있는지만).

    - 내 PC 안(127.0.0.1)에서만 열린다. Origin 이 chrome-extension:// 로 시작할 때만 받는다 — 웹페이지는 Origin 을
      속일 수 없어서, 아무 페이지가 숫자를 바꿔 넣지 못한다. 받는 것은 숫자뿐이고 파일 경로·명령은 받지 않는다.
    - 따로 도는 스레드(daemon)라 앱이 끝나면 같이 끝난다. 포트를 다른 프로그램이 쓰고 있으면 start() 가 False.
    - on_report(source, label, months) 는 받은 스레드에서 불린다(Tk 를 만지지 말 것 — 로그 한 줄 정도).
    - on_reject(reason) — POST 를 거절할 때 까닭 이름만(origin_missing·origin_other·path·length·size·json·v·source·
      months·write). 숫자·주소·Origin 값은 넘기지 않는다(2026-11-01 리규형님 버튼 "거절하면 까닭을 콘솔에" — 확장 몫이
      0 인 원인 찾기). 받은 스레드에서 불린다.
    """

    def __init__(self, reports, host=RECEIVER_HOST, port=RECEIVER_PORT, on_report=None, log=None, on_reject=None):
        self.reports = reports
        self.host = host
        self.port = port
        self.on_report = on_report
        self.on_reject = on_reject
        self._log = log or (lambda msg: None)
        self._server = None
        self._thread = None

    def start(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "BluemingReadAloud"
            sys_version = ""

            def log_message(self, *args):   # 기본은 stderr 에 쓴다 — 설치본(창 없는 exe)엔 stderr 가 없다
                pass

            def _reply(self, code, body):
                raw = json.dumps(body).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/v1/health":
                    self._reply(200, {"ok": True})
                else:
                    self._reply(404, {"ok": False})

            def _reject(self, code, reason):
                if receiver.on_reject:
                    try:
                        receiver.on_reject(reason)
                    except Exception:
                        pass
                self._reply(code, {"ok": False, "reason": reason})

            def do_POST(self):
                if self.path != RECEIVER_PATH:
                    self._reject(404, "path")
                    return
                origin = str(self.headers.get("Origin", ""))
                if not origin.startswith("chrome-extension://"):
                    self._reject(403, "origin_other" if origin else "origin_missing")
                    return
                try:
                    length = int(self.headers.get("Content-Length", ""))
                except ValueError:
                    self._reject(400, "length")
                    return
                if length < 0 or length > RECEIVER_MAX_BYTES:
                    self._reject(413, "size")
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self._reject(400, "json")
                    return
                try:
                    ok, info = receiver.reports.accept(payload)
                except Exception as e:
                    receiver._log(f"[사용량] 확장 기록 저장 실패: {e}")
                    self._reject(500, "write")
                    return
                if not ok:
                    self._reject(400, info)
                    return
                if receiver.on_report:   # 답보다 먼저 — 답을 받은 쪽이 보면 이미 알림이 끝나 있게(콘솔 한 줄이라 빠르다)
                    try:
                        receiver.on_report(info, _clean_label(payload.get("label")), payload.get("months"))
                    except Exception:
                        pass
                self._reply(200, {"ok": True})

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = False   # 윈도우의 SO_REUSEADDR 는 남이 같은 포트를 가로채게 둔다 — 끈다

        try:
            self._server = Server((self.host, self.port), Handler)
        except OSError as e:
            self._log(f"[사용량] 받는 창구를 열지 못했습니다({self.host}:{self.port}): {e}")
            self._server = None
            return False
        self.port = self._server.server_address[1]   # port=0(시험)이면 실제로 받은 번호
        self._thread = threading.Thread(target=self._server.serve_forever, name="tts-usage-receiver", daemon=True)
        self._thread.start()
        return True

    @property
    def running(self):
        return self._server is not None

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
