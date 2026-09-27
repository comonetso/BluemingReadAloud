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
- Unit tests: `python -m unittest discover -s tests` (engine, text splitting, whisperer glue extracted by AST —
  the tests never import `whisperer.py`). Verification order used in this project:
  edit → `py_compile` → unit tests → dev run → user checks it for real → build (only after the user says it passed).
- Check build success by the output file timestamp too, not only the exit code
  (`cmd > log 2>&1; echo ...` returns the exit code of `echo`).

## Architecture Overview

### Core Files

- **whisperer.py** — the main app (the name is historical; renaming is a pending user decision).
  Tray, global hotkey, global mouse hook for the red dot, TTS glue, settings, dialogs.
- **selection_button.py** — the red dot shown next to a selection (port of the extension's `js/selection-button.js`):
  `SelectionGestureDetector` (pure drag / double-click logic) and `SelectionButton` (the dot window).
- **bottom_bar.py** / **reader_window.py** — bottom playback bar and reader window (highlighter fallback).
- **source_highlight.py** — highlighter painted directly over the original text in the foreground app
  (UI Automation on its own thread + a click-through overlay). Optional: if it fails to import, the app falls back
  to the reader window. Contract: `SourceHighlighter(root)`, `begin(source_text, segments, on_result)`,
  `highlight(idx)`, `notify_scroll()`, `end()`, `destroy()`, `active`.
- **tts_engine.py** / **readaloud_text.py** — playback engine and text splitting (tests in `tests/`).
- **messages.py** — Korean/English UI strings. Add every user-facing message to both `ko` and `en`.
  Keep the nested `messages["ko"]` / `messages["en"]` blocks: `get_message()` indexes them first,
  and removing them turns every message into "[Missing message]".

### TTS Pipeline (whisperer.py)

1. **Entry points** — global hotkey (pynput listener `on_press`), red dot click (`_on_selection_button_click`).
   The floating icon was removed on 2026-09-28 (user decision); the red dot replaces it. The tray has no play/stop item.
   **Browsers**: when "Disable in Browsers" is on (default) and the foreground window belongs to `Aside.exe`,
   `whale.exe` or `chrome.exe` (case-insensitive), the red dot is not shown and the hotkey starts no new reading
   (the Chrome extension handles those browsers). The hotkey still stops a reading in progress there (no Ctrl+C is sent).
   `msedgewebview2.exe` (web views inside other apps) is not a browser. The check (`_foreground_disabled_browser`:
   GetForegroundWindow → GetWindowThreadProcessId → OpenProcess(QUERY_LIMITED) → QueryFullProcessImageNameW) runs on
   the Tk main thread only (`_handle_selection_button_msg`, start of `read_selected_text`), never in a hook callback.
2. **`read_selected_text()`** — releases modifier keys, backs up the clipboard, **clears it**,
   sends Ctrl+C, waits, then reads the clipboard. Three-way branch:
   selection → hide the red dot + `speak_text()`; no selection + playing → `stop_tts()`;
   no selection + idle → **nothing** (user decision 2026-09-28). The clipboard is restored when nothing was selected.
   From the red dot (`from_selection_button=True`) an empty selection never stops playback (the extension's dot only reads).
3. **`speak_text()`** — `readaloud_text.split_for_reading()` (the extension's per-line split: speech cleanup,
   CharBreaker chunks, offsets back into the original text for the highlighter), stops the previous reading,
   then starts a new `tts_engine.TtsSession`. Right before `session.start()` it calls `_begin_source_highlight()`
   → `SourceHighlighter.begin(source_text, segments, on_result)` while the selection is still alive. Sound never waits
   for that result.
4. **`tts_engine.TtsSession`** — one object per reading. Thread `tts-producer` synthesizes up to 2 segments ahead
   (`PREFETCH_AHEAD`) with Google Cloud TTS v1 (`make_google_synthesize`, LINEAR16 24 kHz, `speaking_rate`);
   thread `tts-player` writes 0.1 s blocks to one `sd.OutputStream` (gapless). Recent results are reused
   (2-entry cache, like the extension's `js/tts-engines.js:385-407`).
5. **Events** — the engine's `on_event(kind, data)` → `gui_queue` → `check_gui_queue()` → `_handle_tts_event()`
   → bottom bar + highlighter. Highlighter rule (user decision 2026-09-28): `on_result(ok=True)` → paint on the
   original text (`SourceHighlighter.highlight(idx)` per `segment` event), **no reader window**;
   `ok=False` → reader window if "Use Reader Window" is on; **while waiting for the result, no reader window**.
   State: `_source_hl_session` + `_source_hl_state` (`None` / `"pending"` / `"on"` / `"off"`); stale results from an
   older session are dropped. `session_end` → `_end_source_highlight()` → `SourceHighlighter.end()`.
   Mouse wheel → `SourceHighlighter.notify_scroll()` from the mouse hook (`_notify_source_scroll`, flag only).
6. **Stop** — `stop_current_playback()` / `stop_tts()`: takes the session under `_tts_state_lock`, then
   `session.stop()` aborts the stream.

### System Integration

- **Tray**: pystray, runs on its own thread. Menu labels (and on Windows also checked/enabled) are re-evaluated only
  when `update_tray_menu()` is called. Items (user decision 2026-09-28, exactly these five): "TTS Settings…",
  "Use Reader Window" (check), "Disable in Browsers" (check), "Read button on selected text" (check), "Exit".
  Check items go through `gui_queue` to the Tk main thread.
- **Settings dialog** (`show_tts_settings_dialog`): voice + preview, speaking rate, hotkey, and a "General" group moved
  from the tray: language (한국어 / English — applied on Save, then the tray is rebuilt via `_apply_language`),
  "Credentials" button (`show_api_key_dialog`), "Open Console" button (`open_console_window`). "Open README" was removed.
- **Red dot** (`selection_button.py` + `setup_selection_button()` / `setup_mouse_listener()` in whisperer.py):
  a pynput **mouse** listener feeds left press/release to `SelectionGestureDetector`; a drag (Windows `SM_CXDRAG`)
  or a double/triple-click release puts `("selection_button", "show", x, y)` on `gui_queue`, and the Tk main thread
  calls `SelectionButton.show_at`. Presses on the dot itself and gestures that start on our own windows are filtered.
  Wheel, keys and other buttons hide it. Clicking the dot → `read_selected_text(from_selection_button=True)`.
  Tray off = hide the dot and stop the mouse hook (setting `selection_button_enabled`, default on like the extension).
  Position (`selection_button.dot_position`): right of the release point + GAP, clamped into the monitor work area;
  if the clamped dot would cover the cursor pixel (e.g. after dragging a maximized window's scrollbar at the right
  screen edge) it goes to the cursor's left (`x - GAP - size`).
- **Global hotkey**: pynput. Default TTS hotkey Ctrl+Alt+D (user setting may differ).
- **Single instance**: Windows named mutex + UDP socket bound to `localhost:51888`.
- **Source highlight** (`source_highlight.py`): all UI Automation calls on one dedicated thread (COM initialized there,
  request queue); the overlay window is drawn on the Tk main thread (click-through `WS_EX_TRANSPARENT|WS_EX_LAYERED`,
  NOACTIVATE, TOOLWINDOW, topmost) and hidden when the target window is no longer in the foreground.
  2026-09-28 measurements in VS Code: only the ancestor **Document** element (ControlType 50030) has TextPattern;
  `GetCurrentPattern(UIA_TextPatternId).QueryInterface(IUIAutomationTextPattern)` works (`GetCurrentPatternAs` failed);
  `RangeFromPoint` → `ExpandToEnclosingUnit(TextUnit_Line)` → `GetBoundingRectangles()` takes 1–2 ms.
- **Auth**: Google Cloud service account JSON (`google_credentials.json`, kept by user decision).
  The auth dialog copies the chosen file into the app folder. If the saved path is invalid,
  `load_settings()` falls back to `<app dir>/google_credentials.json` — note this fallback runs only when the settings file exists.

### Settings

- `whisperer_settings.json` in the working directory (git-ignored). Keys: `language`, `google_credentials_path`,
  `tts_hotkey`, `tts_settings` (`voice_name`, `speaking_rate`, `volume`), `reader_window_enabled`,
  `reader_window_geometry`, `bottom_bar_monitor`, `selection_button_enabled`, `disable_in_browsers` (default true),
  `source_highlight_enabled` (default true — deliberately **not** in the tray or the settings dialog; the user fixed the
  tray list, so it can only be turned off by editing the file). Boolean keys with non-boolean values are ignored.
- `save_settings()` rewrites the whole file; keep `save_settings()` and `load_settings()` in sync when adding a key.
  Old keys (STT keys, the floating icon's `controller_position` / `controller_hidden`) are ignored on load and
  dropped from the file at the next save.

### Threading

- Main thread: tkinter (`root` is hidden) + `check_gui_queue()` polling every 100 ms.
- Tray thread (pystray), pynput keyboard listener thread, pynput mouse listener thread (red dot).
- TTS: `tts-producer` + `tts-player` threads per reading (`tts_engine.TtsSession`); voice preview thread.
- Source highlight: one UI Automation thread inside `source_highlight.py`; results come back via `root.after`.
- Anything that touches Tk from another thread must go through `gui_queue` → `check_gui_queue()`.

### Directory Structure

- `logs/` — app logs (`whisperer_*.log`), `whisperer_console.log` is the live console log
- `docs/session_logs/` — past session logs (historical record; old names/paths are intentional)
- `build/`, `dist/` — PyInstaller output (git-ignored)
- `recordings/`, `tts_audio/` — leftovers from the STT era / old TTS files. Do not delete without asking the user.

### Reading UI

- Bottom playback controller (`bottom_bar.py`) and reader-window highlighter (`reader_window.py`) exist since c9627f4.
- Highlighting directly on the original text (`source_highlight.py`, 2026-09-28) is the primary highlighter; the reader
  window is only the fallback when that is not possible (see TTS Pipeline step 5).

## Important Notes

- **The red dot window must never take focus** (`WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW`, shown with
  `ShowWindow(SW_SHOWNOACTIVATE)`). If it took focus, the Ctrl+C after clicking it would go to the dot instead of the app
  where the text is selected, and it would read "nothing selected". Do not use Tk `attributes("-alpha")` /
  `("-transparentcolor")` or `deiconify()` on it: Tk rewrites the extended style (drops NOACTIVATE) or forces focus.
- **Keep the mouse/keyboard hook callbacks tiny.** They run on pynput threads and Windows silently removes a slow
  low-level hook. Only the detector call, flag updates, `gui_queue.put` and `SourceHighlighter.notify_scroll()`
  (sets a flag) — no Tk calls, no file I/O, no `log_to_console`, no process/window queries such as the browser check
  (see `_make_selection_hook`). The wheel notice exists only while the mouse hook runs, i.e. while the red dot is on.
- **UI Automation rules** (it froze VS Code once on 2026-09-28 — a FindAll over the whole window calling patterns and
  `GetVisibleRanges` on every element). Only `source_highlight.py` may call UIA, only on its own thread. Never call
  whole-range APIs: `GetVisibleRanges`, `GetText` / `GetBoundingRectangles` on the whole `DocumentRange`,
  `FindAll(TreeScope_Descendants)` over a window or document. If a single call takes over 1 s, stop painting on the
  original text for the rest of that reading. `whisperer.py` itself never calls UIA.
- **The red dot is a guess from mouse gestures.** Windows gives no "text selected" signal for other apps, and
  UI Automation is not used for the dot. Known limits: dragging a window title bar also shows the dot
  (clicking it sends Ctrl+C to that window like the hotkey does — it reads text still selected there, otherwise
  nothing); keyboard / Shift+click selections show no dot (the hotkey still works);
  the dot also appears while selecting inside input fields.
- **Judge "is TTS playing" with `tts_playing`.** `is_speaking` is a dead variable.
- **Never reuse or `clear()` a session's stop event** (`TtsSession._stop_event`). A producer blocked in synthesis
  would come back to life as a zombie thread. Every reading creates a new `TtsSession` (tts_engine.py header).
- `sd.stop()` does not stop an `sd.OutputStream`; the engine stops it with `stream.abort()` in `TtsSession.stop()`.
- Do not add the U+2200–22FF range to the noise regex in preprocessing (U+2212 minus sign would be lost).
- `np.frombuffer(...)` is read-only; `.copy()` before writing it to the stream.
- Keep clearing the clipboard before Ctrl+C in `read_selected_text()`; without it an old clipboard is read
  when nothing is selected. The ~0.8 s wait on the Tk main thread is accepted by design.
- Single-instance port is **51888** (51889 in older docs was wrong). Changing the mutex name or port
  is a user decision — an old exe and a new exe could then run together and both catch the hotkey.
- Do not register Windows reserved shortcuts (Win+L, Ctrl+Alt+Del, ...) as hotkeys. The code has no filter for this.
- Keep the pynput `on_press`/`on_release` handlers free of I/O (Windows low-level hook timeout); hand work off with
  `root.after(...)` (keyboard) or `gui_queue.put(...)` (mouse).
- Modifier-key reset in `on_release` (Ctrl/Shift/Alt pressed flags) is required by the TTS hotkey — without it a
  stuck Shift makes a bare key trigger reading.
- `open_console.bat` is rewritten by the app every time the console is opened.
