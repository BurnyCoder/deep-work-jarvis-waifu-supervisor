package com.procrastination.hellophone.ai

import android.content.Context
import android.graphics.Bitmap
import android.util.Log
import com.procrastination.hellophone.capture.ImageStitcher
import com.procrastination.hellophone.data.Config
import com.procrastination.hellophone.data.ProductivityResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

class ProductivityAnalyzer(private val context: Context) {

    companion object {
        private const val TAG = "ProductivityAnalyzer"
    }

    private var openAIClient: OpenAIClient? = null
    private val captures = mutableListOf<Bitmap>()
    private var onResultCallback: ((ProductivityResult) -> Unit)? = null

    fun setApiKey(apiKey: String) {
        if (apiKey.isNotBlank()) {
            openAIClient = OpenAIClient(apiKey)
        }
    }

    fun setOnResultCallback(callback: (ProductivityResult) -> Unit) {
        onResultCallback = callback
    }

    suspend fun addCapture(
        screenCapture: Bitmap?,
        cameraCapture: Bitmap?
    ): ProductivityResult? {
        // Stitch screen and camera captures
        val stitched = ImageStitcher.stitchImages(screenCapture, cameraCapture)
        if (stitched != null) {
            captures.add(stitched)
            saveCapture(stitched)
        }

        // Check if we have enough captures for analysis
        if (captures.size >= Config.CAPTURES_BEFORE_ANALYSIS) {
            return analyzeCaptures()
        }

        return null
    }

    private suspend fun analyzeCaptures(): ProductivityResult? = withContext(Dispatchers.IO) {
        val client = openAIClient
        if (client == null) {
            Log.w(TAG, "OpenAI client not configured")
            clearCaptures()
            return@withContext null
        }

        // Create grid from accumulated captures
        val grid = ImageStitcher.createGrid(captures)
        if (grid == null) {
            Log.w(TAG, "Failed to create capture grid")
            clearCaptures()
            return@withContext null
        }

        // Save grid for reference
        saveGrid(grid)

        // Analyze with AI
        Log.d(TAG, "Sending grid to AI for analysis...")
        val analysisResult = client.analyzeProductivity(grid)

        // Clean up
        grid.recycle()
        clearCaptures()

        if (analysisResult == null) {
            Log.w(TAG, "AI analysis returned null")
            return@withContext null
        }

        val result = ProductivityResult(
            productive = analysisResult.productive,
            reason = analysisResult.reason
        )

        Log.d(TAG, "Analysis result: productive=${result.productive}, reason=${result.reason}")
        onResultCallback?.invoke(result)

        return@withContext result
    }

    private fun saveCapture(bitmap: Bitmap) {
        try {
            val filename = "capture_${System.currentTimeMillis()}.jpg"
            val file = File(context.cacheDir, filename)
            file.outputStream().use { out ->
                bitmap.compress(Bitmap.CompressFormat.JPEG, 85, out)
            }
            Log.d(TAG, "Saved capture: ${file.absolutePath}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to save capture", e)
        }
    }

    private fun saveGrid(bitmap: Bitmap) {
        try {
            val filename = "grid_${System.currentTimeMillis()}.jpg"
            val file = File(context.cacheDir, filename)
            file.outputStream().use { out ->
                bitmap.compress(Bitmap.CompressFormat.JPEG, 85, out)
            }
            Log.d(TAG, "Saved grid: ${file.absolutePath}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to save grid", e)
        }
    }

    private fun clearCaptures() {
        captures.forEach { it.recycle() }
        captures.clear()
    }

    fun getCaptureCount(): Int = captures.size
}
