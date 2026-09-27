# messages.py - 다국어 메시지 정의 파일

# 다국어 메시지
messages = {
    "ko": {
        "start": "=== BluemingReadAloud 시작 ===",
        "start_time": "시작 시간: {}",
        "os": "운영체제: {}",
        "tray_icon_created": "시스템 트레이에 아이콘이 생성되었습니다. 우클릭하여 메뉴를 확인하세요.",
        "key_detected": "키 입력 감지: {}",
        "ctrl_key_pressed": "Ctrl 키 눌림",
        "shift_key_pressed": "Shift 키 눌림",
        "alt_key_pressed": "Alt 키 눌림",
        "text": "텍스트: {}",
        "console_opened": "=== 콘솔 창이 열렸습니다 ===",
        "program_status": "프로그램 상태: 실행 중",
        "console_open_error": "콘솔 창 열기 오류: {}",
        "open_console": "콘솔 창 열기",
        "exit": "종료",
        "change_language": "언어 변경 (Change Language)",
        "language_changed": "언어가 변경되었습니다: {}",
        "whisper_console": "BluemingReadAloud 콘솔",
        "console_title": "=== BluemingReadAloud 콘솔 ===",
        "console_info": "이 창을 닫아도 프로그램은 계속 실행됩니다.",
        "log_start": "로그 출력을 시작합니다...",
        "key_monitoring": "키 입력 감지 및 읽기 상태를 모니터링합니다...",
        "tray_missing": "pystray 또는 PIL 라이브러리가 설치되지 않았습니다. 시스템 트레이 기능이 비활성화됩니다.",
        "program_title": "\n=== BluemingReadAloud ===",
        "press_to_exit": "Press CTRL+C to exit",
        "waiting_input": "Waiting for input...",
        "press_enter_exit": "\nPress Enter to exit...",
        "save": "저장",
        "cancel": "취소",
        "error": "오류",
        "warning": "경고",
        "language_menu": "언어 설정",
        "korean_language": "한국어",
        "english_language": "영어",
        "text_length": "텍스트 길이: {} 글자",
        "controller_created": "미니 컨트롤러가 화면에 표시되었습니다.",
        "controller_position_saved": "컨트롤러 위치가 저장되었습니다."
    },
    "en": {
        "start": "=== BluemingReadAloud Started ===",
        "start_time": "Start time: {}",
        "os": "Operating system: {}",
        "tray_icon_created": "System tray icon created. Right-click to see menu options.",
        "key_detected": "Key detected: {}",
        "ctrl_key_pressed": "Ctrl key pressed",
        "shift_key_pressed": "Shift key pressed",
        "alt_key_pressed": "Alt key pressed",
        "text": "Text: {}",
        "console_opened": "=== Console window opened ===",
        "program_status": "Program status: Running",
        "console_open_error": "Console open error: {}",
        "open_console": "Open Console",
        "exit": "Exit",
        "change_language": "Change Language (언어 변경)",
        "language_changed": "Language changed to: {}",
        "whisper_console": "BluemingReadAloud Console",
        "console_title": "=== BluemingReadAloud Console Window ===",
        "console_info": "You can monitor program logs and status in this window.",
        "log_start": "Starting log recording...",
        "key_monitoring": "Monitoring key inputs...",
        "tray_missing": "pystray or PIL library is not installed. System tray functionality will be disabled.",
        "program_title": "\n=== BluemingReadAloud ===",
        "press_to_exit": "Press CTRL+C to exit",
        "waiting_input": "Waiting for input...",
        "press_enter_exit": "\nPress Enter to exit...",
        "save": "Save",
        "cancel": "Cancel",
        "error": "Error",
        "warning": "Warning",
        "language_menu": "Language Settings",
        "korean_language": "Korean",
        "english_language": "English",
        "text_length": "Text length: {} characters",
        "controller_created": "Mini controller is displayed on screen.",
        "controller_position_saved": "Controller position saved."
    },
    # 메뉴 항목
    "open_readme": {
        "ko": "README 파일 열기",
        "en": "Open README File"
    },
    "open_console": {
        "ko": "콘솔 창 열기",
        "en": "Open Console"
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
    "google_credential_setting": {
        "ko": "Google Cloud 인증 설정",
        "en": "Google Cloud Credentials"
    },
    "google_credential_updated": {
        "ko": "Google Cloud 인증 정보가 업데이트되었습니다.",
        "en": "Google Cloud credentials updated."
    },
    "set_tts_hotkey": {
        "ko": "읽어주기 단축키 설정",
        "en": "TTS Hotkey Settings"
    },
    "tts_hotkey_updated": {
        "ko": "읽어주기 단축키가 업데이트되었습니다.",
        "en": "TTS hotkey updated."
    },
    "set_tts_hotkey_title": {
        "ko": "읽어주기 단축키 설정",
        "en": "TTS Hotkey Configuration"
    },
    "menu_tts_settings": {
        "ko": "TTS 설정",
        "en": "TTS Settings"
    },
    "menu_stop_tts": {
        "ko": "읽기 중지",
        "en": "Stop Reading"
    },
    "menu_hide_controller": {
        "ko": "○ 플로팅 아이콘 숨기기",
        "en": "○ Hide Floating Icon"
    },
    "menu_show_controller": {
        "ko": "◉ 플로팅 아이콘 보이기",
        "en": "◉ Show Floating Icon"
    },
    "ctrl_menu_hide": {
        "ko": "숨기기",
        "en": "Hide"
    },
    "controller_hidden_log": {
        "ko": "플로팅 컨트롤러를 숨겼습니다. (트레이 메뉴에서 다시 표시)",
        "en": "Floating controller hidden. (Restore it from the tray menu)"
    },
    "controller_shown_log": {
        "ko": "플로팅 컨트롤러를 다시 표시했습니다.",
        "en": "Floating controller restored."
    },
    "settings_saved": {
        "ko": "설정이 저장되었습니다.",
        "en": "Settings saved."
    },
    "dialog_tts_title": {
        "ko": "TTS 설정",
        "en": "TTS Settings"
    },
    "label_voice_model": {
        "ko": "음성 모델:",
        "en": "Voice Model:"
    },
    "label_speaking_rate": {
        "ko": "재생 속도:",
        "en": "Speaking Rate:"
    },
    "btn_preview": {
        "ko": "미리듣기",
        "en": "Preview"
    },
    "group_hotkey": {
        "ko": "단축키 설정",
        "en": "Hotkey Settings"
    },
    "label_voice_female": {
        "ko": "여성",
        "en": "Female"
    },
    "label_voice_male": {
        "ko": "남성",
        "en": "Male"
    },
    "menu_language": {
        "ko": "언어 변경 (한/영)",
        "en": "Change Language (KR/EN)"
    },
    "language_changed": {
        "ko": "언어가 변경되었습니다: {0}",
        "en": "Language changed: {0}"
    },
    "current_language_ko": {
        "ko": "현재: 한국어",
        "en": "Current: Korean"
    },
    "current_language_en": {
        "ko": "현재: English",
        "en": "Current: English"
    },
    # ── 리더 창·하단 컨트롤 바 (2026-09-28) ──
    # 트레이 메뉴 체크 항목 (whisperer.py update_tray_menu)
    "menu_reader_window": {
        "ko": "리더 창",
        "en": "Reader Window"
    },
    # 리더 창 제목 (reader_window.py)
    "reader_window_title": {
        "ko": "리더 창",
        "en": "Reader Window"
    },
    # 하단 바 문구 (bottom_bar.py). 키 이름과 문구는 크롬 확장 read-aloud-hrg 의
    # _locales/ko·en/messages.json 의 pagebar_* 를 그대로 가져왔다
    "pagebar_calculating": {
        "ko": "계산 중",
        "en": "Calculating…"
    },
    "pagebar_about": {
        "ko": "약",
        "en": "about"
    },
    "pagebar_prev": {
        "ko": "이전 단락",
        "en": "Previous paragraph"
    },
    "pagebar_next": {
        "ko": "다음 단락",
        "en": "Next paragraph"
    },
    "pagebar_play": {
        "ko": "재생",
        "en": "Resume"
    },
    "pagebar_pause": {
        "ko": "일시정지",
        "en": "Pause"
    },
    "pagebar_loading": {
        "ko": "불러오는 중",
        "en": "Loading"
    },
    "pagebar_mute": {
        "ko": "음소거",
        "en": "Mute"
    },
    "pagebar_unmute": {
        "ko": "음소거 해제",
        "en": "Unmute"
    },
    "pagebar_stop": {
        "ko": "읽기 중지",
        "en": "Stop reading"
    },
    "pagebar_settings": {
        "ko": "음성 설정",
        "en": "Voice settings"
    },
    "pagebar_rate": {
        "ko": "속도",
        "en": "Speed"
    },
    "pagebar_volume": {
        "ko": "볼륨",
        "en": "Volume"
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