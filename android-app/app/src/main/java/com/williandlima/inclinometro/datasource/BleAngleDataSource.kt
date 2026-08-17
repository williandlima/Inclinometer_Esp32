package com.williandlima.inclinometro.datasource

import android.annotation.SuppressLint
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.Context
import java.io.IOException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.CancellableContinuation
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeout

/**
 * Fonte de dados real: conecta via BLE ao inclinômetro ESP32 e escuta
 * notificações de ângulo, conforme [BleContract]. Também suporta calibração
 * e captura de vibração pelo mesmo contrato.
 *
 * O firmware segue esse contrato (ver `firmware/README.md`), mas não foi
 * validado contra hardware real ainda. Seleção de dispositivo é feita por
 * endereço MAC informado pelo usuário, ou pela tela de scan (`BleScanner`).
 *
 * No Android só pode haver UMA operação GATT em andamento por vez na mesma
 * conexão (habilitar notify, escrever característica) — disparar a próxima
 * antes do callback da anterior chegar (`onDescriptorWrite`/
 * `onCharacteristicWrite`) faz a operação seguinte falhar silenciosamente,
 * sem erro nenhum. Por isso todas passam por [enqueueGattOperation] em vez
 * de serem chamadas direto.
 */
@SuppressLint("MissingPermission")
class BleAngleDataSource(
    private val context: Context,
    private val deviceAddress: String,
) : AngleDataSource {

    override val label: String = "BLE ($deviceAddress)"

    private var gatt: BluetoothGatt? = null
    private var calibrateCharacteristic: BluetoothGattCharacteristic? = null
    private var vibrationConfigCharacteristic: BluetoothGattCharacteristic? = null

    private var pendingWriteContinuation: CancellableContinuation<Unit>? = null
    private var vibrationStatusListener: ((status: Int, progress: Int, totalSamples: Int) -> Unit)? = null
    private var vibrationDataListener: ((startIndex: Int, samples: ShortArray) -> Unit)? = null

    private val gattOperationQueue = ArrayDeque<() -> Unit>()
    private var gattOperationInFlight = false

    private fun enqueueGattOperation(operation: () -> Unit) {
        gattOperationQueue.addLast(operation)
        if (!gattOperationInFlight) {
            processNextGattOperation()
        }
    }

    private fun processNextGattOperation() {
        val next = gattOperationQueue.removeFirstOrNull()
        if (next == null) {
            gattOperationInFlight = false
            return
        }
        gattOperationInFlight = true
        next()
    }

    override fun readings(): Flow<AngleReading> = callbackFlow {
        val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        val adapter = bluetoothManager.adapter
            ?: run {
                close(IOException("Bluetooth não disponível neste dispositivo."))
                return@callbackFlow
            }
        val device = adapter.getRemoteDevice(deviceAddress)

        val callback = object : BluetoothGattCallback() {
            override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
                when (newState) {
                    BluetoothProfile.STATE_CONNECTED -> g.discoverServices()
                    BluetoothProfile.STATE_DISCONNECTED -> close(IOException("Conexão BLE perdida."))
                }
            }

            override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
                val service = g.getService(BleContract.SERVICE_UUID)
                val angleCharacteristic = service?.getCharacteristic(BleContract.ANGLE_CHARACTERISTIC_UUID)
                if (service == null || angleCharacteristic == null) {
                    close(IOException("Serviço/característica BLE do inclinômetro não encontrados."))
                    return
                }
                calibrateCharacteristic = service.getCharacteristic(BleContract.CALIBRATE_CHARACTERISTIC_UUID)
                vibrationConfigCharacteristic =
                    service.getCharacteristic(BleContract.VIBRATION_CONFIG_CHARACTERISTIC_UUID)
                val vibrationStatusChar = service.getCharacteristic(BleContract.VIBRATION_STATUS_CHARACTERISTIC_UUID)
                val vibrationDataChar = service.getCharacteristic(BleContract.VIBRATION_DATA_CHARACTERISTIC_UUID)

                // Enfileiradas: ver nota da classe sobre operações GATT
                // seriais no Android.
                enqueueGattOperation { enableNotify(g, angleCharacteristic) }
                vibrationStatusChar?.let { c -> enqueueGattOperation { enableNotify(g, c) } }
                vibrationDataChar?.let { c -> enqueueGattOperation { enableNotify(g, c) } }
            }

            private fun enableNotify(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
                g.setCharacteristicNotification(characteristic, true)
                val descriptor = characteristic.getDescriptor(BleContract.CLIENT_CHARACTERISTIC_CONFIG_UUID)
                if (descriptor == null) {
                    processNextGattOperation()
                    return
                }
                @Suppress("DEPRECATION")
                descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                @Suppress("DEPRECATION")
                val started = g.writeDescriptor(descriptor)
                if (!started) {
                    processNextGattOperation()
                }
            }

            override fun onDescriptorWrite(g: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
                processNextGattOperation()
            }

            @Suppress("DEPRECATION")
            override fun onCharacteristicChanged(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
                val raw = characteristic.value ?: return
                when (characteristic.uuid) {
                    BleContract.ANGLE_CHARACTERISTIC_UUID -> emitAngleFromBytes(raw)
                    BleContract.VIBRATION_STATUS_CHARACTERISTIC_UUID -> handleVibrationStatus(raw)
                    BleContract.VIBRATION_DATA_CHARACTERISTIC_UUID -> handleVibrationData(raw)
                }
            }

            override fun onCharacteristicWrite(
                g: BluetoothGatt,
                characteristic: BluetoothGattCharacteristic,
                status: Int,
            ) {
                val continuation = pendingWriteContinuation
                pendingWriteContinuation = null
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    continuation?.resume(Unit)
                } else {
                    continuation?.resumeWithException(IOException("Falha ao escrever característica BLE (status=$status)."))
                }
                processNextGattOperation()
            }

            private fun emitAngleFromBytes(raw: ByteArray) {
                if (raw.size < 2) return
                val rawValue = ((raw[1].toInt() and 0xFF) shl 8) or (raw[0].toInt() and 0xFF)
                val angle = rawValue.toShort() / BleContract.ANGLE_SCALE
                trySend(AngleReading(angleDeg = angle, timestamp = System.currentTimeMillis()))
            }

            private fun handleVibrationStatus(raw: ByteArray) {
                if (raw.size < 2) return
                val status = raw[0].toInt() and 0xFF
                val progress = raw[1].toInt() and 0xFF
                val total = if (raw.size >= 4) {
                    (raw[2].toInt() and 0xFF) or ((raw[3].toInt() and 0xFF) shl 8)
                } else {
                    0
                }
                vibrationStatusListener?.invoke(status, progress, total)
            }

            private fun handleVibrationData(raw: ByteArray) {
                if (raw.size < 2) return
                val startIndex = (raw[0].toInt() and 0xFF) or ((raw[1].toInt() and 0xFF) shl 8)
                val sampleCount = (raw.size - 2) / 2
                val samples = ShortArray(sampleCount)
                for (i in 0 until sampleCount) {
                    val lo = raw[2 + i * 2].toInt() and 0xFF
                    val hi = raw[2 + i * 2 + 1].toInt() and 0xFF
                    samples[i] = ((hi shl 8) or lo).toShort()
                }
                vibrationDataListener?.invoke(startIndex, samples)
            }
        }

        gatt = device.connectGatt(context, false, callback)

        awaitClose {
            gatt?.disconnect()
            gatt?.close()
            gatt = null
            calibrateCharacteristic = null
            vibrationConfigCharacteristic = null
            gattOperationQueue.clear()
            gattOperationInFlight = false
        }
    }

    override val supportsCalibration: Boolean = true

    override suspend fun calibrate() {
        val g = gatt ?: throw IOException("Não conectado ao dispositivo.")
        val characteristic = calibrateCharacteristic
            ?: throw IOException("Característica de calibração não encontrada.")
        writeCharacteristic(g, characteristic, byteArrayOf(0x01))
    }

    override val supportsVibrationCapture: Boolean = true

    override suspend fun startVibrationCapture(
        durationS: Int,
        rateHz: Int,
        onProgress: (Int) -> Unit,
    ): List<AngleReading> {
        val g = gatt ?: throw IOException("Não conectado ao dispositivo.")
        val characteristic = vibrationConfigCharacteristic
            ?: throw IOException("Característica de configuração de vibração não encontrada.")

        val samples = sortedMapOf<Int, Short>()
        var totalExpected: Int? = null

        val config = ByteArray(4)
        config[0] = (durationS and 0xFF).toByte()
        config[1] = ((durationS shr 8) and 0xFF).toByte()
        config[2] = (rateHz and 0xFF).toByte()
        config[3] = ((rateHz shr 8) and 0xFF).toByte()

        val timeoutS = durationS + BleContract.VIBRATION_CAPTURE_TIMEOUT_MARGIN_S
        val result = withTimeout(timeoutS * 1000L) {
            // Escreve a config sequencialmente, na mesma coroutine (contexto
            // estruturado) — só depois entra em espera pelas notificações.
            writeCharacteristic(g, characteristic, config)

            suspendCancellableCoroutine { continuation ->
                vibrationStatusListener = { status, progress, total ->
                    when (status) {
                        1 -> onProgress(progress)
                        2 -> {
                            totalExpected = total
                            if (samples.size >= total && continuation.isActive) {
                                continuation.resume(finishVibrationCapture(samples, rateHz))
                            }
                        }
                        3 -> {
                            if (continuation.isActive) {
                                continuation.resumeWithException(
                                    IOException("Firmware reportou erro durante a captura de vibração.")
                                )
                            }
                        }
                    }
                }
                vibrationDataListener = { startIndex, chunk ->
                    chunk.forEachIndexed { i, value -> samples[startIndex + i] = value }
                    val total = totalExpected
                    if (total != null && samples.size >= total && continuation.isActive) {
                        continuation.resume(finishVibrationCapture(samples, rateHz))
                    }
                }
                continuation.invokeOnCancellation {
                    vibrationStatusListener = null
                    vibrationDataListener = null
                }
            }
        }

        vibrationStatusListener = null
        vibrationDataListener = null
        return result
    }

    private fun finishVibrationCapture(samples: Map<Int, Short>, rateHz: Int): List<AngleReading> {
        val total = samples.size
        val now = System.currentTimeMillis()
        val startMillis = now - (total * 1000L) / rateHz
        return samples.entries.sortedBy { it.key }.map { (index, value) ->
            AngleReading(
                angleDeg = value / BleContract.ANGLE_SCALE,
                timestamp = startMillis + (index * 1000L) / rateHz,
            )
        }
    }

    private suspend fun writeCharacteristic(
        g: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        value: ByteArray,
    ) = suspendCancellableCoroutine<Unit> { continuation ->
        enqueueGattOperation {
            pendingWriteContinuation = continuation
            @Suppress("DEPRECATION")
            characteristic.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
            @Suppress("DEPRECATION")
            characteristic.value = value
            @Suppress("DEPRECATION")
            val started = g.writeCharacteristic(characteristic)
            if (!started) {
                pendingWriteContinuation = null
                processNextGattOperation()
                continuation.resumeWithException(IOException("Falha ao iniciar escrita BLE."))
            }
        }
    }
}
