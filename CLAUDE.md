# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Python Environment
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application in development mode
python whisperer.py

# Build executable with PyInstaller
pyinstaller Yeogiaen_WhisperTyper.spec

# Alternative build command
pyinstaller --onefile --noconsole --icon=favicon.ico --add-data "messages.py;." --add-data "README.md;." --add-data "README.KR.md;." --add-data "favicon.ico;." whisperer.py
```

### Testing and Distribution
```bash
# Test the built executable
./dist/Yeogiaen_WhisperTyper.exe

# Open console for debugging
python -u whisperer.py
```

## Architecture Overview

### Core Components

**whisperer.py** - Main application file containing:
- Voice recording functionality using sounddevice
- OpenAI Whisper API integration for speech-to-text conversion
- System tray integration with pystray
- Global hotkey handling with pynput
- Audio file management and optimization
- Multi-language support (Korean/English)

**messages.py** - Internationalization module:
- Contains all user-facing messages in Korean and English
- Used throughout the application for consistent localization
- Includes system messages, error messages, and UI text

### Key Features Architecture

**Audio Processing Pipeline:**
1. Microphone input capture via sounddevice
2. Real-time audio data collection
3. FLAC format conversion with optimization
4. Timestamp-based file naming
5. Automatic cleanup and storage management

**API Integration:**
- OpenAI Whisper API client initialization
- Configurable temperature and prompt settings
- Language detection and custom prompts for different modes
- Error handling and retry logic

**System Integration:**
- Windows system tray icon with context menu
- Global hotkey registration (default: Ctrl+Shift+Alt)
- Clipboard integration for automatic text pasting
- Multiple instance prevention using socket binding

**Settings Management:**
- JSON-based configuration in whisperer_settings.json
- Runtime settings modification via system tray
- API key secure storage in openai_api_key.txt
- Language preference persistence

### Directory Structure

- `/recordings/` - Audio files stored in FLAC format with timestamps
- `/logs/` - Application logs with rotation
- `/build/` - PyInstaller build artifacts
- `/dist/` - Final executable and distribution files

### Configuration System

The application uses a hierarchical configuration approach:
1. Default hardcoded settings in whisperer.py
2. JSON configuration file (whisperer_settings.json) 
3. Runtime modifications via system tray menu
4. Environment-specific settings (API keys, device selection)

### Threading Architecture

- Main UI thread for system tray and basic operations
- Recording thread for audio capture
- API communication thread for Whisper requests
- Background optimization threads for audio processing

## Important Notes

- The application prevents multiple instances using socket binding on port 51889 (test port)
- Audio files are optimized for API upload with configurable quality settings
- Hotkey combinations are filtered to avoid Windows system conflicts
- All user messages support Korean/English localization via the messages module
- Logging includes both file-based and console output for debugging