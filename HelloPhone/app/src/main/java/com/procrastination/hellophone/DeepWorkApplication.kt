package com.procrastination.hellophone

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

class DeepWorkApplication : Application() {

    companion object {
        const val MONITORING_CHANNEL_ID = "deep_work_monitoring"
        const val BLOCKING_CHANNEL_ID = "deep_work_blocking"
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager = getSystemService(NotificationManager::class.java)

            // Monitoring service channel
            val monitoringChannel = NotificationChannel(
                MONITORING_CHANNEL_ID,
                "Productivity Monitoring",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Shows when Deep Work monitoring is active"
            }
            notificationManager.createNotificationChannel(monitoringChannel)

            // Blocking alerts channel
            val blockingChannel = NotificationChannel(
                BLOCKING_CHANNEL_ID,
                "App Blocking Alerts",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Alerts when blocked apps are detected"
            }
            notificationManager.createNotificationChannel(blockingChannel)
        }
    }
}
