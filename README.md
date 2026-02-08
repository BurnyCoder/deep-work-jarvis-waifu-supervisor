# Deep Work - Productivity Enforcer

<img width="996" height="1171" alt="image" src="https://github.com/user-attachments/assets/8e6ed5de-53d0-4da8-972c-7fac8e2f962a" />

A productivity enforcement app that helps maintain deep focus during work sessions through blocking, AI-powered monitoring, and voice feedback.

**Available for:**
- **Windows** - Website blocking, app killing, web dashboard (this folder)
- **Android** - App blocking, native UI ([HelloPhone/](HelloPhone/README.md))

---

## Windows Version

A Windows productivity enforcement app with website blocking, app killing, AI-powered monitoring, and voice feedback.

## Features

- **Website Blocking** - Blocks distracting sites (Reddit, YouTube, Twitter, Discord, etc.) via hosts file
- **App Killing** - Continuously terminates distraction apps (Discord, Telegram, Steam)
- **AI Monitoring** - Captures screenshots + webcam, analyzes with GPT-4o Vision
- **Voice Feedback** - Speaks gentle nudges when you're not being productive
- **Three Modes** - ON (full enforcement), OFF (disabled), BREAK (timed pause)
- **Confirmation Phrase** - Prevents impulsive disabling by requiring a typed phrase
- **Web Dashboard** - Clean UI to control modes and view analysis results

## Requirements

- Windows 10/11
- Python 3.9+
- OpenAI API key (for GPT-4o Vision)
- Administrator privileges (for hosts file modification)
- Webcam (optional, for webcam capture)

## Installation

```bash
# Clone or download the project
cd assistant

# Install dependencies
pip install -r requirements.txt

# Set up your OpenAI API key
copy .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

## Usage

**Important:** Run as Administrator for website blocking to work.

**Option 1: Double-click** `run.bat` (automatically requests admin privileges)

**Option 2: Command line**
```bash
# Right-click Command Prompt -> "Run as administrator"
python main.py
```

Open http://localhost:8000 in your browser.

### Modes

| Mode | Description |
|------|-------------|
| **ON** | Website blocking + app killing + monitoring active |
| **OFF** | Everything disabled |
| **BREAK** | Temporary pause with timer, auto-restores to ON |

### Disabling

To prevent impulsive disabling, you must type the confirmation phrase:

```
I will not stop cool deepwork session
```

## Configuration

Edit `config.py` to customize:

```python
# Blocked websites
BLOCKED_SITES = ["reddit.com", "youtube.com", ...]

# Apps to kill
BLOCKED_APPS = ["Discord.exe", "Telegram.exe", "Steam.exe"]

# Confirmation phrase
CONFIRMATION_PHRASE = "I will not stop cool deepwork session"

# Monitoring interval (seconds)
CAPTURE_INTERVAL_SECONDS = 60

# Captures before AI analysis
CAPTURES_BEFORE_ANALYSIS = 5
```

## Project Structure

```
assistant/
├── run.bat              # Double-click to run (requests admin)
├── main.py              # FastAPI app entry point
├── config.py            # Configuration constants
├── state.py             # App state management
├── blocker.py           # Website blocking (hosts file)
├── app_killer.py        # Process killing
├── monitor.py           # Screenshot + webcam capture
├── ai_analyzer.py       # OpenAI Vision API
├── tts.py               # Text-to-speech
├── requirements.txt     # Dependencies
├── .env                 # API keys (create from .env.example)
├── templates/
│   └── index.html       # Web UI
└── results/             # Saved captures and analysis
```

## How It Works

1. **ON Mode Activated** → Blocks sites in hosts file, starts app killer thread
2. **Every 60 seconds** → Captures all monitors + webcam, stitches into one image
3. **After 5 captures** → Sends grid to GPT-4o Vision for productivity analysis
4. **If not productive** → Speaks a gentle, encouraging nudge via TTS
5. **Break Mode** → Temporarily unblocks everything, timer auto-restores ON mode
6. **Cleanup on exit** → Restores hosts file to original state

## Troubleshooting

**Website blocking not working?**
- Ensure you're running as Administrator
- Try flushing DNS: `ipconfig /flushdns`
- Check if antivirus is blocking hosts file changes

**Webcam not capturing?**
- Check if another app is using the webcam
- Try changing camera index in `monitor.py` (line with `VideoCapture(0)`)

**TTS not speaking?**
- Install pypiwin32: `pip install pypiwin32`
- Check Windows volume settings

**OpenAI API errors?**
- Verify your API key in `.env`
- Ensure you have GPT-4o access and sufficient credits

---

## Android Version

See [HelloPhone/README.md](HelloPhone/README.md) for the Android app with:

- App blocking via UsageStats + overlay
- Screen + camera capture with MediaProjection/CameraX
- GPT-4o Vision productivity analysis
- Native Material 3 UI with Jetpack Compose
- Text-to-speech feedback

## License

MIT
