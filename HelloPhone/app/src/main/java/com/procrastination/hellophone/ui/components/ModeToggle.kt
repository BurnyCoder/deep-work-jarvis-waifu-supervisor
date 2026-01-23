package com.procrastination.hellophone.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.procrastination.hellophone.data.Mode

@Composable
fun ModeToggle(
    currentMode: Mode,
    breakRemainingSeconds: Int,
    onModeChange: (Mode, Int) -> Unit,
    modifier: Modifier = Modifier
) {
    var breakMinutes by remember { mutableStateOf("5") }

    Column(
        modifier = modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Current mode display
        Text(
            text = when (currentMode) {
                Mode.ON -> "Deep Work Mode: ON"
                Mode.OFF -> "Deep Work Mode: OFF"
                Mode.BREAK -> "Break Mode"
            },
            style = MaterialTheme.typography.headlineMedium,
            color = when (currentMode) {
                Mode.ON -> Color(0xFF4CAF50)
                Mode.OFF -> Color.Gray
                Mode.BREAK -> Color(0xFFFFA726)
            }
        )

        if (currentMode == Mode.BREAK && breakRemainingSeconds > 0) {
            val minutes = breakRemainingSeconds / 60
            val seconds = breakRemainingSeconds % 60
            Text(
                text = "Time remaining: ${minutes}m ${seconds}s",
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(top = 8.dp)
            )
        }

        Spacer(modifier = Modifier.height(24.dp))

        // Mode buttons
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            ModeButton(
                text = "ON",
                isSelected = currentMode == Mode.ON,
                color = Color(0xFF4CAF50),
                onClick = { onModeChange(Mode.ON, 0) }
            )

            ModeButton(
                text = "OFF",
                isSelected = currentMode == Mode.OFF,
                color = Color.Gray,
                onClick = { onModeChange(Mode.OFF, 0) }
            )
        }

        Spacer(modifier = Modifier.height(16.dp))

        // Break section
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = breakMinutes,
                onValueChange = { value ->
                    if (value.all { it.isDigit() } && value.length <= 3) {
                        breakMinutes = value
                    }
                },
                label = { Text("Minutes") },
                modifier = Modifier.width(100.dp),
                singleLine = true
            )

            Spacer(modifier = Modifier.width(16.dp))

            Button(
                onClick = {
                    val minutes = breakMinutes.toIntOrNull() ?: 5
                    onModeChange(Mode.BREAK, minutes)
                },
                colors = ButtonDefaults.buttonColors(
                    containerColor = Color(0xFFFFA726)
                )
            ) {
                Text("Take Break")
            }
        }
    }
}

@Composable
private fun ModeButton(
    text: String,
    isSelected: Boolean,
    color: Color,
    onClick: () -> Unit
) {
    if (isSelected) {
        Button(
            onClick = onClick,
            colors = ButtonDefaults.buttonColors(containerColor = color)
        ) {
            Text(text)
        }
    } else {
        OutlinedButton(onClick = onClick) {
            Text(text)
        }
    }
}
