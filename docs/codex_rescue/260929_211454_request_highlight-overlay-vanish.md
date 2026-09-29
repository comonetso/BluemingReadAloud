---
type: codex_request
mode: readonly
stamp: 260929_211454
slug: highlight-overlay-vanish
subject: 형광펜 막이 사라져 안 돌아옴
response_path: docs/codex_rescue/260929_211454_response_highlight-overlay-vanish.md
---

# Codex 요청 — 원문 위 형광펜 막이 스크롤 뒤 사라져 끝까지 안 돌아온다 / 엉뚱한 자리·크기로 다시 그려진다

## 이 요청의 성격 — 독립 조사 위임
나(Claude)는 이 문제에서 막혔다. 너에게 **이 사건을 직접 조사해 달라**고 부탁한다.

이 문서는 사건 개요서지 정답의 범위가 아니다. 내가 정리한 자료 안에서만 답을 찾을 이유가 없다 —
**나는 이미 그 안에서 답을 못 찾았다.** 아래에 원본 경로를 적어 두었으니 **직접 열어서 네 방법으로 다시 봐라.**

- **원본이 내 요약과 충돌하면 원본이 이긴다.**
- 내 가설은 검토 대상일 뿐 **분석의 출발점도 경계도 아니다.**
- 필요한 계산·재현(가짜 UIA 로 도는 단위 테스트 등)은 직접 실행해라. 산출물은 `docs/codex_rescue/.scratch/` 에 마음껏 만들어라.

## 사용자가 직접 관측한 것     ← 코드·로그·DB 어디에도 없다. 가장 강한 증거다
아래는 사용자가 자기 눈으로 확인해 말한 것을 원문 그대로 옮긴 것이다(음성 입력이라 맞춤법이 깨져 있다).

> "형광팬이 가끔 사라지는 현상이 있어,, 이건 반듯이 고처야데,, 어떤 트리거에 의해서 사라지는거 같은데,, 사라지는것을 고치기 힘들다면 진행바에 다시 나타나게 하는 버튼을 두던지"
> "형광색이 레이어 형태라 그런지.. 스크롤을 하면 랜더링이 밀리는 느낌이야"
> "사라졌다가 다시 나타나지 않아,, 지금은 브라우저에서 태스트했어"
> "이런경우도 있네?? 니미럴.. 그냥 두는게 낳을듯도 한데"  ← 아래 VS Code 스크린샷을 보여 주며

질문에 대한 사용자 답(선택지 그대로):
- (브라우저 Aside) 막이 사라졌을 때 읽던 문단은? → **"화면 밖에서 돌아와도 안 나옴"** — 스크롤해서 읽던 문단이 화면 밖으로 갔다가 다시 화면에 돌아왔는데도 막이 안 나타났다
- 사라진 뒤 다음 문단(다음 조각)으로 읽기가 넘어갔을 때는? → **"끝까지 안 나타남"**
- (VS Code) 막이 작고 엉뚱한 자리에 떴을 때 직전에 스크롤했나? → **"스크롤 함"**

VS Code 스크린샷(사용자가 보낸 이미지 — 파일로는 없다. 내가 본 것을 적는다):
- VS Code 의 Claude Code 채팅 패널. 사용자가 영어 문단(Claude 의 생각 과정 표시, 회색 기울임꼴, 여러 줄)을 골라 읽혔다.
- 번역문 막(짙은 회색 바탕·노랑 테두리·옅은 회색 글씨)이 **그 영어 문단보다 위쪽**(채팅 상단 탭 제목 바로 아래)에 떴다.
  폭은 원문 문단 폭의 약 1/4, **글자는 원문 줄보다 훨씬 작다**(원문 한 줄 높이의 절반 정도로 보임). 번역문이 막 안에서 여러 줄로 접혀 있다.
- 🔴 사용자가 이미 해봤고 기각한 방향: 없음
- 아직 확인하지 못한 것: Aside 에서 읽은 페이지가 어떤 사이트였는지(정적 문서인지, 내용이 계속 바뀌는 웹앱인지) — **미확인**

## 계측치와의 대조     ← 어긋나면 그것이 단서다
형광펜 모듈은 막이 **보이다 숨겨질 때**와 **다시 보일 때** 로그를 남긴다(오늘 추가한 진단 로그).

