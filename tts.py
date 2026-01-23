"""Text-to-speech feedback using pyttsx3."""

import threading
from typing import Optional

import pyttsx3


class TextToSpeech:
    def __init__(self):
        self._engine: Optional[pyttsx3.Engine] = None
        self._lock = threading.Lock()
        self._speaking = False

    def _get_engine(self) -> pyttsx3.Engine:
        """Get or create the TTS engine."""
        if self._engine is None:
            self._engine = pyttsx3.init()
            # Set properties
            self._engine.setProperty('rate', 150)  # Speed
            self._engine.setProperty('volume', 0.9)  # Volume (0-1)

            # Try to use a pleasant voice
            voices = self._engine.getProperty('voices')
            for voice in voices:
                # Prefer female voice if available
                if 'female' in voice.name.lower() or 'zira' in voice.name.lower():
                    self._engine.setProperty('voice', voice.id)
                    break

        return self._engine

    def speak(self, text: str, block: bool = False):
        """
        Speak the given text.

        Args:
            text: Text to speak
            block: If True, wait for speech to complete. If False, run in background thread.
        """
        if block:
            self._speak_sync(text)
        else:
            thread = threading.Thread(target=self._speak_sync, args=(text,), daemon=True)
            thread.start()

    def _speak_sync(self, text: str):
        """Speak text synchronously."""
        with self._lock:
            if self._speaking:
                return  # Skip if already speaking

            self._speaking = True
            try:
                engine = self._get_engine()
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                print(f"TTS error: {e}")
            finally:
                self._speaking = False

    def speak_productivity_nudge(self, reason: str):
        """Speak a gentle productivity nudge."""
        self.speak(reason)

    def speak_mode_change(self, mode: str):
        """Announce mode changes."""
        messages = {
            "on": "Deep work mode activated. Let's focus!",
            "off": "Deep work mode disabled. Take care!",
            "break": "Break time started. Enjoy your rest!"
        }
        message = messages.get(mode.lower(), f"Mode changed to {mode}")
        self.speak(message)


# Global TTS instance
tts = TextToSpeech()
