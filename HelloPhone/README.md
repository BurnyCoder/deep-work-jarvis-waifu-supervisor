# Deep Work - Android Productivity Enforcer

An Android productivity enforcement app that helps maintain deep focus during work sessions through app blocking, AI-powered monitoring, and voice feedback.

This is the Android companion to the [Windows Deep Work app](../README.md).

## Features

- **App Blocking** - Detects and blocks distracting apps (Discord, Telegram, YouTube, Reddit, etc.) with a full-screen overlay
- **AI Monitoring** - Captures screenshots + front camera, analyzes with GPT-4o Vision
- **Voice Feedback** - Speaks gentle nudges when you're not being productive
- **Three Modes** - ON (full enforcement), OFF (disabled), BREAK (timed pause)
- **Confirmation Phrase** - Prevents impulsive disabling by requiring a typed phrase
- **Native UI** - Modern Material 3 design with Jetpack Compose

## Requirements

- Android 8.0+ (API 26+)
- OpenAI API key (for GPT-4o Vision)
- Android Studio Hedgehog (2023.1.1) or newer

## Setup with Android Studio

### 1. Clone the Repository

```bash
git clone <repository-url>
cd assistant/HelloPhone
```

### 2. Open in Android Studio

1. Open Android Studio
2. Select **File > Open**
3. Navigate to the `HelloPhone` folder and click **Open**
4. Wait for Gradle sync to complete

### 3. Configure SDK

If prompted, install the required SDK:
- **Compile SDK**: 36
- **Min SDK**: 26
- **Target SDK**: 36

Go to **File > Project Structure > SDK Location** to verify your Android SDK path.

### 4. Build the Project

```bash
# From command line
./gradlew assembleDebug

# Or in Android Studio
# Build > Make Project (Ctrl+F9)
```

### 5. Run on Device/Emulator

1. Connect an Android device via USB (with USB debugging enabled) or start an emulator
2. Click the **Run** button (green play icon) or press `Shift+F10`
3. Select your target device

**Note**: For full functionality, a physical device is recommended (emulators may have issues with camera and screen capture).

## First Launch Setup

### 1. Grant Permissions

When you first launch the app, you'll be prompted to grant:

| Permission | Purpose |
|------------|---------|
| **Camera** | Front camera capture for monitoring |
| **Notifications** | Foreground service notification |
| **Usage Access** | Detect which app is in foreground (requires manual grant in Settings) |
| **Screen Capture** | Capture screenshots when ON mode is activated |

### 2. Configure OpenAI API Key

1. Go to the **Settings** tab
2. Enter your OpenAI API key (starts with `sk-`)
3. Tap **Save API Key**

Get your API key from: https://platform.openai.com/api-keys

### 3. Grant Usage Access

This permission must be granted manually:

1. Go to **Settings** tab in the app
2. Tap **Grant** next to "Usage Access"
3. Find "Deep Work" in the list and enable it

## Usage

### Modes

| Mode | Description |
|------|-------------|
| **ON** | App blocking + monitoring active. Blocked apps trigger a full-screen overlay. |
| **OFF** | Everything disabled. Requires confirmation phrase to switch from ON. |
| **BREAK** | Temporary pause with timer. Auto-restores to ON when break ends. |

### Enabling Deep Work Mode

1. Open the app
2. Tap **ON** button
3. Grant screen capture permission when prompted
4. The app will now:
   - Block distracting apps with an overlay
   - Capture screen + camera every 60 seconds
   - Analyze productivity after 5 captures
   - Speak a nudge if you're not productive

### Taking a Break

1. Enter break duration in minutes
2. Tap **Take Break**
3. App blocking and monitoring pause
4. Timer shows remaining break time
5. Automatically returns to ON mode when break ends

### Disabling Deep Work Mode

To prevent impulsive disabling, you must type the confirmation phrase:

```
I will not stop cool deepwork session
```

## Project Structure

```
HelloPhone/app/src/main/java/com/procrastination/hellophone/
├── MainActivity.kt                    # Entry point with navigation
├── DeepWorkApplication.kt             # Application class
├── BlockingOverlayActivity.kt         # Full-screen blocker
│
├── data/
│   ├── Config.kt                      # Blocked apps, confirmation phrase
│   ├── AppState.kt                    # Mode enum and state
│   ├── ProductivityResult.kt          # AI analysis result
│   └── PreferencesRepository.kt       # DataStore persistence
│
├── service/
│   ├── AppBlockerService.kt           # UsageStats polling + overlay
│   └── MonitoringService.kt           # Foreground service for captures
│
├── capture/
│   ├── ScreenCaptureManager.kt        # MediaProjection handling
│   ├── CameraCaptureManager.kt        # CameraX capture
│   └── ImageStitcher.kt               # Image grid creation
│
├── ai/
│   ├── OpenAIClient.kt                # Retrofit client for GPT-4o
│   └── ProductivityAnalyzer.kt        # Analysis orchestration
│
├── tts/
│   └── SpeechManager.kt               # Text-to-speech wrapper
│
├── viewmodel/
│   └── MainViewModel.kt               # UI state management
│
└── ui/
    ├── screens/
    │   ├── HomeScreen.kt              # Main dashboard
    │   └── SettingsScreen.kt          # Configuration
    └── components/
        ├── ModeToggle.kt              # ON/OFF/BREAK buttons
        └── ConfirmationDialog.kt      # Phrase input dialog
```

## Configuration

Edit `data/Config.kt` to customize:

```kotlin
// Apps to block (package names)
val BLOCKED_APPS = listOf(
    "com.discord",
    "org.telegram.messenger",
    "com.google.android.youtube",
    // ...
)

// Confirmation phrase
const val CONFIRMATION_PHRASE = "I will not stop cool deepwork session"

// Monitoring settings
const val CAPTURE_INTERVAL_SECONDS = 60
const val CAPTURES_BEFORE_ANALYSIS = 5
```

## Website Blocking

Android doesn't allow direct website blocking like Windows. Instead, configure **Private DNS** in Android Settings:

1. Go to **Settings > Network & Internet > Private DNS**
2. Select "Private DNS provider hostname"
3. Enter a filtering DNS like:
   - `dns.adguard.com` (blocks ads + trackers)
   - `<your-config>.dns.nextdns.io` (customizable blocklists)

## Troubleshooting

**App blocking not working?**
- Ensure Usage Access permission is granted
- Check Settings > Apps > Special app access > Usage access

**Screen capture not starting?**
- You must grant permission each time you enable ON mode (Android requirement)
- Make sure no other app is using screen capture

**Camera not capturing?**
- Check camera permission in app settings
- Close other apps that might be using the camera

**AI analysis not working?**
- Verify your OpenAI API key in Settings
- Check you have GPT-4o access and sufficient credits
- Check internet connection

**TTS not speaking?**
- Check device volume
- Ensure TTS is enabled in Android Settings > Accessibility > Text-to-speech

## Dependencies

- Jetpack Compose (Material 3)
- CameraX
- Retrofit + OkHttp
- DataStore Preferences
- Kotlin Coroutines

## Building Release APK

```bash
# Generate signed APK
./gradlew assembleRelease

# Or in Android Studio
# Build > Generate Signed Bundle / APK
```

The APK will be at `app/build/outputs/apk/release/app-release.apk`

## License

MIT
