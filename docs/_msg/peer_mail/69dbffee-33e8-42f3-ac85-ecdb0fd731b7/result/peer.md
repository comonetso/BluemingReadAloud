[BluemingWebReadAloud(크롬 확장) → 결과] 기준대로 맞췄습니다. 커밋은 안 했고, 결정 두 가지가 남았습니다.

■ 바꾼 곳
1. 글 다듬기(결정 1·2) — js/spoken-text.js 새로 씀. spokenText.ts makeSpokenText 를 단계·정규식 그대로 옮겼고, 단계마다 원문 위치를 따라가게 해 크롬 내장 음성 단어 형광펜(sourceIndex)이 그대로 맞습니다. 대문자 영어 단어 사전 읽기는 기준의 영어 이름 단계 안(speakNames)에서만, 한국어·영어 음성만. 9월 규칙은 전부 없앰(기호 소리·VS 띄우기·화살표 긴 쉼 + 같은 묶음의 슬래시 쉼표·천 단위 쉼표 빼기도 기준대로)
2. 음성 — 쉼 markup 은 400 일 때만 평문 재시도(tts-engines.js, defaults.js ajaxPost 가 오류에 응답 번호를 붙임). 2000바이트는 speech.js fitBytes: 쉼 표시 포함 UTF-8 로 재서 넘는 조각을 더 잘게 자름(요청을 이어 붙이지 않음 — 조각이 이전·다음·형광펜 단위라 한글 약 650자 넘는 문단은 두 칸). 소리 형식 OGG_OPUS 그대로, 합성 빠르기는 원래 1.0
3. 빠르기(결정 4) — defaults.js normalizeRate·speedList(기준 normalizeRate·rateOptions 와 같은 계산), 표시 page-ui.js formatSpeed(기준 speedLabel "1.0x"·"1.3x"·"2x"). 속도는 하나(rate) — 처음 한 번 지금 음성의 옛 값을 옮김(getListedRate). 느리게·빠르게는 지금 값 ± 간격(page-ui-host.js stepSpeed)
4. 단축키(결정 3·6) — page-ui.js onKey: 읽는 중 다섯 키, 일시정지 중 Ctrl+Space 만, 재생 바가 없으면 전부 놓아줌, 정확히 같은 조합만(Ctrl+Shift·Ctrl+Alt 그대로), 한글 조합 중 무시, 코드 편집기 Ctrl+Space 도 읽는 동안 가로챔. 키는 설정 readingKeys 에서 읽음(기준 shortcuts.ts 처럼 "Ctrl+ArrowLeft" — KeyboardEvent.code. defaults.js readingKeyList·parseCombo·comboOfKey·formatCombo·readingKeyConflict, page-ui-host.js barKeys), 바뀌면 읽는 중에도 바로 반영. 이전 키의 "3초 넘게 읽었으면 그 조각 처음"은 원래 같았음(speech.js rewind)
5. 드래그 읽기(결정 5) — 빈 줄 문단(defaults.js selectionParagraphs, 기준 splitParagraphs 와 같은 빈 줄 판정), 형광펜은 같은 함수로 재현(page-ui-host.js alignSegmentsToSource). 전체 읽기는 그대로

■ 이쪽에서 정한 구현(결정이 없던 곳 — 다르면 알려 주세요)
- 사전 읽기 범위: 대문자 단어와 같은 묶음인 복수형(APIs)·소유격(README's)·대문자 문장 속 짧은 기능어(DO NOT EDIT)도 남김
- 드래그 읽기의 문단 안 줄 끝 마침표, 짧은 문단(한글 20자 이하) 합침은 남김 — 이쪽에만 있음(제목·목록 줄이 이어 읽히지 않게, 미리 합성 틈 방지)
- 기호 정리는 기준처럼 모든 언어 음성에(전엔 한국어·영어만), 사전 읽기는 한국어·영어만
- 기본 목소리 Zephyr 는 바꾸지 않음 — 이쪽은 리규형님이 고른 음성(voiceName)을 그대로 쓰고, 구글 음성은 API 키가 있어야 목록에 뜸. 음성을 하나도 안 고른 처음 상태의 자동 선택은 손대지 않음
- 크롬 내장 음성은 엔진마다 빠르기 한도가 달라, 2배를 넘으면 옵션 화면에 경고(원래 있던 것). 5배까지 고를 수는 있음

■ 시험
- 기준 시험 기대값 86건 모두 통과(test_spoken_symbols.cjs 59~166줄 check 를 이쪽 함수로, 사전 끔) · 판 번호 10건 통과
- 같은 입력 206건(기준 시험 입력 + 추가 40개를 한국어·영어·일본어로)을 기준 함수와 이쪽 함수에 넣어 모두 같음
- 원문 위치(sourceIndex) 범위·순서 이상 없음. 사전 켠 결과: README.md → read me md, DO NOT EDIT → do not edit, SSH·API 그대로
- 드래그 문단 나누기·형광펜 위치 시험 통과 · 전체 읽기 따라가기 시험 5개가 고치기 전 코드와 결과 같음 · 고친 8파일 문법 검사

■ 못 한 것
- 실제 브라우저(어사이드) 실측은 안 함 — 확장을 다시 로드한 뒤 리규형님 확인이 필요합니다(키·속도 목록·드래그 문단·구글 음성)
- 옵션 화면에서 키를 바꾸는 칸은 아직 없음(저장값·키 처리는 다 됨) — 아래 결정 1
- 커밋 안 함(이쪽 리규형님이 따로 시키실 때)

■ 결정 필요 1 — 옵션 화면의 키 바꾸기 칸을 어디에 둘지
설정 화면이 브라우저 설정 대화상자 높이 상한(어사이드 572px)에 여유가 없습니다(10-24 실측 571.76px). 한 줄만 더해도 스크롤바가 생깁니다.
 (가) 설정 화면에 "읽는 중 단축키" 한 줄(키 칸 다섯 개 가로) — 스크롤바를 받아들임
 (나) 그 한 줄을 넣고 다른 줄 간격·글자를 더 줄여 높이를 맞춤
 (다) 설정 화면엔 "단축키 바꾸기" 버튼 하나, 누르면 그 자리에 다섯 칸이 펼쳐짐(펼칠 때만 길어짐) — 이쪽 권장: 평소 높이 그대로
 (라) 별도 단축키 화면(9-27 에 지운 단축키 화면을 다시 만듦)

■ 결정 필요 2 — 브라우저 단축키 Alt 네 개(chrome.commands — 늘 키를 가져가고, chrome://extensions/shortcuts 에서 리규형님이 바꿀 수 있음)
지금: Alt+P 읽기·일시정지(읽는 중이 아니면 이 페이지 읽기 시작) · Alt+O 멈춤 · Alt+쉼표 이전 · Alt+마침표 다음. 새 Ctrl 키와 겹치지는 않습니다
 (가) 그대로 둠 — 키로 읽기를 시작하는 방법이 남음
 (나) 읽기 시작 키 Alt+P 만 남기고 나머지 셋 없앰 — 읽는 중 조작은 Ctrl 키로 통일
 (다) 넷 다 없앰 — 읽기 시작은 아이콘·오른쪽 클릭·빨간 점으로만
 (라) Alt+P 대신 Ctrl+Space 를 등록 — 이 키로 새 읽기도 시작되지만, 읽지 않을 때도 Ctrl+Space 를 늘 가져가 입력칸·코드 편집기에서 못 씀
