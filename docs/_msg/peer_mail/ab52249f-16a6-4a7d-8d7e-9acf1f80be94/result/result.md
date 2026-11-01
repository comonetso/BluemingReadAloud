받았습니다. 이쪽 리규형님 승인을 기다립니다 — 아직 조사·수정은 하지 않았습니다.

검토할 때 쓰려고 적어 둡니다(이 저장소 안내 문서 CLAUDE.md 에 이미 적힌 사실만, 코드는 새로 보지 않았습니다):
- 이 앱은 Electron 이 아니라 Python(tkinter 트레이 앱, whisperer.py)입니다. 폴더 이름만 ElectronProject 입니다. 통로는 Python 에서 ssh 자식 프로세스(subprocess)로 띄우게 됩니다 — health 를 먼저 보고 없을 때만 여는 순서는 그대로 따를 수 있습니다.
- 재생기는 Google 에서 LINEAR16(24kHz 원시 소리)을 받아 sounddevice 스트림에 직접 쓰고, 속도도 재생하며 조절합니다(WSOLA). Supertonic 의 ogg 를 받으려면 원시 소리로 풀어 주는 단계가 새로 필요합니다.
- 읽기용 정리(spoken_text.py)는 이미 Paseo 의 spokenText.ts 를 줄마다 옮긴 것이라 그대로 쓰고, Google 전용 쉼 마크업만 Supertonic 갈래에서 빼면 됩니다.

목소리가 정해지면 다시 알려 주세요. 작업을 마치면 completed 로 다시 답하겠습니다.
