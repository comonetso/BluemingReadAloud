# -*- coding: utf-8 -*-
"""재생 엔진 — 조각(segment)을 차례로 합성해서 끊김 없이 이어 재생한다.

whisperer.py 에 있던 TTS 재생부(speak_text 의 _speak producer/consumer, _synthesize_chunk,
stop_current_playback 의 스트림 멈춤 부분)를 옮겨 와서 클래스 하나(TtsSession)로 묶었다.
옛 전처리·조각 함수(_preprocess_for_tts, _chunk_text_for_tts)는 readaloud_text.split_for_reading 으로 대체됐다.

소리 없이 테스트할 수 있게 바깥 의존성은 전부 "주입"받는다.
  - synthesize(text, rate) -> numpy int16 배열(24kHz 모노) 또는 None. 실패하면 예외를 던져도 된다.
      실제 앱에서는 make_google_synthesize() 가 만든 함수(Google Cloud TTS)를 넣는다.
      보통 예외·None 은 "그 조각만 건너뛰기" 다. SegmentFailed 를 던지면 건너뛰지 않고, 그 조각을 읽을 차례가
      왔을 때 읽기를 멈춘다(번역 실패 — translation.py, 2026-09-29 사용자 결정 "그 조각 차례에 멈춤").
  - open_stream() -> start/write/stop/abort/close 가 있는 출력 스트림.
      실제 앱에서는 sounddevice_stream_factory() 가 만든 함수(sd.OutputStream)를 넣는다.
  - clock() -> 초 단위 시각. 기본 time.monotonic. 테스트는 가짜 시계를 넣는다.

알림은 콜백 하나 on_event(kind, data) 로 보낸다.
  kind="session_start"  data={"source_text": 원문, "segments": split_for_reading 결과}
  kind="segment"        data=조각 번호(int)  — 형광펜을 옮길 때
  kind="state"          data={"state", "elapsed", "total", "progress", "can_prev", "can_next",
                              "can_mute", "muted", "rate", "volume"} — 하단 바 표시용
  kind="segment_failed" data={"index": 조각 번호, "message": 이유} — synthesize 가 SegmentFailed 를 던진 조각을
                        읽을 차례가 와서 읽기를 멈췄다. 앞 조각은 끝까지 들린다. 뒤이어 state·session_end 가 온다.
  kind="session_end"    data=None — 읽기가 끝났거나 멈췄다(맨 마지막에 딱 한 번)
  ⚠️ session_start(와 첫 segment·state)는 start() 를 부른 스레드에서, 나머지는 전부 재생 스레드 하나
     ("tts-player")에서만 보낸다. 보내는 스레드가 하나라서 순서가 뒤섞이지 않는다(일시정지를 눌렀는데 늦게 도착한
     옛 PLAYING 이 PAUSED 를 덮어쓰는 일이 없다). 예외: 재생 스레드를 띄우지 못하면 start() 가 대신
     STOPPED·session_end 를 보낸다(_abort_start). Tk 는 스레드 안전하지 않으므로 받는 쪽(whisperer.py)은
     여기서 UI 를 직접 만지지 말고 gui_queue 로 Tk 메인 스레드에 넘겨야 한다.
  ⚠️ on_event 는 빨리 돌아와야 한다(재생 스레드가 그동안 다음 블록을 못 쓴다). 엔진 락을 쥔 채로 부르지 않으므로
     on_event 안에서 세션 메서드(stop 등)를 불러도 교착은 없다.

확장(F:\\workspace\\EtcProject\\ChromeExtentions\\read-aloud-hrg, HEAD afae39a)에서 가져온 규칙과 값
  - 이전/다음 이동은 750ms 기다렸다가 실행, 그 사이 또 누르면 목표만 갱신       js/speech.js:35-36, 231-235
  - 이전: 지금 조각이 시작된 지 3초가 넘었으면 지금 조각을 처음부터, 아니면 이전 조각  js/speech.js:202-213 (3000 은 :206)
    첫 조각에서 이전 = 처음부터(기다리지 않음)                                   js/document.js:332-339
  - 이동·정지 뒤 늦게 도착한 결과는 재생 세대 번호로 버린다(확장의 playId 역할)     js/speech.js:229-241 debounce+switchMap
  - 로딩 표시는 소리를 2초 넘게 기다릴 때만(깜빡임 방지)                         js/speech.js:168-178
  - 이전/다음 버튼은 PLAYING·PAUSED 일 때만                                      js/page-ui.js:694-695
  - 총 시간은 처음엔 None("계산 중"), 그 뒤 잰 평균 속도로 추정                    js/page-ui-host.js:435-627 makePlaybackTiming
  - 바가 1초마다 시계를 갱신                                                     js/page-ui-host.js:327-343 startTick
  - 음소거는 재생을 멈추지 않고 소리만 끈다, 읽기가 끝나면 음소거도 풀린다          js/page-ui-host.js:105, 413-421
  - 합성 소리 재사용: 최근 것 2개, 글 하나당 1개, 늦게 끝난 옛 요청은 새 것을 못 덮음  js/tts-engines.js:385-407
    (키 = 읽을 글 + 합성 값. 아래 "합성 소리 재사용" 참고)
앱(옛 whisperer.py)에서 이어받은 값
  - 24kHz LINEAR16, 0.1초(2400샘플) 블록 쓰기, 선합성 2조각, 끝에 0.25초 무음 드레인, producer join 1초
  - 합성 결과의 WAV 머리 44바이트를 떼고 .copy() (frombuffer 결과는 읽기 전용이라 write 에서 문제될 수 있음)

⚠️ 절대 건드리면 안 되는 함정 (docs/session_logs/2026-06-07_work_log.md §4, 2026-07-27_work_log.md §10)
  1) 좀비 스레드: 옛 코드는 전역 tts_stop_event 하나를 모든 읽기가 같이 썼고, finally 에서 clear() 하면
     put(timeout) 에 갇힌 producer 의 while 조건이 되살아나 영원히 안 끝났다.
     → 여기서는 세션마다 자기 멈춤 신호(_stop_event)를 새로 만들고 **한 번 켜면 절대 끄지(clear) 않는다.**
       새 읽기는 새 TtsSession 객체를 만든다. 멈춤 신호를 재사용하거나 clear() 하는 코드를 넣지 마라.
  2) sd.stop() 은 OutputStream 을 못 멈춘다(sd.play/rec 전용). 정지는 반드시 stream.abort() 로.
  3) 다른 스레드에서 abort() 하는 순간 재생 스레드가 close() 하면 이미 해제된 스트림을 건드릴 수 있다
     → abort/stop/close 는 _stream_lock 으로 한 줄로 세운다. write() 는 락 밖에서 한다(그래야 abort 가 끼어든다).
     stop() 은 이 락을 기다리지 않는다(Tk 메인이 멈추지 않게 — stop() 설명).
  4) 새 읽기는 앞 읽기의 "스트림이 닫힘"(_stream_released)만 기다린다. 앞 읽기의 합성 스레드는 네트워크 요청이
     끝날 때까지 살아 있을 수 있지만, 멈춤 신호를 보고 결과를 버리고 끝나므로 좀비가 아니다.

2026-09-28 깨 보기에서 고친 것 (tests/test_tts_engine.py TestRobustness 가 재발을 막는다)
  - 합성 요청이 걸린 채 정지하면 session_end 가 1초 늦고 새 읽기도 1초 늦게 시작하던 것 → 끝 알림을 먼저, 스트림만 기다림
  - 합성 스레드가 예상 못 한 오류로 죽으면 재생 스레드가 영원히 기다리던 것 → _producer_failed 로 끝냄
  - 정상 종료 드레인 중 stop() 이 Tk 메인을 잡던 것 → 스트림 락을 기다리지 않음
  - 스레드 시작 실패 시 session_end 가 안 오고 합성 스레드가 남던 것 → _abort_start

합성 소리 재사용 (2026-09-28 추가 — 이동할 때마다 이미 합성한 조각까지 버리고 다시 요청하던 것)
  확장(GoogleWavenetTtsEngine, js/tts-engines.js:385-407)이 하는 일
    - prefetched 배열에 합성 결과를 "최근 것이 앞" 으로 최대 2개 둔다(:407 .slice(0, 2)).
    - 찾는 키는 (읽을 글, options 객체)(:393, :400). options 는 읽기마다 새로 만들고(document.js:276-285),
      합성에 들어가는 값을 바꾸면 새 객체로 바꾼다(speech.js:57-62 "audio made with the old values isn't reused",
      page-ui-host.js:220-236). → 결국 "같은 읽기 안에서 같은 글 + 같은 합성 값" 일 때만 재사용한다.
      (확장의 Google 음성은 속도를 합성이 아니라 오디오 재생 속도로 적용해서 속도를 바꿔도 같은 객체를 쓴다 —
       page-ui-host.js:223-227 updateParams. 2026-09-28 부터 이 앱도 같다: 합성은 늘 속도 SYNTH_RATE(1.0)로
       요청하고 재생할 때 _Stretcher 가 속도를 적용한다 → 속도를 바꿔도 캐시 키의 속도는 늘 1.0 이라 다시 요청하지 않는다.)

속도 즉시 반영 (2026-09-28 사용자 요청 "하단 바에서 속도를 바꿔도 즉시 반영이 안 된다 / 크롬 확장은 즉시 된다")
  예전: 속도를 합성 요청(speaking_rate)에 넣었다 → 이미 받은 소리는 옛 속도라 "다음 조각부터" 바뀌었다.
  지금: 확장처럼 합성은 1.0, 재생할 때 0.1초 블록마다 그 순간의 속도로 늘이고 줄인다(_Stretcher — audiotsm WSOLA,
        목소리 높낮이는 그대로). set_rate 는 값만 바꾸고, 다음 블록(0.1초 안)부터 새 속도다.
  재생 위치(_off)·조각 길이(_known_sec)는 "원본(1.0) 기준 샘플·초" 로 센다. 하단 바에 보내는 시간은 현재 속도로 나눈다.
    - 같은 글의 항목은 1개만 남긴다(:407 filter). 같은 글에 대해 더 늦게 보낸 요청의 결과가 이미 있으면
      먼저 보낸 요청이 늦게 끝나도 그걸 덮지 않는다(:405-406 seq 비교).
    - 재생(speak)은 캐시에서 꺼내 쓰기만 하고 지우지 않는다(:393). 확장이 미리 만드는 건 "다음 조각" 1개라
      (speech.js:251) 2칸이면 "다음 조각 + 지금 조각" 이 서로 밀어내지 않는다(:386-387 주석).
  이 앱에서 옮긴 모양 (TtsSession._cache)
    - 키 = (읽을 글, 속도). 음성은 세션마다 고정이다(whisperer.speak_text 가 세션을 만들 때 음성을 넣은
      synthesize 를 만든다). markup/평문 여부는 (글, 음성)으로 정해진다(readaloud_text.pauses_markup) —
      markup 이 거절돼 평문으로 다시 받은 소리도 확장처럼 그 글의 소리로 둔다. 그래서 캐시를 세션 안에만 두면
      (글, 속도)만으로 합성 결과가 하나로 정해진다. 새 읽기(새 세션)는 빈 캐시로 시작한다(확장도 읽기마다 새 options).
    - 크기 2, 글 하나당 1개, 늦은 옛 요청은 새 것을 못 덮음 — 확장 값 그대로.
      단, 같은 글 두 항목 중 한쪽만 "지금 속도" 소리면 그쪽을 남긴다(속도를 값으로 비교해서 생기는 차이 —
      _cache_put_locked 설명. 확장은 합성 값이 되돌아가는 일이 없어 순번만 봐도 됐다).
    - 다른 점(구조 차이): 이 앱은 조각을 "지금 + 앞으로 2개"(PREFETCH_AHEAD, 옛 앱 값) 까지 미리 합성해
      _ready/_audio 에 들고 있다. 이것이 확장 캐시의 "다음 + 지금" 에 해당한다. 이동·속도 변경 때 이 묶음 중
      새 자리에서도 쓸 것은 그대로 남기고, 못 쓰게 된 것만 캐시(2칸)로 옮긴다. 캐시에서 꺼내 쓰면 캐시에서
      빠진다(자리를 비워 다른 소리를 담게). 다 읽고 자연스럽게 지나간 조각은 옛 코드처럼 버린다(캐시에 안 넣음).
    - 세대 번호 규칙은 그대로다: 이동·속도 변경 전에 보낸 요청의 결과(옛 세대)는 재생 자리(_ready)에 절대
      넣지 않는다. 소리가 있으면 캐시에만 넣는다 — 나중에 (글, 속도)가 딱 맞을 때만 꺼내 쓰이므로
      옛 자리·옛 속도의 소리가 울릴 일은 없다.
    - 메모리: 24kHz int16 = 약 48KB/초. 캐시가 늘리는 몫은 최대 2조각.
"""

