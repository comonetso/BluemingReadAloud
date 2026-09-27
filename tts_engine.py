# -*- coding: utf-8 -*-
"""재생 엔진 — 조각(segment)을 차례로 합성해서 끊김 없이 이어 재생한다.

whisperer.py 에 있던 TTS 재생부(speak_text 의 _speak producer/consumer, _synthesize_chunk,
stop_current_playback 의 스트림 멈춤 부분)를 옮겨 와서 클래스 하나(TtsSession)로 묶었다.
옛 전처리·조각 함수(_preprocess_for_tts, _chunk_text_for_tts)는 readaloud_text.split_for_reading 으로 대체됐다.

소리 없이 테스트할 수 있게 바깥 의존성은 전부 "주입"받는다.
  - synthesize(text, rate) -> numpy int16 배열(24kHz 모노) 또는 None. 실패하면 예외를 던져도 된다.
      실제 앱에서는 make_google_synthesize() 가 만든 함수(Google Cloud TTS)를 넣는다.
  - open_stream() -> start/write/stop/abort/close 가 있는 출력 스트림.
      실제 앱에서는 sounddevice_stream_factory() 가 만든 함수(sd.OutputStream)를 넣는다.
  - clock() -> 초 단위 시각. 기본 time.monotonic. 테스트는 가짜 시계를 넣는다.

알림은 콜백 하나 on_event(kind, data) 로 보낸다.
  kind="session_start"  data={"source_text": 원문, "segments": split_for_reading 결과}
  kind="segment"        data=조각 번호(int)  — 형광펜을 옮길 때
  kind="state"          data={"state", "elapsed", "total", "progress", "can_prev", "can_next",
                              "can_mute", "muted", "rate", "volume"} — 하단 바 표시용
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
"""

import re
import threading
import time
import traceback

import readaloud_text

