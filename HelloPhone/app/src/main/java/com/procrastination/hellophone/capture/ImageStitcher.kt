package com.procrastination.hellophone.capture

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect

object ImageStitcher {

    private val labelPaint = Paint().apply {
        color = Color.WHITE
        textSize = 32f
        isAntiAlias = true
    }

    private val backgroundPaint = Paint().apply {
        color = Color.argb(180, 50, 50, 50)
    }

    /**
     * Stitches screen capture and camera capture into a single labeled image.
     */
    fun stitchImages(
        screenCapture: Bitmap?,
        cameraCapture: Bitmap?,
        labels: List<String> = listOf("Screen", "Camera")
    ): Bitmap? {
        val images = listOfNotNull(screenCapture, cameraCapture)
        if (images.isEmpty()) return null

        val labelHeight = 50
        val maxWidth = 800
        val maxHeight = 600

        // Scale images to fit
        val scaledImages = images.map { img ->
            scaleToFit(img, maxWidth, maxHeight)
        }

        // Calculate total dimensions
        val totalWidth = scaledImages.sumOf { it.width }
        val totalHeight = scaledImages.maxOf { it.height } + labelHeight

        // Create result bitmap
        val result = Bitmap.createBitmap(totalWidth, totalHeight, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(result)
        canvas.drawColor(Color.rgb(30, 30, 30))

        var xOffset = 0
        scaledImages.forEachIndexed { index, bitmap ->
            // Draw label background
            canvas.drawRect(
                xOffset.toFloat(),
                0f,
                (xOffset + bitmap.width).toFloat(),
                labelHeight.toFloat(),
                backgroundPaint
            )

            // Draw label text
            val label = labels.getOrElse(index) { "Image $index" }
            val textWidth = labelPaint.measureText(label)
            val textX = xOffset + (bitmap.width - textWidth) / 2
            canvas.drawText(label, textX, 35f, labelPaint)

            // Draw image
            canvas.drawBitmap(bitmap, xOffset.toFloat(), labelHeight.toFloat(), null)

            xOffset += bitmap.width
        }

        // Recycle scaled images if they're different from originals
        scaledImages.forEachIndexed { index, scaled ->
            if (scaled != images[index]) {
                scaled.recycle()
            }
        }

        return result
    }

    /**
     * Creates a grid from multiple captures.
     */
    fun createGrid(
        captures: List<Bitmap>,
        itemWidth: Int = 600,
        itemHeight: Int = 400,
        columns: Int = 3
    ): Bitmap? {
        if (captures.isEmpty()) return null

        val rows = (captures.size + columns - 1) / columns
        val gridWidth = columns * itemWidth
        val gridHeight = rows * itemHeight

        val result = Bitmap.createBitmap(gridWidth, gridHeight, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(result)
        canvas.drawColor(Color.DKGRAY)

        captures.forEachIndexed { index, bitmap ->
            val col = index % columns
            val row = index / columns
            val x = col * itemWidth
            val y = row * itemHeight

            val scaled = scaleToFit(bitmap, itemWidth, itemHeight)

            // Center the scaled image in the cell
            val offsetX = x + (itemWidth - scaled.width) / 2
            val offsetY = y + (itemHeight - scaled.height) / 2

            canvas.drawBitmap(scaled, offsetX.toFloat(), offsetY.toFloat(), null)

            if (scaled != bitmap) {
                scaled.recycle()
            }
        }

        return result
    }

    private fun scaleToFit(bitmap: Bitmap, maxWidth: Int, maxHeight: Int): Bitmap {
        val widthRatio = maxWidth.toFloat() / bitmap.width
        val heightRatio = maxHeight.toFloat() / bitmap.height
        val ratio = minOf(widthRatio, heightRatio, 1f)

        if (ratio >= 1f) return bitmap

        val newWidth = (bitmap.width * ratio).toInt()
        val newHeight = (bitmap.height * ratio).toInt()

        return Bitmap.createScaledBitmap(bitmap, newWidth, newHeight, true)
    }
}
