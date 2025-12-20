# messages.py - 다국어 메시지 정의 파일

# 다국어 메시지
messages = {
    "ko": {
        "start": "=== Whisperer Voice-to-Text 시작 ===",
        "start_time": "시작 시간: {}",
        "os": "운영체제: {}",
        "recordings_dir_created": "녹음 파일 저장 폴더 생성: {}",
        "recordings_dir": "녹음 파일 저장 폴더: {}",
        "default_input_device": "기본 입력 장치: {} (장치 번호: {})",
        "mic_init": "마이크 초기화 중...",
        "mic_init_complete": "마이크 초기화 완료",
        "mic_init_error": "마이크 초기화 오류: {}",
        "tray_icon_created": "시스템 트레이에 아이콘이 생성되었습니다. 우클릭하여 메뉴를 확인하세요.",
        "key_detected": "키 입력 감지: {}",
        "ctrl_key_pressed": "Ctrl 키 눌림",
        "shift_key_pressed": "Shift 키 눌림",
        "alt_key_pressed": "Alt 키 눌림",
        "key_combo_detected": "Ctrl + Shift + Alt 조합 감지됨",
        "recording_start": "\n녹음 시작 (Ctrl+Shift+Alt 조합)",
        "recording_mic": "녹음에 사용할 마이크: {}",
        "recording_stream_started": "녹음 스트림 시작됨",
        "recording_stop": "녹음 중지...",
        "mic_stream_stopping": "마이크 스트림 중지 중...",
        "mic_stream_stopped": "마이크 스트림 중지됨 - 시스템 트레이에서 마이크 아이콘이 사라져야 함",
        "mic_stream_stop_error": "마이크 스트림 중지 오류: {}",
        "no_audio_data": "녹음된 오디오 데이터가 없습니다.",
        "recording_length": "녹음 길이: {:.2f}초",
        "recording_too_short": "녹음이 1초 미만입니다.",
        "audio_file_saved": "오디오 파일 저장 완료: {}",
        "sending_to_whisper": "OpenAI Whisper에 오디오 데이터 전송 중...",
        "using_language": "언어 설정: {}",
        "api_response_time": "API 응답 시간: {:.0f}ms",
        "transcript": "Transcript:",
        "text_copied": "텍스트가 클립보드에 복사되었습니다.",
        "paste_success_1": "방법 1로 붙여넣기 성공",
        "paste_fail_1": "방법 1 붙여넣기 실패: {}",
        "paste_success_2": "방법 2로 붙여넣기 성공",
        "paste_fail_2": "방법 2 붙여넣기 실패: {}",
        "paste_success_3": "방법 3으로 붙여넣기 성공",
        "paste_fail_3": "방법 3 붙여넣기 실패: {}",
        "all_paste_failed": "모든 붙여넣기 방법이 실패했습니다. 수동으로 Ctrl+V를 눌러주세요.",
        "text": "텍스트: {}",
        "copy_error": "텍스트 복사 중 오류 발생: {}",
        "manual_copy": "수동으로 텍스트를 복사하세요:",
        "api_error": "OpenAI API 오류: {}",
        "console_opened": "=== 콘솔 창이 열렸습니다 ===",
        "program_status": "프로그램 상태: 실행 중",
        "recordings_folder": "녹음 파일 저장 폴더: {}",
        "console_open_error": "콘솔 창 열기 오류: {}",
        "open_recordings_folder": "녹음 파일 폴더 열기",
        "open_console": "콘솔 창 열기",
        "exit": "종료",
        "change_language": "언어 변경 (Change Language)",
        "language_changed": "언어가 변경되었습니다: {}",
        "whisper_console": "Yeogiaen WhisperTyper 콘솔",
        "console_title": "=== Yeogiaen WhisperTyper 콘솔 ===",
        "console_info": "이 창을 닫아도 프로그램은 계속 실행됩니다.",
        "log_start": "로그 출력을 시작합니다...",
        "key_monitoring": "키 입력 감지 및 녹음 상태를 모니터링합니다...",
        "tray_missing": "pystray 또는 PIL 라이브러리가 설치되지 않았습니다. 시스템 트레이 기능이 비활성화됩니다.",
        "pyaudio_available": "PyAudio 라이브러리를 사용합니다.",
        "pyaudio_missing": "PyAudio 라이브러리가 설치되지 않았습니다. sounddevice를 사용합니다.",
        "api_key_missing": "API 키 파일({})이 없습니다. 직접 API 키를 입력해주세요.",
        "enter_api_key": "OpenAI API 키를 입력하세요: ",
        "no_api_key": "API 키가 입력되지 않았습니다. 프로그램을 종료합니다.",
        "api_key_saved": "API 키가 {} 파일에 저장되었습니다.",
        "api_key_save_error": "API 키 저장 중 오류 발생: {}",
        "api_key_read_error": "API 키 파일 읽기 오류: {}",
        "audio_devices_info": "=== 오디오 입력 장치 정보 ===",
        "default_device": "기본 입력 장치: {} (장치 번호: {})",
        "recording_device": "녹음에 사용할 마이크: {}",
        "mic_preinit": "마이크 장치 미리 초기화 중...",
        "mic_preinit_success": "마이크 초기화 성공 - 시스템 트레이에 마이크 아이콘이 표시되어야 함",
        "mic_preinit_release": "마이크 초기화 해제",
        "mic_preinit_error": "마이크 미리 초기화 오류: {}",
        "program_title": "\n=== Whisperer Voice-to-Text ===",
        "hold_keys": "Hold Left Ctrl + Shift + Alt to record",
        "press_to_exit": "Press CTRL+C to exit",
        "waiting_input": "Waiting for input...",
        "press_enter_exit": "\nPress Enter to exit...",
        "set_openai_api_key": "OpenAI API 키 설정",
        "openai_api_key_title": "OpenAI API 키 설정",
        "openai_api_key_desc": "OpenAI API 키를 입력하세요. API 키는 https://platform.openai.com/api-keys 에서 확인할 수 있습니다.",
        "save": "저장",
        "cancel": "취소",
        "error": "오류",
        "warning": "경고",
        "no_api_key_warning": "API 키를 입력하지 않았습니다. API 키는 필수입니다.",
        "api_key_required": "OpenAI API 키가 필요합니다",
        "api_key_required_desc": "Whisper를 사용하기 위해서는 OpenAI API 키가 필요합니다.\nAPI 키를 입력하지 않으면 프로그램이 종료됩니다.",
        "api_key_loaded": "OpenAI API 키가 로드되었습니다. 변경하려면 Ctrl+Alt+O를 누르거나 시스템 트레이 메뉴를 사용하세요.",
        "api_key_shortcut_info": "API 키 변경 단축키: Ctrl+Alt+O",
        "api_key_shortcut_detected": "API 키 설정 단축키 감지됨 (Ctrl+Alt+O)",
        "api_key_testing": "API 키 테스트 중...",
        "api_key_valid": "API 키가 유효합니다.",
        "api_key_invalid": "잘못된 API 키입니다. 다시 확인해주세요.",
        "api_key_invalid_long": "API 키가 잘못되었습니다. API 키를 확인하고 다시 설정해주세요.",
        "api_key_error": "API 키 오류",
        "api_test_error": "API 테스트 중 오류 발생",
        "api_connection_error": "API 서버 연결 실패. 인터넷 연결을 확인하세요.",
        "openai_module_error": "OpenAI 모듈을 로드할 수 없습니다.",
        "processing_audio": "오디오 처리 중...",
        "saving_audio_file": "오디오 파일 저장 중: {}",
        "no_api_key_set": "API 키가 설정되지 않았습니다. API 키 설정 창을 엽니다.",
        "auto_language_detection": "자동 언어 감지 사용 중...",
        "auto_detection_enabled": "언어 자동 감지가 활성화되었습니다.",
        "auto_detection_disabled": "언어 자동 감지가 비활성화되었습니다.",
        "language_menu": "언어 설정",
        "auto_detection": "언어 자동 감지",
        "korean_language": "한국어",
        "english_language": "영어",
        "recognition_result": "음성 인식 결과",
        "auto_language_mode": "자동 언어 감지 모드",
        "recognized_text": "인식된 텍스트: {}",
        "text_length": "텍스트 길이: {} 글자",
        "attempting_paste": "붙여넣기 시도 중...",
        "paste_complete": "붙여넣기 완료",
        "paste_error": "붙여넣기 오류: {}",
        "attempting_direct_input": "대체 방법으로 텍스트 직접 입력 시도...",
        "direct_input_complete": "직접 텍스트 입력 완료",
        "direct_input_error": "직접 텍스트 입력 오류: {}",
        "clipboard_success": "결과가 클립보드에 복사되었습니다. Ctrl+V로 붙여넣기 할 수 있습니다.",
        "all_input_failed": "경고: 텍스트 입력 및 복사 모두 실패했습니다.",
        "no_text_recognized": "텍스트를 인식하지 못했습니다.",
        "recognition_error": "음성 인식 오류: {}",
        "openai_api_not_set": "OpenAI API 또는 API 키가 설정되지 않았습니다.",
        "audio_processing_error": "오디오 처리 오류: {}",
        "recording_stop_error": "녹음 종료 오류: {}"
    },
    "en": {
        "start": "=== Whisperer Voice-to-Text Started ===",
        "start_time": "Start time: {}",
        "os": "Operating system: {}",
        "recordings_dir_created": "Recordings folder created: {}",
        "recordings_dir": "Recordings folder: {}",
        "default_input_device": "Default input device: {} (Device number: {})",
        "mic_init": "Initializing microphone...",
        "mic_init_complete": "Microphone initialization complete",
        "mic_init_error": "Microphone initialization error: {}",
        "tray_icon_created": "System tray icon created. Right-click to see menu options.",
        "key_detected": "Key detected: {}",
        "ctrl_key_pressed": "Ctrl key pressed",
        "shift_key_pressed": "Shift key pressed",
        "alt_key_pressed": "Alt key pressed",
        "key_combo_detected": "Ctrl + Shift + Alt combination detected",
        "recording_start": "\nRecording started (Ctrl+Shift+Alt combination)",
        "recording_mic": "Microphone used for recording: {}",
        "recording_stream_started": "Recording stream started",
        "recording_stop": "Recording stopped...",
        "mic_stream_stopping": "Stopping microphone stream...",
        "mic_stream_stopped": "Microphone stream stopped - Microphone icon should disappear from system tray",
        "mic_stream_stop_error": "Microphone stream stop error: {}",
        "no_audio_data": "No audio data recorded.",
        "recording_length": "Recording length: {:.2f} seconds",
        "recording_too_short": "Recording is less than 1 second.",
        "audio_file_saved": "Audio file saved: {}",
        "sending_to_whisper": "Sending audio data to OpenAI Whisper...",
        "using_language": "Language setting: {}",
        "api_response_time": "API response time: {:.0f}ms",
        "transcript": "Transcript:",
        "text_copied": "Text copied to clipboard.",
        "paste_success_1": "Paste successful using method 1",
        "paste_fail_1": "Paste failed using method 1: {}",
        "paste_success_2": "Paste successful using method 2",
        "paste_fail_2": "Paste failed using method 2: {}",
        "paste_success_3": "Paste successful using method 3",
        "paste_fail_3": "Paste failed using method 3: {}",
        "all_paste_failed": "All paste methods failed. Please press Ctrl+V manually.",
        "text": "Text: {}",
        "copy_error": "Error copying text: {}",
        "manual_copy": "Please copy the text manually:",
        "api_error": "OpenAI API error: {}",
        "console_opened": "=== Console window opened ===",
        "program_status": "Program status: Running",
        "recordings_folder": "Recordings folder: {}",
        "console_open_error": "Console open error: {}",
        "open_recordings_folder": "Open Recordings Folder",
        "open_console": "Open Console",
        "exit": "Exit",
        "change_language": "Change Language (언어 변경)",
        "language_changed": "Language changed to: {}",
        "whisper_console": "Yeogiaen WhisperTyper Console",
        "console_title": "=== Yeogiaen WhisperTyper Console Window ===",
        "console_info": "You can monitor program logs and status in this window.",
        "log_start": "Starting log recording...",
        "key_monitoring": "Monitoring key inputs...",
        "tray_missing": "pystray or PIL library is not installed. System tray functionality will be disabled.",
        "pyaudio_available": "Using PyAudio library.",
        "pyaudio_missing": "PyAudio library is not installed. Using sounddevice instead.",
        "api_key_missing": "API key file ({}) not found. Please enter your API key directly.",
        "enter_api_key": "Enter your OpenAI API key: ",
        "no_api_key": "No API key entered. Exiting program.",
        "api_key_saved": "API key saved to {} file.",
        "api_key_save_error": "Error saving API key: {}",
        "api_key_read_error": "Error reading API key file: {}",
        "audio_devices_info": "=== Audio Input Device Information ===",
        "default_device": "Default input device: {} (Device number: {})",
        "recording_device": "Microphone to use for recording: {}",
        "mic_preinit": "Pre-initializing microphone device...",
        "mic_preinit_success": "Microphone initialization successful - Microphone icon should appear in system tray",
        "mic_preinit_release": "Microphone initialization released",
        "mic_preinit_error": "Microphone pre-initialization error: {}",
        "program_title": "\n=== Whisperer Voice-to-Text ===",
        "hold_keys": "Hold Left Ctrl + Shift + Alt to record",
        "press_to_exit": "Press CTRL+C to exit",
        "waiting_input": "Waiting for input...",
        "press_enter_exit": "\nPress Enter to exit...",
        "set_openai_api_key": "Set OpenAI API Key",
        "openai_api_key_title": "OpenAI API Key Settings",
        "openai_api_key_desc": "Enter your OpenAI API Key. You can find your API key at https://platform.openai.com/api-keys",
        "save": "Save",
        "cancel": "Cancel",
        "error": "Error",
        "warning": "Warning",
        "no_api_key_warning": "API key is required.",
        "api_key_required": "OpenAI API Key Required",
        "api_key_required_desc": "An OpenAI API key is required to use Whisper.\nThe program will exit if no API key is provided.",
        "api_key_loaded": "OpenAI API key loaded. Press Ctrl+Alt+O or use the system tray menu to change it.",
        "api_key_shortcut_info": "API key change shortcut: Ctrl+Alt+O",
        "api_key_shortcut_detected": "API key settings shortcut detected (Ctrl+Alt+O)",
        "api_key_testing": "Testing API key...",
        "api_key_valid": "API key is valid.",
        "api_key_invalid": "Invalid API key. Please check and try again.",
        "api_key_invalid_long": "Invalid API key. Please check and update your API key.",
        "api_key_error": "API Key Error",
        "api_test_error": "API test error",
        "api_connection_error": "Failed to connect to API server. Check your internet connection.",
        "openai_module_error": "Could not load OpenAI module.",
        "processing_audio": "Processing audio...",
        "saving_audio_file": "Saving audio file: {}",
        "no_api_key_set": "API key is not set. Opening API key settings dialog.",
        "auto_language_detection": "Using automatic language detection...",
        "auto_detection_enabled": "Language auto-detection has been enabled.",
        "auto_detection_disabled": "Language auto-detection has been disabled.",
        "language_menu": "Language Settings",
        "auto_detection": "Auto-detect Language",
        "korean_language": "Korean",
        "english_language": "English",
        "recognition_result": "Speech Recognition Result",
        "auto_language_mode": "Automatic language detection mode",
        "recognized_text": "Recognized text: {}",
        "text_length": "Text length: {} characters",
        "attempting_paste": "Attempting to paste...",
        "paste_complete": "Paste completed",
        "paste_error": "Paste error: {}",
        "attempting_direct_input": "Attempting direct text input...",
        "direct_input_complete": "Direct text input completed",
        "direct_input_error": "Direct text input error: {}",
        "clipboard_success": "Text copied to clipboard. You can paste with Ctrl+V.",
        "all_input_failed": "Warning: All text input and copy methods failed.",
        "no_text_recognized": "No text was recognized.",
        "recognition_error": "Speech recognition error: {}",
        "openai_api_not_set": "OpenAI API or API key is not configured.",
        "audio_processing_error": "Audio processing error: {}",
        "recording_stop_error": "Recording stop error: {}"
    },
    # 메뉴 항목
    "open_recordings_folder": {
        "ko": "녹음 파일 폴더 열기",
        "en": "Open Recordings Folder"
    },
    "open_readme": {
        "ko": "README 파일 열기",
        "en": "Open README File"
    },
    "open_console": {
        "ko": "콘솔 창 열기",
        "en": "Open Console"
    },
    "set_openai_api_key": {
        "ko": "OpenAI API 키 설정",
        "en": "Set OpenAI API Key"
    },
    "set_hotkey": {
        "ko": "단축키 설정",
        "en": "Set Hotkey"
    },
    "change_language": {
        "ko": "언어 변경 (Change to English)",
        "en": "Change Language (한국어로 변경)"
    },
    "exit": {
        "ko": "종료",
        "en": "Exit"
    },
    # 단축키 설정 대화상자
    "set_hotkey_title": {
        "ko": "단축키 설정",
        "en": "Hotkey Settings"
    },
    "hotkey_instruction": {
        "ko": "단축키를 설정하세요. 체크박스로 수정자 키를 선택하세요.",
        "en": "Set your hotkey. Select modifier keys with checkboxes."
    },
    "additional_key": {
        "ko": "추가 키(선택사항):",
        "en": "Additional key (optional):"
    },
    "current_hotkey": {
        "ko": "현재 단축키:",
        "en": "Current hotkey:"
    },
    "save": {
        "ko": "저장",
        "en": "Save"
    },
    "cancel": {
        "ko": "취소",
        "en": "Cancel"
    },
    "set_key": {
        "ko": "키 설정",
        "en": "Set Key"
    },
    "press_key": {
        "ko": "키를 누르세요...",
        "en": "Press a key..."
    },
    "clear_key": {
        "ko": "지우기",
        "en": "Clear"
    },
    "conversation_mode": {
        "ko": "대화 모드",
        "en": "Conversation Mode"
    },
    "general_mode": {
        "ko": "일반 대화 모드",
        "en": "General Conversation"
    },
    "address_poi_mode": {
        "ko": "주소+POI 모드",
        "en": "Address+POI Mode"
    },
    "recognition_model_setting": {
        "ko": "인식 모델 설정",
        "en": "Recognition Model"
    },
    "model_long": {
        "ko": "long (긴 음성 최적화)",
        "en": "long (Optimized for long speech)"
    },
    "model_short": {
        "ko": "short (짧은 명령어)",
        "en": "short (Short commands)"
    },
    "model_telephony": {
        "ko": "telephony (전화 통화)",
        "en": "telephony (Phone calls)"
    },
    "google_credential_setting": {
        "ko": "Google Cloud 인증 설정",
        "en": "Google Cloud Credentials"
    },
    "google_credential_updated": {
        "ko": "Google Cloud 인증 정보가 업데이트되었습니다.",
        "en": "Google Cloud credentials updated."
    }
}

# 메시지 가져오기 함수
def get_message(key, *args, language="ko"):
    """
    주어진 키와 언어에 해당하는 메시지를 가져옵니다.
    필요한 경우 형식 지정자를 사용해 추가 인자를 적용합니다.
    """
    try:
        # 언어별 메시지 확인 (ko, en 키 아래에 있는 경우)
        if key in messages[language]:
            msg = messages[language][key]
            if args:
                return msg.format(*args)
            return msg
        # 메뉴 항목 같은 최상위 수준 메시지 확인
        elif key in messages:
            msg = messages[key][language]
            if args:
                return msg.format(*args)
            return msg
        else:
            # 언어별 메시지나 최상위 메시지에 없는 경우 영어 메시지 확인
            if key in messages["en"]:
                msg = messages["en"][key]
                if args:
                    return msg.format(*args)
                return msg
            return f"[Missing message: {key}]"
    except (KeyError, IndexError):
        return f"[Missing message: {key}]"