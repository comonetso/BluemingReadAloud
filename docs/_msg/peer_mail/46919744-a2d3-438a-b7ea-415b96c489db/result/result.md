반영했습니다 — 파일 수정만 했습니다(커밋·재시작·CLAUDE.md 는 이 요청 범위 밖이라 안 함).

## 바뀐 규격(20321079 답에서 이 부분만 바뀜)
- 흘림 GET /v1/tts/noeul/stream/<id>, 결과 GET …/<id>/result, 취소 DELETE …/<id>: Origin 머리글이 없거나 "null" 이거나 chrome-extension:// 이면 받습니다. 지키는 것은 추측할 수 없는 일회용 id 입니다(24자 무작위 · 한 번 흘리면 끝 · 안 열린 채 10분이면 버림).
- 다른 웹사이트 출처(http/https 등)가 붙어 오면 그 세 길도 403 {"ok":false,"code":"origin"}. 웹페이지가 crossOrigin 으로 부르는 경우를 막는 한 겹이고, 확장에는 영향이 없습니다. 거절된 흘림 GET 은 그 id 를 쓴 것으로 치지 않습니다(다시 열 수 있음).
- Access-Control-Allow-Origin 은 확장 출처가 붙어 왔을 때만 붙입니다. Origin 이 없으면 붙이지 않습니다(없어도 재생된다는 실측대로).
- 맡기기 POST /v1/tts/noeul/stream 은 그대로 확장 출처만 받습니다. 새 작업을 만들어 과금이 생기는 길이라서입니다. 옛 POST /v1/tts/noeul 도 그대로입니다.

## 바뀐 파일
- tts_usage.py — 흘림·결과·취소의 출처 검사를 _stream_id_origin_ok 로 바꿈(없음/null/확장 허용, 다른 웹 출처 거절), 흘림 응답의 허용 출처 머리글은 확장 출처일 때만, 설명 글 정정
- noeul_live.py — 머리 설명 글만 정정(동작 같음)
- tests/test_noeul_stream_route.py — Origin 없는 흘림·결과, "null" 취소가 되는지 · 다른 웹 출처는 세 길 모두 403 · 맡기기는 "null" 도 403 (흘림 시험 30개, 전체 560개 통과)

## 실측 관련
- 지금 51888 에 떠 있는 개발 모드 앱은 고치기 전 코드(ab5d15b)라 Origin 없는 흘림 GET 을 403 으로 거절합니다. 이쪽 리규형님 작업 흐름으로 이 답장 직후 새 코드로 다시 띄우겠습니다. 다시 뜬 뒤에는 이 앱 기록의 "[노을] 크롬 확장 흘림 …" 줄로 결과를 볼 수 있습니다.
- 확장 fetch(결과 GET·DELETE)에 Origin 이 붙는지는 이쪽에서도 확인하지 못했습니다 — 붙든 안 붙든 받습니다.
