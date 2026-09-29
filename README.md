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
- **Translate foreign sentences before reading**: a sentence with no Hangul at all is translated into Korean with
  Gemini and then read. English terms inside Korean sentences (`useState`, …) are left as they are. A translated part
  is shown as a dark-gray caption box over the original lines (yellow highlight if the paragraph is only partly
  visible). If a translation fails, reading stops at that sentence with a notice.
- **System tray**: The app runs in the background with a tray icon (see the menu below).
- **Settings window**: Choose a Korean voice (default `ko-KR-Chirp3-HD-Callirrhoe`), preview it, change the speaking
  rate, the hotkey and the interface language (한국어 / English), turn translation and the caption box on / off,
  set the API keys, open the console.
- **Single instance**: A second copy of the app will not start.

## Requirements

- Windows
- **Two Google Cloud API keys**
  - **TTS key** (required): a key allowed to use the Cloud Text-to-Speech API
  - **Gemini key** (for translation): a key allowed to use the Gemini API. Google binds Gemini keys to a service
    account, and a bound key cannot call TTS, so one key cannot do both
- Internet connection
- An audio output device

## Google API Keys

1. On first run (or when there is no TTS key) a dialog asks for the keys. Paste them and press **Save**.
2. Each key is checked once on Save. A wrong key (including the two swapped) shows the reason and nothing is saved.
   The Gemini key may be left empty; then reading stops with a notice when a sentence needs translation.
3. The keys are stored in `whisperer_settings.json`. Change them later from the tray menu → **TTS Settings…** →
   **Credentials**.

`whisperer_settings.json` holds the keys in plain text — never commit or share it.
(The old `google_credentials.json` is no longer used.)

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
    **Translate sentences not in the voice language** · **Show the translation over the original text** (both on by
    default), **Credentials** (the two API keys), **Open Console** (live log, for troubleshooting)
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

- `whisperer_settings.json`: settings (the two API keys, language, hotkey, voice, speaking rate / volume, reader window,
  red dot on / off, disable in browsers, translation / caption box on / off, and `source_highlight_enabled` — the
  highlighter on the original text; this one is not in any menu and can only be changed in the file)
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