import re
import threading
import time
import traceback

import readaloud_text

__all__ = [
    "SAMPLE_RATE", "BLOCK_SAMPLES", "PREFETCH_AHEAD", "SYNTH_CACHE_SIZE", "MOVE_DELAY", "RESTART_AFTER", "LOADING_DELAY",
    "STATE_TICK", "DRAIN_SECONDS", "PRODUCER_JOIN_TIMEOUT", "RATE_MIN", "RATE_MAX", "VOLUME_MIN", "VOLUME_MAX",
    "TtsSession", "SegmentFailed", "make_google_synthesize", "sounddevice_stream_factory", "play_start_beep",
    "voice_lang_of", "voice_type_of", "clamp_rate", "clamp_volume", "is_silent_segment", "count_spoken_chars",
    "apply_gain", "pcm_from_linear16",
]

# ── 옛 앱(whisperer.py _speak/_synthesize_chunk)에서 쓰던 값 그대로 ─────────────────
SAMPLE_RATE = 24000          # LINEAR16 24kHz (옛 _synthesize_chunk)
BLOCK_SAMPLES = 2400         # 0.1초씩 write → 정지·일시정지 반응성 (옛 _speak BLOCK)
PREFETCH_AHEAD = 2           # 지금 조각 뒤로 최대 2조각까지 미리 합성 (옛 Queue(maxsize=2))
DRAIN_SECONDS = 0.25         # 정상 종료 때 마지막 소리가 장치로 빠져나가게 흘려보내는 무음 (옛 _speak)
PRODUCER_JOIN_TIMEOUT = 1.0  # 끝날 때 합성 스레드를 기다리는 한도 (옛 prod_thread.join(timeout=1.0))
WAV_HEADER_BYTES = 44        # LINEAR16 응답 앞의 WAV 머리 (옛 _synthesize_chunk)

# ── 확장 read-aloud-hrg 의 값 ───────────────────────────────────────────────
MOVE_DELAY = 0.75            # speech.js:35-36  forward/rewind {delay: 750}
RESTART_AFTER = 3.0          # speech.js:206    Date.now()-current.ts > 3000
LOADING_DELAY = 2.0          # speech.js:172    rxjs.timer(2000) — 소리를 2초 넘게 기다릴 때만 LOADING
STATE_TICK = 1.0             # page-ui-host.js:327-343 startTick — 재생 중 1초마다 바 갱신
SYNTH_CACHE_SIZE = 2         # tts-engines.js:407 prefetched ... .slice(0, 2) — 합성 소리 캐시 칸 수

# ── 범위 ───────────────────────────────────────────────────────────────────
# Cloud TTS AudioConfig.speaking_rate 허용 범위 = 0.25~4.0.
# 근거: ① 앱 TTS 설정 창 슬라이더가 옛날부터 0.25~4.0 (whisperer.py show_tts_settings_dialog)
#       ② 2026-09-28 실제 호출에서 speaking_rate=4.0 을 ko-KR-Chirp3-HD-Callirrhoe·ko-KR-Wavenet-A 둘 다 받아 줬다.
# ⚠️ 설치된 google-cloud-texttospeech 2.33.0 의 docstring(cloud_tts.py AudioConfig)은 "[0.25, 2.0], 넘으면 오류"
#    라고 적혀 있다. 실측과 다르다. 나중에 서버가 2.0 을 넘는 값을 거절하기 시작하면 여기를 2.0 으로 내려라
#    (거절되면 그 조각은 합성 실패로 건너뛰어진다).
RATE_MIN, RATE_MAX = 0.25, 4.0
# 재생 블록에 곱하는 게인. 1 을 넘기면 int16 이 깨지므로(클리핑) 0~1. 하단 바 슬라이더는 0.2~1(page-ui.js).
VOLUME_MIN, VOLUME_MAX = 0.0, 1.0

# 대기 한 번의 최대 길이(실제 시간). 이동 마감·로딩 표시 같은 "시각" 조건을 다시 확인하는 주기다.
# 옛 코드의 queue.get/put(timeout=0.2)·블록 0.1초와 같은 역할의 구현 세부값(동작 규칙이 아님).
POLL = 0.1


class SegmentFailed(Exception):
    """synthesize 가 이걸 던지면 그 조각은 건너뛰지 않는다 — 읽을 차례가 오면 읽기를 멈추고 segment_failed 를 보낸다.

    메시지(str(e))가 알림의 "message" 로 간다. 이동하면(이전/다음) 실패 기록은 지워지고 그 조각은 다시 요청된다.
    """


# ════════════════════════════════════════════════════════════════════
# 작은 도우미들
# ════════════════════════════════════════════════════════════════════

def voice_lang_of(voice_name):
    """음성 이름의 앞 두 덩어리 = 언어 코드. "ko-KR-Chirp3-HD-Callirrhoe" → "ko-KR".

    옛 _synthesize_chunk 와 같은 방식(split('-') 앞 두 개, 모자라면 "ko-KR")이다.
    split_for_reading 의 lang/voice_lang 과 합성 요청의 language_code 둘 다 이 값을 쓴다.
    """
    parts = str(voice_name or "").split("-")
    return f"{parts[0]}-{parts[1]}" if len(parts) >= 2 and parts[0] and parts[1] else "ko-KR"


def voice_type_of(voice_name):
    """음성 종류. "ko-KR-Chirp3-HD-Callirrhoe" → "Chirp3-HD", "ko-KR-Wavenet-A" → "Wavenet". 모르면 None.

    확장 tts-engines.js:455 의 정규식 /^([a-z]{2,3}-[A-Z]{2})-(\\S+)-(\\w+)$/ 과 같다.
    pauses_markup() 이 "Chirp3-HD" 인지 볼 때 쓴다.
    """
    m = re.match(r"^([a-z]{2,3}-[A-Z]{2})-(\S+)-(\w+)$", str(voice_name or ""))
    return m.group(2) if m else None


def clamp_rate(rate):
    """속도를 Cloud TTS 허용 범위로 자른다. 숫자가 아니면 1.0(Cloud TTS 의 '보통 속도')."""
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return 1.0
    if r != r:  # NaN
        return 1.0
    return min(RATE_MAX, max(RATE_MIN, r))


def clamp_volume(volume):
    """볼륨(게인)을 0~1 로 자른다. 숫자가 아니면 1.0(확장 defaults.js:36 volume 기본값)."""
    try:
        v = float(volume)
    except (TypeError, ValueError):
        return 1.0
    if v != v:
        return 1.0
    return min(VOLUME_MAX, max(VOLUME_MIN, v))


def is_silent_segment(text):
    """합성하지 않고 건너뛸 조각인가: 공백뿐이거나 "." 하나뿐.

    split_for_reading 은 확장처럼 이런 조각도 그대로 돌려준다(readaloud_text.py 모듈 설명의 "버릇").
    API 요청을 낭비하지 않도록 건너뛰되, 조각 번호는 그대로 둔다(형광펜 번호가 어긋나지 않게).
    """
    t = (text or "").strip()
    return t == "" or t == "."


def count_spoken_chars(text):
    """총 시간 추정에 쓰는 글자 수 = 공백을 뺀 글자 수 (page-ui-host.js:629-631 countSpokenChars)."""
    return len(re.sub(r"\s+", "", text or ""))


