package com.procrastination.hellophone.service

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import com.procrastination.hellophone.DeepWorkApplication
import com.procrastination.hellophone.MainActivity
import com.procrastination.hellophone.R
import com.procrastination.hellophone.capture.ScreenCaptureManager
import com.procrastination.hellophone.data.Config
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MonitoringService : Service() {

    companion object {
        private const val TAG = "MonitoringService"
        private const val NOTIFICATION_ID = 1001

        private var mediaProjectionResultCode: Int = 0
        private var mediaProjectionData: Intent? = null

        fun setMediaProjectionResult(resultCode: Int, data: Intent?) {
            mediaProjectionResultCode = resultCode
            mediaProjectionData = data
        }

        fun start(context: Context) {
            val intent = Intent(context, MonitoringService::class.java)
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, MonitoringService::class.java))
        }
    }

    private val handler = Handler(Looper.getMainLooper())
    private var isRunning = false
    private var screenCaptureManager: ScreenCaptureManager? = null
    private val captures = mutableListOf<Bitmap>()

    private var onAnalysisReady: ((Bitmap) -> Unit)? = null

    private val captureRunnable = object : Runnable {
        override fun run() {
            if (isRunning) {
                captureAndProcess()
                handler.postDelayed(this, Config.CAPTURE_INTERVAL_SECONDS * 1000L)
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "Monitoring service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!isRunning) {
            startForeground(NOTIFICATION_ID, createNotification())
            initializeScreenCapture()
            isRunning = true
            handler.postDelayed(captureRunnable, Config.CAPTURE_INTERVAL_SECONDS * 1000L)
            Log.d(TAG, "Monitoring service started")
        }
        return START_STICKY
    }

    override fun onDestroy() {
        isRunning = false
        handler.removeCallbacks(captureRunnable)
        screenCaptureManager?.stopCapture()
        captures.clear()
        Log.d(TAG, "Monitoring service stopped")
        super.onDestroy()
    }

    private fun createNotification(): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, DeepWorkApplication.MONITORING_CHANNEL_ID)
            .setContentTitle("Deep Work Active")
            .setContentText("Monitoring your productivity...")
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun initializeScreenCapture() {
        if (mediaProjectionData != null) {
            screenCaptureManager = ScreenCaptureManager(this)
            screenCaptureManager?.startCapture(mediaProjectionResultCode, mediaProjectionData!!)
        } else {
            Log.w(TAG, "No MediaProjection data available")
        }
    }

    private fun captureAndProcess() {
        Log.d(TAG, "Capturing screen...")

        // Capture screen
        val screenBitmap = screenCaptureManager?.captureScreen()
        if (screenBitmap != null) {
            captures.add(screenBitmap)
            saveCapture(screenBitmap)
            Log.d(TAG, "Captured screen. Total captures: ${captures.size}")

            // Check if we have enough captures for analysis
            if (captures.size >= Config.CAPTURES_BEFORE_ANALYSIS) {
                val gridBitmap = createCaptureGrid()
                if (gridBitmap != null) {
                    onAnalysisReady?.invoke(gridBitmap)
                }
                captures.forEach { it.recycle() }
                captures.clear()
            }
        } else {
            Log.w(TAG, "Failed to capture screen")
        }
    }

    private fun saveCapture(bitmap: Bitmap) {
        try {
            val dateFormat = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault())
            val filename = "capture_${dateFormat.format(Date())}.jpg"
            val file = File(cacheDir, filename)
            file.outputStream().use { out ->
                bitmap.compress(Bitmap.CompressFormat.JPEG, 85, out)
            }
            Log.d(TAG, "Saved capture to: ${file.absolutePath}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to save capture", e)
        }
    }

    private fun createCaptureGrid(): Bitmap? {
        if (captures.isEmpty()) return null

        val itemWidth = 600
        val itemHeight = 400
        val columns = 3
        val rows = (captures.size + columns - 1) / columns

        val gridWidth = columns * itemWidth
        val gridHeight = rows * itemHeight

        val gridBitmap = Bitmap.createBitmap(gridWidth, gridHeight, Bitmap.Config.ARGB_8888)
        val canvas = android.graphics.Canvas(gridBitmap)
        canvas.drawColor(android.graphics.Color.DKGRAY)

        captures.forEachIndexed { index, bitmap ->
            val col = index % columns
            val row = index / columns
            val x = col * itemWidth
            val y = row * itemHeight

            val scaled = Bitmap.createScaledBitmap(bitmap, itemWidth, itemHeight, true)
            canvas.drawBitmap(scaled, x.toFloat(), y.toFloat(), null)
            scaled.recycle()
        }

        return gridBitmap
    }

    fun setOnAnalysisReadyCallback(callback: (Bitmap) -> Unit) {
        onAnalysisReady = callback
    }
}
