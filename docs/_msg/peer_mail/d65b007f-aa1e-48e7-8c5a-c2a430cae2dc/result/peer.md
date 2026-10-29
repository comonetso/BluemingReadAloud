[완료] 따라 읽기가 기사 아닌 페이지에서 대화 영역 끝에서 멈추고, 단추·숨긴 글·시각을 뺍니다 (js/page-ui.js, 미커밋)

■ 끝을 정한 기준
- Readability 가 기사를 찾고 고른 곳이 기사 안이면 지금 그대로(기사 마지막 블록 + 참고문헌 제목 20개 앞 멈춤).
- 아니면(기사 아님 · 기사 밖 · Readability 없음): 고른 글의 첫 글자를 감싼 요소부터 위로 올라가며 처음 만나는
  "getComputedStyle(e).overflowY 가 auto·scroll·overlay 이고 e.scrollHeight > e.clientHeight" 인 요소의 끝까지(그 요소 childNodes 끝). body 까지 없으면 페이지 끝.
  그 뒤 참고문헌 제목 멈춤은 그대로 적용. (page-ui.js articleEnd → 새 함수 scrollBoxEnd)

■ 아이콘·시각을 거른 기준
- 텍스트 노드의 부모가 closest('button, [role="button"], [aria-hidden="true"], time') 안이면 그 글자를 지움(새 함수 isPagePart·dropText).
  지운 자리 앞뒤 공백은 하나로 합치고, 줄바꿈 수는 지운 조각 사이사이 공백 중 가장 많은 쪽(문단 사이 블록이면 빈 줄 유지, 문장 속 단추면 빈칸 하나).
  형광펜 짝짓기·블록 나눔도 같은 노드를 뺌.
- 적용: 따라 읽기와 "이 말만 읽기"(넓힌 글)만. 창 없는 드래그 읽기(고른 그대로)는 안 뺌.
- 참고: 확장의 글은 크롬 선택 글(selection.toString)이라 user-select:none 글은 원래 안 들어갑니다. claude.ai 의 시각·단추·옆 칸 대부분이 select-none 이라 이미 빠져 있었고, PC 앱 UIA 측정의 35칸 대부분은 확장에선 애초에 안 읽혔을 것입니다. PC 앱은 이 구분이 없으니 user-select:none 판정도 맞춰야 같은 결과가 날 수 있습니다.

■ 실측 (어사이드, 실제 확장 파일을 서비스 워커와 같은 방식으로 그 탭에 넣고 captureSelection — 소리 없음)
- "x.com 감시 - 삭제금지" 대화는 찾지 못했습니다: 어사이드 열린 탭에 없고, claude.ai recents·code 목록 링크 이름에도 없었습니다. 주소를 알면 같은 스크립트로 바로 잴 수 있습니다(.agent/tests/follow-box/run-claude.js).
- 대신 같은 계열 화면인 Claude Code 텔레그램 채널 "메일확인"(claude.ai/code/project/chan_…)의 마지막 메시지 마지막 문단에서:
  · 고치기 전: 마지막 문단 뒤에 "이와 같은 링크는 Claude 데스크톱 앱에서 열립니다."(화면 아래 알림 띠, 대화 상자 밖) 한 줄이 더 읽힘. Readability 판정 isProbablyReaderable = false → 페이지 끝까지 갈래 확인.
  · 고친 뒤: 마지막 문단에서 끝(뒤에 0자). 형광펜 짝짓기 됨.
  · 대화 상자 = 'h-full overflow-y-auto overflow-x-hidden [contain:strict]'(scrollHeight 9191 > clientHeight 723, 입력창 없음). 입력창·오른쪽 개요 칸은 그 바깥 상자('dframe-pane-scroller …', 스크롤 안 됨)에 있음.
  · 이 화면의 메시지 아래 "메시지 작업 표시" 단추·"오전 1:33"(time)은 user-select:none 이라 원래 안 읽힘.
- ego 흉내 화면(왼쪽 목록 · 스크롤 대화 상자 · 메시지마다 Copy 단추·aria-hidden 아이콘·time · 본문 속 인라인 단추 · 입력창 · 오른쪽 Routines 칸, run-chat.mjs):
  첫 문단 → 대화 끝까지 4문단, 단추·숨긴 글·시각 모두 빠지고 입력창·예약 칸 없음 / 마지막 문단 → 그 문단만 / 인라인 단추 든 문단 "이 말만" → 단추 글 빠지고 빈칸 하나.
- 바뀌지 않은 것 확인: 따라 읽기 창 8경우(run.mjs) 같음. 위키백과 제2차 세계대전 앞쪽 문단 → 9.3만 자·227조각, "See also" 앞 문단에서 끝(전과 같음), 참고문헌 안에서 고르면 안 멈춤. 시간 0.21~0.29초(전 0.17~0.21초, 빼는 글 짝짓기 한 번 더).

■ 한계 — 리규형님 결정이 필요합니다 (그대로 두었습니다)
- 대화가 짧아 대화 상자가 스크롤되지 않으면 "실제로 스크롤되는 상자"가 없어 예전처럼 페이지 끝까지 갑니다(흉내 화면에서 확인: 입력창 문구·Routines 칸까지 읽음).
  대안: (가) 그대로 둠 (나) 스크롤 여부를 안 보고 overflow-y 가 auto·scroll 인 가장 가까운 상자 — 짧은 대화도 잡히지만, 메시지 안 코드 블록·표처럼 가로 스크롤 상자(overflow-x 가 auto 면 overflow-y 도 auto 로 계산됨)에서 고르면 그 상자 안에서 멈출 위험 (다) (나) + overflow-x 가 auto·scroll 인 상자는 건너뜀.
- 캡처의 영어 화면(오른쪽 Routines·Outputs)에서 실제로 무엇이 선택 가능해 읽혔는지는 그 화면을 못 찾아 확인 못 했습니다. 리규형님이 확장을 새로고침한 뒤 그 대화에서 써 보셔야 확정됩니다.
- 커밋은 안 했습니다(이쪽 리규형님이 시키실 때).
