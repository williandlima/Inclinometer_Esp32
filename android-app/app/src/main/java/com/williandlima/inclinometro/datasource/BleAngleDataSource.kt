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
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow

/**
 * Fonte de dados real: conecta via BLE ao inclinômetro ESP32 e escuta
 * notificações de ângulo, conforme [BleContract].
 *
 * O firmware ainda não existe nesta fase — esta implementação segue o
 * contrato já definido, pronta para quando o hardware estiver disponível.
 * Seleção de dispositivo é feita por endereço MAC informado pelo usuário
 * (sem tela de scan dedicada por enquanto).
 */
@SuppressLint("MissingPermission")
class BleAngleDataSource(
    private val context: Context,
    private val deviceAddress: String,
) : AngleDataSource {

    override val label: String = "BLE ($deviceAddress)"

    override fun readings(): Flow<AngleReading> = callbackFlow {
        val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        val adapter = bluetoothManager.adapter
            ?: run {
                close(IOException("Bluetooth não disponível neste dispositivo."))
                return@callbackFlow
            }
        val device = adapter.getRemoteDevice(deviceAddress)

        var gatt: BluetoothGatt? = null

        val callback = object : BluetoothGattCallback() {
            override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
                when (newState) {
                    BluetoothProfile.STATE_CONNECTED -> g.discoverServices()
                    BluetoothProfile.STATE_DISCONNECTED -> close(IOException("Conexão BLE perdida."))
                }
            }

            override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
                val characteristic = g.getService(BleContract.SERVICE_UUID)
                    ?.getCharacteristic(BleContract.ANGLE_CHARACTERISTIC_UUID)
                if (characteristic == null) {
                    close(IOException("Serviço/característica BLE do inclinômetro não encontrados."))
                    return
                }
                g.setCharacteristicNotification(characteristic, true)
                val descriptor = characteristic.getDescriptor(BleContract.CLIENT_CHARACTERISTIC_CONFIG_UUID)
                if (descriptor != null) {
                    @Suppress("DEPRECATION")
                    descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    @Suppress("DEPRECATION")
                    g.writeDescriptor(descriptor)
                }
            }

            @Suppress("DEPRECATION")
            override fun onCharacteristicChanged(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
                val raw = characteristic.value ?: return
                emitAngleFromBytes(raw)
            }

            private fun emitAngleFromBytes(raw: ByteArray) {
                if (raw.size < 2) return
                val rawValue = (raw[0].toInt() and 0xFF) or ((raw[1].toInt() and 0xFF) shl 8)
                val angle = rawValue / BleContract.ANGLE_SCALE
                trySend(AngleReading(angleDeg = angle, timestamp = System.currentTimeMillis()))
            }
        }

        gatt = device.connectGatt(context, false, callback)

        awaitClose {
            gatt?.disconnect()
            gatt?.close()
        }
    }
}
