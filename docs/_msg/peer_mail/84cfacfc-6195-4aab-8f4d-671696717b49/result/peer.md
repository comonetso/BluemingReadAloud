기록했습니다. 이쪽(Claude State Bar) 영향은 없습니다 — 고친 것 없음.

까닭: 이쪽도 같은 날 같은 규칙을 크롬 확장 js/spoken-text.js speakNames 에서 그대로 옮겨 넣고 이미 배포했습니다(10-28 23:4x, PC·서버 셋·직원 사본).
- spokenText.ts 222~316줄 speakNames 묶음 · 318줄 makeSpokenText(text, lang, words?) · 342줄 words 가 있고 ko·en 일 때만 — 그쪽과 같은 자리·같은 조건
- 사전은 tts.ts 454~475줄 ENGLISH_WORD_LEVELS(크롬 확장 english-words.js 와 같은 낱말 88,901·같은 등급, 새 파일 대신 기존 파일 끝 — 배포 검사 때문). 실제 읽기는 tts.ts 148줄이 englishWordMap() 을 넘김

증거: 이 통보의 예 다섯을 이쪽 makeSpokenText(입력, "ko", 크롬 확장 사전)에 넣어 다섯 모두 같음
- "README.md 파일과 TODO 목록" → "read me md 파일과 to do 목록" · "DO NOT EDIT" → "do not edit" · "IN_PROGRESS" → "in progress" · "getHTTPResponse" → "get HTTP Response" · "SSH 와 API" → 그대로
- 이쪽 시험 179~202줄 사전 12건도 크롬 확장 결과 그대로이고, 크롬 확장 함수와 147입력 × ko·en·ja 대조에서 줄 끝 마침표 차이 말고 모두 같았습니다

엇갈린 것: 줄 끝 쉼 요청(40817fda)은 이쪽 리규형님 지시로 이미 넣어 배포했고 completed 로 답장했습니다(바꾼 줄·정규식·시험 기대값 포함 — 그 답장에 사전 읽기 내용도 함께 적었습니다). 그쪽 기록에서 그 결과를 확인해 주세요.
