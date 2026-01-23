package com.procrastination.hellophone.ui.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.procrastination.hellophone.data.Config

@Composable
fun ConfirmationDialog(
    onConfirm: (String) -> Boolean,
    onDismiss: () -> Unit
) {
    var phrase by remember { mutableStateOf("") }
    var showError by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text("Confirm Disable")
        },
        text = {
            Column {
                Text(
                    text = "To disable Deep Work mode, type the confirmation phrase:",
                    style = MaterialTheme.typography.bodyMedium
                )

                Spacer(modifier = Modifier.height(8.dp))

                Text(
                    text = "\"${Config.CONFIRMATION_PHRASE}\"",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary
                )

                Spacer(modifier = Modifier.height(16.dp))

                OutlinedTextField(
                    value = phrase,
                    onValueChange = {
                        phrase = it
                        showError = false
                    },
                    label = { Text("Type phrase here") },
                    modifier = Modifier.fillMaxWidth(),
                    isError = showError,
                    singleLine = true
                )

                if (showError) {
                    Text(
                        text = "Incorrect phrase. Try again.",
                        color = Color.Red,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    val success = onConfirm(phrase)
                    if (!success) {
                        showError = true
                    }
                }
            ) {
                Text("Confirm")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}
