package com.procrastination.hellophone

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import com.procrastination.hellophone.data.Mode
import com.procrastination.hellophone.service.AppBlockerService
import com.procrastination.hellophone.service.MonitoringService
import com.procrastination.hellophone.tts.SpeechManager
import com.procrastination.hellophone.ui.screens.HomeScreen
import com.procrastination.hellophone.ui.screens.SettingsScreen
import com.procrastination.hellophone.ui.theme.HelloPhoneTheme
import com.procrastination.hellophone.viewmodel.MainViewModel

class MainActivity : ComponentActivity() {

    private var speechManager: SpeechManager? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        speechManager = SpeechManager(this)

        enableEdgeToEdge()
        setContent {
            HelloPhoneTheme {
                val viewModel: MainViewModel = viewModel()

                DeepWorkApp(
                    viewModel = viewModel,
                    speechManager = speechManager
                )
            }
        }
    }

    override fun onDestroy() {
        speechManager?.shutdown()
        super.onDestroy()
    }
}

@Composable
fun DeepWorkApp(
    viewModel: MainViewModel,
    speechManager: SpeechManager?
) {
    val context = LocalContext.current
    val activity = context as? Activity

    var selectedTab by remember { mutableStateOf(0) }
    val state by viewModel.state.collectAsState()

    // Permission launchers
    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            // Camera permission granted
        }
    }

    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        // Notification permission handled
    }

    val mediaProjectionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            MonitoringService.setMediaProjectionResult(result.resultCode, result.data)
            MonitoringService.start(context)
        }
    }

    // Handle mode changes
    LaunchedEffect(state.mode) {
        speechManager?.speakModeChange(state.mode)

        when (state.mode) {
            Mode.ON -> {
                // Start services
                if (AppBlockerService.hasUsageStatsPermission(context)) {
                    AppBlockerService.start(context)
                }

                // Request screen capture permission
                if (activity != null) {
                    val projectionManager = context.getSystemService(MediaProjectionManager::class.java)
                    mediaProjectionLauncher.launch(projectionManager.createScreenCaptureIntent())
                }
            }
            Mode.OFF, Mode.BREAK -> {
                // Stop services
                AppBlockerService.stop(context)
                MonitoringService.stop(context)
            }
        }
    }

    // Request permissions on first launch
    LaunchedEffect(Unit) {
        // Request camera permission
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED
        ) {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }

        // Request notification permission (Android 13+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    icon = { Icon(Icons.Default.Home, contentDescription = "Home") },
                    label = { Text("Home") },
                    selected = selectedTab == 0,
                    onClick = { selectedTab = 0 }
                )
                NavigationBarItem(
                    icon = { Icon(Icons.Default.Settings, contentDescription = "Settings") },
                    label = { Text("Settings") },
                    selected = selectedTab == 1,
                    onClick = { selectedTab = 1 }
                )
            }
        }
    ) { innerPadding ->
        when (selectedTab) {
            0 -> HomeScreen(
                viewModel = viewModel,
                modifier = Modifier.padding(innerPadding)
            )
            1 -> SettingsScreen(
                viewModel = viewModel,
                modifier = Modifier.padding(innerPadding)
            )
        }
    }
}
