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
  the tests never import `whisperer.py`; `tests/test_whisperer_selection.py` extracts the mouse hook and the
  browser / Telegram checks the same way). Verification order used in this project:
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
  `highlight(idx, caption=None)` (caption = translated text → drawn as a caption box instead of yellow),
  `notify_scroll()`, `end()`, `destroy()`, `active`, and one-shot queries answered later on the Tk main thread:
  `query_selection_end(on_done)`, `query_page_scheme(on_done)` (`"https"`, `"chrome-extension"`, … or `None`),
  `query_telegram_selected(x, y, on_done, right_click=None)` (`True` / `"menu"` / `False`, `None` on failure;
  `right_click` = last right-click spot `(rx, ry)`, also checked),
  `query_follow_text(on_done)` (follow-read window, 2026-10-28 — see below; result dict or `None`).
  `begin(..., area=(id, "para"|"all"))` paints over the range that query kept instead of the current selection
  (`follow_lost` if another follow query replaced it).
- **follow_dialog.py** — the follow-read window (2026-10-28 user request, Paseo plugin `client/web.ts confirmBox` look):
  "따라 읽기 할까요?" with [이 말만 읽기] [따라 읽기]. Enter = follow (default), outside click = this paragraph only,
  Esc = read nothing (user decision), foreground change = read nothing (app choice), centered on the foreground monitor.
  Never takes focus (NOACTIVATE + `ShowWindow(SW_SHOWNOACTIVATE)`, like the red dot) — Enter/Esc come from the key hook.
- **tts_engine.py** / **readaloud_text.py** — playback engine and text splitting (tests in `tests/`).
- **spoken_text.py** — the text actually sent to the voice (tables → sentences, brackets, paths, symbols, Korean numbers).
  A line-by-line port of the Paseo status bar plugin's `server/presentation/spokenText.ts`
  (`F:\workspace\EtcProject\VsCodeExtentions\claudeContextBar\paseo-plugins\claude-state-bar`) — user decision 2026-10-28:
  Paseo plugin, this app and the Chrome extension must read the same text the same way, so follow that file when it changes.
  `tests/test_spoken_text.py` holds that repo's test expectations unchanged (86 + 10 cases).
  `spoken_unicode.py` is generated (`node tools/gen_spoken_unicode.cjs > spoken_unicode.py`) — Python `re` has no `\p{...}`.
- **translation.py** — translate sentences that are not in the voice language (2026-09-29). Rules and the Gemini API
  client are in its header. Voices are Korean only, so "primary language" = Hangul.
- **messages.py** — Korean/English UI strings. Add every user-facing message to both `ko` and `en`.
  Keep the nested `messages["ko"]` / `messages["en"]` blocks: `get_message()` indexes them first,
  and removing them turns every message into "[Missing message]".

### TTS Pipeline (whisperer.py)

1. **Entry points** — global hotkey (pynput listener `on_press`), red dot click (`_on_selection_button_click`).
   The floating icon was removed on 2026-09-28 (user decision); the red dot replaces it. The tray has no play/stop item.
   **Browsers**: when "Disable in Browsers" is on (default) and the foreground window belongs to `Aside.exe`,
   `whale.exe` or `chrome.exe` (case-insensitive), the app asks the page's URL scheme (`_unless_web_page` →
   `SourceHighlighter.query_page_scheme`: from the focus up to the first Document element, whose Value is the page URL in
   Chromium — measured 2026-10-23; a focused link's own Value is the link target, so only the Document's Value counts).
   On a normal web page (`http`/`https`) the red dot is not shown and the hotkey starts no new reading (the Chrome
   extension handles it); the hotkey still stops a reading in progress there (no Ctrl+C is sent). Pages the extension
   cannot run on (new tab = `chrome-extension`, settings, local files) and an **unknown** scheme (slow call, focus outside
   the page such as the tab strip, no UIA) behave like any other app (user decision 2026-10-23). Only the scheme is kept or
   logged, never the host. Aside sometimes takes ~2.4 s on one call → the 1 s limit gives "unknown" → the app acts.
   `msedgewebview2.exe` (web views inside other apps) is not a browser. The exe check (`_foreground_exe_name`:
   GetForegroundWindow → GetWindowThreadProcessId → OpenProcess(QUERY_LIMITED) → QueryFullProcessImageNameW) runs on
   the Tk main thread only (`_handle_selection_button_msg`, start of `read_selected_text`), never in a hook callback.