def apply_gain(block, gain):
    """재생 블록에 볼륨 게인을 곱한다. 1 이면 그대로, 0 이하(음소거)면 무음."""
    import numpy as np
    if gain >= 1.0:
        return block
    if gain <= 0.0:
        return np.zeros_like(block)
    return (block.astype(np.float32) * gain).astype(block.dtype)


# 합성 요청에 넣는 속도 — 늘 1.0. 실제 속도는 재생할 때 _Stretcher 가 적용한다(모듈 설명 "속도 즉시 반영")
SYNTH_RATE = 1.0


class _ListWriter:
    """audiotsm 출력 받이: 늘이고 줄인 소리 조각을 주인(_Stretcher)의 목록에 쌓는다(audiotsm Writer 약속: channels, write)."""
    channels = 1

    def __init__(self, owner):
        self._owner = owner

    def write(self, buffer):
        n = buffer.shape[1]
        if n:
            self._owner._out.append(buffer[0].copy())
            self._owner._out_len += n
        return n


class _Stretcher:
    """조각 하나의 소리를 재생 속도에 맞춰 0.1초 블록씩 늘이고 줄인다 — 확장이 audio.playbackRate 로 하는 일.

    왜: 확장의 Google 음성은 합성 요청에 속도를 넣지 않고 재생할 때 브라우저가 속도를 바꾼다(tts-engines.js:510-520)
        → 슬라이더를 움직이면 즉시 바뀐다. 이 앱은 소리를 직접 장치로 쓰므로 브라우저 대신 audiotsm 의 WSOLA
        (목소리 높낮이는 그대로 두고 빠르기만 바꾸는 방식)로 한다.
    어떻게: 블록이 필요할 때마다 원본에서 필요한 만큼만 읽어 늘이고 줄인다(조금씩 이어서 처리). 속도가 바뀌면
        set_speed 로 다음 블록부터 바로 새 속도다. 원본을 얼마나 읽었는지(consumed)를 돌려줘 재생 위치·시간 계산에 쓴다.
        (실측 2026-09-28: 10초 분량을 한 번에 29ms, 블록씩 이어서 50ms — 재생을 끊을 만큼 느리지 않다)
    ⚠️ WSOLA 는 끝부분 약 1,900샘플(80ms)을 내보내지 못한다(실측: 3초 72000 → 70144). 끝 음절이 잘리지 않게
       원본 끝에 무음 TAIL_PAD 샘플을 붙여 넣는다(05-23 "청크 끝 잘림" 과 같은 종류의 사고를 막으려고).
       그 대가로 조각 사이에 약 85ms/속도 의 무음이 생긴다(말 사이 쉼 정도).
    속도 1.0 이면 늘이고 줄이지 않고 원본을 그대로 내보낸다(음질이 원본 그대로). 재생 도중 1.0 ↔ 다른 속도를 오가면
    그 자리(원본에서 읽은 위치)에서 방식을 갈아탄다 — WSOLA → 원본으로 갈 때 WSOLA 안에 남은 수십 ms 는 버려진다.
    audiotsm 을 못 불러오면 늘 원본 그대로 내보낸다(속도 1.0 — 느리거나 빠르게는 못 함, 읽기는 된다).
    """
    TAIL_PAD = 2048

    def __init__(self, audio, rate):
        self._audio = audio
        self._total = len(audio)
        self._raw_off = 0          # 원본 그대로 모드에서 읽은 위치 / WSOLA 모드가 시작된 원본 위치
        self._tsm = None           # None = 원본 그대로 모드
        self._tsm_ok = True        # audiotsm 을 쓸 수 있는지(한 번 실패하면 이 조각에선 다시 안 해 본다)
        self._out = []
        self._out_len = 0
        self._in_done = False      # 마지막 write_to 가 "지금 입력으로 낼 것은 다 냈다" 고 했는지
        self._flushed = False
        self._speed = rate
        if not self._unity(rate):
            self._start_tsm(rate)

    @staticmethod
    def _unity(rate):
        return abs(float(rate) - 1.0) < 1e-6

    def _start_tsm(self, rate):
        """원본의 지금 위치(_raw_off)부터 WSOLA 로 늘이고 줄이기 시작한다."""
        import numpy as np
        try:
            from audiotsm import wsola
            from audiotsm.io.array import ArrayReader
            rest = self._audio[self._raw_off:]
            f = np.concatenate([rest.astype(np.float32) / 32768.0, np.zeros(self.TAIL_PAD, np.float32)])
            self._padded_total = len(f)
            self._reader = ArrayReader(f[np.newaxis, :])
            self._tsm = wsola(1, speed=rate)
            self._writer = _ListWriter(self)
            self._out, self._out_len = [], 0
            self._in_done = self._flushed = False
            self._speed = rate
        except Exception:
            self._tsm = None
            self._tsm_ok = False

    def consumed(self):
        """원본(무음 패딩 제외)에서 읽어 간 샘플 수. WSOLA 모드에서는 내부 버퍼만큼 약간 앞선 값이다(시간 표시용이라 충분)."""
        if self._tsm is None:
            return self._raw_off
        read = self._padded_total - self._reader._data.shape[1]
        return min(self._raw_off + read, self._total)

    def next_block(self, n, rate):
        """(블록 int16 최대 n 샘플, 이번에 원본을 더 읽은 샘플 수). 다 냈으면 빈 블록."""
        import numpy as np
        if self._tsm is not None and self._unity(rate) and not self._flushed:
            # WSOLA → 원본 그대로: 읽어 간 자리부터 원본을 직접 낸다(WSOLA 안에 남은 수십 ms 는 버림)
            self._raw_off = self.consumed()
            self._tsm = None
            self._out, self._out_len = [], 0
        elif self._tsm is None and not self._unity(rate) and self._tsm_ok and self._raw_off < self._total:
            self._start_tsm(rate)          # 원본 그대로 → WSOLA: 지금 자리부터
        if self._tsm is None:
            blk = self._audio[self._raw_off:self._raw_off + n]
            self._raw_off += len(blk)
            return blk, len(blk)
        if rate != self._speed:
            self._tsm.set_speed(rate)
            self._speed = rate
        before = self.consumed()
        guard = 0
        while self._out_len < n and not self._flushed and guard < 10000:
            guard += 1
            if self._in_done and self._reader.empty:
                # 입력을 다 넣었고 낼 것도 다 냈다 → 안에 남은 것을 마저 꺼낸다(audiotsm run() 과 같은 순서)
                for _ in range(10000):
                    _, fin = self._tsm.flush_to(self._writer)
                    if fin:
                        break
                self._tsm.clear()
                self._flushed = True
                break
            self._tsm.read_from(self._reader)
            _, self._in_done = self._tsm.write_to(self._writer)
        need = min(n, self._out_len)
        parts, got = [], 0
        while got < need:
            p = self._out[0]
            take = min(len(p), need - got)
            parts.append(p[:take])
            got += take
            if take == len(p):
                self._out.pop(0)
            else:
                self._out[0] = p[take:]
        self._out_len -= got
        if not parts:
            return np.zeros(0, dtype=np.int16), self.consumed() - before
        blk = np.clip(np.concatenate(parts) * 32768.0, -32768, 32767).astype(np.int16)
        return blk, self.consumed() - before

    @property
    def done(self):
        """이 조각 소리를 끝까지 다 냈는지."""
        if self._tsm is None:
            return self._raw_off >= self._total
        return self._flushed and self._out_len == 0


def pcm_from_linear16(audio_content):
    """LINEAR16 응답(WAV) → int16 배열. 머리 44바이트를 뗀다. 소리가 없으면 None. (옛 _synthesize_chunk)"""
    import numpy as np
    if not audio_content or len(audio_content) <= WAV_HEADER_BYTES:
        return None
    # .copy() — frombuffer 결과는 읽기 전용이라 일부 환경에서 OutputStream.write 에 문제가 된다(06-07 §4)
    return np.frombuffer(audio_content[WAV_HEADER_BYTES:], dtype=np.int16).copy()


def _markup_supported(tts):
    """설치된 google-cloud-texttospeech 의 SynthesisInput 에 markup 필드가 있는가 (2.33.0 에는 있음)."""
    try:
        return "markup" in tts.SynthesisInput.meta.fields
    except Exception:
        return False


def make_google_synthesize(client, tts, voice_name, sample_rate=SAMPLE_RATE, log=None):
    """Google Cloud TTS 로 조각 하나를 합성하는 함수 synthesize(text, rate) 를 만든다 (옛 _synthesize_chunk).

    client: texttospeech.TextToSpeechClient,  tts: texttospeech 모듈(요청 객체를 만드는 데 씀).
    한국어 Chirp3-HD 는 쉼표·화살표 자리 쉼을 markup 으로 먼저 요청하고, 거절되면(어떤 예외든) 평문으로
    다시 요청한다 — 확장 tts-engines.js:530-535 와 같다(쉼 없이라도 읽는 게 안 읽는 것보다 낫다).
    markup 은 readaloud_text.pauses_markup (tts-engines.js:542-550 이식)이 만든다. 해당 없으면 None → 평문.
    설치된 라이브러리에 markup 필드가 없으면 처음부터 평문만 쓴다.
    반환: int16 numpy 배열(24kHz) 또는 None(소리 없음). 요청 자체가 실패하면 예외가 올라간다.
    """
    log = log or (lambda msg: None)
    voice_lang = voice_lang_of(voice_name)
    voice_type = voice_type_of(voice_name)
    use_markup = _markup_supported(tts)

    def synthesize(text, rate):
        voice = tts.VoiceSelectionParams(language_code=voice_lang, name=voice_name)
        audio_config = tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            speaking_rate=clamp_rate(rate),
        )
        markup = readaloud_text.pauses_markup(text, voice_lang, voice_type) if use_markup else None
        if markup is not None:
            try:
                resp = client.synthesize_speech(input=tts.SynthesisInput(markup=markup),
                                                voice=voice, audio_config=audio_config)
                return pcm_from_linear16(resp.audio_content)
            except Exception as e:
                log(f"[TTS] markup 요청이 거절되어 평문으로 다시 요청합니다: {e}")
        resp = client.synthesize_speech(input=tts.SynthesisInput(text=text),
                                        voice=voice, audio_config=audio_config)
        return pcm_from_linear16(resp.audio_content)

    return synthesize


