---
type: codex_request
mode: edit
stamp: 261118_055840
slug: noeul-app-streaming
subject: 읽기 앱 노을 받는 대로 틀기
response_path: docs/codex_rescue/261118_055840_response_noeul-app-streaming.md
---

# Codex 작업 지시 — PC 읽기 앱이 직접 읽을 때도 OpenAI 노을, 소리를 받는 대로 틀기

## 이 요청의 성격
새 기능 구현이다(버그 조사 아님). 사용자(리규형님)가 버튼으로 정한 결정이 아래에 있다 — 결정은 바꾸지 말고, **구현 방식**은 네가 원본을 읽고 정해라.
내가 적은 방향(맨 아래 "내 가설")은 검토 대상일 뿐이다. 원본이 다른 길을 가리키면 그쪽으로 가라.

## 사용자가 직접 관측한 것
해당 없음(새 기능). 단, 같은 노을을 이미 쓰는 Paseo 쪽 실측이 있다 — 아래 "Paseo 실측·규칙".

## 지금 바로 열 수 있는 원본
| 무엇 | 경로 | 왜 |
|---|---|---|
| 재생 엔진 | `F:/workspace/EtcProject/ElectronProject/BluemingReadAloud/tts_engine.py` | 고칠 중심. 머리 설명(1~115줄)에 계약·함정이 있다 |
| 노을 연결 | `F:/workspace/EtcProject/ElectronProject/BluemingReadAloud/noeul_live.py` | 이미 있음(오늘 커밋 de72342). `read_noeul` 은 조각을 끝까지 읽힌 뒤 PCM 을 돌려준다 — 받는 대로 넘기는 길이 없다 |
| 앱 본체 | `F:/workspace/EtcProject/ElectronProject/BluemingReadAloud/whisperer.py` | 목소리 목록·소리 만드는 함수 고르기·미리 듣기·사용량 |
| 사용량 | `F:/workspace/EtcProject/ElectronProject/BluemingReadAloud/tts_usage.py` | `UsageCounter.count`(324줄)·`usage_kind`(149)·`voice_label`(175) |
| 조각 나누기 | `F:/workspace/EtcProject/ElectronProject/BluemingReadAloud/readaloud_text.py` | `split_paragraphs_for_reading`(1028) — 문단 = 조각 |
| 번역 감싸기 | `F:/workspace/EtcProject/ElectronProject/BluemingReadAloud/translation.py` | `make_translating_synthesize` — synthesize 를 감싼다 |
| 프로젝트 규칙 | `F:/workspace/EtcProject/ElectronProject/BluemingReadAloud/CLAUDE.md` | 구조·스레드·하지 말 것(읽기만, 고치지 마라) |
| 시험 | `F:/workspace/EtcProject/ElectronProject/BluemingReadAloud/tests/` | `test_tts_engine.py`·`test_noeul_live.py` 등 |
| Paseo 서버(참고 원본) | `F:/workspace/EtcProject/VsCodeExtentions/claudeContextBar/paseo-plugins/claude-state-bar/server/presentation/tts.ts` | 받는 대로 틀기 원조: `streamPiecesGrowing`(610-635)·`streamStartSec`(637-641)·`streamProduce`(570-585)·`streamDrain`(535-540)·`streamCancel`(555-560)·`liveRead` 의 sink(329~)·`countUsage`(1140-1160) |
| Paseo 화면(참고 원본) | `F:/workspace/EtcProject/VsCodeExtentions/claudeContextBar/paseo-plugins/claude-state-bar/client/presentation/thinkingPlayer.ts` | 문단 미리 열기·dropSlot(948)·끝내기(797)·멈춤(814-818)·문단 열 때 빠르기(971) |
| Paseo 실측 기록 | `F:/workspace/EtcProject/VsCodeExtentions/claudeContextBar/docs/paseo-plugin-tools/records-261118/noeul_live/` | `stream_sim2.cjs`·`stream_sim2_r15*.log`(빠르기별 끊김) |
| Paseo 답(이 앱에 옮기는 법) | `F:/workspace/EtcProject/ElectronProject/BluemingReadAloud/docs/_msg/peer_mail/17eddb94-a5a1-40b4-9e77-93fd5f8f4d3e/result/peer.md` | Claude State Bar 가 위 원본을 줄 번호로 정리한 답. 원본과 다르면 원본이 이긴다 |

- 🔴 위 표의 것을 "달라"고 하지 마라. 열어라.

## 조사 깊이 — 깊게
호출 관계와 엣지 케이스까지 따라가라. 대표 사례와 대조군은 원본으로 끝까지 대조해라.
찾은 결론을 스스로 반증해 보고, 반증에 실패한 것만 확정으로 적어라. 근거는 파일 경로와 줄 번호로 적어라.

