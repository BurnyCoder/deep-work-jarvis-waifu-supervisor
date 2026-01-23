package com.procrastination.hellophone

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.procrastination.hellophone.ui.theme.HelloPhoneTheme

class BlockingOverlayActivity : ComponentActivity() {

    companion object {
        const val EXTRA_BLOCKED_APP = "blocked_app"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val blockedApp = intent.getStringExtra(EXTRA_BLOCKED_APP) ?: "Unknown app"

        enableEdgeToEdge()
        setContent {
            HelloPhoneTheme {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Color(0xFF1A1A2E))
                        .padding(32.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Text(
                        text = "Deep Work Mode Active",
                        style = MaterialTheme.typography.headlineLarge,
                        color = Color.White,
                        textAlign = TextAlign.Center
                    )

                    Spacer(modifier = Modifier.height(24.dp))

                    Text(
                        text = "This app is blocked:",
                        style = MaterialTheme.typography.bodyLarge,
                        color = Color.Gray
                    )

                    Text(
                        text = blockedApp,
                        style = MaterialTheme.typography.titleMedium,
                        color = Color(0xFFF44336)
                    )

                    Spacer(modifier = Modifier.height(48.dp))

                    Text(
                        text = "Stay focused! You can do it.",
                        style = MaterialTheme.typography.bodyLarge,
                        color = Color(0xFF4CAF50),
                        textAlign = TextAlign.Center
                    )

                    Spacer(modifier = Modifier.height(48.dp))

                    Button(
                        onClick = { goHome() }
                    ) {
                        Text("Go to Home Screen")
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    Button(
                        onClick = { openDeepWorkApp() }
                    ) {
                        Text("Open Deep Work")
                    }
                }
            }
        }
    }

    private fun goHome() {
        val homeIntent = android.content.Intent(android.content.Intent.ACTION_MAIN).apply {
            addCategory(android.content.Intent.CATEGORY_HOME)
            flags = android.content.Intent.FLAG_ACTIVITY_NEW_TASK
        }
        startActivity(homeIntent)
        finish()
    }

    private fun openDeepWorkApp() {
        val intent = android.content.Intent(this, MainActivity::class.java).apply {
            flags = android.content.Intent.FLAG_ACTIVITY_NEW_TASK or
                    android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        startActivity(intent)
        finish()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        // Prevent going back to the blocked app
        goHome()
    }
}