def sounddevice_stream_factory(sample_rate=SAMPLE_RATE):
    """실제 스피커 출력 스트림을 여는 함수를 만든다 (옛 _speak 의 sd.OutputStream 과 같은 설정).

    스트림 하나를 세션 내내 열어 두고 조각 PCM 을 이어서 write 하므로 조각 사이 끊김이 0 이다(gapless).
    """
    def open_stream():
        import sounddevice as sd
        return sd.OutputStream(samplerate=sample_rate, channels=1, dtype="int16")
    return open_stream


def play_start_beep():
    """읽기 시작 알림음 (옛 _speak 의 비프음 그대로: 880Hz, 0.2초, 크기 0.7, 44.1kHz).

    winsound 메모리 재생이라 sd.stop() 의 영향을 받지 않는다. 동기 재생(약 0.2초 멈춤)이라
    Tk 메인 스레드가 아니라 재생 스레드에서 불러야 한다(TtsSession 의 before_play 로 넘긴다).
    """
    import io
    import wave
    import winsound
    import numpy as np
    sr = 44100
    dur = 0.2
    samples = int(sr * dur)
    t = np.linspace(0, dur, samples, False)
    data = (np.sin(2 * np.pi * 880 * t) * 32767 * 0.7).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data.tobytes())
    winsound.PlaySound(buf.getvalue(), winsound.SND_MEMORY)


# ════════════════════════════════════════════════════════════════════
# 재생 세션
# ════════════════════════════════════════════════════════════════════