## 환경
- Windows 11, Python 3.13.5 (`PYTHONUTF8=1` 필요), tkinter 메인 스레드 + 별도 스레드들, sounddevice `OutputStream`(24kHz 모노 int16), numpy, audiotsm(WSOLA), PyInstaller 로 exe 빌드(빌드는 하지 마라).
- 시험: `PYTHONUTF8=1 python -m unittest discover -s tests` — 지금 488개 전부 통과. 시험은 `whisperer.py` 를 import 하지 않고 AST 로 함수를 꺼낸다(`tests/test_whisperer_*.py` 참고).

## 리규형님 결정(바꾸지 마라)
1. 이 앱이 **직접 읽을 때도** 노을(GPT-Live `gpt-live-1`, 목소리 `noeul`)을 고를 수 있게 한다. 기본은 계속 Google Zephyr.
2. 첫 소리 늦음은 **Paseo 와 같게 "받는 대로 틀기"** 로 푼다(조각이 다 된 뒤 넘기기 아님).
3. 노을 사용량은 **Paseo 와 같게 글자 수로 센다** — 노을 연결(조각) 하나가 성공할 때마다 그 조각 글의 글자 수(코드 포인트)를, 이 앱 사용량 파일의 `months` 와 OpenAI 키의 `keys` 칸 **두 곳에 같이**(`UsageCounter.count(kind, sent, key=key_mark)` 가 이미 두 곳에 더한다). 종류 이름 `openai`. 다시 시도로 버린 연결·실패한 연결은 세지 않는다. 키 칸 이름은 OpenAI 키의 `tts_usage.key_mark`. **크롬 확장 대신 읽은 것(`/v1/tts/noeul`)은 지금처럼 세지 않는다**(확장이 센다 — 두 번 세기 금지).
4. OpenAI 키는 Paseo 키 파일(`noeul_live.read_paseo_openai_key`)에서 읽는다(이 앱 인증 창에는 칸을 만들지 않는다).
5. 노을 부르는 순서·다시 시도·첫머리 판정·끝 판정은 `noeul_live.py` 에 이미 옮긴 Paseo 11-18 판 그대로.

## Paseo 실측·규칙 — 원본은 위 tts.ts, 요약은 17eddb94 답
- 조각 나누기 `streamPiecesGrowing`: 문단 안에서만(문단 경계를 넘지 않는다). 첫 조각 = 첫 문장, 45자 넘으면 앞부분 8자 이상 된 첫 쉼표 뒤에서 자름, 8자보다 짧으면 45자 안쪽까지 다음 문장을 붙임. 뒤 조각 상한 `min(300, floor((첫 조각 글자 + (지금까지 합 − 마지막 조각 글자)/(r − 1)) × 0.85))`, r = `max(1.5, min(빠르기, 3))`. 한 문장이 상한보다 길면 그 문장 통째로 한 조각.
- 조각마다 노을 연결 하나, 문단 안 최대 8개 동시(`LIVE_PARALLEL`), 전체 동시 연결 상한 12(`noeul_live.LIVE_SESSIONS_MAX` — 확장 창구와 공유).
- 시작 전 모음 `streamStartSec` = `max(1, 첫 조각 글자 ÷ 6.5 × (1 − 1/r) + 0.4)` 초(원본 1배 소리 기준), 여기 r = `max(1, 실제 빠르기)`.
- 받은 소리는 오는 대로 넘기고, 트는 쪽은 지금 조각에서 꺼내다 그 조각이 다 되면 다음으로. 비었는데 아직 안 됐으면 기다림(그게 끊김).
- 빠르기는 문단을 열 때 한 번 계획하고, 읽는 도중 바뀌어도 계획을 다시 하지 않는다(재생 빠르기만 바로 바뀜).
- 문단 이동·끝내기: 미리 연 범위 밖 작업을 취소 → 라이브 연결마다 session.close. 멈춤(일시정지): 연결을 끊지 않고 계속 받아 둔다.
- 실측: 1·1.1·1.3·1.5배 끊김 0, 첫 소리 3.4~5.8초(stream_sim2_*_b·c·d.log).
- 앞뒤 무음: 첫 소리 앞 0.1초만, 조각 끝 무음은 0.1초만 넘겼다(liveRead 의 deliver/held — 이음매 빈 시간).

## 현재 코드 — 시작점(원본이 정본)
- `whisperer.py:3645-3667` `speak_text` — 지금은 늘 Google:
  ```python
  synthesize = tts_engine.make_google_synthesize(
      google_tts_client, google_tts, tts_voice_name, log=log_to_console,
      on_sent=lambda sent: _count_tts_usage(voice_for_usage, sent, key_for_usage))
  if raw_texts:
      synthesize = translation.make_translating_synthesize(synthesize, translator, ..., raw_texts, ...)
  session = tts_engine.TtsSession(text, segments, synthesize, tts_engine.sounddevice_stream_factory(),
      _make_tts_event_handler(box), rate=tts_speaking_rate, ..., previous=previous, log=log_to_console)
  ```
