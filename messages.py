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
        "text_length": "텍스트 길이: {} 글자"
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
        "text_length": "Text length: {} characters"
    },
    # 메뉴 항목 (트레이는 2026-09-28 사용자 확정 다섯 개: TTS 설정…·리더 창 사용·브라우저에서 비활성화·
    #  텍스트 선택 시 읽기 버튼·종료. 옛 "README 파일 열기"(open_readme)·"언어 변경 (한/영)"(menu_language)·
    #  "현재: 한국어/English"(current_language_ko/en)·"Google Cloud 인증 설정"(google_credential_setting) 문구는
    #  그 항목을 트레이에서 빼면서 지웠다. 콘솔·인증·언어는 설정 창으로 옮겼다 — 아래 "설정 창 일반" 묶음)
    # 설정 창 "콘솔 창 열기" 버튼 (옛 트레이 항목과 같은 문구)
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
    # 트레이 첫 항목 — 설정 창을 연다(창을 여는 항목이라 말줄임표 "…" — 사용자가 정한 문구 "TTS 설정…")
    "menu_tts_settings": {
        "ko": "TTS 설정…",
        "en": "TTS Settings…"
    },
    "menu_stop_tts": {
        "ko": "읽기 중지",
        "en": "Stop Reading"
    },
    # (옛 플로팅 아이콘 문구 menu_hide_controller·menu_show_controller·ctrl_menu_hide·controller_hidden_log·
    #  controller_shown_log·controller_created·controller_position_saved 는 2026-09-28 플로팅 아이콘 제거 때 지웠다)
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
    "language_changed": {
        "ko": "언어가 변경되었습니다: {0}",
        "en": "Language changed: {0}"
    },
    # ── 설정 창 "일반" 묶음 (2026-09-28, 트레이에서 옮겨 옴 — whisperer.py show_tts_settings_dialog) ──
    "group_general": {
        "ko": "일반",
        "en": "General"
    },
    "label_language": {
        "ko": "언어:",
        "en": "Language:"
    },
    # 언어 이름은 그 언어 자신의 표기로 둔다(어느 화면 언어에서도 알아보게) — 그래서 ko/en 값이 같다
    "language_name_ko": {
        "ko": "한국어",
        "en": "한국어"
    },
    "language_name_en": {
        "ko": "English",
        "en": "English"
    },
    # "인증 설정" 버튼 — Google Cloud 서비스 계정 JSON 고르는 창(show_api_key_dialog)을 연다
    "btn_credentials": {
        "ko": "인증 설정",
        "en": "Credentials"
    },
    # ── 리더 창·하단 컨트롤 바 (2026-09-28) ──
    # 트레이 메뉴 체크 항목 (whisperer.py update_tray_menu). 켜 두면 "원문 위에 칠할 수 없을 때" 리더 창을 띄운다
    "menu_reader_window": {
        "ko": "리더 창 사용",
        "en": "Use Reader Window"
    },
    # 트레이 메뉴 체크 항목 — 켜면 Aside·웨일·크롬에서 빨간 점·단축키가 쉰다(그 브라우저는 크롬 확장이 읽는다)
    "menu_disable_in_browsers": {
        "ko": "브라우저에서 비활성화",
        "en": "Disable in Browsers"
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
    },
    # ── 빨간 점(선택 버튼) (2026-09-28) ──
    # 글을 드래그·더블클릭으로 고르면 선택 끝 옆에 뜨는 빨간 점. 문구는 크롬 확장 read-aloud-hrg 의
    # _locales/ko·en/messages.json 에서 그대로 가져왔다(selection_button_title · options_selection_button)
    # 점에 마우스를 올렸을 때의 설명 (selection_button.py)
    "selection_button_title": {
        "ko": "선택한 글 읽기",
        "en": "Read the selected text"
    },
    # 트레이 메뉴 켬/끔 체크 항목 (whisperer.py update_tray_menu)
    "menu_selection_button": {
        "ko": "텍스트 선택 시 읽기 버튼",
        "en": "Read button on selected text"
    },
    # ── 주 언어가 아닌 문장 번역 (2026-09-29, translation.py) ──
    # 설정 창 "일반" 체크 (whisperer.py show_tts_settings_dialog)
    "label_translate_foreign": {
        "ko": "주 언어가 아닌 문장은 번역해서 읽기",
        "en": "Translate sentences not in the voice language before reading"
    },
    # 설정 창 "일반" 체크 — 번역된 조각은 원문 위 막에 번역문을 쓴다 (whisperer.py translation_overlay_enabled)
    "label_translate_overlay": {
        "ko": "번역문을 원문 위에 막으로 표시",
        "en": "Show the translation over the original text"
    },
    # 번역 실패로 읽기를 멈췄을 때의 경고 창 (whisperer.py _notify_segment_failed). {0} = 실패 이유
    "translate_failed_title": {
        "ko": "번역 실패",
        "en": "Translation failed"
    },
    "translate_failed_body": {
        "ko": "문장을 번역하지 못해 읽기를 멈췄습니다.\n\n{0}",
        "en": "Reading stopped because a sentence could not be translated.\n\n{0}"
    },
    # ── 인증 창 — API 키 두 개 (2026-09-29, whisperer.py show_api_key_dialog) ──
    "auth_title": {
        "ko": "Google API 키 설정",
        "en": "Google API Keys"
    },
    "auth_help": {
        "ko": ("API 키 두 개를 넣어 주세요.\n\n"
               "· TTS 키 (필수): Cloud Text-to-Speech API 를 허용한 키\n"
               "· Gemini 키 (번역용): Gemini API 를 허용한 키. 비워 두면 번역할 문장이 나올 때 읽기를 멈추고 알립니다.\n\n"
               "구글 정책상 키 하나로 둘 다 쓸 수 없습니다. 키는 Google Cloud 콘솔 → API 및 서비스 → 사용자 인증 정보에서 만듭니다:\n"
               "https://console.cloud.google.com/apis/credentials"),
        "en": ("Enter two API keys.\n\n"
               "· TTS key (required): a key allowed to use the Cloud Text-to-Speech API\n"
               "· Gemini key (for translation): a key allowed to use the Gemini API. If empty, reading stops with a notice "
               "when a sentence needs translation.\n\n"
               "Google does not allow one key for both. Create keys in Google Cloud Console → APIs & Services → Credentials:\n"
               "https://console.cloud.google.com/apis/credentials")
    },
    "auth_tts_key": {
        "ko": "TTS 키:",
        "en": "TTS key:"
    },
    "auth_gemini_key": {
        "ko": "Gemini 키:",
        "en": "Gemini key:"
    },
    "auth_show_keys": {
        "ko": "키 보이기",
        "en": "Show keys"
    },
    "auth_need_tts_key": {
        "ko": "TTS 키를 넣어 주세요.",
        "en": "Enter the TTS key."
    },
    "auth_checking": {
        "ko": "키 확인 중…",
        "en": "Checking keys…"
    },
    "auth_tts_key_failed": {
        "ko": "TTS 키 확인 실패: {0}",
        "en": "TTS key check failed: {0}"
    },
    "auth_gemini_key_failed": {
        "ko": "Gemini 키 확인 실패: {0}",
        "en": "Gemini key check failed: {0}"
    },
    "auth_error": {
        "ko": "오류: {0}",
        "en": "Error: {0}"
    },
    "auth_saved": {
        "ko": "✓ API 키 설정이 완료되었습니다.",
        "en": "✓ API keys saved."
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