# TTS 기능 추가 구현 계획

## 1단계: 설정 저장/로드 (save_settings, load_settings)
- tts_voice_name 추가
- tts_speaking_rate 추가

## 2단계: speak_text 함수 업데이트
- 설정된 voice_name 사용
- 설정된 speaking_rate 사용
- current_audio_stream에 스트림 저장

## 3단계: TTS 중지/재개 함수
- stop_tts(): 현재 재생 중지
- resume_tts(): (필요시)

## 4단계: TTS 설정 대화상자
- show_tts_settings_dialog()
- 음성 선택 (드롭다운)
- 속도 조절 (슬라이더)
- 미리듣기 버튼

## 5단계: 트레이 메뉴에 추가
- "TTS 설정"
- "TTS 중지" (재생 중일 때만 활성화)

## 구현 순서
1. save_settings, load_settings 수정
2. speak_text 수정
3. stop_tts 함수 추가
4. show_tts_settings_dialog 추가
5. 트레이 메뉴 업데이트
