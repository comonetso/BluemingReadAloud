[완료] 줄 끝 쉼 — Paseo 기준(LINE_NEEDS_PERIOD)과 똑같이 반영 (커밋 안 함, 실제 청취는 리규형님 실측 전)

■ 한 일
1. js/spoken-text.js makeSpokenText 맨 끝에 기준 규칙을 그대로 더함 — 기준과 같은 순서(공백 정리 → \n{3,} → 앞뒤 다듬기) 뒤에 LINE_NEEDS_PERIOD /[^\s.!?,;:…。！？、，；：،؛؟](?=\n)/g → "$&.". 엔진이 듣는 줄 끝 마침표는 이제 이것 하나.
2. 미리 붙이는 마침표 정리 — 드래그 읽기의 줄마다(defaults.js selectionParagraphs)와 문단 끝(speech.js needsPeriod 넓은·좁은 규칙)은 지우지 않고 남겼다. 이유: 조각 자르기의 문장 나누기가 "마침표+줄바꿈"에서 자르고 형광펜 재현도 그 글자를 따라가서, 빼면 긴 문단이 줄 중간에서 잘린다(구글 번역 200자 등) — "조각 나누기·형광펜은 그대로"를 지키려고.
   대신 그 마침표 앞에 보이지 않는 표시 글자를 달아("\u2063.", defaults.js ADDED_PERIOD) makeSpokenText 가 맨 처음에 지운다(위치 추적 포함). 그래서 엔진 글 = 표시 없는 원문을 기준 함수에 넣은 결과. (가) 문단 마지막 줄 안 붙음 (나) 아랍어 ، ؛ ؟ 줄 안 붙음 모두 기준대로.
   같은 표시를 쓰도록 맞춘 곳: speech.js(문단 끝·따라가기 다시 자르기 recut·짧은 줄 바이트 세기에서 표시 제외), page-ui-host.js alignParagraphs(형광펜 재현).
3. 구글 문서·PDF 등(좁은 규칙): 문단 안 줄바꿈에서 이제 쉰다 — 아래 7)에서 "둘째 문단\n안에 줄바꿈" 이 기준과 같음. 한국어 문단 끝도(예전 좁은 규칙은 영문·숫자·')' 뒤에만) 조각 안에서 다음 문단이 이어지면 쉰다.
4. compare.mjs: 줄 번호 대신 기준 시험 파일에서 check( / checkWords( 로 시작하는 줄을 찾아, 문법이 맞을 때까지 다음 줄을 붙여 호출 단위로 돌림(여러 줄 호출 "마크다운 표" 포함). 대조는 사전 끔 + 같은 사전(이쪽 englishWords Map)을 양쪽에 넘겨 켬 두 번.

■ 시험 결과 (node 22.17)
1) 기준 check( 95/95 · 2) checkWords( 12/12 · 3) 판 번호 10/10
4) 기준 함수와 대조: 사전 끔 236건·같은 사전 켬 236건 모두 같음(차이 0) — 요청의 줄 끝 쉼 예 9개는 기준 시험 안에 있어 통과에 포함
5) sourceIndex 이상 없음 · 6) 표시 마침표 빼기 16/16 같음
7) 실제 흐름(드래그 읽기 문단 → 문단 끝 마침표 → 엔진 글, 구글 문서식 문단 합친 조각) 22/22 기준과 같음
- 드래그 읽기 시험 selection.js·selection_split.js 통과(기대값에 표시 글자 반영)
- 전체 읽기 따라가기 시험 6개(follow_sim·_b·_c·_d·_off·engine_sim2): 고치기 전 코드와 결과가 표시 글자 말고는 한 줄도 다르지 않음 → 조각 나누기·따라가기·미리 만들기 그대로

■ 바뀐 파일 (BluemingWebReadAloud)
- js/spoken-text.js — LINE_NEEDS_PERIOD(맨 끝), 표시 마침표 지우기(맨 처음)
- js/defaults.js — ADDED_PERIOD, selectionParagraphs 가 그것으로 붙임
- js/speech.js — needsPeriod·recut 이 ADDED_PERIOD, 짧은 줄 바이트 세기에서 표시 제외
- js/page-ui-host.js — alignParagraphs 가 ADDED_PERIOD 재현
- (로컬 시험) .agent/tests/spoken-paseo/compare.mjs·selection.js

■ 확인 못 한 것
- 실제 음성으로 듣는 실측(어사이드)은 아직 — 확장 새로고침 뒤 목록·제목이 있는 글을 드래그 읽기, 구글 문서에서 줄바꿈 있는 문단을 읽어 줄 끝에서 쉬는지 들어 보면 된다.
- 읽는 글 표시 창(작은 창)·형광펜에 보이는 글에는 표시 글자가 들어가지만 보이지 않는 글자라 화면은 예전과 같다(눈으로는 미확인).
