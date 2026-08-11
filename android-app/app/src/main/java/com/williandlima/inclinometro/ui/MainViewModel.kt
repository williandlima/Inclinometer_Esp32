package com.williandlima.inclinometro.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.williandlima.inclinometro.datasource.AngleDataSource
import com.williandlima.inclinometro.datasource.AngleReading
import com.williandlima.inclinometro.datasource.BleAngleDataSource
import com.williandlima.inclinometro.datasource.ConnectionMode
import com.williandlima.inclinometro.datasource.SimulatedAngleDataSource
import com.williandlima.inclinometro.limits.HistoryRepository
import com.williandlima.inclinometro.limits.LimitKind
import com.williandlima.inclinometro.limits.LimitTracker
import com.williandlima.inclinometro.limits.db.AppDatabase
import com.williandlima.inclinometro.report.PdfReportGenerator
import java.io.File
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class UiState(
    val mode: ConnectionMode = ConnectionMode.SIMULATED,
    val running: Boolean = false,
    val currentAngle: Double? = null,
    val minReading: AngleReading? = null,
    val maxReading: AngleReading? = null,
    val minFlash: Boolean = false,
    val maxFlash: Boolean = false,
    val statusMessage: String = "Pronto.",
    val bleDeviceAddress: String = "",
)

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val repository = HistoryRepository(AppDatabase.getInstance(application).dao())
    private val tracker = LimitTracker()

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    private var collectJob: Job? = null
    private var currentSessionId: Long? = null

    fun setMode(mode: ConnectionMode) {
        if (!_uiState.value.running) {
            _uiState.update { it.copy(mode = mode) }
        }
    }

    fun setBleDeviceAddress(address: String) {
        _uiState.update { it.copy(bleDeviceAddress = address) }
    }

    fun toggleStartStop() {
        if (_uiState.value.running) stop() else start()
    }

    private fun start() {
        val mode = _uiState.value.mode
        if (mode == ConnectionMode.REAL && _uiState.value.bleDeviceAddress.isBlank()) {
            _uiState.update { it.copy(statusMessage = "Informe o endereço MAC do dispositivo BLE.") }
            return
        }

        val source: AngleDataSource = if (mode == ConnectionMode.SIMULATED) {
            SimulatedAngleDataSource()
        } else {
            BleAngleDataSource(getApplication(), _uiState.value.bleDeviceAddress)
        }

        tracker.reset()
        viewModelScope.launch {
            currentSessionId = repository.startSession(mode)
            _uiState.update {
                it.copy(
                    running = true,
                    minReading = null,
                    maxReading = null,
                    statusMessage = "Conectado: ${source.label}",
                )
            }
            collectJob = source.readings()
                .catch { e -> _uiState.update { s -> s.copy(statusMessage = "Erro: ${e.message}") } }
                .onEach { reading -> onReading(reading) }
                .launchIn(viewModelScope)
        }
    }

    private suspend fun onReading(reading: AngleReading) {
        val sessionId = currentSessionId ?: return
        repository.addReading(sessionId, reading)
        _uiState.update { it.copy(currentAngle = reading.angleDeg) }

        for (event in tracker.process(reading)) {
            repository.addLimitEvent(sessionId, event)
            when (event.kind) {
                LimitKind.MIN -> {
                    _uiState.update { it.copy(minReading = event.reading, minFlash = true) }
                    scheduleFlashReset(isMin = true)
                }
                LimitKind.MAX -> {
                    _uiState.update { it.copy(maxReading = event.reading, maxFlash = true) }
                    scheduleFlashReset(isMin = false)
                }
            }
        }
    }

    private fun scheduleFlashReset(isMin: Boolean) {
        viewModelScope.launch {
            delay(1500)
            _uiState.update { if (isMin) it.copy(minFlash = false) else it.copy(maxFlash = false) }
        }
    }

    private fun stop() {
        collectJob?.cancel()
        collectJob = null
        val sessionId = currentSessionId
        viewModelScope.launch {
            sessionId?.let { repository.endSession(it) }
            _uiState.update { it.copy(running = false, statusMessage = "Parado.") }
        }
    }

    fun resetLimits() {
        val wasRunning = _uiState.value.running
        val mode = _uiState.value.mode
        tracker.reset()
        viewModelScope.launch {
            if (wasRunning) {
                currentSessionId?.let { repository.endSession(it) }
                currentSessionId = repository.startSession(mode)
            }
            _uiState.update {
                it.copy(
                    minReading = null,
                    maxReading = null,
                    statusMessage = if (wasRunning) {
                        "Limites resetados (histórico anterior preservado)."
                    } else {
                        "Limites resetados."
                    },
                )
            }
        }
    }

    suspend fun generateReportFile(): File? {
        val sessionId = currentSessionId ?: repository.listSessions().firstOrNull()?.id ?: run {
            _uiState.update { it.copy(statusMessage = "Ainda não há nenhuma sessão registrada.") }
            return null
        }
        val session = repository.getSession(sessionId) ?: return null
        val readings = repository.getReadings(sessionId)
        val events = repository.getLimitEvents(sessionId)
        return PdfReportGenerator.generate(getApplication(), session, readings, events)
    }

    override fun onCleared() {
        collectJob?.cancel()
        super.onCleared()
    }
}