- `tts_engine.py` — `synthesize(text, rate) -> numpy int16 전체` 계약(머리 9~12줄). 합성 스레드 하나(`_produce` 955)가 지금 조각 뒤 2조각까지(`PREFETCH_AHEAD`) 차례로 통째 합성 → `_put_ready_locked`(1279) → 재생 스레드(`_play_loop` 1117 · `_step_locked` 1145)가 꺼내 `_Stretcher`(309, 전체 audio 를 받아 빠르기를 WSOLA 로)로 늘려 `OutputStream` 하나에 0.1초 블록씩 씀. 소리 캐시 2칸(`_take_cached_locked` 1334 · `_cache_put_locked` 1353), 이동(`forward` 833 · `rewind` 852), 빠르기(`set_rate` 893), 멈춤/재개(800/806), 끝(`stop` 770).
- `noeul_live.py` — `read_noeul(text, key, lang, *, log, opener, clock, close_delay, cancelled)` → 끝까지 읽힌 뒤 PCM bytes. 소리 조각은 `_read_once` 안 `session.output_audio.delta` 에서 `chunks` 에 모인다 — 여기에 받는 대로 넘기는 콜백(Paseo liveRead 의 sink)이 없다. 다시 시도는 소리를 넘기기 전에만 해야 겹치지 않는다(Paseo `retryable = !last && !sent`).
- `tts_usage.py:149` `usage_kind(voice_name)` — 목소리 이름 → 종류(chirp3hd·wavenet·그 밖은 타입 이름 소문자). `tts_engine.voice_lang_of`/`voice_type_of`(170/180) 가 목소리 이름 앞부분으로 언어(`ko`)를 판단한다 — 노을 이름을 정할 때 이 판정과 `readaloud_text`·`spoken_text` 의 언어 처리가 그대로 맞게 해라.
- 목소리 목록 `whisperer.py:297` `KOREAN_VOICES`(Paseo FEATURED_GOOGLE_VOICES 와 같은 8개), 표시 `tts_usage.voice_label`(설정 창 `show_tts_settings_dialog` 2632~2692).

## 작업 — 직접 수정할 것
1. 설정 창 목소리 목록 **맨 끝**에 노을 하나를 더한다(표시 예: "노을 · OpenAI 라이브 · 분당 0.05달러 (이번 달 PC 앱 n자)" — 기존 `voice_label` 모양에 맞춰라). 저장·불러오기·미리 듣기도 노을로 되게.
2. 노을을 고르면 `speak_text` 가 Google 대신 노을로 읽는다 — **받는 대로 틀기**(위 Paseo 규칙). 번역(`make_translating_synthesize`)·원문 위 형광펜·문단 앞뒤 이동(Ctrl+←/→)·빠르기(Ctrl+↑/↓, 재생 때 WSOLA)·멈춤/재개·끝내기가 지금처럼 문단 단위로 돌아야 한다.
3. 노을 키가 없거나(no_key)·IP 불허·키 거절·다시 시도를 다 쓴 실패는 그 문단 차례에 읽기를 멈추고 경고 창(`tts_engine.SegmentFailed` 경로 — 번역 실패와 같은 장치)으로 알린다. 문장은 `noeul_live.MESSAGES` 를 써라.
4. 문단 이동·끝내기 때 미리 연 노을 연결은 닫아 과금을 줄인다(`noeul_live.read_noeul(cancelled=...)` 가 이미 있다). 멈춤 때는 끊지 않는다.
5. 사용량은 위 결정 3대로.
6. 시험을 더해라(가짜 연결·가짜 시계 — `tests/test_noeul_live.py` 의 `FakeConn`/`Attempts` 방식 참고): 조각 나누기 규칙, 시작 전 모음, 받는 대로 넘기기·조각 넘어가기·기다림, 이동·끝내기 때 취소, 다시 시도가 소리를 넘긴 뒤엔 일어나지 않음, 사용량 두 곳·확장 창구 몫 제외, Google 읽기는 그대로.

