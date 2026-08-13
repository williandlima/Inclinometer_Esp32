# Firmware — Inclinômetro ESP32

Firmware do ESP32 que expõe o ângulo do MPU6050 tanto por **RS485/Modbus
RTU** quanto por **Bluetooth LE**, simultaneamente, seguindo os contratos já
assumidos e documentados nos dois apps:

- `python-app/data_source/modbus_source.py` (RS485)
- `python-app/data_source/ble_source.py` (BLE)
- `android-app/app/.../datasource/BleContract.kt` (BLE)

## Estrutura

```
firmware/
  platformio.ini
  src/
    main.cpp             setup()/loop(), instancia e conecta os módulos abaixo
    Config.h              pinagem + constantes de protocolo (Modbus/BLE)
    Mpu6050.h/.cpp         driver I2C mínimo do MPU6050 (sem lib externa)
    AngleSensor.h/.cpp     ângulo por atan2 + calibração (offset)
    VibrationCapture.h/.cpp  motor de captura em alta taxa, compartilhado
                             pelos dois transportes
    ModbusSlave.h/.cpp    escravo Modbus RTU sobre RS485
    BleServer.h/.cpp      servidor BLE (GATT)
```

## ⚠️ Pinagem — AJUSTAR conforme o projeto elétrico

O projeto elétrico (pinagem definitiva, escolha do conversor RS485, etc.) é
responsabilidade separada, ainda em definição. Os pinos usados aqui
(`firmware/src/Config.h`) são **placeholders** com valores comuns de dev
kits ESP32:

| Sinal | Pino (placeholder) |
|---|---|
| I2C SDA (MPU6050) | GPIO 21 |
| I2C SCL (MPU6050) | GPIO 22 |
| RS485 RX (UART2) | GPIO 16 |
| RS485 TX (UART2) | GPIO 17 |
| RS485 DE/RE (direção) | GPIO 4 |

Ajuste essas constantes em `Config.h` quando a pinagem definitiva existir.

Da mesma forma, a fórmula do ângulo em `AngleSensor.cpp` (`atan2(ay, az)`)
assume uma orientação de montagem do MPU6050 que **ainda não foi
confirmada** — pode precisar trocar os eixos/sinais usados conforme a
orientação real do sensor no pan-tilt.

## Contrato implementado

### RS485 / Modbus RTU (escravo, ID configurável em `Config.h`, padrão 1)

| Registrador | Tipo | Função |
|---|---|---|
| Input reg. 0 | leitura | Ângulo atual * 100 (uint16) |
| Coil 0 | escrita | `true` → calibra (zera o eixo de tilt) |
| Coil 1 | escrita | `true` → inicia captura de vibração |
| Holding reg. 10 | escrita | Duração da captura (s) |
| Holding reg. 11 | escrita | Taxa de amostragem (Hz) |
| Input reg. 20-22 | leitura | Status / progresso (%) / total de amostras da captura |
| Holding reg. 30 | escrita | Cursor (índice inicial do bloco a ler) |
| Input reg. 31-62 | leitura | Bloco de até 32 amostras (int16, ângulo relativo * 100) |

### BLE (serviço `6e6e0001-...`)

| Characteristic | Propriedade | Função |
|---|---|---|
| `6e6e0002-...` (ângulo) | read/notify | Ângulo atual * 100 (uint16 LE), a cada ~200ms |
| `6e6e0003-...` (calibrar) | write | Byte `0x01` → calibra |
| `6e6e0004-...` (config vibração) | write | 4 bytes LE: duração(s) + taxa(Hz) → inicia captura |
| `6e6e0005-...` (status vibração) | notify | status/progresso/total de amostras |
| `6e6e0006-...` (dados vibração) | notify | Amostras em pacotes (índice + até 8 amostras int16 LE) |

Detalhes byte a byte de cada mensagem estão comentados no topo de
`ModbusSlave.cpp`/`BleServer.cpp` e nos módulos Python/Kotlin equivalentes.

## Build

Projeto [PlatformIO](https://platformio.org/), ambiente `esp32dev`
(framework Arduino, sem bibliotecas externas — só o que já vem com o core
`espressif32`: `Wire`, UART, e a lib BLE clássica `BLEDevice`).

```bash
cd firmware
pio run              # compila
pio run -t upload    # compila e grava no ESP32 conectado por USB
pio device monitor    # abre o monitor serial (115200 baud)
```

**Não foi possível compilar neste ambiente de desenvolvimento**: o
`pio run` precisa baixar o toolchain/plataforma `espressif32` da internet
na primeira vez, e o acesso de rede deste sandbox bloqueia esse download
(mesma limitação de rede já encontrada antes neste projeto, ex: para
baixar a logo da Avibras Aeroco). O código foi revisado manualmente com
cuidado (tipos, includes, formato de cada mensagem confrontado byte a byte
com os módulos Python/Kotlin), mas **precisa ser compilado e testado em
hardware real** antes de considerar o firmware pronto — nem a lógica de
sensor, nem os protocolos RS485/BLE foram validados contra hardware físico.

## Limitações conhecidas / próximos passos

- Buffer de captura de vibração limitado a `VIBRATION_MAX_SAMPLES = 6000`
  amostras (~12KB de RAM) — captura pedida além disso é truncada
  silenciosamente (menos amostras que o solicitado, mas sem erro).
- Calibração não é persistida entre reboots (offset fica só em RAM).
- Framing Modbus RTU usa um timeout fixo simplificado (5ms de silêncio)
  para detectar fim de frame, em vez do cálculo exato de 3.5 caracteres
  do padrão — funciona bem nas baudrates baixas típicas de RS485, mas
  pode precisar de ajuste fino em baudrates mais altas.
- Pinagem e orientação do sensor são placeholders, como descrito acima.
