# BluemingReadAloud

A lightweight Windows tray app that reads selected text aloud using Google Cloud Text-to-Speech.
Select text in any application, press the hotkey, and it is read back to you.

## Key Features

- **Read selected text aloud**: Select text anywhere and press the hotkey (default `Ctrl+Alt+D`).
  The app copies the selection, cleans it up for speech (Markdown symbols, URLs, special characters),
  splits long text into chunks and plays them back-to-back without gaps.
- **One hotkey, three actions**
  - Text selected → read it (a new selection replaces what is currently being read)
  - Nothing selected while reading → stop
  - Nothing selected while idle → show / hide the floating icon
- **Floating icon**: A small round always-on-top button.
  - Click: read the current selection, or stop while reading
  - Drag: move it (the position is remembered)
  - Right-click: hide it
- **System tray**: The app runs in the background with a tray icon (see the menu below).
- **Voice settings**: Choose a Korean voice (default `ko-KR-Chirp3-HD-Callirrhoe`), preview it,
  change the speaking rate and the hotkey.
- **Korean / English interface**
- **Single instance**: A second copy of the app will not start.

### In development

- **Highlighter**: highlight the part being read, line by line (on the original text where possible,
  otherwise in a reader window).
- **Bottom playback controller**

These are not available yet.

## Requirements

- Windows
- A Google Cloud **service account JSON key** for a project with the Cloud Text-to-Speech API enabled
- Internet connection
- An audio output device

## Google Cloud Credentials

1. On first run (or when no valid key is found) a dialog asks for the service account JSON file.
2. The selected file is copied into the app folder as `google_credentials.json` and used from then on.
3. You can change it later from the tray menu → **Google Cloud Credentials**.

Never commit or share `google_credentials.json`.

## How to Use

1. Start the app. A tray icon and the floating icon appear.
2. Select text in any application.
3. Press the hotkey (default `Ctrl+Alt+D`) or click the floating icon.
4. To stop, press the hotkey again with nothing selected, or click the floating icon.

## System Tray Menu

Right-click the tray icon:

- **TTS Settings**: voice model (with preview), speaking rate, hotkey
- **Google Cloud Credentials**: change the service account JSON key
- **Change Language (KR/EN)**
- **Open README File**
- **Open Console**: shows the live log (for troubleshooting)
- **⏹ TTS 중지** (Stop reading; enabled only while reading)
- **Show / Hide Floating Icon**: always available here, so a hidden icon can be restored
- **Exit**

## Run from Source

```bash
pip install -r requirements.txt
python whisperer.py
```

The main script is still named `whisperer.py`.

## Build

```bash
python -m PyInstaller BluemingReadAloud.spec --noconfirm
```

- Output: `dist/BluemingReadAloud.exe`
- The exe requests administrator rights (UAC prompt) because the global keyboard hook needs them.

## Files

- `whisperer_settings.json`: settings (language, hotkey, voice, speaking rate, floating icon position / visibility)
- `google_credentials.json`: Google Cloud service account key
- `logs/`: log files

These are created in the app's working folder.

## History

Originally developed in 2025 at LMTY Yeogiaen Service Co., Ltd. as "Yeogiaen STT Typer" (speech-to-text + text-to-speech).
Speech-to-text has been removed; the app is now text-to-speech only.

## Credits

- Google Cloud Text-to-Speech API
- Python libraries: google-cloud-texttospeech, sounddevice, numpy, pynput, pyperclip, pystray, Pillow, ttkbootstrap (tkinter)

## License

This project is provided under the MIT License.
