바꿨습니다 — Paseo 사용량 내보내기 간격 5분 → 1분(PC 몫·서버 셋 몫 모두). 이쪽 리규형님 버튼 "PC·서버 모두 1분".

- 코드: paseo-plugins/claude-state-bar/server/presentation/tts.ts USAGE_EXPORT_MS = 60_000. 파일 위치·모양(v·updatedAt·month·sources·total·stale)은 그대로.
- 한 차례가 끝난 뒤 다음 차례를 1분 뒤에 겁니다(startUsageExport) — 서버 접속이 늦어도(접속 시간 초과 8초·한 서버 20초) 차례가 겹치지 않습니다. 그래서 실제 간격은 "1분 + 한 차례 걸린 시간"(지금 약 1초)입니다.
- 서버 부담: PC 가 서버마다 1분에 한 번 ssh 로 작은 파일 몇 개를 읽습니다(서버당 하루 약 1,440번). 이쪽에서 괜찮다고 판단했습니다.
- 시험 tts_usage 13/13(1분·차례 뒤 예약 확인) · 형 검사 통과 · PC 데몬에 배포(다시 불러온 뒤 요청 끊김·시간 초과 0).
- 실측: tts-usage-all.json updatedAt 19:28:09 → 19:29:10(KST), stale 없음, 이번 달 Chirp 3 HD 합계 30,019자.
- PC 데몬에서만 도는 코드라 서버에는 다음 배포 때 같은 판으로 맞춥니다(동작 영향 없음).
