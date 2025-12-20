**This application was developed on March 17, 2025, by developers at LMTY Yeogiaen Service Co., Ltd. to make Cursor AI more convenient to use.**

# Yeogiaen STT Typer

A lightweight desktop application that converts speech to text in real-time using Google Cloud Speech-to-Text V2 API. Perfect for quick voice memos, dictation, and accessibility needs.

## Key Features

- **Easy Voice Recording**: Press default shortcut (Ctrl+Shift+Alt) to start recording, release any key to stop
- **Google STT V2 Integration**: Accurate and fast speech recognition using the latest Google Cloud engine
- **Conversation Mode**: Switch between General mode and Address+POI mode for optimized recognition rules (punctuation, etc.)
- **Recognition Model Selection**: Choose from optimized models like long (long speech), short (commands), and telephony
- **Clipboard Integration**: Automatically copies and pastes converted text
- **Multi-language Support**: Full Korean and English interface (including menus and settings)
- **Customizable Shortcuts**: Change shortcuts as needed (excluding Windows system reserved shortcuts)
- **System Tray Integration**: Runs in the background with system tray icon access
- **Automatic Recording Save**: All recordings are saved with timestamps in FLAC format (16kHz)

## Requirements

- Windows Operating System
- Google Cloud Service Account JSON Key ([Setup Guide](https://cloud.google.com/speech-to-text/v2/docs/setup))
- Internet connection for API access
- Microphone device (default or selectable)

## Installation

1. Download the latest version from the releases page
2. Extract the ZIP file to your desired location
3. Run `STT_Typer.exe` (or `whisperer.exe`)
4. Select your Google Cloud Service Account JSON file when prompted (only required on first run)

## How to Use

1. The application runs in the background with a system tray icon
2. Press and hold the set shortcut (default: Ctrl+Shift+Alt) to start recording
3. Speak clearly into your microphone
4. Release any key to stop recording and automatically convert to text
5. The converted text is automatically copied to clipboard and pasted at the current cursor position
6. Recorded files are automatically saved in the 'recordings' folder

## System Tray Options

Right-click the system tray icon to access the following options:

- **Open Recordings Folder**: Opens the folder containing all recorded audio files
- **Open README**: Opens help documentation in the current language
- **Open Console Window**: Opens console window for debugging and log viewing
- **Set Google Cloud Credentials**: Change your service account JSON key file
- **Conversation Mode**: Choose between General or Address/POI mode (affects punctuation handling)
- **Recognition Model**: Select Google STT models (long, short, telephony)
- **Set Hotkey**: Modify recording start/stop shortcuts
- **Change Language**: Switch between Korean and English interface (updates all menus)
- **Exit**: Close the application

## Notes

- The application requires an internet connection to use the Google Cloud STT V2 API
- Your service account JSON key is copied to the program directory and used for authentication
- Recordings are saved in FLAC format in the `recordings` folder with timestamped filenames
- The program automatically prevents duplicate execution
- All logs are stored in the 'logs' folder to help with troubleshooting

## Credits

This application uses:
- Google Cloud Speech-to-Text V2 API (Speech Recognition)
- Python Libraries:
  - google-cloud-speech (Authentication and API calls)
  - sounddevice (Audio Recording)
  - soundfile (Audio File Processing)
  - pynput (Keyboard Event Handling)
  - pystray (System Tray Icon)
  - tkinter (GUI Elements)

## License

This project is provided under the MIT License.


