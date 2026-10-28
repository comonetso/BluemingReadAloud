[완료] 멈추는 제목 목록 확정 · 아이콘 페이지 전체 읽기에도 같은 멈추기 (커밋 안 함, 리규형님 실측 전)

■ 1. 목록 확정 → 한 곳으로 모음
- 새 파일 js/stop-headings.js 하나에 확정된 20개 이름, 이름 비교(띄어쓰기·[편집]/[edit]·앞 번호·콜론 빼고, 대소문자 없이 제목 전체), "이 지점 뒤 첫 멈출 제목 찾기(이미 그런 절 안이면 없음)"를 둠(readAloudStopHeadings).
- 따라 읽기(js/page-ui.js stopAtNotes)는 안에 있던 목록·비교를 지우고 이 파일을 씀 — 동작은 그대로. 서비스 워커가 따라 읽기 때 Readability 와 함께 이 파일을 넣음(js/events.js).
- 이제 목록을 바꿀 곳은 이 파일 한 곳.

■ 2. 아이콘 "페이지 전체 읽기"에도 멈추기
- js/content/html-doc.js: 읽기 시작 때(parse) 첫 번째로 읽을 요소 뒤의 첫 멈출 제목을 찾아 두고, 문단 뽑기(extractParas)가 그 제목부터의 문단을 버림. 제목을 품은 요소(위키백과처럼 본문 전체가 한 요소이고 자식마다 한 줄인 경우)는 그 제목 줄부터 버림.
- 번역 따라 읽기(DeepL — 읽는 중에 다시 뽑기 refreshTexts)도 같은 뽑기 함수라 같이 잘림(실측: 다시 뽑아도 172문단 그대로).
- "이미 그 절 안이면 안 멈춤": 전체 읽기는 늘 페이지 처음(첫 읽을 요소)부터 시작해서(getCurrentIndex = 0, 가운데부터 읽기 없음), 첫 읽을 요소가 그런 절 안일 때만 해당 — 그때는 안 멈춤(같은 함수).
- js/content.js getRequireJs: 전체 읽기 스크립트 목록에 stop-headings.js 를 html-doc.js 앞에 더함.
- 위키백과 제2차 세계대전 실측(ego, 실제 html-doc.js·content.js·readability.js 를 페이지에 넣어 getTexts):
  멈추기 없이 967문단·16.5만 자, 끝 "…Atlas of the World Battle Fronts (July 1943 – August 1945)"(외부 링크 항목), Notes·References·Sources·Further reading·External links 제목이 읽힘
  → 멈추기 켜고 172문단·8.6만 자, 끝 "Other technological and engineering feats…"(See also 바로 앞 문단), 멈출 이름의 제목은 하나도 안 읽힘. 뽑는 시간 0.28초(멈추기 없이 0.35초).
- 따라 읽기 다시 확인: 다섯 곳 모두 같은 문단에서 끝(바뀐 것 없음). 지난 답장에 적고 시험은 안 했던 "참고문헌 절 안에서 고르면 안 멈춤"도 이번에 확인 — Notes 절 안 항목을 고르면 멈추지 않고 본문 끝(외부 링크 마지막 줄)까지.

■ 바뀐 파일 (BluemingWebReadAloud)
- js/stop-headings.js — 새 파일(목록·비교·찾기)
- js/page-ui.js — stopAtNotes 가 공용 파일 사용, 안에 있던 목록·비교 지움
- js/events.js — 따라 읽기 때 stop-headings.js 도 넣음
- js/content.js — 전체 읽기 스크립트 목록에 stop-headings.js
- js/content/html-doc.js — notesHeading·beforeNotes, extractParas 가 자름
- README.md — 본문 읽기 설명에 멈춤 한 줄
- (로컬 시험) .agent/tests/follow-box/run-whole.mjs(새 — 전체 읽기 멈추기), run-big.mjs(공용 파일·참고문헌 안 경우)

■ 확인 방법
1. chrome://extensions 에서 확장 새로고침, 위키백과 긴 문서도 새로고침(이미 넣힌 옛 스크립트를 비우려고).
2. 확장 아이콘으로 전체 읽기 → 재생 바 "다음"으로 끝 쪽까지 넘기면 See also 바로 앞 문단이 마지막(See also·Notes·References·External links 를 읽지 않음).
3. 따라 읽기는 지난번 확인 방법 그대로.
