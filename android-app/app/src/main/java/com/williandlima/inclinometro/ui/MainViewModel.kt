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
import com.williandlima.inclinometro.limits.VibrationStats
import com.williandlima.inclinometro.limits.VibrationStatsCalculator
import com.williandlima.inclinometro.limits.db.AppDatabase
import com.williandlima.inclinometro.report.PdfReportGenerator
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Estado da conexão exibido na UI, mesma semântica do app desktop
 * (`_CONN_STYLES` em `python-app/ui/main_window.py`). */
enum class ConnectionStatus { PARADO, CONECTANDO, CONECTADO, ERRO, SIMULACAO }

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
    val connectionStatus: ConnectionStatus = ConnectionStatus.PARADO,
    val calibrating: Boolean = false,
    val vibrationCapturing: Boolean = false,
    val vibrationProgress: Int = 0,
    val vibrationResult: VibrationStats? = null,
)

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val repository = HistoryRepository(AppDatabase.getInstance(application).dao())
    private val tracker = LimitTracker()

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    private var collectJob: Job? = null
    private var vibrationJob: Job? = null
    private var currentSessionId: Long? = null
    private var currentSource: AngleDataSource? = null

    private var lastVibrationCaptureId: Long? = null
    private var lastVibrationReadings: List<AngleReading> = emptyList()
    private var lastVibrationFreqsHz: DoubleArray = DoubleArray(0)
    private var lastVibrationMagnitudes: DoubleArray = DoubleArray(0)

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
        currentSource = source

        tracker.reset()
        viewModelScope.launch {
            currentSessionId = repository.startSession(mode)
            _uiState.update {
                it.copy(
                    running = true,
                    minReading = null,
                    maxReading = null,
                    statusMessage = "Conectado: ${source.label}",
                    connectionStatus = if (mode == ConnectionMode.SIMULATED) {
                        ConnectionStatus.SIMULACAO
                    } else {
                        ConnectionStatus.CONECTANDO
                    },
                )
            }
            collectJob = source.readings()
                .catch { e ->
                    _uiState.update { s ->
                        s.copy(
                            statusMessage = "Erro: ${e.message}",
                            connectionStatus = if (s.mode == ConnectionMode.REAL) ConnectionStatus.ERRO else s.connectionStatus,
                        )
                    }
                }
                .onEach { reading -> onReading(reading) }
                .launchIn(viewModelScope)
        }
    }

    private suspend fun onReading(reading: AngleReading) {
        val sessionId = currentSessionId ?: return
        repository.addReading(sessionId, reading)
        _uiState.update {
            it.copy(
                currentAngle = reading.angleDeg,
                connectionStatus = if (it.mode == ConnectionMode.REAL) ConnectionStatus.CONECTADO else it.connectionStatus,
            )
        }

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
        vibrationJob?.cancel()
        vibrationJob = null
        currentSource = null
        val sessionId = currentSessionId
        viewModelScope.launch {
            sessionId?.let { repository.endSession(it) }
            _uiState.update { it.copy(running = false, statusMessage = "Parado.", connectionStatus = ConnectionStatus.PARADO) }
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

    // ------------------------------------------------------------ calibração

    fun calibrate() {
        val source = currentSource
        if (!_uiState.value.running || source == null) {
            _uiState.update { it.copy(statusMessage = "Inicie a leitura antes de calibrar.") }
            return
        }
        if (!source.supportsCalibration) {
            _uiState.update { it.copy(statusMessage = "Esta fonte de dados não suporta calibração.") }
            return
        }

        _uiState.update { it.copy(calibrating = true) }
        viewModelScope.launch {
            try {
                source.calibrate()
                _uiState.update { it.copy(statusMessage = "Calibração concluída: posição atual definida como 0°.") }
                resetLimits()
            } catch (e: Exception) {
                _uiState.update { it.copy(statusMessage = "Falha na calibração: ${e.message}") }
            } finally {
                _uiState.update { it.copy(calibrating = false) }
            }
        }
    }

    // ------------------------------------------------------- Modo Vibração

    fun startVibrationCapture(durationS: Int, rateHz: Int) {
        val source = currentSource
        if (!_uiState.value.running || source == null) {
            _uiState.update { it.copy(statusMessage = "Inicie a leitura antes de usar o Modo Vibração.") }
            return
        }
        if (!source.supportsVibrationCapture) {
            _uiState.update { it.copy(statusMessage = "Esta fonte de dados não suporta captura de vibração.") }
            return
        }

        val mode = _uiState.value.mode
        _uiState.update {
            it.copy(
                vibrationCapturing = true,
                vibrationProgress = 0,
                vibrationResult = null,
                statusMessage = "Captura de vibração em andamento...",
            )
        }
        vibrationJob = viewModelScope.launch {
            try {
                val readings = source.startVibrationCapture(durationS, rateHz) { percent ->
                    _uiState.update { it.copy(vibrationProgress = percent) }
                }
                if (readings.isEmpty()) {
                    _uiState.update { it.copy(statusMessage = "Nenhuma amostra foi capturada.") }
                    return@launch
                }

                val captureId = repository.saveVibrationCapture(mode, durationS, rateHz, readings)
                val stats = VibrationStatsCalculator.computeStats(readings)
                val (freqs, magnitudes) = VibrationStatsCalculator.computeFft(readings, rateHz)

                lastVibrationCaptureId = captureId
                lastVibrationReadings = readings
                lastVibrationFreqsHz = freqs
                lastVibrationMagnitudes = magnitudes

                _uiState.update { it.copy(vibrationResult = stats, statusMessage = "Captura de vibração concluída.") }
            } catch (e: TimeoutCancellationException) {
                _uiState.update { it.copy(statusMessage = "Tempo esgotado aguardando a captura de vibração.") }
            } catch (e: CancellationException) {
                _uiState.update { it.copy(statusMessage = "Captura de vibração cancelada.") }
            } catch (e: Exception) {
                _uiState.update { it.copy(statusMessage = "Captura de vibração: ${e.message}") }
            } finally {
                _uiState.update { it.copy(vibrationCapturing = false) }
            }
        }
    }

    fun cancelVibrationCapture() {
        vibrationJob?.cancel()
    }

    fun dismissVibrationResult() {
        _uiState.update { it.copy(vibrationResult = null) }
    }

    suspend fun generateVibrationReportFile(): File? {
        val captureId = lastVibrationCaptureId ?: return null
        val readings = lastVibrationReadings
        if (readings.isEmpty()) return null
        val captureInfo = repository.listVibrationCaptures().firstOrNull { it.id == captureId } ?: return null
        val stats = VibrationStatsCalculator.computeStats(readings)
        return PdfReportGenerator.generateVibrationReport(
            getApplication(),
            captureInfo,
            readings,
            stats,
            lastVibrationFreqsHz,
            lastVibrationMagnitudes,
        )
    }

    override fun onCleared() {
        collectJob?.cancel()
        vibrationJob?.cancel()
        super.onCleared()
    }
}