- Aside 건 (`logs/whisperer_20260929_205933.log` 20~23행, 이 시점 코드는 "스크롤 중 숨기기" 도입 **전**):
  ```
  21:02:38 보임: 조각 1
  21:02:46 숨김: 스크롤·창 이동 직후 — 새 위치를 기다림
  21:02:47 보임: 조각 1 (번역문 막)
  21:02:48 숨김: 스크롤·창 이동 직후 — 새 위치를 기다림
  (그 뒤 형광펜 로그 없음 → 읽기 종료)
  ```
  이 시점 코드는 "숨긴 채로 이유가 바뀌는 것"은 기록하지 않았다. 그래서 **48초 이후 왜 계속 숨겨져 있었는지는 로그에 없다.**
  콘솔 출력(아래 원본 표)에는 조각 3개로 나뉘었고 사용자가 읽기를 멈췄다(`재생 종료 (stopped)`)고 남아 있다.
  🔴 사용자는 "다음 조각에서도 끝까지 안 나타났다"고 했다 — 한 조각만의 문제가 아니라 **그 읽기의 형광펜 전체가 멈췄다.**
  `_stop`(느림·범위 잃음·창 닫힘) 경로였다면 whisperer 콘솔에 `[형광펜] 읽는 도중 원문 위 칠하기를 멈췄습니다` 가 남는데 **없다.**

- VS Code 건 (`logs/whisperer_20260929_210300.log` 18~41행, "스크롤 중 숨기기" 도입 **후**):
  스크롤마다 `숨김: 스크롤 중` → 약 0.4초 뒤 `보임: 조각 1 (번역문 막)` 이 11번 반복됐다. 즉 **다시 그리긴 했다.**
  그런데 사용자 눈에는 **자리와 크기가 틀렸다.** 로그상 "보임"은 사각형을 받아 그렸다는 뜻일 뿐, 그 사각형이 맞는지는 모른다.

## 지금 바로 열 수 있는 원본     ← 요구하지 말고 열어라
작업 디렉토리 = `F:\workspace\EtcProject\ElectronProject\BluemingReadAloud` (git 레포, 오늘 변경은 전부 미커밋).

| 무엇 | 절대경로 / 접근 명령 | 왜 중요한가 |
|---|---|---|
| 형광펜 모듈 | `F:\workspace\EtcProject\ElectronProject\BluemingReadAloud\source_highlight.py` | 상태 머신 전부. `_UiaWorker._rects`(1035)·`_reveal`(1059)·`_needs_reveal`(1088), `SourceHighlighter` 의 결과 처리(1690 `_inflight` 해제, 1720 `rects` 처리)·`_watch`(1740)·`_select`(1776)·`_flush_query`(1788)·`_redraw`(1799)·`_hide_overlay`(1832), `build_caption_bitmap`(막 크기 계산), `clip_rects`, `rects_from_uia`. 머리 설명(1~72행)에 크로미움 UIA 실측과 금지 호출이 있다 |
| 연결부 | `F:\workspace\EtcProject\ElectronProject\BluemingReadAloud\whisperer.py` | `_handle_tts_event`(segment → `highlight(idx, caption)`), `_begin_source_highlight`, `_on_source_highlight_result`, `_on_source_highlight_stop`, 마우스 훅의 휠 알림 `_notify_source_scroll` |
| 오늘 변경분 | `git -C "F:/workspace/EtcProject/ElectronProject/BluemingReadAloud" diff -- source_highlight.py whisperer.py` | 번역문 막·스크롤 중 숨기기·진단 로그가 오늘 들어갔다. Aside 건은 "스크롤 중 숨기기"(`_scroll_hold`) **전** 코드에서 났다 |
| Aside 건 로그 | `F:\workspace\EtcProject\ElectronProject\BluemingReadAloud\logs\whisperer_20260929_205933.log` | 위 표. 줄 20~23 |
| Aside 건 콘솔 | `C:\Users\bluec\AppData\Local\Temp\claude\f--workspace-EtcProject-ElectronProject-BluemingReadAloud\95e4bac3-0c1c-465f-9e9f-26e4aa3b0014\tasks\b2gjcqjti.output` | 같은 실행의 whisperer 콘솔(조각 수, 번역, 재생 종료) |
| VS Code 건 로그 | `F:\workspace\EtcProject\ElectronProject\BluemingReadAloud\logs\whisperer_20260929_210300.log` | 줄 18~41 |
| VS Code 건 콘솔 | `C:\Users\bluec\AppData\Local\Temp\claude\f--workspace-EtcProject-ElectronProject-BluemingReadAloud\95e4bac3-0c1c-465f-9e9f-26e4aa3b0014\tasks\b7efl2j5y.output` | 같은 실행의 콘솔 |
| 단위 테스트 | `F:\workspace\EtcProject\ElectronProject\BluemingReadAloud\tests\test_source_highlight.py` | 가짜 UIA 문서(`FakeDoc` — 스크롤·화면 밖 줄은 빈 사각형)·가짜 막(`FakeOverlay`)으로 흐름을 재현한다. `python -m unittest tests.test_source_highlight` 로 돈다(현재 52개 통과). **재현 테스트를 `.scratch/` 에 만들어 돌려 봐라** |
| 크로미움 UIA 실측 기록 | `F:\workspace\EtcProject\ElectronProject\BluemingReadAloud\docs\session_logs\2026-09-28_work_log.md` | 09-28 Edge·VS Code 실측과 VS Code 를 얼린 사고 경위 |
| UIA 금지 규칙 | `C:\Users\bluec\.claude\projects\f--workspace-EtcProject-ElectronProject-BluemingReadAloud\memory\no-uia-full-scan.md` | 수정안이 지켜야 할 제약 |

