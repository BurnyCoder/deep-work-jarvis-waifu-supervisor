package com.procrastination.hellophone.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.procrastination.hellophone.data.AppState
import com.procrastination.hellophone.data.Config
import com.procrastination.hellophone.data.Mode
import com.procrastination.hellophone.data.PreferencesRepository
import com.procrastination.hellophone.data.ProductivityResult
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val prefsRepo = PreferencesRepository(application)

    private val _state = MutableStateFlow(AppState())
    val state: StateFlow<AppState> = _state.asStateFlow()

    private val _recentResults = MutableStateFlow<List<ProductivityResult>>(emptyList())
    val recentResults: StateFlow<List<ProductivityResult>> = _recentResults.asStateFlow()

    private val _apiKey = MutableStateFlow("")
    val apiKey: StateFlow<String> = _apiKey.asStateFlow()

    private val _showConfirmationDialog = MutableStateFlow(false)
    val showConfirmationDialog: StateFlow<Boolean> = _showConfirmationDialog.asStateFlow()

    private val _pendingModeChange = MutableStateFlow<Mode?>(null)

    init {
        viewModelScope.launch {
            prefsRepo.appState.collect { savedState ->
                _state.value = savedState
            }
        }

        viewModelScope.launch {
            prefsRepo.apiKey.collect { key ->
                _apiKey.value = key
            }
        }

        // Break timer checker
        viewModelScope.launch {
            while (true) {
                delay(1000)
                val currentState = _state.value
                if (currentState.isBreakExpired) {
                    setModeInternal(Mode.ON)
                }
            }
        }
    }

    fun requestModeChange(mode: Mode, breakMinutes: Int = 5) {
        val currentState = _state.value

        // If turning OFF from ON, require confirmation
        if (currentState.mode == Mode.ON && mode == Mode.OFF) {
            _pendingModeChange.value = mode
            _showConfirmationDialog.value = true
            return
        }

        // Otherwise, change mode directly
        viewModelScope.launch {
            val breakEndTime = if (mode == Mode.BREAK) {
                System.currentTimeMillis() + (breakMinutes * 60 * 1000)
            } else null

            prefsRepo.setMode(mode, breakEndTime)
            _state.update { it.copy(mode = mode, breakEndTime = breakEndTime) }
        }
    }

    fun confirmModeChange(confirmationPhrase: String): Boolean {
        if (confirmationPhrase != Config.CONFIRMATION_PHRASE) {
            return false
        }

        val pendingMode = _pendingModeChange.value ?: return false
        _showConfirmationDialog.value = false
        _pendingModeChange.value = null

        viewModelScope.launch {
            prefsRepo.setMode(pendingMode, null)
            _state.update { it.copy(mode = pendingMode, breakEndTime = null) }
        }
        return true
    }

    fun cancelModeChange() {
        _showConfirmationDialog.value = false
        _pendingModeChange.value = null
    }

    private fun setModeInternal(mode: Mode) {
        viewModelScope.launch {
            prefsRepo.setMode(mode, null)
            _state.update { it.copy(mode = mode, breakEndTime = null) }
        }
    }

    fun setApiKey(key: String) {
        viewModelScope.launch {
            prefsRepo.setApiKey(key)
            _apiKey.value = key
        }
    }

    fun addProductivityResult(result: ProductivityResult) {
        _recentResults.update { current ->
            (listOf(result) + current).take(20)
        }
    }
}