class TtsSession:
    """읽기 한 번 = 세션 하나. 합성 스레드(producer)와 재생 스레드(player) 두 개로 돈다.

    쓰는 법 (whisperer.py speak_text):
        s = TtsSession(원문, split_for_reading(...), synthesize, open_stream, on_event, rate=..., volume=...)
        s.start()
        s.command("togglePause") / s.forward() / s.rewind() / s.set_rate(1.2) / s.stop() ...
    명령 메서드는 어느 스레드에서 불러도 된다(내부 락). 명령은 값만 바꾸고 재생 스레드를 깨운다.
    실제 반영(이동 적용, 상태 알림)은 재생 스레드가 한다 → 알림 순서가 항상 맞다.

    위치를 나타내는 번호 두 개 (확장 speech.js 의 playlist index 와 switchMap 을 흉내 낸 것)
      _target: "지금 읽는(읽을) 조각". 이전/다음을 누르면 **즉시** 바뀐다(확장 playlist.forward()).
               형광펜·시간 표시·can_next 는 이것을 따른다(확장 page-ui-host 가 events 의 index 로 칠하는 것과 같다).
      _cur   : 재생 스레드가 실제로 소리를 내는(낼) 조각. 이동은 750ms 뒤에야 _cur 에 반영된다.
               그 사이에는 옛 조각 소리가 계속 나온다(확장 debounce 동안 switchMap 안쪽이 그대로인 것과 같다).
      _deadline: 기다리는 이동이 적용될 시각. None 이면 기다리는 이동 없음.
    세대 번호
      _synth_gen: 이동하거나 속도를 바꾸면 +1. 합성 스레드는 요청 전 세대를 기억했다가, 결과가 돌아왔을 때
                  세대가 달라져 있으면 재생 자리(_ready)에 넣지 않는다(확장 playId). → 늦게 도착한 옛 조각이
                  새 위치에서 울리지 않는다. 소리 자체는 캐시에 넣어 (글, 속도)가 맞을 때만 다시 쓴다.
    소리를 들고 있는 곳 (모듈 설명 "합성 소리 재사용")
      _audio : 지금 재생 중인 조각 소리 하나
      _ready : 미리 합성해 둔 조각. 조각 번호 → (소리 또는 None(실패), 합성 속도, 요청 순번)
               항상 "지금 조각 ~ 지금+PREFETCH_AHEAD" 안의 번호만 들어 있다.
      _cache : 이동·속도 변경으로 위 둘에서 빠진 소리 + 늦게 온 옛 세대 소리. [(글, 속도, 소리, 요청 순번)],
               최근 것이 앞, 최대 SYNTH_CACHE_SIZE(2)개, 글 하나당 1개 (확장 prefetched 배열)
    """

    def __init__(self, source_text, segments, synthesize, open_stream, on_event=None, *,
                 rate=1.0, volume=1.0, muted=False, can_mute=True, clock=time.monotonic,
                 before_play=None, previous=None, log=None,
                 sample_rate=SAMPLE_RATE, block=BLOCK_SAMPLES, prefetch=PREFETCH_AHEAD,
                 move_delay=MOVE_DELAY, restart_after=RESTART_AFTER, loading_delay=LOADING_DELAY,
                 tick=STATE_TICK, drain=DRAIN_SECONDS, poll=POLL, join_timeout=PRODUCER_JOIN_TIMEOUT,
                 cache_size=SYNTH_CACHE_SIZE):
        self.source_text = source_text
        self.segments = list(segments or [])
        self._texts = [(seg.get("text") if isinstance(seg, dict) else None) or "" for seg in self.segments]
        self._n = len(self._texts)
        self._blank = [is_silent_segment(t) for t in self._texts]

        self._synthesize = synthesize
        self._open_stream = open_stream
        self._on_event = on_event
        self._clock = clock
        self._before_play = before_play
        self._previous = previous
        self._log = log or (lambda msg: None)

        self._sr = int(sample_rate)
        self._block = int(block)
        self._prefetch = int(prefetch)
        self._move_delay = float(move_delay)
        self._restart_after = float(restart_after)
        self._loading_delay = float(loading_delay)
        self._tick = float(tick)
        self._drain = float(drain)
        self._poll = float(poll)
        self._join_timeout = float(join_timeout)
        self._cache_size = max(0, int(cache_size))

        # threading.Condition() 의 기본 락은 RLock 이다(같은 스레드가 다시 잡아도 막히지 않음).
        self._cond = threading.Condition()
        # ⚠️ 이 세션 전용 멈춤 신호. 한 번 set 하면 절대 clear 하지 않는다(모듈 설명의 함정 1).
        self._stop_event = threading.Event()
        # 스트림 abort/stop/close 를 한 줄로 세우는 락 (함정 3). write 는 이 락 밖에서 한다.
        self._stream_lock = threading.Lock()
        self._stream = None
        # "이 세션의 출력 스트림이 닫혔다(또는 끝내 열리지 않았다)" 신호. 다음 읽기가 이것만 기다리고 새 스트림을 연다.
        # ⚠️ 재생 스레드 전체(=합성 스레드 join 까지)를 기다리면, 합성 요청이 네트워크에 걸려 있을 때
        #    새 읽기가 최대 PRODUCER_JOIN_TIMEOUT(1초) 늦게 시작했다(2026-09-28 깨 보기 A2 로 재현) → 스트림만 기다린다.
        self._stream_released = threading.Event()

        self._version = 0            # 명령·합성 결과가 올 때마다 +1 → 재생 스레드가 대기 중에 놓치지 않게
        self._started = False
        self._finished = False       # 재생 스레드가 끝났다(정상 종료든 정지든)
        # 합성 스레드가 예상 못 한 오류로 죽었다. 이러면 더는 소리가 오지 않으므로 재생 스레드가 "error" 로 끝낸다.
        # (없으면 재생 스레드가 오지 않을 소리를 영원히 기다려 바가 "불러오는 중" 으로 멈춘다 — 깨 보기 B 로 재현)
        self._producer_failed = False

        # 위치와 이동 (클래스 설명 참고)
        self._cur = 0
        self._target = 0
        self._ts = None              # _target 이 정해진 시각 — 3초 규칙용 (확장 current.ts)
        self._deadline = None
        self._synth_gen = 0
        self._next_synth = 0         # 합성 스레드가 다음에 합성할 조각
        self._ready = {}             # 조각 번호 → (소리 또는 None(실패), 합성 속도, 요청 순번)
        # 조각 번호 → SegmentFailed 이유. 그 번호는 _ready 에 None 으로도 들어 있다. 이동 때 _ready 와 함께 비운다.
        self._failed = {}
        # 합성 소리 캐시 [(글, 속도, 소리, 요청 순번)] — 최근 것이 앞 (모듈 설명 "합성 소리 재사용")
        self._cache = []
        self._synth_seq = 0          # 합성 요청 순번(보낼 때마다 +1). 확장 prefetchSeq(tts-engines.js:389, 401)

        # 재생 스레드가 손에 든 소리
        self._audio = None
        self._audio_idx = None
        self._audio_rate = None      # 그 소리를 합성한 속도 (이동 때 새 자리에서 다시 쓸 수 있는지 판단)
        self._audio_seq = None       # 그 소리의 요청 순번
        self._off = 0                # 지금 소리(원본, 속도 1.0)에서 이미 읽은 샘플 수
        self._stretch = None         # 지금 소리를 재생 속도로 늘이고 줄이는 _Stretcher (조각마다 새로)
        self._played_any = False

        self._paused = False
        self._rate = clamp_rate(rate)
        self._volume = clamp_volume(volume)
        self._muted = bool(muted)
        self._can_mute = bool(can_mute)

        # 로딩 표시와 알림 관리
        self._waiting_since = None   # 소리를 기다리기 시작한 시각 (LOADING 판정)
        self._dirty = True           # 상태 알림을 새로 보내야 함
        self._last_emit = None
        self._last_state_name = None
        self._emitted_target = None  # 마지막으로 "segment" 알림을 보낸 조각
        self._outbox = []            # 락 안에서 모았다가 락 밖에서 보내는 알림

        # 총 시간 추정 (확장 makePlaybackTiming 취지)
        self._chars = [count_spoken_chars(t) for t in self._texts]
        # 조각의 실제 소리 길이(초). 모르면 None. 건너뛰는 조각은 0.
        self._known_sec = [0.0 if b else None for b in self._blank]
        # 속도 표본: 조각 번호 → (글자 수, 속도 1.0 으로 환산한 초). 속도를 바꿔도 버리지 않도록 환산해 둔다.
        self._speed_samples = {}

        self._producer = None
        self._player = None

    # ── 밖에서 부르는 것들 ────────────────────────────────────────────────

    @property
    def rate(self):
        return self._rate

    @property
    def volume(self):
        return self._volume

    @property
    def muted(self):
        return self._muted

    @property
    def state(self):
        """지금 상태 이름: "LOADING" | "PLAYING" | "PAUSED" | "STOPPED"."""
        with self._cond:
            return self._state_name_locked(self._clock())

    def start(self):
        """읽기를 시작한다. 알림(session_start → 첫 segment → 첫 state)을 이 스레드에서 보낸 뒤 두 스레드를 띄운다.

        첫 state 를 여기서 바로 보내는 이유: 재생 스레드는 앞 읽기 정리를 기다리고 비프음(0.2초)을 낸 뒤에야
        첫 알림을 보낸다. 그 사이 하단 바가 빈 채로 있지 않게 "재생 중, 00:00 / 계산 중" 을 먼저 그리게 한다.
        스레드를 띄우기 전에 보내므로 "session_start 가 항상 맨 앞" 순서는 그대로다.
        """
        with self._cond:
            if self._started:
                raise RuntimeError("TtsSession.start() 는 한 번만 부를 수 있다")
            self._started = True
            now = self._clock()
            self._ts = now             # 확장 "first": ts = Date.now()
            self._report_locked(now)
            first = self._outbox
            self._outbox = []
        self._emit("session_start", {"source_text": self.source_text, "segments": self.segments})
        self._flush(first)
        self._producer = threading.Thread(target=self._produce, name="tts-producer", daemon=True)
        self._player = threading.Thread(target=self._play, name="tts-player", daemon=True)
        try:
            self._producer.start()
            self._player.start()
        except Exception:
            # 스레드를 못 띄웠다(자원 부족 등, 드묾). 그냥 예외만 올리면 session_start 는 이미 나갔는데
            # session_end 는 영영 안 와서 → 하단 바가 떠 있고 tts_playing 이 True 로 굳고, 먼저 뜬 합성 스레드는
            # 멈춤 신호를 못 받아 남는다(깨 보기 D 로 재현). → 여기서 정리하고 끝 알림을 보낸 뒤 예외를 올린다.
            self._abort_start()
            raise

    def _abort_start(self):
        """start() 도중 스레드 시작이 실패했을 때: 멈춤 신호를 켜고 STOPPED·session_end 를 보낸다(재생 스레드 대신)."""
        with self._cond:
            self._stop_event.set()          # 먼저 뜬 합성 스레드가 있으면 이걸 보고 끝난다(끄지 않는다 — 함정 1)
            self._finished = True
            self._changed_locked()
            final = self._snapshot_locked(self._clock())
        self._stream_released.set()         # 스트림을 연 적이 없다 → 다음 읽기가 기다리지 않게
        self._log("[TTS] 재생 스레드를 시작하지 못해 읽기를 끝냅니다")
        self._emit("state", final)
        self._emit("session_end", None)

    def command(self, cmd, value=None):
        """하단 바 명령 이름으로 부르기 (bottom_bar.py on_command 와 같은 이름)."""
        if cmd == "togglePause":
            self.toggle_pause()
        elif cmd == "stop":
            self.stop()
        elif cmd == "forward":
            self.forward()
        elif cmd == "rewind":
            self.rewind()
        elif cmd == "mute":
            self.set_muted(True)
        elif cmd == "unmute":
            self.set_muted(False)
        elif cmd == "setRate":
            self.set_rate(value)
        elif cmd == "setVolume":
            self.set_volume(value)
        else:
            self._log(f"[TTS] 알 수 없는 명령: {cmd}")

    def stop(self):
        """읽기를 멈춘다. 몇 번 불러도 된다. 기다리지 않고 바로 돌아온다(스레드 정리는 join 으로 확인).

        멈춤 신호를 켜고 → 출력 스트림을 abort 해서 write() 에 걸린 재생 스레드를 즉시 풀어 준다.
        ⚠️ 신호는 끄지 않는다(함정 1). sd.stop() 이 아니라 abort 로 멈춘다(함정 2).

        스트림 락은 "기다리지 않고" 잡아 본다(blocking=False). 이 함수는 Tk 메인 스레드(단축키·하단 바 닫기)에서
        불리는데, 락을 쥔 쪽이 재생 스레드 finally 의 stream.stop()(남은 버퍼를 다 들려줄 때까지 막힘)이면
        그동안 화면 전체가 멈췄다(깨 보기 C 로 재현, 가짜 stop 0.4초 → stop() 도 0.4초).
        락을 못 잡아도 괜찮은 이유 — 락을 쥔 쪽은 둘 중 하나다:
          (a) 재생 스레드가 막 스트림을 등록하는 중 → 등록 직후 멈춤 신호를 보고 finally 에서 abort 한다.
          (b) 재생 스레드 finally 가 이미 스트림을 닫는 중 → 곧 닫힌다(남은 소리는 장치 버퍼 길이만큼).
          (c) 다른 스레드의 stop() 이 abort 하는 중 → 그쪽이 멈춘다.
        멈춤 신호를 락보다 "먼저" 켜기 때문에 (a)(b) 쪽이 신호를 놓치는 일은 없다.
        """
        with self._cond:
            self._stop_event.set()
            self._changed_locked()
        if not self._stream_lock.acquire(blocking=False):
            return
        try:
            stream = self._stream
            if stream is not None:
                try:
                    stream.abort()
                except Exception:
                    pass
        finally:
            self._stream_lock.release()

    def pause(self):
        with self._cond:
            if not self._stop_event.is_set() and not self._paused:
                self._paused = True
                self._changed_locked()

    def resume(self):
        with self._cond:
            if not self._stop_event.is_set() and self._paused:
                self._paused = False
                self._changed_locked()

    def toggle_pause(self):
        """일시정지 ↔ 재개 (확장 page-ui-host.js:144 state == "PAUSED" ? resume() : pause())."""
        with self._cond:
            if self._stop_event.is_set():
                return
            self._paused = not self._paused
            self._changed_locked()

    def forward(self):
        """다음 조각으로. 750ms 기다렸다가 옮긴다. 기다리는 동안 또 누르면 목표만 한 칸 더 간다.

        마지막 조각이면 아무것도 안 한다(하단 바는 can_next=False 로 버튼을 끈다).
        확장 speech.js:193-201(forward) + 231-235(debounce).
        """
        with self._cond:
            if self._stop_event.is_set():
                return
            if self._target + 1 >= self._n:
                self._log("[TTS] 다음: 마지막 조각이라 이동하지 않습니다")
                return
            now = self._clock()
            self._target += 1
            self._ts = now
            self._deadline = now + self._move_delay
            self._changed_locked()

    def rewind(self):
        """이전. 지금 조각이 시작된 지 3초가 넘었으면 지금 조각을 처음부터, 아니면 이전 조각으로(750ms 뒤).

        첫 조각이면 처음부터(기다리지 않음) — 확장 document.js:332-339 의 seek(0).
        "처음부터" 두 경우는 확장에서 delay 가 없는 seek 라 바로 적용한다(speech.js:206-208, document.js:337).
        "시작된 지"의 기준 시각은 확장처럼 조각이 정해진 순간(ts)이다 — 합성 대기 시간도 포함된다.
        """
        with self._cond:
            if self._stop_event.is_set():
                return
            now = self._clock()
            if self._ts is None:   # start() 전에 불린 경우(정상 흐름에선 없음) 계산이 깨지지 않게
                self._ts = now
            if self._target > 0 and not (now - self._ts > self._restart_after):
                self._target -= 1
                self._deadline = now + self._move_delay
            else:
                # 지금(_target) 조각을 처음부터. 마감을 "지금"으로 두면 재생 스레드가 다음 걸음에 바로 적용한다.
                # 기다리던 이동이 있었다면 이것으로 덮어쓴다(확장 debounce 는 마지막 명령만 남긴다).
                self._deadline = now
            self._ts = now
            self._changed_locked()

    def set_muted(self, muted):
        """음소거. 재생은 계속되고(시간도 흐름) 소리만 0 으로 쓴다 (확장 page-ui-host.js:413-421)."""
        with self._cond:
            if self._muted != bool(muted):
                self._muted = bool(muted)
                self._changed_locked()

    def set_volume(self, volume):
        """볼륨(0~1). 다음 블록(0.1초 안)부터 바로 적용 — 이미 합성한 소리에 게인을 곱할 뿐이다."""
        v = clamp_volume(volume)
        with self._cond:
            if v != self._volume:
                self._volume = v
                self._changed_locked()

    def set_rate(self, rate):
        """속도. **즉시**(다음 0.1초 블록부터) 적용한다 — 확장이 audio.playbackRate 를 바꾸는 것과 같다.

        합성은 늘 1.0 으로 받아 두고 재생할 때 _Stretcher 가 속도를 적용하므로(모듈 설명 "속도 즉시 반영"),
        여기서는 값만 바꾼다. 받아 둔 소리를 버리거나 다시 요청하지 않는다(세대 번호도 그대로).
        (예전에는 합성 요청 값이라 "다음 조각부터" 였고, 2026-09-28 사용자가 확장처럼 즉시 반영을 요청했다)
        """
        r = clamp_rate(rate)
        with self._cond:
            if self._stop_event.is_set() or r == self._rate:
                return
            self._rate = r
            self._changed_locked()

    def join(self, timeout=None):
        """두 스레드가 끝나기를 기다린다. 끝났으면 True. (시작 못 한 스레드는 건너뛴다 — join 하면 RuntimeError)"""
        deadline = None if timeout is None else time.monotonic() + timeout
        for t in (self._player, self._producer):
            if t is None or t.ident is None:
                continue
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            t.join(remaining)
        return not self.is_alive()

    def join_playback(self, timeout=None):
        """이 세션의 출력 스트림이 닫힐 때까지만 기다린다. 새 읽기가 옛 스트림 정리를 기다릴 때 쓴다(previous=).

        재생 스레드가 끝나기까지는 기다리지 않는다. 재생 스레드는 스트림을 닫은 뒤에도 합성 스레드를
        최대 1초 기다리는데(합성 요청이 네트워크에 걸려 있을 때), 새 읽기가 그 1초를 같이 기다릴 이유가 없다.
        합성 스레드의 늦은 결과는 멈춤 신호를 보고 버려진다. start() 를 부른 적이 없는 세션이면 바로 돌아온다.
        반환: 스트림이 닫혔으면 True.
        """
        if self._player is None:
            return True
        return self._stream_released.wait(timeout)

    def is_alive(self):
        return any(t is not None and t.is_alive() for t in (self._player, self._producer))

    # ── 내부: 공통 ───────────────────────────────────────────────────────

    def _changed_locked(self):
        """(락 안) 무언가 바뀌었다 → 상태 알림을 새로 보내고 기다리는 스레드를 깨운다."""
        self._version += 1
        self._dirty = True
        self._cond.notify_all()

    def _emit(self, kind, data):
        """알림 보내기. 받는 쪽에서 예외가 나도 재생은 계속한다."""
        if self._on_event is None:
            return
        try:
            self._on_event(kind, data)
        except Exception as e:
            self._log(f"[TTS] 알림 처리 오류({kind}): {e}")

    def _flush(self, out):
        for kind, data in out:
            self._emit(kind, data)

    # ── 내부: 합성 스레드 ─────────────────────────────────────────────────

    def _produce(self):
        """합성 스레드: _next_synth 부터 차례로 합성해 _ready 에 넣는다.

        - 지금 조각(_cur) 뒤로 최대 _prefetch 조각까지만 미리 합성한다(옛 Queue(maxsize=2) 역할).
        - 이동을 기다리는 동안(_deadline 있음)에는 새 요청을 하지 않는다 — 연타할 때 API 요청 낭비 방지.
        - 요청하기 전에 확인한다: 이미 _ready 에 있으면(이동 때 남긴 것) 건너뛰고, 캐시에 (글, 속도)가 같은
          소리가 있으면 꺼내 쓴다 → API 요청 없음. 둘 다 없을 때만 요청한다.
        - 요청 전 세대(_synth_gen)를 기억했다가, 돌아왔을 때 세대가 바뀌었으면 재생 자리(_ready)에 넣지 않는다
          (확장 playId). 소리가 있으면 캐시에만 넣는다 — 새 자리에서도 같은 (글, 속도)가 필요하면
          다음 걸음에 캐시에서 꺼내 쓰여 같은 요청을 두 번 보내지 않는다.
        - 공백뿐이거나 "." 뿐인 조각은 요청하지 않는다(재생 스레드가 번호만 넘긴다).
        - 멈춤 신호를 보면 바로 끝난다. 신호는 절대 꺼지지 않으므로 여기서 영원히 도는 일이 없다(함정 1).
          (캐시를 봐도 이 규칙은 그대로다 — 캐시 확인은 락 안에서 바로 끝나고 기다리지 않는다)
        """
        try:
            while True:
                with self._cond:
                    while True:
                        if self._stop_event.is_set():
                            return
                        idx = self._next_synth
                        if (self._deadline is None and idx < self._n
                                and idx <= self._cur + self._prefetch):
                            # 요청할 필요 없음 → 다음 번호로:
                            #   건너뛰는 조각 / 이미 지나간 조각 / 지금 재생 중인 조각 / 이미 _ready 에 있음 / 캐시에서 꺼냄
                            # ⚠️ "지나간·재생 중" 확인이 꼭 필요하다: 이동 때 남긴 소리(_ready[목표])는 재생 스레드가
                            #    이동을 적용한 그 락 안에서 바로 꺼내 재생을 시작한다. 합성 스레드는 그 뒤에 깨어나
                            #    _next_synth(=목표)를 보므로, 이 확인이 없으면 이미 재생 중인 조각을 또 요청하고
                            #    그 결과가 _ready 에 영영 안 쓰이는 채로 남는다(구현 중 발견. 이 확인을 빼면
                            #    tests TestSynthCache 의 "다음 후 이전"·"처음부터"·"늦은 결과" 테스트가 실패한다).
                            if (self._blank[idx] or idx < self._cur or idx == self._audio_idx
                                    or idx in self._ready or self._take_cached_locked(idx)):
                                self._next_synth = idx + 1
                                continue
                            break
                        self._cond.wait(self._poll)
                    gen = self._synth_gen
                    rate = SYNTH_RATE        # 합성은 늘 1.0 — 속도는 재생할 때 적용(모듈 설명 "속도 즉시 반영")
                    self._next_synth = idx + 1
                    self._synth_seq += 1
                    seq = self._synth_seq
                    text = self._texts[idx]
                audio = None
                failure = None
                try:
                    self._log(f"[TTS] 조각 {idx + 1}/{self._n} 합성 ({len(text)}자, 속도 {rate:.2f}): {text[:80]}")
                    audio = self._synthesize(text, rate)
                except SegmentFailed as e:
                    # 건너뛰지 않는다 — 이 조각 차례가 오면 재생 스레드가 읽기를 멈춘다(_step_locked)
                    failure = str(e)
                    self._log(f"[TTS] 조각 {idx + 1} 실패 — 차례가 오면 읽기를 멈춥니다: {failure}")
                except Exception as e:
                    # 실패한 조각은 건너뛴다(번호 유지). 옛 producer 도 실패 조각을 continue 로 건너뛰었다.
                    self._log(f"[TTS] 조각 {idx + 1} 합성 오류: {e}")
                    audio = None
                with self._cond:
                    if self._stop_event.is_set():
                        return
                    if gen != self._synth_gen:
                        # ⚠️ 옛 세대 결과는 재생 자리에 넣지 않는다(늦게 온 소리가 새 위치·새 속도에서 울리면 안 됨).
                        #    실패도 기록하지 않는다 — 새 자리에서 필요하면 다시 요청한다.
                        self._cache_put_locked(text, rate, audio, seq)
                        self._log(f"[TTS] 조각 {idx + 1}: 이동·속도 변경 전 요청이라 재생하지 않고 캐시에만 둡니다")
                        continue
                    if failure is not None:
                        self._failed[idx] = failure
                    self._put_ready_locked(idx, audio, rate, seq)
        except Exception:
            # 합성 요청 자체의 실패(네트워크·API 오류)는 위 안쪽 except 가 조각 하나만 건너뛰게 처리한다.
            # 여기까지 온 건 이 스레드의 예상 못 한 오류다 → 더는 소리를 못 만든다. 재생 스레드에 알려서
            # 오지 않을 소리를 영원히 기다리지 않고 끝내게 한다(_step_locked 가 _producer_failed 를 본다).
            self._log("[TTS] 합성 스레드 오류:\n" + traceback.format_exc())
            with self._cond:
                self._producer_failed = True
                self._changed_locked()

    # ── 내부: 재생 스레드 ─────────────────────────────────────────────────

    def _play(self):
        """재생 스레드: 스트림을 열고, 조각 소리를 0.1초 블록으로 이어서 쓴다. 알림도 전부 여기서 보낸다.

        끝나는 길은 셋: 다 읽음(finished) / stop()(stopped) / 오류. 어느 길이든 finally 에서
        스트림을 닫고 → 합성 스레드를 깨워 끝내고 → STOPPED 상태와 session_end 를 한 번 보낸다.
        ⚠️ finally 에서 멈춤 신호를 끄지(clear) 않는다. 오히려 켜서 합성 스레드를 확실히 끝낸다.
        """
        stream = None
        reason = "stopped"
        try:
            # 앞 읽기의 재생 스레드가 스트림을 닫을 때까지 기다린다(옛 코드의 "0.15초 정리 여유" 대신).
            # ⚠️ 앞 세션 참조는 여기서 한 번 쓰고 놓는다(self._previous = None). 들고 있으면 "읽는 중에 새 글을 읽힘"
            #    을 반복할 때 새 세션 → 앞 세션 → 그 앞 세션 … 으로 사슬이 이어져, 멈춘 세션마다 남아 있는 소리
            #    (_ready 최대 3 + _audio 1 + 합성 소리 캐시 최대 2 조각)가 사슬이 끝날 때까지 메모리에 남았다
            #    (2026-09-28 반증에서 발견 — 캐시가 세션마다 2조각을 더 붙잡게 되면서 커짐.
            #     tests TestSynthCache test_new_session_does_not_keep_previous_session_alive 가 재발을 막는다).
            previous, self._previous = self._previous, None
            if previous is not None:
                try:
                    previous.join_playback(self._join_timeout)
                except Exception:
                    pass
            previous = None
            if self._before_play is not None and not self._stop_event.is_set():
                try:
                    self._before_play()
                except Exception as e:
                    self._log(f"[TTS] 비프음 오류: {e}")
            if self._stop_event.is_set():
                return
            try:
                stream = self._open_stream()
                stream.start()
            except Exception as e:
                reason = "error"
                self._log(f"[TTS] 출력 장치를 열 수 없습니다: {e}")
                return
            with self._stream_lock:
                self._stream = stream
            if self._stop_event.is_set():
                # stop() 이 스트림을 모른 채 먼저 불렸다 → finally 에서 abort
                return
            reason = self._play_loop(stream)
            if reason == "finished" and self._played_any and not self._stop_event.is_set():
                # 마지막 소리가 장치로 빠져나가도록 무음을 한 번만 흘린다(조각마다 넣지 않음 → gapless 유지)
                try:
                    import numpy as np
                    stream.write(np.zeros(int(self._sr * self._drain), dtype=np.int16))
                except Exception:
                    pass
        except Exception:
            reason = "error"
            self._log("[TTS] 재생 스레드 오류:\n" + traceback.format_exc())
        finally:
            with self._stream_lock:
                if stream is not None:
                    try:
                        if self._stop_event.is_set():
                            stream.abort()   # 사용자 정지 → 즉시 멈춤
                        else:
                            stream.stop()    # 정상 종료 → 남은 버퍼를 다 들려주고 멈춤
                    except Exception:
                        pass
                    try:
                        stream.close()
                    except Exception:
                        pass
                self._stream = None
            # 스트림이 닫혔다(또는 열지 못했다) → 다음 읽기가 새 스트림을 열어도 된다(join_playback)
            self._stream_released.set()
            with self._cond:
                self._finished = True
                self._stop_event.set()        # 합성 스레드 종료 신호 (끄지 않는다)
                self._changed_locked()
                final = self._snapshot_locked(self._clock())
            # 끝 알림은 합성 스레드를 기다리기 "전에" 보낸다. 합성 요청이 네트워크에 걸려 있으면 join 이 최대 1초
            # 걸리는데, 그동안 하단 바가 "재생 중" 으로 남아 있었다(깨 보기 A1 로 재현). 합성 스레드는 알림을
            # 보내지 않으므로(알림은 이 스레드만 보냄) 순서를 바꿔도 "session_end 가 맨 마지막" 은 그대로다.
            self._log(f"[TTS] 재생 종료 ({reason})")
            self._emit("state", final)
            self._emit("session_end", None)
            if self._producer is not None and self._producer is not threading.current_thread():
                self._producer.join(self._join_timeout)

    def _play_loop(self, stream):
        """한 걸음씩: (락 안에서) 무엇을 할지 정하고 → (락 밖에서) 알림을 보내고 → 쓰거나 기다린다."""
        while True:
            with self._cond:
                action = self._step_locked()
                out = self._outbox
                self._outbox = []
                seen = self._version
            self._flush(out)
            kind = action[0]
            if kind == "done":
                return action[1]
            if kind == "wait":
                with self._cond:
                    # 알림을 보내는 사이에 명령이 들어왔으면(_version 변화) 기다리지 않고 바로 다시 본다
                    if self._version == seen and not self._stop_event.is_set():
                        self._cond.wait(max(0.0, min(self._poll, action[1])))
                continue
            # kind == "write" — 블로킹 write 는 락 밖에서. stop() 의 abort 가 여기를 풀어 준다.
            try:
                stream.write(action[1])
            except Exception as e:
                if self._stop_event.is_set():
                    return "stopped"
                raise RuntimeError(f"출력 스트림 쓰기 실패: {e}")
            with self._cond:
                self._after_write_locked(action[2])

    def _step_locked(self):
        """(락 안) 다음에 할 일: ("write", 블록, 샘플 수) | ("wait", 초) | ("done", 이유)."""
        if self._stop_event.is_set():
            return ("done", "stopped")
        now = self._clock()

        # 1) 기다리던 이동이 때가 됐으면 적용
        if self._deadline is not None and now >= self._deadline:
            self._apply_move_locked()

        # 2) 손에 든 소리가 없으면 다음 조각 소리를 준비
        while self._audio is None:
            if self._deadline is not None:
                # 지금 조각이 끝났는데 이동을 기다리는 중 → 이동이 다음 위치를 정한다(확장: movePending 이면 자동 forward 안 함)
                self._report_locked(now)
                return ("wait", self._deadline - now)
            if self._cur >= self._n:
                return ("done", "finished")
            if self._blank[self._cur]:
                self._advance_locked(now)
                continue
            entry = self._ready.pop(self._cur, None)
            if entry is None:
                if self._producer_failed:
                    # 합성 스레드가 죽어서 이 조각 소리는 영영 안 온다 → 기다리지 말고 끝낸다(원인은 로그에 있음)
                    self._log(f"[TTS] 합성 스레드가 멈춰 조각 {self._cur + 1} 부터 읽을 수 없습니다")
                    return ("done", "error")
                if self._waiting_since is None:
                    self._waiting_since = now
                self._report_locked(now)
                return ("wait", self._poll)
            self._waiting_since = None
            audio, rate, seq = entry
            failure = self._failed.pop(self._cur, None)
            if failure is not None:
                # SegmentFailed — 건너뛰지 않고 여기서 읽기를 멈춘다. 앞 조각 소리는 이미 다 썼다(finally 의 stream.stop()
                # 이 남은 버퍼를 다 들려주고 멈춘다). 알림은 _outbox 로 → 락 밖에서 state·session_end 보다 먼저 나간다.
                self._log(f"[TTS] 조각 {self._cur + 1}: 실패한 조각이라 읽기를 멈춥니다")
                self._outbox.append(("segment_failed", {"index": self._cur, "message": failure}))
                return ("done", "segment_failed")
            if audio is None or len(audio) == 0:
                # 합성 실패(또는 빈 소리) → 건너뛴다. 번호는 그대로라 뒤 조각의 형광펜이 어긋나지 않는다
                self._log(f"[TTS] 조각 {self._cur + 1}: 소리가 없어 건너뜁니다")
                self._advance_locked(now)
                continue
            self._audio = audio
            self._audio_idx = self._cur
            self._audio_rate = rate
            self._audio_seq = seq
            self._off = 0
            self._stretch = _Stretcher(audio, self._rate)   # 이 조각을 재생 속도로 늘이고 줄일 부품(조각마다 새로)
            self._dirty = True

        # 3) 일시정지 중이면 쓰지 않고 기다린다 (장치는 버퍼가 비면 무음을 낸다 — 옛 코드도 조각 사이에 그랬다)
        if self._paused:
            self._report_locked(now)
            wait = self._poll if self._deadline is None else self._deadline - now
            return ("wait", wait)

        # 4) 다음 블록 — 지금 속도로 늘이고 줄인 0.1초(속도를 바꾸면 이 블록부터 바로 새 속도).
        #    볼륨·음소거는 게인으로 — 역시 다음 블록부터 바로 적용. 세 번째 값은 "원본에서 더 읽은 양"(재생 위치용).
        block, consumed = self._stretch.next_block(self._block, self._rate)
        if len(block) == 0:
            # 늘이고 줄인 소리를 끝까지 다 냈다 → 조각 끝. 다음 조각으로 넘어가 한 걸음 더 본다
            self._finish_audio_locked()
            return self._step_locked()
        gain = 0.0 if self._muted else self._volume
        self._report_locked(now)
        return ("write", apply_gain(block, gain), consumed)

    def _after_write_locked(self, count):
        """(락 안) 블록을 다 썼다(count = 그 블록이 원본에서 읽은 샘플 수). 조각 끝이면 다음 조각으로 넘어간다."""
        self._off += count
        self._played_any = True
        if self._audio is not None and self._stretch is not None and self._stretch.done:
            self._finish_audio_locked()

    def _finish_audio_locked(self):
        """(락 안) 지금 조각을 다 냈다 → 소리를 놓고, 이동을 기다리는 중이 아니면 다음 조각으로."""
        # 다 읽은 조각의 소리는 버린다(캐시에 넣지 않음 — 옛 코드와 같다. 모듈 설명 "합성 소리 재사용")
        self._audio = None
        self._audio_idx = None
        self._audio_rate = None
        self._audio_seq = None
        self._off = 0
        self._stretch = None
        if self._deadline is None:
            # 확장 speech.js:254-258 — "end" 이고 이동 대기 중이 아니면 다음 조각으로(지연 없음, ts 새로)
            self._advance_locked(self._clock())

    def _advance_locked(self, now):
        """(락 안) 자연스럽게 다음 조각으로. 세대는 그대로(미리 합성한 소리를 그대로 쓴다)."""
        self._cur += 1
        self._target = self._cur
        self._ts = now
        self._waiting_since = None
        self._cond.notify_all()   # 합성 스레드: 미리 합성할 창이 한 칸 밀렸다

    def _apply_move_locked(self):
        """(락 안) 기다리던 이동을 적용: 목표 조각부터 (처음부터) 재생한다.

        옛 코드는 여기서 들고 있던 소리(지금 조각 + 미리 합성한 조각)를 전부 버리고 다시 요청했다.
        (2차 UI 검증: 고유 조각 6개에 합성 요청 15번, 되돌아갈 때 소리를 기다리는 무음)
        이제는 들고 있던 소리 중 새 자리("목표 ~ 목표+PREFETCH_AHEAD")에서 같은 속도로 다시 쓸 것은 남기고
        (지금 조각을 처음부터 다시 읽을 때도 요청 없이 바로 처음부터), 나머지는 캐시(2칸)로 옮긴다.
        세대 번호는 그대로 올린다: 지금 합성 중이던 요청의 결과는 재생 자리에 넣지 않고 캐시에만 넣는다(확장 playId).
        """
        self._deadline = None
        self._cur = self._target
        self._synth_gen += 1      # 합성 중이던 결과는 돌아와도 재생 자리에 넣지 않는다(확장 playId)
        outgoing = self._take_ready_locked()
        if self._audio is not None and len(self._audio) > 0:
            # 읽던 소리도 통째로(처음부터 다시 쓸 수 있게) 내놓는다. _off 는 아래에서 0 으로
            outgoing.append((self._audio_idx, self._audio, self._audio_rate, self._audio_seq))
        self._audio = None
        self._audio_idx = None
        self._audio_rate = None
        self._audio_seq = None
        self._off = 0
        self._stretch = None
        self._next_synth = self._cur
        self._refill_window_locked(self._cur, outgoing)
        self._waiting_since = None
        self._dirty = True
        self._cond.notify_all()
        self._log(f"[TTS] 이동: 조각 {self._cur + 1}/{self._n} 부터")

    # ── 내부: 합성 소리 재사용 (모듈 설명 "합성 소리 재사용") ─────────────────────

    def _put_ready_locked(self, idx, audio, rate, seq):
        """(락 안) 조각 idx 의 소리를 재생 자리(_ready)에 넣고, 그 길이로 시간 추정 자료를 갱신한다.

        합성 결과가 왔을 때와 캐시에서 꺼냈을 때 둘 다 여기로 온다(길이·속도 표본 계산이 한 군데에 있게).
        audio 가 None/빈 소리면 "실패" 로 넣는다 → 재생 스레드가 건너뛴다.
        """
        self._ready[idx] = (audio, rate, seq)
        if audio is not None and len(audio) > 0:
            sec = len(audio) / self._sr
            self._known_sec[idx] = sec
            if self._chars[idx] > 0:
                self._speed_samples[idx] = (self._chars[idx], sec * rate)
        else:
            self._known_sec[idx] = 0.0
        self._changed_locked()

    def _take_ready_locked(self):
        """(락 안) _ready 를 비우고, 그 안의 "쓸 수 있는 소리" 를 [(번호, 소리, 속도, 순번)] 로 돌려준다.

        실패(None)·빈 소리는 돌려주지 않는다 — 이동 뒤 다시 요청하게 둔다(옛 코드와 같다. 확장도 실패한
        prefetch 는 캐시에 넣지 않는다 — tts-engines.js:410-413 catch → false).
        """
        out = [(i, a, r, s) for i, (a, r, s) in self._ready.items() if a is not None and len(a) > 0]
        self._ready = {}
        self._failed = {}    # 실패(SegmentFailed)도 잊는다 — 새 자리에서 필요하면 다시 요청한다(번역 재시도)
        return out

    def _refill_window_locked(self, first, outgoing):
        """(락 안) 이동·속도 변경 뒤: 새 창(first ~ _cur+_prefetch)에 쓸 소리를 채우고 나머지는 캐시로 보낸다.

        outgoing: 재생 자리에서 빠진 소리 [(번호, 소리, 속도, 순번)]. 순서가 중요하다:
          1) 새 창의 각 조각에 대해 — outgoing 에 같은 번호·같은 속도 소리가 있으면 그대로 _ready 로,
             없으면 캐시에서 (글, 속도)가 같은 것을 꺼낸다.
          2) 그다음에 남은 outgoing 을 캐시에 넣는다(오래 전에 요청한 것부터 넣어 최근 것이 앞에 오게).
          → 1)을 먼저 해야 한다. 거꾸로 하면 남은 것을 넣느라 새 창에 필요한 캐시 소리가 밀려나 버린다
            (예: "다음" 뒤 "이전 두 번" 으로 돌아가면 돌아갈 자리의 소리가 캐시에서 밀려 다시 요청하게 된다).
        같은 번호면 글도 같으므로(세션 안에서 조각 글은 안 바뀐다) 번호+속도가 같으면 같은 소리다.
        채우지 못한 번호는 합성 스레드가 _next_synth 부터 차례로 처리한다(거기서도 캐시를 한 번 더 본다).
        """
        by_idx = {}
        for item in outgoing:
            by_idx[item[0]] = item
        last = min(self._n - 1, self._cur + self._prefetch)
        for i in range(max(0, first), last + 1):
            if self._blank[i] or i in self._ready:
                continue
            item = by_idx.get(i)
            if item is not None and item[2] == SYNTH_RATE:
                del by_idx[i]
                self._put_ready_locked(i, item[1], item[2], item[3])
            else:
                self._take_cached_locked(i)
        for i, audio, rate, seq in sorted(by_idx.values(), key=lambda it: it[3]):
            self._cache_put_locked(self._texts[i], rate, audio, seq)

    def _take_cached_locked(self, idx):
        """(락 안) 캐시에 조각 idx 의 (글, 지금 속도) 소리가 있으면 꺼내서 _ready 에 넣고 True.

        키 = (글, 속도). 음성·markup 여부가 키에 없는 이유는 모듈 설명 참고(세션마다 음성 고정, 캐시도 세션 안).
        확장은 꺼내 쓴 뒤에도 캐시에 남겨 두지만(tts-engines.js:393), 여기서는 꺼내면 캐시에서 뺀다 —
        꺼낸 소리는 _ready/_audio 가 들고 있으므로, 캐시 2칸은 그 밖의 소리를 담는 데 쓴다(모듈 설명 "다른 점").
        """
        if not self._cache:
            return False
        text = self._texts[idx]
        rate = SYNTH_RATE    # 합성은 늘 1.0 — 재생 속도와 상관없이 같은 소리를 쓴다
        for j, (t, r, audio, seq) in enumerate(self._cache):
            if t == text and r == rate:
                del self._cache[j]
                self._put_ready_locked(idx, audio, r, seq)
                self._log(f"[TTS] 조각 {idx + 1}: 합성해 둔 소리를 다시 씁니다(요청 없음, 속도 {r:.2f})")
                return True
        return False

    def _cache_put_locked(self, text, rate, audio, seq):
        """(락 안) 소리 하나를 캐시 맨 앞에 넣는다. 확장 tts-engines.js:403-407 prefetch 의 then 과 같은 규칙:

          - 같은 글의 항목은 1개만 남긴다(:407 filter). 같은 글 항목이 이미 있으면 둘 중 하나만 고른다:
              ① 한쪽만 "지금 속도" 소리면 그쪽을 남긴다(아래 "왜").
              ② 둘 다 지금 속도이거나 둘 다 아니면 확장 규칙 — 더 늦게 보낸 요청(순번이 큰 것)을 남긴다(:405-406).
          - 맨 앞에 넣고 SYNTH_CACHE_SIZE(2)개만 남긴다 — 넘치면 가장 오래 전에 넣은 것부터 버린다(:407 slice).
        실패(None)·빈 소리는 넣지 않는다(:410-413 — 확장도 실패는 캐시에 넣지 않는다).

        왜 ① 이 필요한가 (2026-09-28 반증에서 찾은 결함 — tests TestSynthCache
        test_rate_back_then_move_keeps_current_rate_sound 가 재발을 막는다):
          확장은 순번만 본다. 확장에서는 합성 값을 바꾸면 options 가 "새 객체" 가 되고 옛 객체로 돌아가는 일이
          없어서(speech.js:57-62), "더 늦게 보낸 요청" 이 곧 "지금 값으로 만든 소리" 였다. 이 앱은 속도를 값으로
          비교하므로(1.0 → 1.5 → 1.0 이면 1.0 소리를 다시 쓴다) 이 등식이 깨진다. 순번만 보면
          "속도 1.0 → 1.5 → 1.0 으로 되돌린 뒤 이전 두 번" 에서, 창을 떠나는 1.0 소리(먼저 보낸 요청)가
          캐시에 남아 있던 1.5 소리(나중 요청)에 막혀 버려지고, 쓸모없는 1.5 소리만 남아 조각 3·4 를 1.0 으로
          다시 요청했다. → "지금 속도" 를 먼저 보고, 같을 때만 확장의 순번 규칙을 쓴다.
          (이것은 요청 횟수만 바꾼다. 어떤 소리가 울리는지는 키(글, 속도)가 정하므로 그대로다.)
        """
        if audio is None or len(audio) == 0 or self._cache_size <= 0:
            return
        new_now = rate == SYNTH_RATE
        for t, r, _a, s in self._cache:
            if t != text:
                continue
            old_now = r == SYNTH_RATE
            if old_now and not new_now:
                return                      # ① 지금 속도 소리를 옛 속도 소리가 밀어내지 못한다
            if old_now == new_now and s > seq:
                return                      # ② 확장 :405-406 — 먼저 보낸 요청은 나중 요청을 못 덮는다
        self._cache = [(text, rate, audio, seq)] + [e for e in self._cache if e[0] != text]
        del self._cache[self._cache_size:]

    # ── 내부: 상태·시간 계산 ──────────────────────────────────────────────

    def _state_name_locked(self, now):
        if self._finished or self._stop_event.is_set():
            return "STOPPED"
        if self._paused:
            return "PAUSED"
        if self._waiting_since is not None and now - self._waiting_since > self._loading_delay:
            return "LOADING"
        return "PLAYING"

    def _report_locked(self, now):
        """(락 안) 보낼 알림을 _outbox 에 모은다: 목표 조각이 바뀌었으면 segment, 필요하면 state."""
        t = self._target
        if t != self._emitted_target and 0 <= t < self._n and not self._blank[t]:
            self._emitted_target = t
            self._outbox.append(("segment", t))
        name = self._state_name_locked(now)
        if name != self._last_state_name:
            self._dirty = True
        if name == "PLAYING" and (self._last_emit is None or now - self._last_emit >= self._tick):
            self._dirty = True
        if self._dirty:
            self._dirty = False
            self._last_emit = now
            self._last_state_name = name
            self._outbox.append(("state", self._snapshot_locked(now)))

    def _speed1_locked(self):
        """속도 1.0 기준 평균 말하기 속도(글자/초). 아직 잰 것이 없으면 None."""
        chars = 0
        secs = 0.0
        for c, s in self._speed_samples.values():
            if c > 0 and s > 0:
                chars += c
                secs += s
        return chars / secs if chars > 0 and secs > 0 else None

    def _snapshot_locked(self, now):
        """(락 안) 하단 바에 보낼 상태 dict (bottom_bar.BottomBar.update 약속 모양)."""
        name = self._state_name_locked(now)
        speed1 = self._speed1_locked()
        rate = self._rate
        n = self._n

        # 시간은 "지금 속도로 들었을 때" 초로 보낸다: 조각 길이(_known_sec)·재생 위치(_off)는 원본(1.0) 기준이라 속도로 나눈다
        def estimate(i):
            if self._known_sec[i] is not None:
                return self._known_sec[i] / rate
            return self._chars[i] / (speed1 * rate) if speed1 else 0.0

        target = min(self._target, n)
        # 목표 조각의 소리를 지금 내고 있을 때만 그 안에서 흐른 시간을 센다(이동 대기 중이면 0 — 확장 switchTo 와 같음)
        if (self._audio is not None and self._audio_idx == self._target and self._deadline is None):
            cur_played = self._off / self._sr / rate
        else:
            cur_played = 0.0
        elapsed = sum(estimate(i) for i in range(target)) + cur_played

        total = None
        if speed1 is not None:
            total = 0.0
            for i in range(n):
                total += max(estimate(i), cur_played) if i == target else estimate(i)

        if total:
            progress = min(1.0, elapsed / total)
        else:
            total_chars = sum(self._chars)
            if total_chars and target < n:
                known = self._known_sec[target]
                known = known / rate if known else known
                frac = cur_played / known if known else 0.0
                progress = (sum(self._chars[:target]) + frac * self._chars[target]) / total_chars
            else:
                progress = 1.0 if (total_chars and target >= n) else 0.0
            progress = max(0.0, min(1.0, progress))

        navigable = name in ("PLAYING", "PAUSED")
        return {
            "state": name,
            "elapsed": elapsed,
            "total": total,
            "progress": progress,
            "can_prev": navigable,
            "can_next": navigable and self._target + 1 < n,
            "can_mute": self._can_mute,
            "muted": self._muted,
            "rate": rate,
            "volume": self._volume,
        }
