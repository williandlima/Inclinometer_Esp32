package com.williandlima.inclinometro.ui

import android.content.Context
import android.content.Intent
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.williandlima.inclinometro.datasource.AngleReading
import com.williandlima.inclinometro.datasource.ConnectionMode
import com.williandlima.inclinometro.ui.theme.AmberFlash
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.launch

private val timeFormatter = SimpleDateFormat("HH:mm:ss", Locale("pt", "BR"))

@Composable
fun MainScreen(viewModel: MainViewModel) {
    val state by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val minCardColor by animateColorAsState(
        targetValue = if (state.minFlash) AmberFlash else MaterialTheme.colorScheme.surfaceVariant,
        label = "minCardColor",
    )
    val maxCardColor by animateColorAsState(
        targetValue = if (state.maxFlash) AmberFlash else MaterialTheme.colorScheme.surfaceVariant,
        label = "maxCardColor",
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        val modoLabel = if (state.mode == ConnectionMode.SIMULATED) "Simulação" else "Real (BLE)"
        val estadoLabel = if (state.running) "em execução" else "parado"
        Text("Modo: $modoLabel — $estadoLabel", style = MaterialTheme.typography.bodyMedium)

        Spacer(Modifier.height(16.dp))

        Text(
            text = state.currentAngle?.let { "%.2f°".format(it) } ?: "--.--°",
            style = MaterialTheme.typography.displayLarge,
            fontWeight = FontWeight.Bold,
        )

        Spacer(Modifier.height(24.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            LimitCard(
                title = "Mínimo",
                reading = state.minReading,
                containerColor = minCardColor,
                modifier = Modifier.weight(1f),
            )
            LimitCard(
                title = "Máximo",
                reading = state.maxReading,
                containerColor = maxCardColor,
                modifier = Modifier.weight(1f),
            )
        }

        Spacer(Modifier.height(24.dp))

        if (!state.running) {
            ModeSelector(
                mode = state.mode,
                onModeChange = viewModel::setMode,
                bleAddress = state.bleDeviceAddress,
                onBleAddressChange = viewModel::setBleDeviceAddress,
            )
            Spacer(Modifier.height(16.dp))
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = viewModel::toggleStartStop) {
                Text(if (state.running) "Parar" else "Iniciar")
            }
            OutlinedButton(onClick = viewModel::resetLimits) {
                Text("Resetar limites")
            }
        }

        Spacer(Modifier.height(8.dp))

        Button(onClick = {
            scope.launch {
                val file = viewModel.generateReportFile()
                if (file != null) {
                    sharePdf(context, file)
                }
            }
        }) {
            Text("Gerar relatório PDF")
        }

        Spacer(Modifier.height(16.dp))
        Text(state.statusMessage, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun LimitCard(
    title: String,
    reading: AngleReading?,
    containerColor: androidx.compose.ui.graphics.Color,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = containerColor),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(title, fontWeight = FontWeight.Bold)
            Text(
                reading?.let { "%.2f°".format(it.angleDeg) } ?: "--.--°",
                style = MaterialTheme.typography.titleLarge,
            )
            Text(reading?.let { timeFormatter.format(Date(it.timestamp)) } ?: "")
        }
    }
}

@Composable
private fun ModeSelector(
    mode: ConnectionMode,
    onModeChange: (ConnectionMode) -> Unit,
    bleAddress: String,
    onBleAddressChange: (String) -> Unit,
) {
    Column {
        Row(verticalAlignment = Alignment.CenterVertically) {
            RadioButton(selected = mode == ConnectionMode.SIMULATED, onClick = { onModeChange(ConnectionMode.SIMULATED) })
            Text("Simulação")
            Spacer(Modifier.width(16.dp))
            RadioButton(selected = mode == ConnectionMode.REAL, onClick = { onModeChange(ConnectionMode.REAL) })
            Text("Real (BLE)")
        }
        if (mode == ConnectionMode.REAL) {
            OutlinedTextField(
                value = bleAddress,
                onValueChange = onBleAddressChange,
                label = { Text("Endereço MAC do dispositivo BLE") },
            )
        }
    }
}

private fun sharePdf(context: Context, file: File) {
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "application/pdf"
        putExtra(Intent.EXTRA_STREAM, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(intent, "Compartilhar relatório"))
}