## 작업 규칙
- **최소 변경.** Google 읽기 동작은 바뀌면 안 된다 — 기존 시험 488개는 그대로 통과해야 한다.
- 고쳐도 되는 파일: `tts_engine.py`·`noeul_live.py`·`whisperer.py`·`tts_usage.py`·`readaloud_text.py`·`translation.py`, 그리고 `tests/` 안. 🔴 **저장소 맨 위 폴더에 새 파일을 만들지 마라** — 그 폴더 소유자가 관리자 그룹이라 쓰기가 막힐 수 있다(9-29 실측: `docs/codex_rescue/` 응답·`.scratch` 쓰기 Access denied). 새 코드는 위 기존 파일 안에, 새 시험은 `tests/` 안에.
- 🔴 `CLAUDE.md`·`AGENTS.md`·`docs/` 아래 문서는 고치지 마라(문서는 Claude 가 정리한다). 응답 문서와 `.scratch` 만 예외.
- 🔴 **실제 OpenAI 를 부르지 마라** — 이 PC 는 OpenAI 조직 IP 허용 목록 밖이고 연결 시간만큼 과금된다. 시험은 가짜 연결로만.
- 🔴 **근거 없는 값을 넣지 마라**(사용자 규칙). Paseo 원본에 있는 값은 그 출처(파일:줄)를 주석에 적어라. Paseo 에 없어서 네가 정해야 했던 값은 **응답에 "내가 정한 값" 목록으로 모두 밝혀라**(무엇·얼마·왜).
- CLAUDE.md "Important Notes" 를 지켜라 — 세션 정지 신호(`_stop_event`)를 다시 쓰거나 지우지 않기, Tk 는 메인 스레드에서만(`gui_queue`), 키보드·마우스 훅 콜백은 작게, `sd.stop()` 은 OutputStream 을 못 멈춤.
- 저장소 상태를 바꾸는 명령 금지(git commit·checkout·stash·reset, 패키지 설치, 빌드). 앱 실행도 하지 마라(설치본이 51888 을 잡고 돌고 있다).
- 확인이 안 서는 곳은 고치지 말고 응답에 "왜 확신이 안 서는지"를 적어라. 🔴 이 실행에는 승인을 눌러 줄 사람이 없다 — "먼저 물어봐"는 성립하지 않는다.

## 내(Claude)가 세운 가설 — 증거가 아니다
- 엔진에 "아직 자라는 소리"를 하나 더 둘 수 있다고 본다: 노을 synthesize 가 문단마다 {조각별 PCM 블록 목록, done, error} 를 담은 객체를 바로 돌려주고, 합성 스레드는 그것을 `_ready` 에 넣고, 재생 스레드는 시작 전 모음만큼 모이면 틀기 시작해 블록이 모자라면 기다린다. `_Stretcher` 가 전체 audio 를 전제로 하니 블록을 이어 받게 바꿔야 할 것이다. 캐시는 완성된 뒤에만, 이동 때 안 끝난 것은 cancelled 로 닫는다.
- 이건 해석이다. 엔진 원본이 더 나은 자리(예: 재생 스레드 쪽만 바꾸기, synthesize 계약을 그대로 두는 길)를 가리키면 그쪽으로 가라.

## 실패 이력
| 분류 | 내용 | 다시 봐도 되나 |
|---|---|---|
| ③ 자료 부족 | "조각이 다 된 뒤 넘기기" 방식의 실측은 없다(Paseo 답 3번은 계산뿐). 그래서 리규형님이 받는 대로 틀기를 골랐다 | — |

## 완료 게이트
- G1 노을을 고르고 읽으면 첫 소리가 첫 조각의 시작 전 모음만큼 모인 뒤 나온다는 것이 코드·시험으로 이어진다
- G2 1·1.5배에서 조각 사이가 끊기지 않는 조건(조각 계획·동시 생성·기다림)이 Paseo 규칙대로 구현됐다
- G3 Google 읽기·기존 시험이 그대로다
- G4 이동·끝내기 취소, 실패 시 멈춤+경고, 사용량 두 곳(확장 몫 제외)이 시험으로 확인된다
- G5 "내가 정한 값" 목록과 남은 위험이 열거됐다

## 보고 — 아래 경로에 저장할 것
    docs/codex_rescue/261118_055840_response_noeul-app-streaming.md
    (frontmatter: type: codex_response / mode: edit / stamp: 261118_055840 / slug: noeul-app-streaming / author: codex)
    쓰기가 막히면 같은 내용을 최종 메시지로 그대로 출력해라. 자동으로 회수해 저장한다.
    🔴 **파일을 하나 고칠 때마다 1번에 바로 적어라.** 사용량 한도로 도중에 끊기면 무엇을 고쳤는지가
    이 기록에만 남는다. 수정 전에 frontmatter 와 빈 1번 섹션부터 만들어라.

1. 변경한 파일·라인 요약     ← 고칠 때마다 덧붙인다
2. 무엇을 왜 바꿨나 (before → after)
3. 빌드·검증 방법 — 돌린 시험 명령과 결과(통과 수)
4. 내가 정한 값 목록(Paseo 에 없는 값 — 무엇·얼마·왜)
5. 남은 리스크·확신도 — 특히 실제 노을 없이 확인 못 한 것
