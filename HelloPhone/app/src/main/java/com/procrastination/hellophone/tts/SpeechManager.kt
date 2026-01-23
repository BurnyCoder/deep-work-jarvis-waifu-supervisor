package com.procrastination.hellophone.tts

import android.content.Context
import android.speech.tts.TextToSpeech
import android.util.Log
import com.procrastination.hellophone.data.Mode
import java.util.Locale

class SpeechManager(context: Context) {

    companion object {
        private const val TAG = "SpeechManager"
    }

    private var tts: TextToSpeech? = null
    private var isInitialized = false

    init {
        tts = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val result = tts?.setLanguage(Locale.US)
                if (result == TextToSpeech.LANG_MISSING_DATA ||
                    result == TextToSpeech.LANG_NOT_SUPPORTED
                ) {
                    Log.w(TAG, "Language not supported, using default")
                    tts?.setLanguage(Locale.getDefault())
                }

                // Set speech rate
                tts?.setSpeechRate(0.9f)

                isInitialized = true
                Log.d(TAG, "TTS initialized successfully")
            } else {
                Log.e(TAG, "TTS initialization failed with status: $status")
            }
        }
    }

    fun speak(text: String) {
        if (!isInitialized) {
            Log.w(TAG, "TTS not initialized yet")
            return
        }

        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "utterance_${System.currentTimeMillis()}")
        Log.d(TAG, "Speaking: $text")
    }

    fun speakProductivityNudge(reason: String) {
        speak(reason)
    }

    fun speakModeChange(mode: Mode) {
        val message = when (mode) {
            Mode.ON -> "Deep work mode activated. Let's focus!"
            Mode.OFF -> "Deep work mode disabled. Take care!"
            Mode.BREAK -> "Break time started. Enjoy your rest!"
        }
        speak(message)
    }

    fun stop() {
        tts?.stop()
    }

    fun shutdown() {
        tts?.stop()
        tts?.shutdown()
        tts = null
        isInitialized = false
        Log.d(TAG, "TTS shutdown")
    }
}
