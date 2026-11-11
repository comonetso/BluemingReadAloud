완료(리규형님 컨펌 받고 진행). 파일 수정과 단위 시험까지이고, 커밋·개발 실행·빌드는 아직 안 했습니다.

[바꾼 것]
- tts_usage.py
  - key_mark(key) = Paseo usageKeyMark 와 같은 계산(trim → UTF-8 sha256 hex 앞 12, tail 끝 4). 키 값은 안 씀.
  - UsageCounter.count(kind, sent, key=이름표): months 에 더하는 것과 같은 시점·글자 수를 keys[id].months[달][종류] 에 더함. 기존 months 그대로.
  - 키 칸 없는 파일(옛 판·keys 칸이 깨진 파일)은 처음 셀 때 이번 달 몫만 지금 키로 옮김(지난달 그대로) — Paseo adoptKeys 와 같게.
  - UsageCounter.adopt_keys(key): 앱이 키로 합성기를 만들 때(시작·키 변경) 파일이 있고 keys 칸이 없으면 만들고 이번 달을 옮김(Paseo adoptUsageKeysNow 와 같게). 파일 없음·깨짐·keys 이미 있음이면 안 씀.
  - 키 칸마다 자기 달 중 최근 13개(Paseo pruneMonths(e.months) 와 같게), 달 없는 키 칸은 뺌.
  - ExtensionReports: 본문 keys 를 sources[source].keys 에 그대로 보관(받을 때마다 통째로 바꿈 — keys 를 안 보낸 판이면 칸 없음). keys 가 없거나 null 이면 키 없이 받음. 모양이 틀리면(id 가 12자리 소문자 16진수가 아님·tail 4글자 초과·달/종류 칸 틀림) 본문 통째 거절, 까닭 "keys"(months 와 같은 규칙).
- whisperer.py: 합성기를 만들 때 그 키의 이름표(google_tts_key_mark)를 같이 둠. 읽기는 시작할 때의 이름표로, 미리 듣기는 그 순간의 합성기·이름표로 셈.
- 시험: tests/test_tts_usage.py 10개 추가(이름표 기대값은 node crypto createHash 로 뽑은 값), tests/test_tts_engine.py 의 읽기 세기 시험에 "읽는 도중 키를 바꿔도 처음 키로" 추가. CLAUDE.md 설명 갱신.

[확인한 것]
- py_compile 통과, 전체 단위 시험 428개 OK(사용량 시험 26 → 36).
- 파일 모양: {"v":1,"months":{…},"keys":{"<id>":{"tail":"1234","months":{"2026-11":{"chirp3hd":N}}}}}. 키 칸에는 센 종류만 있고 0 은 채우지 않음(Paseo countUsage 와 같음).

[못 한 것·주의]
- 앱을 실제로 돌려 %APPDATA% 파일에 keys 가 생기는지는 아직 안 봤습니다(개발 실행·리규형님 확인 전).
- 지금 설치된 앱은 옛 코드라, 설치본으로 읽으면 keys 없이 months 만 다시 씁니다. 그 사이 Paseo 는 이 앱 몫을 PC 키로 봅니다. 새 코드가 다음에 셀 때 이번 달을 다시 옮기므로 숫자는 맞춰집니다(그 사이 키를 안 바꿨다면). 새 빌드·설치는 리규형님 결정 대기.
- Paseo keyedMonthCounts 로 이쪽이 쓴 파일을 직접 읽어 보는 교차 시험은 안 했습니다(모양은 tts.ts 495–630 을 읽고 맞춤).
- 크롬 확장이 실제로 keys 를 보내는 것은 그쪽 몫이라 확인 못 했습니다.