- 🔴 **UI Automation 을 실제로 호출하는 코드를 실행하지 마라.** 09-28 에 창 전체를 훑는 UIA 호출로 사용자 VS Code 가 얼었다.
  지금도 사용자 PC 에 VS Code·브라우저·이 앱(개발 모드)이 떠 있다. **조사는 코드 판독과 가짜 UIA 단위 테스트로만** 해라.
- 🔴 위 표에 있는 것을 "제공해 달라"고 답변에 적지 마라. 이미 열 수 있다.

## 먼저 할 것 — 추론보다 관측이 앞선다
1. 위 표의 원본을 **실제로 열어라.** 무엇을 어떤 명령으로 열었는지 답변 1번에 적어라.
2. `SourceHighlighter` 상태 머신에서 **"한 번 숨겨진 뒤 그 읽기가 끝날 때까지(다음 조각 포함) 다시 그려지지 않는"** 경로를 전부 찾아라.
   후보 변수: `_inflight` · `_need_query` · `_settle_left` · `_scroll_hold` · `_fg_ok` · `_raw_rects` · `_mapped` · `_state` · `_current_idx`·`_want_idx`, 워커 쪽 `_sess`·`s.ranges`.
3. 그중 **Aside 건 로그 + 사용자 관측("화면에 돌아와도·다음 조각에서도 안 나옴")과 맞는 경로**를 가려라.
   가능하면 `.scratch/` 에 가짜 UIA 로 그 상황을 재현하는 테스트를 만들어 **실제로 돌려** 확인해라.
4. VS Code 건: 스크롤 뒤 다시 그린 막이 **원문보다 위·좁게·작은 글자**로 나온 이유를 `_redraw` → `clip_rects` → `build_caption_bitmap`(줄 높이·폭 계산) 흐름에서 찾아라.
5. 🔴 **`사용자가 직접 관측한 것` 이 설명되기 전에는 수정안을 쓰지 마라.**
6. **확인한 사실은 그때마다 응답 문서에 적어라.** 적는 순서는 맨 아래 `응답 저장 위치` 에 있다.

## 환경
- Windows 11 Pro, Python 3.13, comtypes 로 UIAutomationCore 사용(전용 MTA 스레드), Tk(ttkbootstrap) 메인 스레드.
- 막 창: 클릭 통과 층 창(`WS_EX_LAYERED|TRANSPARENT|NOACTIVATE|TOOLWINDOW`) 하나를 `UpdateLayeredWindow` 로 그린다. 앱은 시스템 DPI 인식.
- 대상 앱: VS Code(크로미움, Claude Code 확장 채팅 패널 — 가상 목록일 수 있음), Aside 브라우저(크로미움 기반).
- 휠 알림은 pynput 마우스 훅에서 `notify_scroll()`(플래그만 세움)으로 온다. 스크롤바 끌기·키보드 스크롤은 알림이 없고 `REFRESH_S`(1초) 주기 재조회에 기댄다.
- 틱: `WATCH_MS` 50ms, `SETTLE_TICKS` 6, `REFRESH_S` 1.0 (모두 머리 상수).

## 문제 — 증상
1. (Aside, 스크롤 중 숨기기 도입 전 코드) 읽는 도중 스크롤하면 막이 사라지고, **읽던 문단이 화면에 돌아와도, 다음 조각으로 넘어가도 그 읽기가 끝날 때까지 다시 나타나지 않는다.** 멈춤(`_stop`) 기록은 없다.
2. (VS Code, 도입 후 코드) 스크롤하면 숨겼다가 다시 그리는데, 다시 그린 번역문 막이 **원문 문단 위쪽의 엉뚱한 자리에, 좁고 글자가 아주 작게** 나온다.
3. (사용자 체감) 스크롤하면 막이 원문보다 늦게 따라와 밀려 보인다 — 이건 구조상 한계로 보고 "스크롤 중 숨기기"로 대응했다. 이번 요청의 중심은 1·2 다.

