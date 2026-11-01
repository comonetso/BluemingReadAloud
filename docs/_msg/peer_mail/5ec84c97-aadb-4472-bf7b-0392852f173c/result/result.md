정리 끝 — 이 대화 리규형님 확인(버튼 "시작") 뒤 진행했습니다. PC 앱은 이미 거의 맞았고, 남은 한 곳만 고쳤습니다. 커밋·설치 파일은 아직입니다.

이미 맞던 것(근거)
- 고르는 목록 = Paseo 여덟 개·같은 차례: whisperer.py:292 KOREAN_VOICES (Zephyr·Aoede·Callirrhoe·Despina·Kore·Leda = ko-KR-Chirp3-HD-*, Wavenet-A·Wavenet-B = ko-KR-Wavenet-*). 188410e0 때 맞춤 — 그때 남성 WaveNet C·D, Neural2 A·B·C, Standard A·B·C·D 를 뺐습니다.
- 기본 목소리 = Zephyr: whisperer.py:266-267
- 목록 밖 저장값은 그 하나만 맨 앞에 붙임(voiceOptions 와 같음): whisperer.py:2665-2667
- 트레이 메뉴에는 목소리 칸이 없습니다(다섯 항목 고정). 키 확인(whisperer.py:541)은 목록을 받아 키만 확인하고 목소리를 고르지 않습니다.
- Google 이 아닌 읽기 공급자는 이 앱에 없습니다(Gemini 는 번역 전용 — 손대지 않음).

이번에 고친 것
- 설정 창에서 고른 칸을 못 찾을 때 쓰던 값이 옛 기본 Wavenet-A 였습니다(미리 듣기·저장 두 곳) → 기본값 DEFAULT_VOICE(Zephyr)로 묶었습니다: whisperer.py:2705, 2853. 이제 "ko-KR-Wavenet-A" 글자는 여덟 개 목록 안에만 있습니다.

확인
- 시험 418건 통과. 화면은 바뀌지 않습니다(고른 칸을 못 찾는 일은 읽기 전용 목록이라 사실상 없음).
- 저장된 목소리: PC 앱 개발 모드 Zephyr, 설치본 Callirrhoe — 둘 다 여덟 안이라 목록 앞에 따로 붙는 것 없음.
- 남겨 둔 것: 사용량 세기(tts_usage.py)는 목록 밖 저장값(예 옛 Neural2)도 종류별로 따로 쌓습니다 — 옛 설정을 깨지 않으려는 것이고 고르는 길은 아닙니다.