2. **`read_selected_text()`** — releases modifier keys, backs up the clipboard, **clears it**,
   sends Ctrl+C, waits, then reads the clipboard. Three-way branch:
   selection → hide the red dot + `_speak_or_ask_follow()`; no selection + playing → `stop_tts()`;
   no selection + idle → **nothing** (user decision 2026-09-28). The clipboard is restored when nothing was selected.
   From the red dot (`from_selection_button=True`) an empty selection never stops playback (the extension's dot only reads).
   **Follow-read window** (2026-10-28 user decisions): if the copied text is one paragraph (`split_paragraphs` = 1), the app
   asks `SourceHighlighter.query_follow_text` (UIA thread): paragraph around the selection + the text below it, fetched for
   at most `FOLLOW_FETCH_S` = 1 s (user decision). Chromium (`FrameworkId` "Chrome" — measured in Aside/Whale) uses UIA
   paragraph units (block, `<br>` line, list item) and walks down with `Move` (stops on 0 / no progress / repeated text —
   Aside repeated the last block thousands of times when the end point was stretched instead); other apps (Notepad) use
   blank lines (line walk) and 2000-character end-point steps. No `DocumentRange`. If the selection lies inside that
   paragraph → the window; choice → `speak_text(all or para, hl_area=(id, ...))` (web blocks joined with blank lines).
   Otherwise (several paragraphs, no TextPattern e.g. Telegram, unknown) → `speak_text(clipboard text)` as before.
3. **`speak_text()`** — `readaloud_text.split_paragraphs_for_reading()` (2026-10-28, Paseo plugin rules): paragraphs =
   blocks separated by blank lines; each paragraph → `spoken_text.make_spoken_text` → pieces of at most 2000 UTF-8 bytes
   cut at sentence boundaries (`split_input`, port of `tts.ts splitInput`). Every piece carries `para` (paragraph number) and
   the **paragraph's** source offsets. Pieces start playing one by one (the plugin waits for a whole paragraph; measured
   2026-10-28: one 2000-byte request takes ~13 s, so a long paragraph would delay the first sound). The old per-line split
   (`split_for_reading`, Chrome extension port) is kept but no longer used. Then it stops the previous reading
   and starts a new `tts_engine.TtsSession`. Right before `session.start()` it calls `_begin_source_highlight()`
   → `SourceHighlighter.begin(source_text, segments, on_result)` while the selection is still alive. Sound never waits
   for that result.
   **Translation** (setting `translate_enabled`, default on — user decisions 2026-09-29): a sentence with **no Hangul at
   all** is translated to Korean by Gemini (`gemini-3.5-flash-lite`, Gemini API key) before synthesis; Korean sentences
   with English terms stay as they are. A paragraph with such a sentence (`keep_whole=translation.plan`) stays one piece
   with its raw text (URLs masked as "URL" so addresses never go to Gemini) → `translation.mark_for_translation` →
   `make_translating_synthesize` wraps `synthesize`: translate → `spoken_text.make_spoken_text` → TTS (a translated text
   over 2000 bytes is split inside `make_google_synthesize`). Timeout 3 s (user decision; measured 0.87–1.55 s). A failed translation raises `tts_engine.SegmentFailed` →
   reading **stops at that segment's turn** and a warning box appears (`segment_failed` event → `_notify_segment_failed`).
4. **`tts_engine.TtsSession`** — one object per reading. Thread `tts-producer` synthesizes up to 2 segments ahead
   (`PREFETCH_AHEAD`) with Google Cloud TTS v1 (`make_google_synthesize`, LINEAR16 24 kHz, synthesized at 1.0);
   thread `tts-player` writes 0.1 s blocks to one `sd.OutputStream` (gapless) and applies the speed while playing
   (WSOLA — `set_rate` takes effect from the next block). Recent results are reused
   (2-entry cache, like the extension's `js/tts-engines.js:385-407`). Volume is always 1.0 (user decision 2026-10-24 —
   the volume slider was removed; loudness is the Windows volume).
   **Voice / requests** (2026-10-28, Paseo `tts.ts`): default voice `ko-KR-Chirp3-HD-Zephyr` (was Callirrhoe; a saved
   voice is kept). Korean Chirp3-HD asks for pauses with markup first and falls back to plain text **only on HTTP 400**
   (auth, quota, timeout fail at once). LINEAR16 stays (the player writes samples itself; the plugin uses MP3).
   **Speed** (2026-10-24 list in the bottom bar; ranges from the Paseo plugin 2026-10-28): the step is chosen in the
   settings dialog (`tts_rate_step`: 0.1 → 0.5–2×, 0.25 → 0.5–5×, default 0.1 — `tts_engine.RATE_STEPS`); speeds are
   1× ± steps, rounded like `normalizeRate` (`tts_engine.snap_rate`). The bottom bar list shows 1× and up only, plus the
   current value when it is below 1× (`rate_choices(step, rate)` = `rateOptions`); below 1× is reached with Ctrl+↓ only.
   Labels like the plugin: "1.0x", "1.3x", "2x" (`format_rate`). Speed is picked in the bottom bar (button next to Close →
   list) or with **Ctrl+↓ one step slower / Ctrl+↑ one step faster** (`_step_rate` → `tts_engine.step_rate`, stops at the
   ends). Both go through `_on_bar_command("setRate")`: applied at once, saved, bar list refreshed. Changing the step in
   the settings dialog while reading re-snaps the speed and refreshes the bar list at once. The voice preview clamps the
   speed to 4.0 (server limit; reading always synthesizes at 1.0).
   **Previous / next** (2026-10-28): by paragraph — `TtsSession.forward/rewind` jump to the first piece of the next /
   previous paragraph (`para`); "previous" restarts the current paragraph if it started more than 3 s ago (the paragraph's
   start time is kept while moving to its next piece). Pieces without `para` behave as before (one piece = one paragraph).
