package com.procrastination.hellophone.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.procrastination.hellophone.data.Mode
import com.procrastination.hellophone.data.ProductivityResult
import com.procrastination.hellophone.ui.components.ConfirmationDialog
import com.procrastination.hellophone.ui.components.ModeToggle
import com.procrastination.hellophone.viewmodel.MainViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun HomeScreen(
    viewModel: MainViewModel,
    modifier: Modifier = Modifier
) {
    val state by viewModel.state.collectAsState()
    val showConfirmationDialog by viewModel.showConfirmationDialog.collectAsState()
    val recentResults by viewModel.recentResults.collectAsState()

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = "Deep Work",
            style = MaterialTheme.typography.displaySmall
        )

        Spacer(modifier = Modifier.height(32.dp))

        ModeToggle(
            currentMode = state.mode,
            breakRemainingSeconds = state.breakRemainingSeconds,
            onModeChange = { mode, breakMinutes ->
                viewModel.requestModeChange(mode, breakMinutes)
            }
        )

        Spacer(modifier = Modifier.height(32.dp))

        HorizontalDivider()

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = "Recent Analysis Results",
            style = MaterialTheme.typography.titleMedium
        )

        Spacer(modifier = Modifier.height(8.dp))

        if (recentResults.isEmpty()) {
            Text(
                text = "No results yet. Enable ON mode to start monitoring.",
                style = MaterialTheme.typography.bodyMedium,
                color = Color.Gray
            )
        } else {
            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(recentResults) { result ->
                    ProductivityResultCard(result)
                }
            }
        }
    }

    if (showConfirmationDialog) {
        ConfirmationDialog(
            onConfirm = { phrase ->
                viewModel.confirmModeChange(phrase)
            },
            onDismiss = {
                viewModel.cancelModeChange()
            }
        )
    }
}

@Composable
private fun ProductivityResultCard(result: ProductivityResult) {
    val dateFormat = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
    val timeString = dateFormat.format(Date(result.timestamp))

    Card(
        colors = CardDefaults.cardColors(
            containerColor = if (result.productive) {
                Color(0xFFE8F5E9)
            } else {
                Color(0xFFFFEBEE)
            }
        )
    ) {
        Column(
            modifier = Modifier.padding(12.dp)
        ) {
            Text(
                text = if (result.productive) "Productive" else "Not Productive",
                style = MaterialTheme.typography.titleSmall,
                color = if (result.productive) Color(0xFF4CAF50) else Color(0xFFF44336)
            )
            Text(
                text = result.reason,
                style = MaterialTheme.typography.bodySmall
            )
            Text(
                text = timeString,
                style = MaterialTheme.typography.labelSmall,
                color = Color.Gray
            )
        }
    }
}
