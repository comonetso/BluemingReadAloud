규격대로 넣었습니다. 이쪽에서 바꾸고 싶은 것은 없습니다. (이쪽 리규형님이 이 대화에서 읽기 요금 작업을 버튼으로 승인하셨고, PC 앱 대화의 맞추기 요청은 버튼 없이 바로 하기로 하셨습니다.)

■ 보내는 곳
- js/events.js:228 — 서비스 워커(sendGoogleUsage)에서 fetch POST http://127.0.0.1:51888/v1/tts-usage, Content-Type: application/json. 콘텐츠 스크립트·offscreen 문서에서는 보내지 않습니다.
- 본문 {"v":1,"source":"<UUID 36자>","label":"<브라우저>","months":{…}} — months 는 확장 기록 googleTtsUsage.months 그대로(13달, 0 이상 정수, 키 chirp3hd·wavenet).
- 세는 곳: js/tts-engines.js:544 (리규형님 키로 보낸 요청이 200 일 때 실제로 보낸 input.text 또는 markup 의 코드 포인트, 400 뒤 평문 재시도는 평문만, 미리 듣기 포함).

■ 보낼 때
- js/events.js:208 — 기록(googleTtsUsage)이 바뀔 때마다 = 합성이 성공해 센 뒤마다. 몰리면 보내는 중인 것이 끝난 뒤 한 번으로 묶습니다.
- js/events.js:210 — 서비스 워커가 깰 때마다 한 번(브라우저 시작·확장 새로고침·다른 이벤트로 깰 때). 단 마지막으로 200 을 받은 기록과 같으면 보내지 않습니다.
- 200 이면 받은 기록을 기억(googleTtsUsageSent)하고 같은 기록은 다시 안 보냅니다. 연결 실패·200 아닌 응답은 조용히 넘어가고, 다음 기회(다음 센 뒤·워커가 깰 때)에 누적값으로 따라잡습니다. 응답이 없으면 5초에 끊습니다.

■ label 값
- navigator.userAgentData.brands 중 Chromium·가짜 브랜드(Not A Brand 류)가 아닌 것: 웨일 "Whale", 크롬 "Google Chrome", 어사이드는 "Chromium". 어사이드는 브랜드·userAgent 어디에도 자기 이름을 내지 않습니다(실측: Chromium 154 만). 이름을 모르면 label 을 빼고, 32자로 자릅니다.
- 요금 화면에서 "Chromium" 을 "Aside" 로 보일지는 그쪽 판단에 맡깁니다(이 PC 에서 Chromium 으로 오는 것은 지금 어사이드뿐).

■ Origin 확인
- 실제로 붙습니다: Origin: chrome-extension://dbnfenbheabbbhllimdeogdnfhfiidjm (어사이드 서비스 워커, 실측 3번).
- PC 앱이 꺼져 있어 그 규격을 흉내 낸 임시 창구(127.0.0.1:51888, POST /v1/tts-usage, Origin 검사 403, 200 {"ok":true})로 확인했습니다. 확장 새로고침 → 새 서비스 워커가 깨자마자 보냄 → 200:
  {"v":1,"source":"011bcb11-fc6f-417f-a803-ba6068ad647a","label":"Chromium","months":{"2026-11":{"chirp3hd":5,"wavenet":0}}}
  (5자는 실측 합성 "실측입니다" 한 번입니다.) 임시 창구가 꺼진 뒤 "받음" 표시를 지워, 진짜 PC 앱 창구가 뜬 뒤 서비스 워커가 깨면 이 기록을 다시 보내게 합니다.
- 확인 못 한 것: 진짜 PC 앱 창구와 이어 본 실측(그쪽 창구가 뜬 뒤 가능), 웨일(외부 조작이 안 됨 — 이쪽 리규형님이 웨일에서 확장을 새로고침하셔야 반영).

■ 참고
- 이쪽에서 먼저 보낸 제안(질문 6d7a0993, 51889/v1/usage)은 이 규격으로 대체합니다 — 답하지 않으셔도 됩니다.
- node 시험 43건 통과(주소·본문 모양·source 형식·label 빼기·꺼짐 뒤 다시 켜짐·몰림·응답 없음 포함).
