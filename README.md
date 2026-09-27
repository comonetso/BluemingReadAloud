# BluemingReadAloud

A lightweight Windows tray app that reads selected text aloud using Google Cloud Text-to-Speech.
Select text in any application and a small **red dot** appears next to the end of the selection.
Click the dot or press the hotkey, and the text is read back to you.

## Key Features

- **Read selected text aloud**: Select text anywhere and press the hotkey (default `Ctrl+Alt+D`).
  The app copies the selection, cleans it up for speech (Markdown symbols, URLs, special characters),
  splits long text into chunks and plays them back-to-back without gaps.
- **Red dot (read-selection button)**: As in the Chrome extension, when you select text by **dragging or
  double-clicking**, a small red dot appears next to where you released the mouse. Click it to read the selection.
  - It disappears when you click elsewhere, press a key or scroll.
  - Clicking the dot keeps the focus and the selection in the window where you selected the text.
  - Windows does not tell other apps when text is selected, so the dot is shown from mouse gestures.
    It can also appear after dragging a window's title bar (clicking it then acts like the hotkey: it reads text
    still selected in that window, otherwise nothing happens), and it does not
    appear for keyboard selections (Shift+arrows) — use the hotkey for those.
  - When there is no room on the right (e.g. at the right edge of the screen) it appears to the left of the mouse
    pointer, never right under it.
  - Turn it on or off from the tray menu (**Read button on selected text**, on by default).
- **One hotkey, three actions**
  - Text selected → read it (a new selection replaces what is currently being read)
  - Nothing selected while reading → stop
  - Nothing selected while idle → nothing happens
- **Bottom playback bar**: shown at the bottom of the screen while reading
  (pause, previous / next paragraph, mute, speed, volume, stop).
- **Highlighter on the original text**: while reading, the current line is painted with a translucent yellow
  highlight directly over the text in the window where you selected it. It scrolls the line into view if needed
  and hides while another window is in front.
- **Reader window**: only when the app cannot paint over the original text, a separate window shows the text and
  highlights the current line (toggle it with **Use Reader Window** in the tray). It is not shown while the app is
  still checking whether it can paint over the original text.
- **Paused in browsers**: Aside, Whale and Chrome are handled by the Chrome extension (read-aloud-hrg), so in those
  browser windows the red dot does not appear and the hotkey does not start a new reading (it can still stop a
  reading in progress). Toggle it with **Disable in Browsers** in the tray (on by default). Web views inside other
  apps (e.g. VS Code) are not affected.
- **System tray**: The app runs in the background with a tray icon (see the menu below).
- **Settings window**: Choose a Korean voice (default `ko-KR-Chirp3-HD-Callirrhoe`), preview it, change the speaking
  rate, the hotkey and the interface language (한국어 / English), set the Google Cloud credentials, open the console.
- **Single instance**: A second copy of the app will not start.

## Requirements

- Windows
- A Google Cloud **service account JSON key** for a project with the Cloud Text-to-Speech API enabled
- Internet connection
- An audio output device

## Google Cloud Credentials

1. On first run (or when no valid key is found) a dialog asks for the service account JSON file.
2. The selected file is copied into the app folder as `google_credentials.json` and used from then on.
3. You can change it later from the tray menu → **TTS Settings…** → **Credentials** button.

Never commit or share `google_credentials.json`.

## How to Use

1. Start the app. A tray icon appears.
2. Select text in any application by dragging or double-clicking. A red dot appears next to the selection.
3. Click the red dot, or press the hotkey (default `Ctrl+Alt+D`).
4. To stop, press the hotkey again with nothing selected, or use the stop button on the bottom playback bar.

## System Tray Menu

Right-click the tray icon:

- **TTS Settings…**: opens the settings window
  - voice model (with preview), speaking rate, hotkey
  - General: language (한국어 / English — applied when you press **Save**; the tray menu switches too),
    **Credentials** (change the service account JSON key), **Open Console** (live log, for troubleshooting)
- **Use Reader Window** (check): show the reader window when the app cannot paint over the original text
- **Disable in Browsers** (check): pause the red dot and the hotkey in Aside, Whale and Chrome (on by default)
- **Read button on selected text** (check): turn the red dot on / off
- **Exit**

To stop reading, use the stop button on the bottom playback bar, or press the hotkey with nothing selected.

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

- `whisperer_settings.json`: settings (language, hotkey, voice, speaking rate / volume, reader window, red dot on / off,
  disable in browsers, and `source_highlight_enabled` — the highlighter on the original text; this one is not in any
  menu and can only be changed in the file)
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