## 현재 코드 — 시작점만 (원본이 정본이다)
- 조각 범위는 `begin` 때 사용자의 **선택 범위를 복제해** 조각마다 미리 만들어 워커 세션(`_sess.ranges`)에 쥐고 있다(머리 설명 흐름 2).
- 조각을 칠할 때마다 워커가 그 범위의 `GetBoundingRectangles` 만 다시 부른다(`_rects`, 1035). 빈 사각형이 오면 `reveal` 요청일 때 `_needs_reveal` 이 True → `_reveal` 로 스크롤을 시도하고 `scrolled=True` 를 돌려준다.
- Tk 쪽은 `scrolled` 결과면 사각형을 비우고 `SETTLE_TICKS` 동안 다시 받는다(1720~). 빈 사각형이면 `_redraw` 가 숨긴다.
- `_flush_query`(1788) 는 `_inflight` 가 True 면 새 요청을 보내지 않는다. `_inflight` 는 `gen == self._gen` 인 `rects` 결과가 와야 풀린다(1690).

## 내(Claude)가 세운 가설     ← 증거가 아니다. 검토 대상일 뿐이다
- H1: 크로미움이 스크롤로 접근성 트리를 다시 만들면서 **begin 때 복제해 둔 조각 범위가 전부 한꺼번에 죽는다.** 예외 없이 빈 사각형만 돌려주니 `lost` 로 멈추지도 않고 계속 숨겨진다. 모든 조각이 같은 선택에서 복제됐으니 다음 조각도 같다 → "화면에 돌아와도·다음 조각도 안 나옴"과 맞는다.
- H2: 어떤 경로에서 `_inflight` 가 풀리지 않아 이후 요청이 영영 안 나간다(다음 조각 포함).
- H3: VS Code 건은 스크롤 애니메이션이 끝나기 전 사각형을 받았거나, `clip_rects` 로 잘린 사각형의 높이 가운데 값을 줄 높이로 써서 글자가 작아졌다.
- 🔴 이건 해석이다. 틀렸으면 버려라. 원본이 다른 곳을 가리키면 그쪽으로 가라.

## 실패 이력 — 무엇이 죽었고 무엇이 살아 있나
| 분류 | 내용 | 그 원본을 다시 봐도 되나 |
|---|---|---|
| ③ 자료 부족 | 처음엔 로그 파일이 7월부터 0바이트였다(`basicConfig` 가 먼저 깔린 기본 설정 때문에 무시됨). 오늘 `force=True` 로 고쳐서 이제 기록된다. 그래서 Aside 건은 "숨긴 채 이유 변화"가 없다 | ✅ 코드 판독·가짜 테스트로 경로를 좁혀라 |
| ② 대응은 했으나 원인 미상 | "스크롤 중 숨기기"(`_scroll_hold`)를 넣었다 — 밀림 체감 대응이지 사라짐의 원인 수정이 아니다. VS Code 건에서 다시 그리긴 하지만 자리·크기가 틀렸다 | ✅ 오늘 diff 에 있다 |

## 완료 게이트 — 무엇이 설명돼야 "풀렸다"고 할 수 있나
- G1 증상 1(끝까지 안 돌아옴)의 **인과 경로**가 코드로 이어지는가 — 어떤 상태가 어떤 값으로 굳어서 다음 조각까지 막는지
- G2 왜 **스크롤 뒤에만** 나는가, 그리고 왜 `_stop` 기록이 없는가
- G3 VS Code 건(증상 2) — 자리가 위로 가고 글자가 작아지는 이유가 같은 원인인지 별개인지
- G4 **반증 가능한 예측** — 예: "가짜 UIA 에서 스크롤 뒤 범위가 빈 사각형만 돌려주게 하면 다음 조각도 안 칠해진다"를 테스트로 보였는가
- G5 수정안이 인과의 어느 고리를 끊는지. **아래 UIA 금지 규칙을 지키는 방법**이어야 한다
- G6 남은 불확실성 열거

