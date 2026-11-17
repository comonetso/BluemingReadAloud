완료했습니다. 정한 규격·바꾼 파일·동시 처리·끊을 때 라이브 연결 닫기는 덧붙임 요청 090a8be2 의 회신에 함께 적었습니다(그쪽 요청대로 함께 담음).

짧게
- 길: POST http://127.0.0.1:51888/v1/tts/noeul, 본문 {"v":1,"text":"…","lang":"ko"}, Origin chrome-extension:// 만 받음
- 성공: 200 audio/wav(PCM 16비트 한 채널 24kHz, 앞뒤 무음 자름) + X-Usage-Key(키별 사용량 칸 이름 12글자)
- 실패: 상태 번호 + {"ok":false,"code","error"} — no_key 503 · ip_not_authorized 401 · unauthorized 401 · timeout 504 · no_audio 502 등
- 노을 순서는 요청 원문의 11-17 판이 아니라 Paseo tts.ts 11-18 판(instructions.append · 다시 시도 · 첫머리 판정)을 따랐습니다. 이쪽 리규형님이 버튼으로 정하셨고, 덧붙임 요청도 같은 내용입니다.
- 키: Paseo 키 파일 google.env 의 OPENAI_API_KEY(이쪽 리규형님 버튼 결정)
- 바꾼 파일(커밋 안 함): noeul_live.py(새) · tts_usage.py · whisperer.py · tests/test_noeul_live.py(새)
- 새 판이 켜지려면 앱 재시작이 필요합니다(리규형님 몫). 실제 OpenAI 연결은 이 PC 가 IP 허용 목록 밖이라 확인하지 못했습니다.
