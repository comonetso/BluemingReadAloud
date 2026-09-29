# -*- coding: utf-8 -*-
"""주 언어가 아닌 문장을 번역해서 읽기 (2026-09-29 추가).

규칙 (2026-09-29 사용자 확정)
  - 판별 단위는 문장. 주 언어 글자가 한 글자도 없는 문장만 번역한다.
    비율 기준(예: "주 언어 90% 미만")은 쓰지 않는다 — "React 컴포넌트에서 useState hook을 쓰면 됩니다" 는
    공백 빼고 영어 17자·한글 12자(한글 41%)라, 비율로 자르면 멀쩡한 한국어 문장이 번역으로 넘어간다.
    "한글이 한 글자라도 있으면 그대로" 로 자르면 한국어 문장 속 영어(대부분 용어·이름)는 저절로 남는다.
  - 주 언어 = 읽어 주는 음성의 언어. 음성 목록이 한국어뿐(whisperer.KOREAN_VOICES)이라 주 언어 글자 = 한글.
    다른 언어 음성이면 번역하지 않는다(supports).
  - 번역은 Gemini 글 모델, Gemini API(generativelanguage.googleapis.com) 를 API 키로 부른다.
    Gemini 3.5 Live Translate 는 음성→음성 전용(글 입력 없음)이라 쓸 수 없다.
    처음엔 서비스 계정(Vertex AI)으로 만들었다가 같은 날 사용자 결정으로 키 방식으로 바꿨다. 키는 TTS 키와 따로다 —
    구글이 Gemini 키는 서비스 계정에 묶게 하고 묶인 키는 TTS 를 못 부른다(실측: Gemini 키로 TTS 401,
    TTS 키로 Gemini 403). 그래서 인증 창에 키 두 칸(whisperer.show_api_key_dialog).
  - 번역이 실패하면 그 조각을 읽을 차례에 읽기를 멈추고 알린다 → tts_engine.SegmentFailed.
    번역 한 번이 TIMEOUT(3초)을 넘으면 실패다(사용자 결정. 실측 0.87~1.55초, 12회).
  - 설정 창 체크(translate_enabled), 처음 값은 켬.

구현하며 정한 것 (2026-09-29 사용자에게 알림)
  - 숫자·기호만 있는 문장, URL 대체 문구(readaloud_text.URL_REPLACEMENT "HTTP URL.")는 번역하지 않는다.
  - 이어진 번역 대상 문장은 한 덩어리로 묶어(문맥 유지) 조각당 요청 한 번에 보낸다.
  - 번역 지시: 코드·식별자·파일명·명령어·제품명·프로그래밍 용어는 원문 그대로.
  - 번역 결과는 읽기 한 번(세션) 동안만 기억한다(make_translating_synthesize 안).

어디에 끼는가 (whisperer.speak_text)
  split_for_reading(keep_raw=True) → mark_for_translation 이 번역할 문장이 있는 조각의 text 를 "변환 전 글"(raw)로
  바꾼다 → make_translating_synthesize 가 그 조각만 번역 → 읽기용 변환(spoken_text) → 합성.
  엔진(tts_engine)은 모른다. 엔진의 소리 캐시 키가 (글, 속도)라 raw 가 키가 되고, 이동 뒤 되돌아와도 다시 번역하지 않는다.
  형광펜은 조각 번호·원문 위치로 칠하므로 그대로 원문(영어) 위에 칠해진다.
"""

import json
import re
import threading

import readaloud_text
from tts_engine import SegmentFailed

__all__ = [
    "MODEL", "API_BASE", "TIMEOUT", "TranslationError", "GeminiTranslator", "MissingTranslator", "check_gemini_key",
    "supports", "has_primary", "needs_translation", "sentence_spans", "plan", "translate_segment",
    "mark_for_translation", "make_translating_synthesize",
]

MODEL = "gemini-3.5-flash-lite"   # 2026-09 Gemini API 문서가 새 프로젝트에 권하는 저지연 모델(정식판)
API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# 번역 한 번의 제한 시간(초). 2026-09-29 사용자 결정 — 실측 0.87~1.55초(12회, 가운데 약 1초).
# 넘으면 그 조각 차례에 읽기를 멈추고 알린다. 인증 창의 키 확인 요청도 같은 값을 쓴다.
TIMEOUT = 3.0

SYSTEM_INSTRUCTION = (
    "You translate text for a Korean text-to-speech reader. "
    "The user message is a JSON array of strings. Translate each string into natural Korean and return "
    "a JSON array of the same length, in the same order. "
    "Keep code, identifiers, file names, commands, product names and programming terms exactly as written. "
    "Return only the JSON array."
)


class TranslationError(Exception):
    """번역 요청이 실패했거나 응답 모양이 이상하다."""


# ════════════════════════════════════════════════════════════════════
# 판별 — 어느 문장을 번역하나
# ════════════════════════════════════════════════════════════════════

