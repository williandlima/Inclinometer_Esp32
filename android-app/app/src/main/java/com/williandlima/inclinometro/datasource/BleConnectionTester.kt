package com.williandlima.inclinometro.datasource

import android.annotation.SuppressLint
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.Context
import java.io.IOException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeout

data class BleConnectionTestResult(
    val angleDeg: Double,
    val firmwareVersion: String,
    /** `null` se o firmware não expõe o eixo de azimute (anterior à v1.2.0). */
    val panDeg: Double? = null,
)

/**
 * Testa a conexão BLE com o ESP32: conecta, lê os dois eixos e a versão do
 * firmware uma única vez, e desconecta — sem iniciar uma sessão de leitura
 * contínua. Equivalente ao "Testar conexão com ESP32" do app desktop
 * (`python-app/data_source/ble_source.py`, `test_connection`).
 *
 * As leituras são encadeadas (ângulo → azimute → versão) porque no Android só
 * pode haver uma operação GATT em andamento por vez. Azimute e versão são
 * diagnósticos secundários: se qualquer um falhar ou não existir, o teste
 * ainda é considerado bem-sucedido, só sem aquele dado.
 */
@SuppressLint("MissingPermission")
object BleConnectionTester {
    private const val TIMEOUT_MS = 8000L

    suspend fun test(context: Context, deviceAddress: String): BleConnectionTestResult =
        withTimeout(TIMEOUT_MS) {
            suspendCancellableCoroutine { continuation ->
                val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
                val adapter = bluetoothManager.adapter
                if (adapter == null) {
                    continuation.resumeWithException(IOException("Bluetooth não disponível neste dispositivo."))
                    return@suspendCancellableCoroutine
                }
                val device = adapter.getRemoteDevice(deviceAddress)

                var gatt: BluetoothGatt? = null
                var angleDeg: Double? = null
                var panDeg: Double? = null

                fun finish(result: Result<BleConnectionTestResult>) {
                    gatt?.disconnect()
                    gatt?.close()
                    if (continuation.isActive) {
                        result.fold(
                            onSuccess = { continuation.resume(it) },
                            onFailure = { continuation.resumeWithException(it) },
                        )
                    }
                }

                fun readVersionOrFinish(g: BluetoothGatt) {
                    val versionChar = g.getService(BleContract.SERVICE_UUID)
                        ?.getCharacteristic(BleContract.FIRMWARE_VERSION_CHARACTERISTIC_UUID)
                    if (versionChar == null || !g.readCharacteristic(versionChar)) {
                        // Versão é só diagnóstico secundário — não falha o teste sem ela.
                        finish(Result.success(BleConnectionTestResult(angleDeg ?: 0.0, "?", panDeg)))
                    }
                }

                fun readPanOrVersion(g: BluetoothGatt) {
                    val panChar = g.getService(BleContract.SERVICE_UUID)
                        ?.getCharacteristic(BleContract.PAN_CHARACTERISTIC_UUID)
                    // Ausente em firmware anterior à v1.2.0: segue pra versão.
                    if (panChar == null || !g.readCharacteristic(panChar)) {
                        readVersionOrFinish(g)
                    }
                }

                val callback = object : BluetoothGattCallback() {
                    override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
                        when (newState) {
                            BluetoothProfile.STATE_CONNECTED -> g.discoverServices()
                            BluetoothProfile.STATE_DISCONNECTED ->
                                if (angleDeg == null) {
                                    finish(Result.failure(IOException("Conexão BLE perdida.")))
                                }
                        }
                    }

                    override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
                        val service = g.getService(BleContract.SERVICE_UUID)
                        val angleChar = service?.getCharacteristic(BleContract.ANGLE_CHARACTERISTIC_UUID)
                        if (service == null || angleChar == null) {
                            finish(
                                Result.failure(
                                    IOException("Serviço/característica BLE do inclinômetro não encontrados.")
                                )
                            )
                            return
                        }
                        if (!g.readCharacteristic(angleChar)) {
                            finish(Result.failure(IOException("Falha ao ler ângulo via BLE.")))
                        }
                    }

                    @Suppress("DEPRECATION")
                    override fun onCharacteristicRead(
                        g: BluetoothGatt,
                        characteristic: BluetoothGattCharacteristic,
                        status: Int,
                    ) {
                        // O status é avaliado por característica: só a de
                        // ângulo é obrigatória, as outras duas são opcionais.
                        val ok = status == BluetoothGatt.GATT_SUCCESS
                        when (characteristic.uuid) {
                            BleContract.ANGLE_CHARACTERISTIC_UUID -> {
                                if (!ok) {
                                    finish(
                                        Result.failure(
                                            IOException("Falha ao ler característica BLE (status=$status).")
                                        )
                                    )
                                    return
                                }
                                val angle = decodeAngle(characteristic.value)
                                if (angle == null) {
                                    finish(Result.failure(IOException("Resposta BLE inválida para o ângulo.")))
                                    return
                                }
                                angleDeg = angle
                                readPanOrVersion(g)
                            }
                            BleContract.PAN_CHARACTERISTIC_UUID -> {
                                if (ok) {
                                    panDeg = decodeAngle(characteristic.value)
                                }
                                readVersionOrFinish(g)
                            }
                            BleContract.FIRMWARE_VERSION_CHARACTERISTIC_UUID -> {
                                val version = if (ok) decodeFirmwareVersion(characteristic.value) else "?"
                                finish(Result.success(BleConnectionTestResult(angleDeg ?: 0.0, version, panDeg)))
                            }
                        }
                    }
                }

                continuation.invokeOnCancellation {
                    gatt?.disconnect()
                    gatt?.close()
                }

                gatt = device.connectGatt(context, false, callback)
            }
        }

    private fun decodeAngle(raw: ByteArray?): Double? {
        if (raw == null || raw.size < 2) return null
        val rawValue = ((raw[1].toInt() and 0xFF) shl 8) or (raw[0].toInt() and 0xFF)
        return rawValue.toShort() / BleContract.ANGLE_SCALE
    }

    private fun decodeFirmwareVersion(raw: ByteArray?): String {
        if (raw == null || raw.size < 2) return "?"
        val code = (raw[0].toInt() and 0xFF) or ((raw[1].toInt() and 0xFF) shl 8)
        val major = code / 10000
        val minor = (code / 100) % 100
        val patch = code % 100
        return "$major.$minor.$patch"
    }
}
