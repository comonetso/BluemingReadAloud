# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**BluemingReadAloud** — a Windows tray app that reads selected text aloud with Google Cloud Text-to-Speech.
It started as "Yeogiaen STT Typer" (speech-to-text + TTS). Speech-to-text has been removed; the app is TTS-only.
The target behavior follows the Chrome extension `F:\workspace\EtcProject\ChromeExtentions\read-aloud-hrg`.

Governance rules (Korean) are in `AGENTS.md`. Past session logs are in `docs/session_logs/`.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run in development mode (console output; PYTHONUTF8=1 avoids Korean encoding errors)
python -u whisperer.py

# Build the exe (the bare `pyinstaller` command is NOT on PATH on this PC)
python -m PyInstaller BluemingReadAloud.spec --noconfirm
# -> dist/BluemingReadAloud.exe (uac_admin=True: UAC prompt on launch)
```

- `*.spec` is git-ignored (`.gitignore`), so `BluemingReadAloud.spec` is a local file only.
  The old specs (`Yeogiaen_WhisperTyper.spec`, `Yeogiaen_STT_Typer*.spec`) are kept on disk until the user decides to remove them.
- There is no automated test suite. Verification order used in this project:
  edit → `py_compile` → dev run → user checks it for real → build (only after the user says it passed).
- Check build success by the output file timestamp too, not only the exit code
  (`cmd > log 2>&1; echo ...` returns the exit code of `echo`).

## Architecture Overview

### Core Files

- **whisperer.py** — the whole app in one file (the name is historical; renaming is a pending user decision).
  Tray, global hotkey, floating icon, TTS pipeline, settings, dialogs.
- **messages.py** — Korean/English UI strings. Add every user-facing message to both `ko` and `en`.
  Keep the nested `messages["ko"]` / `messages["en"]` blocks: `get_message()` indexes them first,
  and removing them turns every message into "[Missing message]".

### TTS Pipeline (whisperer.py)

1. **Entry points** — global hotkey (pynput listener `on_press`), floating icon click, tray menu.
2. **`read_selected_text()`** — releases modifier keys, backs up the clipboard, **clears it**,
   sends Ctrl+C, waits, then reads the clipboard. Three-way branch:
   selection → `speak_text()`; no selection + playing → `stop_tts()`;
   no selection + idle → `set_controller_visible()` toggle. The clipboard is restored when nothing was selected.
3. **`_preprocess_for_tts()`** — Markdown/URL/symbol cleanup for speech.
4. **`_chunk_text_for_tts()`** — chunking ported from the extension's CharBreaker (750, EastAsian, 200) as of 2026-06-07.
   Switching to the extension's per-line chunk rule is planned (needed for the highlighter).
5. **`_synthesize_chunk()`** — Google Cloud TTS v1 (`google.cloud.texttospeech`), LINEAR16 24 kHz, `speaking_rate`.
6. **`_speak()`** — producer thread synthesizes ahead (`Queue(maxsize=2)`); consumer writes to one
   `sd.OutputStream` in 0.1 s blocks (gapless). Global `tts_output_stream` holds the stream for abort.
7. **Stop** — `stop_current_playback()` / `stop_tts()`: sets `tts_stop_event`, aborts the stream.

### System Integration

- **Tray**: pystray, runs on its own thread. Menu labels are re-evaluated only when `update_tray_menu()`
  (exposed as global `tray_menu_updater`) is called.
- **Floating icon** (`setup_floating_controller`): Tk Toplevel with Win32 `WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW`,
  `HWND_TOPMOST`, round region. Click = read/stop, drag = move (position saved), right-click = popup menu (hide).
  `update_state()` redraws every 500 ms and re-raises the window every 3 s.
- **Global hotkey**: pynput. Default TTS hotkey Ctrl+Alt+D (user setting may differ).
- **Single instance**: Windows named mutex + UDP socket bound to `localhost:51888`.
- **Auth**: Google Cloud service account JSON (`google_credentials.json`, kept by user decision).
  The auth dialog copies the chosen file into the app folder. If the saved path is invalid,
  `load_settings()` falls back to `<app dir>/google_credentials.json` — note this fallback runs only when the settings file exists.

### Settings

- `whisperer_settings.json` in the working directory (git-ignored). TTS keys: `language`, `google_credentials_path`,
  `tts_hotkey`, `tts_settings` (`voice_name`, `speaking_rate`), `controller_position`, `controller_hidden`.
- `save_settings()` rewrites the whole file; keep `save_settings()` and `load_settings()` in sync when adding a key.

### Threading

- Main thread: tkinter (`root` is hidden) + `check_gui_queue()` polling every 100 ms.
- Tray thread (pystray), pynput listener thread.
- TTS: `_speak` consumer thread + producer thread; voice preview thread.
- Anything that touches Tk from another thread must go through `gui_queue` → `check_gui_queue()`.

### Directory Structure

- `logs/` — app logs (`whisperer_*.log`), `whisperer_console.log` is the live console log
- `docs/session_logs/` — past session logs (historical record; old names/paths are intentional)
- `build/`, `dist/` — PyInstaller output (git-ignored)
- `recordings/`, `tts_audio/` — leftovers from the STT era / old TTS files. Do not delete without asking the user.

### In Development (not implemented yet)

- Highlighter: color the chunk being read, per line, on the original text when possible, otherwise in a reader window.
- Bottom playback controller.

## Important Notes

- **Change the floating icon's visibility only through `set_controller_visible()`.** It saves the setting and
  refreshes the tray label together. Direct `withdraw()`/`deiconify()` desyncs the tray label and the saved state.
- **Do not remove the hidden guard in `update_state()`.** Its periodic `lift()`/topmost would bring a withdrawn window back.
- **Judge "is TTS playing" with `tts_playing`.** `is_speaking` is a dead variable.
- **Never add `tts_stop_event.clear()` in `_speak`'s `finally`.** A producer blocked on `put()` comes back to life
  as a zombie thread. Clear the event at the start of the next `_speak`, and join first.
- **Keep the tray "Show floating icon" item.** Hidden state is persisted; the tray item is the emergency way back
  (otherwise only hand-editing the settings file restores it).
- `sd.stop()` does not stop an `sd.OutputStream`; use `tts_output_stream.abort()`/`stop()`.
- Do not add the U+2200–22FF range to the noise regex in preprocessing (U+2212 minus sign would be lost).
- `np.frombuffer(...)` is read-only; `.copy()` before writing it to the stream.
- Keep clearing the clipboard before Ctrl+C in `read_selected_text()`; without it an old clipboard is read
  when nothing is selected. The ~0.8 s wait on the Tk main thread is accepted by design.
- The floating window cannot take focus (`WS_EX_NOACTIVATE`): create popup menus as children of `root`,
  and stop the re-raise loop while a menu is open (`menu_open`).
- Single-instance port is **51888** (51889 in older docs was wrong). Changing the mutex name or port
  is a user decision — an old exe and a new exe could then run together and both catch the hotkey.
- Do not register Windows reserved shortcuts (Win+L, Ctrl+Alt+Del, ...) as hotkeys. The code has no filter for this.
- Keep the pynput `on_press`/`on_release` handlers free of I/O (Windows low-level hook timeout); hand work off with `root.after(...)`.
- Modifier-key reset in `on_release` (Ctrl/Shift/Alt pressed flags) is required by the TTS hotkey — without it a
  stuck Shift makes a bare key trigger reading.
- `open_console.bat` is rewritten by the app every time the console is opened.