# 한글: 자모(1100-11FF) · 호환 자모(3130-318F) · 음절(AC00-D7A3)
_HANGUL = re.compile("[ᄀ-ᇿ㄰-㆏가-힣]")
# 문장 경계: 문장부호 뒤 공백, 또는 줄바꿈. 경계 자체(공백·줄바꿈)는 어느 문장에도 넣지 않는다.
_BOUNDARY = re.compile("(?<=[.!?…。！？])[ \t 　]+|[ \t 　]*\r?\n[ \t 　\r\n]*")


def supports(lang):
    """음성 언어("ko-KR")가 번역을 지원하는 주 언어인가. 지금은 한국어만(주 언어 글자 = 한글)."""
    return (lang or "").lower().split("-")[0] == "ko"


def has_primary(text):
    """주 언어(한국어) 글자가 하나라도 있나."""
    return bool(_HANGUL.search(text or ""))


def needs_translation(sentence):
    """이 문장을 번역하나 — 한글이 한 글자도 없고, 번역할 글자(문자)가 있을 때.

    숫자·기호뿐인 문장, URL 대체 문구("HTTP URL.")만 있는 문장은 번역하지 않는다.
    """
    s = (sentence or "").strip()
    if not s or has_primary(s):
        return False
    rest = s.replace(readaloud_text.URL_REPLACEMENT, "")
    return any(c.isalpha() for c in rest)


def sentence_spans(text):
    """글 → 문장 구간 [(시작, 끝)] (반열린, 앞뒤 공백 제외). 경계는 문장부호 뒤 공백과 줄바꿈."""
    spans = []
    pos = 0
    for m in _BOUNDARY.finditer(text):
        if m.start() > pos:
            spans.append((pos, m.start()))
        pos = m.end()
    if pos < len(text):
        spans.append((pos, len(text)))
    # 앞뒤 공백을 뗀다(경계 정규식이 못 먹은 앞머리 공백 등)
    out = []
    for s, e in spans:
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if s < e:
            out.append((s, e))
    return out


def plan(text):
    """조각 글 → 번역할 구간 [(시작, 끝)]. 이어진 번역 대상 문장은 한 구간으로 묶는다(사이 공백·줄바꿈 포함)."""
    runs = []
    prev_selected = False
    for s, e in sentence_spans(text or ""):
        if needs_translation(text[s:e]):
            if prev_selected:
                runs[-1] = (runs[-1][0], e)
            else:
                runs.append((s, e))
            prev_selected = True
        else:
            prev_selected = False
    return runs


def translate_segment(text, translate):
    """조각 글에서 번역 대상 구간만 번역해 끼워 넣은 글을 돌려준다. 대상이 없으면 그대로.

    translate(list[str]) -> list[str] (같은 길이). 실패하면 예외가 그대로 올라간다.
    """
    runs = plan(text)
    if not runs:
        return text
    sources = [text[s:e] for s, e in runs]
    outs = translate(sources)
    if not isinstance(outs, list) or len(outs) != len(sources) or not all(isinstance(o, str) for o in outs):
        raise TranslationError(f"번역 결과 개수가 맞지 않습니다 (보냄 {len(sources)}, 받음 {outs!r:.200})")
    parts = []
    pos = 0
    for (s, e), out in zip(runs, outs):
        parts.append(text[pos:s])
        parts.append(out.strip())
        pos = e
    parts.append(text[pos:])
    return "".join(parts)


# ════════════════════════════════════════════════════════════════════
# 번역기 — Gemini API (API 키)
# ════════════════════════════════════════════════════════════════════

def _new_session():
    import requests   # google-cloud-texttospeech 가 이미 끌고 온 패키지(requirements.txt 에도 적어 둠)
    return requests.Session()


class GeminiTranslator:
    """translate(list[str]) -> list[str]. Gemini API generateContent 를 API 키(x-goog-api-key 머리글)로 부른다.

    키를 URL(?key=)에 넣지 않는다 — 오류 로그·예외 문구에 URL 이 찍혀도 키가 새지 않게.
    session 은 테스트가 가짜를 넣을 때만 준다.
    """

    def __init__(self, api_key, model=MODEL, timeout=TIMEOUT, session=None):
        if not api_key:
            raise TranslationError("Gemini 키가 없습니다")
        self.url = f"{API_BASE}/models/{model}:generateContent"
        self.model = model
        self._headers = {"x-goog-api-key": api_key}
        self._session = session or _new_session()
        self._timeout = timeout

    def __call__(self, texts):
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(list(texts), ensure_ascii=False)}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
        }
        try:
            resp = self._session.post(self.url, json=body, headers=self._headers, timeout=self._timeout)
        except Exception as e:
            raise TranslationError(f"번역 요청 실패: {e}") from e
        if resp.status_code != 200:
            raise TranslationError(f"번역 요청 실패 (HTTP {resp.status_code}): {_error_message(resp)}")
        try:
            data = resp.json()
            parts = data["candidates"][0]["content"]["parts"]
            raw = "".join(p.get("text", "") for p in parts)
            out = json.loads(raw)
        except Exception as e:
            raise TranslationError(f"번역 응답을 읽지 못했습니다: {e}") from e
        return out


