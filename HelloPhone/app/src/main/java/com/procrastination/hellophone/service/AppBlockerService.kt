package com.procrastination.hellophone.service

import android.app.Service
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import com.procrastination.hellophone.BlockingOverlayActivity
import com.procrastination.hellophone.data.Config

class AppBlockerService : Service() {

    companion object {
        private const val TAG = "AppBlockerService"

        fun start(context: Context) {
            context.startService(Intent(context, AppBlockerService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, AppBlockerService::class.java))
        }

        fun hasUsageStatsPermission(context: Context): Boolean {
            val usageStatsManager = context.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
            val endTime = System.currentTimeMillis()
            val beginTime = endTime - 1000 * 60

            val stats = usageStatsManager.queryUsageStats(
                UsageStatsManager.INTERVAL_DAILY,
                beginTime,
                endTime
            )
            return stats != null && stats.isNotEmpty()
        }
    }

    private val handler = Handler(Looper.getMainLooper())
    private var isRunning = false

    private val checkRunnable = object : Runnable {
        override fun run() {
            if (isRunning) {
                checkForegroundApp()
                handler.postDelayed(this, Config.APP_CHECK_INTERVAL_MS)
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!isRunning) {
            isRunning = true
            handler.post(checkRunnable)
            Log.d(TAG, "App blocker service started")
        }
        return START_STICKY
    }

    override fun onDestroy() {
        isRunning = false
        handler.removeCallbacks(checkRunnable)
        Log.d(TAG, "App blocker service stopped")
        super.onDestroy()
    }

    private fun checkForegroundApp() {
        val foregroundApp = getCurrentForegroundApp()
        if (foregroundApp != null && isBlockedApp(foregroundApp)) {
            Log.d(TAG, "Blocked app detected: $foregroundApp")
            showBlockingOverlay(foregroundApp)
        }
    }

    private fun getCurrentForegroundApp(): String? {
        val usageStatsManager = getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val endTime = System.currentTimeMillis()
        val beginTime = endTime - 1000

        val events = usageStatsManager.queryEvents(beginTime, endTime)
        var lastApp: String? = null

        while (events.hasNextEvent()) {
            val event = UsageEvents.Event()
            events.getNextEvent(event)
            if (event.eventType == UsageEvents.Event.ACTIVITY_RESUMED) {
                lastApp = event.packageName
            }
        }
        return lastApp
    }

    private fun isBlockedApp(packageName: String): Boolean {
        return Config.BLOCKED_APPS.any { blocked ->
            packageName.contains(blocked, ignoreCase = true)
        }
    }

    private fun showBlockingOverlay(blockedApp: String) {
        val intent = Intent(this, BlockingOverlayActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
            putExtra(BlockingOverlayActivity.EXTRA_BLOCKED_APP, blockedApp)
        }
        startActivity(intent)
    }
}