## 수정안의 제약 — UIA 금지 호출 (반드시 지킬 것)
- 금지: `GetVisibleRanges` · `DocumentRange` 전체에 대한 `GetText`/`GetBoundingRectangles`/`FindText` · 창·문서 단위 `FindAll`/`FindFirst`(Descendants·Subtree).
- 허용되어 온 것: 포커스 요소에서 위로 걷기, 사용자가 고른 **선택 범위 안쪽** 호출, 한 자리짜리 호출(`RangeFromPoint` → `ExpandToEnclosingUnit` 은 09-28 실측 1~20ms 로 안전).
- 모든 UIA 호출은 워커 스레드에서만, 한 호출 1초를 넘으면 그 읽기의 칠하기를 멈춘다(이미 구현됨).
- 범위가 죽었을 때 **금지 호출 없이 다시 잡는 방법**이 있으면 제안해라. 없으면 "죽었음을 감지해 알리는" 쪽이라도.
  (사용자는 대안으로 하단 바에 "다시 표시" 버튼도 말했다 — 원인상 필요하다고 판단되면 그 버튼이 무엇을 해야 하는지도 적어라)

## 되물을 수 있다 — 이건 단발이 아니다
네 답변을 내가 검토한 뒤 다시 물을 수 있다. 확신이 없는 부분을 감추지 마라.

## 요청 — 조사를 부탁한다
1. 원본부터 직접 열어라.
2. 원본·재현 테스트에서 실제로 확인한 것과, 그것으로 무엇이 설명되는지.
3. 현재 진단 로그가 이 증상을 잡을 수 있나? 사각지대가 있으면 무엇을 더 남겨야 하는지.
4. 네가 보는 근본 원인(증상 1·2 각각). 내 가설과 어디서 갈라지는지.
5. 수정 방법 before/after 코드. (적용은 내가 한다)
6. 대안 비교 + 추천. 함정.
7. 확신도 — 추측과 확인을 구분해서.

## 답변 형식 — Claude 가 읽고 바로 적용 판단한다
0. `조사 계획` — 첫 원본을 열기 전에 먼저 저장한다.
1. `내가 직접 연 원본` — 어떤 파일을 어떤 명령으로 열었고 무엇이 나왔나. 열 때마다 바로 덧붙인다.
2. `사용자 관측 증상에 대한 설명` — 각 항목이 설명되나. 안 되면 그렇다고 적어라.
3. `네가 보는 근본 원인`
4. `내 가설에 대한 판정` — 짧게.
5. `수정 방법 (before → after)` · `대안 비교와 추천` · `함정·주의점`
6. `완료 게이트 자기판정` — G1~G6 충족/미충족 + 한 줄 근거
7. `확신도와 남은 불확실성`
8. `이 머신에서 접근 불가한 자료` — 없으면 "없음". 위 원본 표 항목은 여기 쓸 수 없다.

## 작업 규칙 — 경계선은 하나다
- **프로덕션 파일을 고치지 마라.** 소스·설정·데이터는 읽기만 한다. git 상태를 바꾸는 명령도 금지다.
- **UI Automation 을 실제로 부르는 코드를 실행하지 마라**(위 이유). 이 앱의 개발 모드 프로세스도 건드리지 마라.
- 네가 쓰는 곳은 정확히 두 곳 — 아래 응답 문서와 `docs/codex_rescue/.scratch/`. 스크래치 안에서는 마음껏 만들어라
  (재현 테스트는 `tests/` 를 복사하지 말고 import 해서 `.scratch/` 에 새로 써라).
- 디스크 읽기와 네트워크 조회는 자유다. 단 네트워크는 조회 전용.
- 이 요청서와 응답은 git 에 커밋된다. API 키 등 비밀값을 응답에 적지 마라(`whisperer_settings.json`·`.env` 에 키가 있다 — 열 필요 없다).

## 응답 저장 위치 (배관 — 첫 원본을 열기 전에 이것만 먼저 읽어라)
아래 경로에 **그 이름 그대로** 저장해라.

    docs/codex_rescue/260929_211454_response_highlight-overlay-vanish.md

- 경로·파일명을 바꾸지 마라.
- 파일 첫머리에 아래 frontmatter를 그대로 넣어라:

      ---
      type: codex_response
      mode: readonly
      stamp: 260929_211454
      slug: highlight-overlay-vanish
      author: codex
      ---

- **쓰기가 막히면 거기서 멈추지 말고, 같은 내용을 최종 메시지로 그대로 출력해라.** 자동으로 회수해 저장한다.
- **조사하면서 채워 나가라.** 이 실행은 도중에 끊길 수 있다.
  1. 첫 원본을 열기 전에 frontmatter 와 `## 0. 조사 계획` 을 먼저 저장한다
  2. 원본을 하나 열어 확인할 때마다 `## 1. 내가 직접 연 원본` 에 바로 덧붙인다
  3. 조사가 끝나면 `답변 형식` 2번부터 이어 쓴다. 결론을 확인한 사실보다 먼저 쓰지 마라
