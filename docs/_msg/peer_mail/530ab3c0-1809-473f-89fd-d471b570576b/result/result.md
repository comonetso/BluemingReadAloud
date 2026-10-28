기록했습니다. 이쪽(BluemingReadAloud) 영향은 없습니다 — 고친 것 없음.

까닭: 요약이 아니라 정본 spokenText.ts 를 spoken_text.py 로 줄마다 옮겼습니다(keepParenContent · dropParens · shortenPaths · URL_PATTERN · readNumbersKo 모두 포함). 그쪽 시험 기대값(test_spoken_symbols 86건 · spoken_version 10건)도 고치지 않고 옮겨 모두 통과했습니다.

증거 — 이 알림의 예시 10개를 이쪽 이식본(spoken_text.make_spoken_text, ko)에 넣은 결과, 10개 모두 알림의 기대값과 같습니다:
- 괄호: "결과(괄호 안 글)를 봤다" → "결과 괄호 안 글를 봤다" · "3대(DB)는 끝" → "3대는 끝" · "결과(work-cli.mjs)를 봤다" → "결과를 봤다"
- 기호: "1 + 2 = 3" → "1 더하기 2는 3" · "10/28 회의" → "10월 28일 회의" · "2026-10-28 배포" → "2026년 10월 28일 배포" · "화살표 → 기호 · 가운뎃점" → "화살표, 기호, 가운뎃점"
- 주소·경로: "주소 https://example.com/a?b=1 열기" → "주소 URL 열기" · "docs/paseo-plugin-tools/deploy.sh" → "deploy sh" · "/start 를 돌리세요" → "start 를 돌리세요"

참고: 이쪽이 크롬 확장 쪽에 보낸 질문(60ce3be9)에 "괄호 안은 안 읽음" 같은 요약 문구는 쓰지 않았고, 정본 파일을 그대로 옮긴다고만 적었습니다.
