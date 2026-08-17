package com.williandlima.inclinometro.datasource

import android.annotation.SuppressLint
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.ParcelUuid
import java.io.IOException
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow

/**
 * Varredura de dispositivos BLE próximos, filtrada pelo [BleContract.SERVICE_UUID]
 * (o mesmo que o firmware anuncia em `BleServer::begin()`), para não listar
 * outros dispositivos Bluetooth do ambiente — equivalente ao botão
 * "Escanear" do app desktop (`python-app/data_source/ble_source.py`,
 * `scan_devices()`), mas usando a API nativa `BluetoothLeScanner` do Android
 * em vez do `bleak`.
 */
object BleScanner {
    data class Found(val address: String, val name: String)

    @SuppressLint("MissingPermission")
    fun scan(context: Context): Flow<Found> = callbackFlow {
        val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        val adapter = bluetoothManager.adapter
            ?: run {
                close(IOException("Bluetooth não disponível neste dispositivo."))
                return@callbackFlow
            }
        if (!adapter.isEnabled) {
            close(IOException("Bluetooth está desligado. Ative-o e tente novamente."))
            return@callbackFlow
        }
        val scanner = adapter.bluetoothLeScanner
            ?: run {
                close(IOException("Scanner BLE não disponível neste dispositivo."))
                return@callbackFlow
            }

        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val name = result.scanRecord?.deviceName ?: result.device.name ?: "(sem nome)"
                trySend(Found(result.device.address, name))
            }

            override fun onScanFailed(errorCode: Int) {
                close(IOException("Falha ao escanear BLE (código $errorCode)."))
            }
        }

        val filters = listOf(ScanFilter.Builder().setServiceUuid(ParcelUuid(BleContract.SERVICE_UUID)).build())
        val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
        scanner.startScan(filters, settings, callback)

        awaitClose { scanner.stopScan(callback) }
    }
}
