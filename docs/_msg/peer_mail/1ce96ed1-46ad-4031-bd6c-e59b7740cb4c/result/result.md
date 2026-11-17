결론: PC 읽기 앱(BluemingReadAloud)에는 OpenAI 로 읽는 길도, OpenAI 목소리를 고르는 칸도 없어서 바꿀 파일이 없습니다. 바꾼 파일 없음(커밋·push 도 없음).

근거
- 읽기는 Google Cloud TTS 하나뿐입니다. 목소리 목록 KOREAN_VOICES = Google 8개(Zephyr·Aoede·Callirrhoe·Despina·Kore·Leda·Wavenet-A·Wavenet-B) — whisperer.py:295-303, 기본값 DEFAULT_VOICE = ko-KR-Chirp3-HD-Zephyr — whisperer.py:269. 이 목록은 Paseo 의 FEATURED_GOOGLE_VOICES(shared/presentation/speech.ts:43)와 같고, 그쪽도 이번에 바뀌지 않아 맞출 것이 없습니다.
- 읽기 공급자(provider)를 고르는 설정이 없습니다. 저장소의 .py 전체에서 openai·gpt-4o·gpt-live·noeul·marin·/v1/audio/speech·realtime 을 찾으면 읽기 코드에는 하나도 없습니다.
- 예전에 저장된 OpenAI 목소리(marin 등)가 들어갈 자리도 없습니다(설정의 tts_settings.voice_name 은 Google 목소리 이름만 씁니다).
- 받아쓰기는 이 앱에서 이미 없앤 기능이고, 번역은 Gemini(translation.py)라 3번 "받아쓰기·번역의 OpenAI 는 그대로"도 해당이 없습니다.

남은 OpenAI 흔적(손대지 않음)
- tts_usage.py:53 IGNORED_KINDS = ("openai",) — Paseo 합계 파일(tts-usage-all.json)의 openai 칸을 이 앱 사용량 화면에 넣지 않고 버립니다. 그래서 Paseo 가 나중에 openai 칸 단위를 글자에서 초로 바꿔도 이 앱 화면에는 영향이 없습니다(칸 이름 "openai" 가 그대로라면). 칸 이름을 바꾸면 그때 알려 주세요.
- .gitignore:15 openai_api_key.txt — 받아쓰기 시절 키 파일을 올리지 않게 막는 줄입니다. 지금 기능과 무관합니다.

확인 못 한 것
- 이 앱에 노을(OpenAI 라이브)로 읽는 길을 새로 만들지는 요청 범위 밖이라 하지 않았습니다(요청은 "고르는 곳이 있으면 줄여 달라"). 만들려면 OpenAI 키 칸·공급자 선택·웹소켓 읽기·사용량 단위가 새로 필요해서 이쪽 리규형님 결정으로 남겨 둡니다. 이 대화는 중계기가 연 대화라 여쭐 사람이 없어, 요약에만 적어 둡니다.