5. **Events** — the engine's `on_event(kind, data)` → `gui_queue` → `check_gui_queue()` → `_handle_tts_event()`
   → bottom bar + highlighter. The highlighter and the reader window get the **paragraph** list and paint by paragraph
   number (`_paragraphs_of` / `_para_index` map piece → paragraph; the next piece of the same paragraph is not repainted —
   2026-10-28, "yellow highlight on the paragraph being read"). Highlighter rule (user decision 2026-09-28):
   `on_result(ok=True)` → paint on the original text (`SourceHighlighter.highlight(para)` per `segment` event), **no reader window**;
   `ok=False` → reader window if "Use Reader Window" is on; **while waiting for the result, no reader window**.
   State: `_source_hl_session` + `_source_hl_state` (`None` / `"pending"` / `"on"` / `"off"`); stale results from an
   older session are dropped. `session_end` → `_end_source_highlight()` → `SourceHighlighter.end()`.
   Mouse wheel → `SourceHighlighter.notify_scroll()` from the mouse hook (`_notify_source_scroll`, flag only).
   **Translation caption** (setting `translation_overlay_enabled`, default on): a translated segment is painted as a
   dark-gray box (#383838, text #CCCCCC, yellow border, GDI ClearType) over the original lines (`_caption_for`).
   The first segment is painted before its translation arrives, so `on_translated` → `"translation_ready"` event
   repaints it. If the paragraph is only partly visible (fewer lines than first seen, or clipped), yellow is used instead.
6. **Stop** — `stop_current_playback()` / `stop_tts()`: takes the session under `_tts_state_lock`, then
   `session.stop()` aborts the stream.

### System Integration

- **Tray**: pystray, runs on its own thread. Menu labels (and on Windows also checked/enabled) are re-evaluated only
  when `update_tray_menu()` is called. Items (user decision 2026-09-28, exactly these five): "TTS Settings…",
  "Use Reader Window" (check), "Disable in Browsers" (check), "Read button on selected text" (check), "Exit".
  Check items go through `gui_queue` to the Tk main thread.
- **Bottom bar** (`bottom_bar.py`, created with `show_settings=False`): the extension's gear button (speed/volume panel)
  is hidden — its code is kept (`_build_panel` …, the default `show_settings=True` is used by `dev_demo_ui.py`).
  Its previous / next buttons move by paragraph like the keys (2026-10-28).
  Right end = [speed] [close]: `set_rate_choices([(rate, text), ...])` shows the speed button ("1.3x"); clicking it opens
  a non-activating list window above the bar (current speed in the accent color; Esc / outside click / foreground change
  closes it, like the panel) → `on_command("setRate", rate)`. Widths in `RATE_*` constants are arbitrary.
- **Settings dialog** (`show_tts_settings_dialog`): voice + preview, speed step (0.1 / 0.25 — the speed itself is in the
  bottom bar), hotkey, and a "General" group moved
  from the tray: language (한국어 / English — applied on Save, then the tray is rebuilt via `_apply_language`),
  "Credentials" button (`show_api_key_dialog`), "Open Console" button (`open_console_window`). "Open README" was removed.
- **Red dot** (`selection_button.py` + `setup_selection_button()` / `setup_mouse_listener()` in whisperer.py):
  a pynput **mouse** listener feeds left press/release to `SelectionGestureDetector`; a drag (Windows `SM_CXDRAG`)
  or a double/triple-click release puts `("selection_button", "show", x, y)` on `gui_queue`; a single-click release puts
  `("selection_button", "click", x, y)` (used only for Telegram, dropped for every other app). A keyboard selection
  (Ctrl+A, Shift+arrows) puts `("selection_button", "keyboard")` once every modifier is released (`on_release`).
  **Telegram** (`Telegram.exe`, user decision 2026-10-23): instead of the selection end, the app asks whether a message
  is selected via the right-click menu "선택" (`_show_dot_if_telegram_selected` → `query_telegram_selected`: focus and
  the element under the release point, up to a ListItem whose parent class contains `HistoryInner`, then
  SelectionItem.IsSelected — the chat list on the left is also "selected", so it is excluded). Dot = next to the release
  point, on "선택" and on every further click that selects another message. Right after "선택" the menu may still be
  closing → result `"menu"` when the focus **or the element under the release point** is a menu, or an element vanished
  (`_Lost`) → ask again every 0.1 s up to 1 s (`TELEGRAM_MENU_RETRY_*`, user decision; measured: selected after 0.23 s).
  Once `"menu"` was seen, `False` is retried too until the limit (the focus can return to a message before the selection
  shows — 2026-10-24); `None` (slow/failed) stops. A short message's menu opens over **another** message, so the release
  point is not the chosen one: the mouse hook also posts `("selection_button", "rpress", x, y)` on right press, kept in
  `_tg_right_click` and passed once to the next show/click check, which also looks at that spot (2026-10-24).
  Clicking the dot reads via Ctrl+C — Telegram copies the selected message
  text (measured, no name/time header). Diagnostic `[텔레그램]` log lines are written per check (file log only).
  The Tk main thread (`_handle_selection_button_msg`) drops it for a web page in a disabled browser, the desktop / taskbar / Explorer
  (`_no_dot_window_at`, `_no_dot_foreground`) and non-client spots such as title bars and scrollbars (`_nonclient_at`,
  WM_NCHITTEST), then **asks the foreground app for the selection end** (`SourceHighlighter.query_selection_end` —
  one-spot UIA calls on the highlighter thread). The dot is shown next to the last selected character only when that
  returns a position; `"none"` (no selection) or `None` (unknown) shows nothing (user decision 2026-09-28: "only when
  text is really selected" — a 4 px drag guess also fired on click jitter at 140 % scaling). A keyboard selection whose
  end is off-screen falls back to the cursor. Drag guessing alone is used only when UIA is unavailable (module missing
  or `source_highlight_enabled` off). Presses on the dot itself and gestures that start on our own windows are filtered.
  Wheel, keys and other buttons hide it. Clicking the dot → `read_selected_text(from_selection_button=True)`.
  Tray off = hide the dot and stop the mouse hook (setting `selection_button_enabled`, default on like the extension).
  Position (`selection_button.dot_position`): right of the given point (selection end, or the release point in the
  fallback) + GAP, clamped into the monitor work area;
  if the clamped dot would cover the cursor pixel (e.g. after dragging a maximized window's scrollbar at the right
  screen edge) it goes to the cursor's left (`x - GAP - size`).
- **Global hotkey**: pynput. Default TTS hotkey Ctrl+Alt+D (user setting may differ). `win32_filter` swallows the
  hotkey's letter key (and its key-up) so it is not typed into the foreground app. Reading keys (2026-10-28, Paseo plugin
  `shared/shortcuts.ts` + `client/web.ts listenTtsSpeedKeys`, replacing the 10-24 "Ctrl+←/→ = speed"):
  **Ctrl+Space pause / resume · Ctrl+← previous paragraph · Ctrl+→ next paragraph · Ctrl+↓ slower · Ctrl+↑ faster**
  (`READ_KEYS` → `_read_key_action`). Swallowed only while a reading exists (`tts_session`); while paused (`tts_paused`)
  only Ctrl+Space is taken and the arrows pass through (word-wise cursor moves work again). With no reading all five pass
  through — Ctrl+Space never starts a new reading. Ctrl+Shift/Alt combinations always pass (`_read_key_swallowing`).
  While a reading exists, Ctrl+Space no longer reaches the foreground app (e.g. VS Code suggestions, Chinese IME switch).
  While the follow-read window is open (`_follow_dialog_open`), Enter and Esc without modifiers are swallowed and passed to
  it (`FOLLOW_KEYS` → `_follow_dialog_key`) — otherwise Enter would replace the selected text in Notepad.
- **Single instance**: Windows named mutex + UDP socket bound to `localhost:51888`.
- **Source highlight** (`source_highlight.py`): all UI Automation calls on one dedicated thread (COM initialized there,
  request queue); the overlay window is drawn on the Tk main thread (click-through `WS_EX_TRANSPARENT|WS_EX_LAYERED`,
  NOACTIVATE, TOOLWINDOW, topmost). It stays visible while the target is not minimized and either in the foreground or
  **not covered at the overlay spot** (5 `WindowFromPoint` probes — user decision 2026-09-29). Wheel → hidden while
  scrolling, one position query after `SETTLE_TICKS` of quiet (user decision "hide while scrolling").
  The user is not satisfied with its accuracy (2026-10-28, parked — see `docs/known_issues.md`; the Chrome extension
  paints the page's HTML directly and is accurate). Known open issue: ranges are taken once at `begin` and never re-verified; Chromium can silently move them after a DOM
  rebuild (Codex analysis `docs/codex_rescue/260929_211454_response_highlight-overlay-vanish.md`). Diagnostic logs
  (position boxes, show/hide reasons) are kept on purpose until that is confirmed.
  2026-09-28 measurements in VS Code: only the ancestor **Document** element (ControlType 50030) has TextPattern;
  `GetCurrentPattern(UIA_TextPatternId).QueryInterface(IUIAutomationTextPattern)` works (`GetCurrentPatternAs` failed);
  `RangeFromPoint` → `ExpandToEnclosingUnit(TextUnit_Line)` → `GetBoundingRectangles()` takes 1–2 ms.
- **Auth** (user decision 2026-09-29, replaced the service account JSON): **two API keys** typed into the auth dialog
  and saved in the settings file — a TTS key (Cloud Text-to-Speech) and a Gemini key (Gemini API). One key cannot do
  both (measured: the Gemini key is service-account-bound → TTS 401; the TTS key → Gemini 403). The dialog checks each
  key once on Save (`_check_tts_key` list_voices / `translation.check_gemini_key`); startup does not. `.env` is not read.
  `google_credentials.json` in the app folder is no longer used (not deleted).

### Settings

- `whisperer_settings.json` in the working directory (git-ignored — it holds API keys in plain text). Keys: `language`,
  `google_tts_api_key`, `gemini_api_key`,
  `tts_hotkey`, `tts_settings` (`voice_name`, `speaking_rate` — snapped to the step's list on load, `rate_step`),
  `reader_window_enabled`,
  `reader_window_geometry`, `bottom_bar_monitor`, `selection_button_enabled`, `disable_in_browsers` (default true),
  `source_highlight_enabled` (default true — deliberately **not** in the tray or the settings dialog; the user fixed the
  tray list, so it can only be turned off by editing the file), `translate_enabled` and `translation_overlay_enabled`
  (both default true, in the settings dialog "General"). Boolean keys with non-boolean values are ignored.
  Settings printed to the console go through `_mask_keys` (key prefix + length only).
- `save_settings()` rewrites the whole file; keep `save_settings()` and `load_settings()` in sync when adding a key.
  Old keys (STT keys, the floating icon's `controller_position` / `controller_hidden`, `google_credentials_path`,
  `tts_settings.volume`) are ignored on load and dropped from the file at the next save.
- Logging: `setup_logging()` uses `basicConfig(force=True)` — earlier `logging.*` calls in `main()` had installed a
  default handler, so `logs/whisperer_*.log` stayed 0 bytes from 2026-07 until 2026-09-29.

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
- **The red dot needs the app to expose a UIA TextPattern.** Windows gives no "text selected" signal for other apps,
  so the dot asks the foreground app through UI Automation (see Red dot above). Apps without a TextPattern on the
  selected text never show the dot and cannot be highlighted on the original either (`no_text_pattern` → reader
  window). Measured 2026-10-10: **Telegram Desktop** (Qt) exposes messages as ListItems with the whole text in `Name`
  and no TextPattern; only its input box has one (right after a drag the focus may still be there → "no selection").
  So text dragged inside a Telegram message still shows no dot and is never highlighted on the original; since
  2026-10-23 the dot appears for messages selected with the right-click menu "선택" (see Red dot above — this replaced
  the 2026-10-10 decision "Telegram uses the hotkey only"). Do not bring drag guessing back for Telegram or for
  "unknown" apps in general (rejected by the user on 2026-10-10). Neither "unknown" nor "none" is logged for other apps,
  so a missing dot leaves no trace in the log (only the web-page case is logged, at debug level). The dot also appears
  while selecting inside input fields.
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
