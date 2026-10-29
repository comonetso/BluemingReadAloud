[완료] 짧은 대화도 대화 상자 끝에서 멈춥니다 — 단, (다) 그대로는 안 돼서 이쪽에서 리규형님이 보완을 고르셨습니다 (js/page-ui.js scrollBoxEnd, 미커밋)

■ (다) 그대로 넣었을 때 생긴 문제 (흉내 화면 실측)
- 브라우저는 overflow-y:auto 만 적은 상자의 overflow-x 계산값도 auto 로 돌려줍니다(CSS 규칙: 한쪽이 visible 이 아니면 visible 은 auto 로 바뀜). 반대로 overflow-x:auto 만 적은 코드 블록도 overflow-y 가 auto.
  → 계산값으로는 "세로만 적은 대화 상자"와 "가로 스크롤 코드 블록"이 둘 다 (auto, auto) 라 구분이 안 됩니다.
- 그래서 (다) 그대로면 overflow-y 만 적은 대화 상자를 코드 블록으로 보고 건너뛰어, 긴 대화조차 페이지 끝까지 읽었습니다(d65b007f 기준보다 나빠짐).
- claude.ai 는 대화 상자에 overflow-x:hidden 을 따로 적어서(텔레그램 채널 화면 실측: 'h-full overflow-y-auto overflow-x-hidden', ox=hidden) (다)가 의도대로 됩니다.

■ 리규형님 결정 (이 대화에서 버튼, 2026-10-29): "지난번 기준도 함께"
- 최종 기준: 고른 글의 첫 글자를 감싼 요소부터 위로 올라가며
  overflowY ∈ {auto, scroll, overlay} 이고 [ overflowX ∉ {auto, scroll, overlay}  또는  scrollHeight > clientHeight ] 인 첫 조상의 끝.
  없으면 페이지 끝. 기사 판정 페이지(articleEnd·참고문헌 제목 멈춤)와 단추·숨긴 글·시각 빼기는 그대로.
- 남는 한계(수락): ① overflow-y 만 적은 사이트에서 짧은 대화는 페이지 끝까지 ② 높이가 정해져 세로로 스크롤되는 코드 블록 안에서 고르면 그 블록 끝에서 끊김.

■ 실측
- 흉내 화면(run-chat.mjs, 대화 상자 = claude.ai 처럼 overflow-y:auto + overflow-x:hidden):
  · 짧은 대화(상자 729/729, 안 스크롤): 마지막 문단 → 그 문단만 / 첫 문단 → 대화 끝까지, 입력창 문구·Routines 칸 안 읽음 ✔
  · 코드 블록(pre overflow-x:auto) 안·표(div overflow-x:auto) 안에서 골라 따라 읽기 → 끊기지 않고 대화 끝까지 ✔
  · 첫 메시지를 감싼 상자에 overflow-y:auto(스크롤 안 됨) → 일찍 멈추지 않고 대화 끝까지 ✔ (그 상자도 계산값이 가로 auto 라 건너뜀)
  · 높이 정해진 세로 스크롤 코드 블록(overflow:auto; max-height) 안 → 그 블록 끝에서 끊김(한계 ②)
- 흉내 화면, 대화 상자 = overflow-y:auto 만: 긴 대화 → 대화 끝에서 멈춤 ✔ / 짧은 대화 → 입력창·Routines 까지 읽음(한계 ①)
- 처음부터 있던 경우: 따라 읽기 창 8경우(run.mjs) 결과 글 같음 ✔. 위키백과 제2차 세계대전 → 9.3만 자·227조각, "See also" 앞 문단에서 끝 ✔, 참고문헌 안 항목 → 안 멈춤 ✔, 0.19~0.26초.
- 어사이드 실제 확장(claude.ai 텔레그램 채널 "메일확인" 대화, 마지막 문단): 뒤에 0자 ✔ (실제 짧은 claude.ai 대화는 못 재 봄 — 흉내 화면으로만)
- 일찍 멈추는 일반 레이아웃 상자: 흉내 화면·채널 화면에서는 보이지 않았습니다. 일반 claude.ai 대화(/chat/…) 화면은 본문이 늦게 떠 측정이 안 됐습니다.
