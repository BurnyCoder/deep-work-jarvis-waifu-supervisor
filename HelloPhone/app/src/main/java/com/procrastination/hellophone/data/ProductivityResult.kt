package com.procrastination.hellophone.data

data class ProductivityResult(
    val productive: Boolean,
    val reason: String,
    val timestamp: Long = System.currentTimeMillis()
)