def _error_message(resp):
    try:
        return resp.json()["error"]["message"][:300]
    except Exception:
        return (resp.text or "")[:300]


def check_gemini_key(api_key, model=MODEL, timeout=TIMEOUT, session=None):
    """인증 창 "설정" 때 Gemini 키가 맞는지 확인한다 — 모델 정보 요청(GET) 한 번. 틀리면 TranslationError.

    실측(2026-09-29): Gemini 키 200(0.49초), TTS 키 403 — 두 칸을 바꿔 넣어도 잡힌다.
    """
    if not api_key:
        raise TranslationError("Gemini 키가 없습니다")
    session = session or _new_session()
    try:
        resp = session.get(f"{API_BASE}/models/{model}", headers={"x-goog-api-key": api_key}, timeout=timeout)
    except Exception as e:
        raise TranslationError(f"확인 요청 실패: {e}") from e
    if resp.status_code != 200:
        raise TranslationError(f"HTTP {resp.status_code}: {_error_message(resp)}")


class MissingTranslator:
    """번역기를 만들지 못했을 때(인증 오류 등) 넣는 자리. 부르면 항상 실패 → 사용자 결정대로 그 조각에서 멈추고 알림."""

    def __init__(self, reason):
        self.reason = reason

    def __call__(self, texts):
        raise TranslationError(f"번역기를 준비하지 못했습니다: {self.reason}")


# ════════════════════════════════════════════════════════════════════
# 읽기에 끼우기
# ════════════════════════════════════════════════════════════════════

def mark_for_translation(segments):
    """split_for_reading(keep_raw=True) 결과를 고친다: 번역할 문장이 있는 조각은 text 를 raw(변환 전 글)로 바꾼다.

    모든 조각에서 "raw" 키는 뺀다(엔진·UI 가 보는 모양을 예전과 같게). 번역 대상 raw 글의 집합을 돌려준다.
    번역 대상이 아닌 조각의 text(변환 뒤)가 이 집합의 글과 같아질 일은 없다 — 대상 raw 에는 한글이 없는 문장이
    있고, 읽기용 변환은 한글을 새로 만들지 않으므로 대상이 아닌 조각의 text 에는 그런 문장이 없다.
    """
    raw_texts = set()
    for seg in segments:
        raw = seg.pop("raw", None)
        if raw and plan(raw):
            seg["text"] = raw
            raw_texts.add(raw)
    return raw_texts


def make_translating_synthesize(synthesize, translate, prepare, raw_texts, log=None, on_translated=None):
    """synthesize(text, rate) 를 감싼다. text 가 raw_texts 에 있으면 번역 → prepare(읽기용 변환) → 합성.

    번역 실패는 tts_engine.SegmentFailed 로 바꿔 던진다(엔진이 그 조각 차례에 멈춘다).
    합성 실패는 예전처럼 그대로 올라간다(엔진이 그 조각만 건너뛴다).
    번역 결과는 이 함수(= 읽기 한 번) 안에서만 기억한다. 속도는 합성이 아니라 재생에서 적용하므로 번역 키는 글뿐이다.
    돌려주는 함수에 translated_of(글) 가 붙어 있다 — 그 조각 글의 번역문(읽기용 변환 전, 막에 쓸 글)이나 None.
      whisperer 가 원문 위 번역문 막(source_highlight caption)에 쓴다. 어느 스레드에서 불러도 된다(락).
    on_translated(글): 번역이 막 끝났을 때 합성 스레드에서 부른다(빨리 돌아와야 한다 — whisperer 는 gui_queue 에 넣기만).
      ⚠️ 첫 조각은 번역보다 "그 조각 칠하기"(segment 알림)가 먼저다(2026-09-29 실사용 로그: 형광펜 칠하기 → 번역 도착 순).
         그래서 segment 알림 때 translated_of 만 보면 첫 조각은 늘 번역문이 없다 → 도착 알림으로 다시 칠한다.
    """
    log = log or (lambda msg: None)
    cache = {}      # 조각 글(raw) → (번역문, 읽기용 변환한 글)
    lock = threading.Lock()

    def synth(text, rate):
        if text not in raw_texts:
            return synthesize(text, rate)
        with lock:
            done = cache.get(text)
        if done is None:
            try:
                translated = translate_segment(text, translate)
            except Exception as e:
                raise SegmentFailed(str(e) or type(e).__name__) from e
            log(f"[번역] {text[:60]!r} → {translated[:60]!r}")
            done = (translated, prepare(translated))
            with lock:
                cache[text] = done
            if on_translated is not None:
                try:
                    on_translated(text)
                except Exception as e:
                    log(f"[번역] 도착 알림 처리 오류: {e}")
        return synthesize(done[1], rate)

    def translated_of(text):
        with lock:
            done = cache.get(text)
        return done[0] if done else None

    synth.translated_of = translated_of
    return synth