__all__ = [
    "SAMPLE_RATE", "BLOCK_SAMPLES", "PREFETCH_AHEAD", "MOVE_DELAY", "RESTART_AFTER", "LOADING_DELAY",
    "STATE_TICK", "DRAIN_SECONDS", "PRODUCER_JOIN_TIMEOUT", "RATE_MIN", "RATE_MAX", "VOLUME_MIN", "VOLUME_MAX",
    "TtsSession", "make_google_synthesize", "sounddevice_stream_factory", "play_start_beep",
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
                  세대가 달라져 있으면 버린다(확장 playId). → 늦게 도착한 옛 조각이 새 위치에서 울리지 않는다.
    """

    def __init__(self, source_text, segments, synthesize, open_stream, on_event=None, *,
                 rate=1.0, volume=1.0, muted=False, can_mute=True, clock=time.monotonic,
                 before_play=None, previous=None, log=None,
                 sample_rate=SAMPLE_RATE, block=BLOCK_SAMPLES, prefetch=PREFETCH_AHEAD,
                 move_delay=MOVE_DELAY, restart_after=RESTART_AFTER, loading_delay=LOADING_DELAY,
                 tick=STATE_TICK, drain=DRAIN_SECONDS, poll=POLL, join_timeout=PRODUCER_JOIN_TIMEOUT):
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
        self._ready = {}             # 조각 번호 → (소리 또는 None(실패), 합성 속도)

        # 재생 스레드가 손에 든 소리
        self._audio = None
        self._audio_idx = None
        self._off = 0                # 지금 소리에서 이미 쓴 샘플 수
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
        """속도. 합성에 들어가는 값이라 **다음 조각부터** 적용한다.

        지금 나오는 조각은 그대로 끝까지 듣고, 미리 합성해 둔 조각(옛 속도)은 버리고 새 속도로 다시 합성한다.
        확장의 "같은 위치에서 바꿔 끼우기(swapSegment)"는 이번 범위 밖이다.
        """
        r = clamp_rate(rate)
        with self._cond:
            if self._stop_event.is_set() or r == self._rate:
                return
            self._rate = r
            self._synth_gen += 1          # 합성 중이던 옛 속도 결과는 돌아와도 버린다
            self._ready.clear()
            have_current = self._audio is not None and self._audio_idx == self._cur
            self._next_synth = self._cur + 1 if have_current else self._cur
            # 아직 안 읽은 조각의 길이는 새 속도로 다시 재야 한다 → 추정으로 돌린다
            for i in range(self._next_synth, self._n):
                if not self._blank[i]:
                    self._known_sec[i] = None
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
        - 요청 전 세대(_synth_gen)를 기억했다가, 돌아왔을 때 세대가 바뀌었으면 결과를 버린다(확장 playId).
        - 공백뿐이거나 "." 뿐인 조각은 요청하지 않는다(재생 스레드가 번호만 넘긴다).
        - 멈춤 신호를 보면 바로 끝난다. 신호는 절대 꺼지지 않으므로 여기서 영원히 도는 일이 없다(함정 1).
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
                            break
                        self._cond.wait(self._poll)
                    gen = self._synth_gen
                    rate = self._rate
                    self._next_synth = idx + 1
                    blank = self._blank[idx]
                    text = self._texts[idx]
                if blank:
                    continue
                audio = None
                try:
                    self._log(f"[TTS] 조각 {idx + 1}/{self._n} 합성 ({len(text)}자, 속도 {rate:.2f}): {text[:80]}")
                    audio = self._synthesize(text, rate)
                except Exception as e:
                    # 실패한 조각은 건너뛴다(번호 유지). 옛 producer 도 실패 조각을 continue 로 건너뛰었다.
                    self._log(f"[TTS] 조각 {idx + 1} 합성 오류: {e}")
                    audio = None
                with self._cond:
                    if self._stop_event.is_set():
                        return
                    if gen != self._synth_gen:
                        self._log(f"[TTS] 조각 {idx + 1}: 이동·속도 변경 전 요청이라 결과를 버립니다")
                        continue
                    self._ready[idx] = (audio, rate)
                    if audio is not None and len(audio) > 0:
                        sec = len(audio) / self._sr
                        self._known_sec[idx] = sec
                        if self._chars[idx] > 0:
                            self._speed_samples[idx] = (self._chars[idx], sec * rate)
                    else:
                        self._known_sec[idx] = 0.0
                    self._changed_locked()
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
            if self._previous is not None:
                try:
                    self._previous.join_playback(self._join_timeout)
                except Exception:
                    pass
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
            audio, _rate = entry
            if audio is None or len(audio) == 0:
                # 합성 실패(또는 빈 소리) → 건너뛴다. 번호는 그대로라 뒤 조각의 형광펜이 어긋나지 않는다
                self._log(f"[TTS] 조각 {self._cur + 1}: 소리가 없어 건너뜁니다")
                self._advance_locked(now)
                continue
            self._audio = audio
            self._audio_idx = self._cur
            self._off = 0
            self._dirty = True

        # 3) 일시정지 중이면 쓰지 않고 기다린다 (장치는 버퍼가 비면 무음을 낸다 — 옛 코드도 조각 사이에 그랬다)
        if self._paused:
            self._report_locked(now)
            wait = self._poll if self._deadline is None else self._deadline - now
            return ("wait", wait)

        # 4) 다음 블록 (볼륨·음소거는 여기서 게인으로 — 다음 블록부터 바로 적용)
        block = self._audio[self._off:self._off + self._block]
        gain = 0.0 if self._muted else self._volume
        self._report_locked(now)
        return ("write", apply_gain(block, gain), len(block))

    def _after_write_locked(self, count):
        """(락 안) 블록을 다 썼다. 조각 끝이면 다음 조각으로 넘어간다."""
        self._off += count
        self._played_any = True
        if self._audio is not None and self._off >= len(self._audio):
            self._audio = None
            self._audio_idx = None
            self._off = 0
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
        """(락 안) 기다리던 이동을 적용: 옛 소리를 버리고 목표 조각부터 새로 합성·재생한다."""
        self._deadline = None
        self._cur = self._target
        self._synth_gen += 1      # 합성 중이던 결과는 돌아와도 버린다(확장 playId)
        self._ready.clear()
        self._next_synth = self._cur
        self._audio = None
        self._audio_idx = None
        self._off = 0
        self._waiting_since = None
        self._dirty = True
        self._cond.notify_all()
        self._log(f"[TTS] 이동: 조각 {self._cur + 1}/{self._n} 부터")

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

        def estimate(i):
            if self._known_sec[i] is not None:
                return self._known_sec[i]
            return self._chars[i] / (speed1 * rate) if speed1 else 0.0

        target = min(self._target, n)
        # 목표 조각의 소리를 지금 내고 있을 때만 그 안에서 흐른 시간을 센다(이동 대기 중이면 0 — 확장 switchTo 와 같음)
        if (self._audio is not None and self._audio_idx == self._target and self._deadline is None):
            cur_played = self._off / self._sr
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
