package com.procrastination.hellophone.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "deep_work_prefs")

class PreferencesRepository(private val context: Context) {

    companion object {
        private val MODE_KEY = stringPreferencesKey("mode")
        private val BREAK_END_TIME_KEY = longPreferencesKey("break_end_time")
        private val OPENAI_API_KEY = stringPreferencesKey("openai_api_key")
    }

    val appState: Flow<AppState> = context.dataStore.data.map { prefs ->
        val modeString = prefs[MODE_KEY] ?: Mode.OFF.name
        val mode = try {
            Mode.valueOf(modeString)
        } catch (e: Exception) {
            Mode.OFF
        }
        val breakEndTime = prefs[BREAK_END_TIME_KEY]

        AppState(
            mode = mode,
            breakEndTime = if (mode == Mode.BREAK) breakEndTime else null
        )
    }

    val apiKey: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[OPENAI_API_KEY] ?: ""
    }

    suspend fun setMode(mode: Mode, breakEndTime: Long? = null) {
        context.dataStore.edit { prefs ->
            prefs[MODE_KEY] = mode.name
            if (breakEndTime != null) {
                prefs[BREAK_END_TIME_KEY] = breakEndTime
            } else {
                prefs.remove(BREAK_END_TIME_KEY)
            }
        }
    }

    suspend fun setApiKey(apiKey: String) {
        context.dataStore.edit { prefs ->
            prefs[OPENAI_API_KEY] = apiKey
        }
    }
}
