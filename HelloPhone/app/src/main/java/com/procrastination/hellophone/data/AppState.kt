package com.procrastination.hellophone.data

enum class Mode {
    ON,
    OFF,
    BREAK
}

data class AppState(
    val mode: Mode = Mode.OFF,
    val breakEndTime: Long? = null
) {
    val isBlockingEnabled: Boolean
        get() = mode == Mode.ON

    val isMonitoringEnabled: Boolean
        get() = mode == Mode.ON

    val breakRemainingSeconds: Int
        get() {
            if (mode != Mode.BREAK || breakEndTime == null) return 0
            return maxOf(0, ((breakEndTime - System.currentTimeMillis()) / 1000).toInt())
        }

    val isBreakExpired: Boolean
        get() = mode == Mode.BREAK && breakEndTime != null && System.currentTimeMillis() >= breakEndTime
}
