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

## Pinagem (ESP32 DevKit clássico / WROOM-32)

Mapeamento definido, refletido em `firmware/src/Config.h`:

| Sinal | Pino ESP32 | Vai para | Observação |
|---|---|---|---|
| **I2C — MPU6050** | | | |
| SDA | GPIO 21 | SDA do MPU6050 | Padrão I2C do ESP32 |
| SCL | GPIO 22 | SCL do MPU6050 | Padrão I2C do ESP32 |
| — | 3.3V | VCC do MPU6050 | Não usar 5V — ver nota de nível lógico abaixo |
| — | GND | GND do MPU6050 | |
| — | GND | AD0 do MPU6050 | Fixa endereço I2C em `0x68` (o que `Mpu6050.h` assume) |
| **RS485 — via módulo transceptor** | | | |
| TX (UART2) | GPIO 17 | **DI** do módulo RS485 | Saída do ESP32 → entrada do transceptor |
| RX (UART2) | GPIO 16 | **RO** do módulo RS485 | Saída do transceptor → entrada do ESP32 |
| Direção | GPIO 4 | **DE + RE̅** (ligados juntos) | Um único pino: HIGH = transmite, LOW = recebe (já implementado em `ModbusSlave.cpp`) |
| — | 3.3V (ver nota) | VCC do módulo RS485 | Ver nota de nível lógico abaixo |
| — | GND | GND do módulo RS485 | |
| — | — | A / B do módulo | Vão para o barramento RS485 (par trançado), não para o ESP32 |

**Notas de hardware:**
- **Nível lógico do módulo RS485**: usar um transceptor nativo 3.3V (ex:
  MAX3485) para não precisar de level shifter entre ele e o ESP32 — módulos
  MAX485 clássicos de 5V colocariam 5V nas linhas `DI`/`RO`/`DE`/`RE`, o que
  pode danificar os pinos do ESP32.
- **Terminação do barramento**: se o inclinômetro for a ponta do cabo (não
  no meio de uma linha com vários equipamentos), colocar um resistor de
  **120Ω entre A e B** no conector, para terminar a linha corretamente —
  mais relevante com o cabo mais longo até o painel de controle (mastro a
  7m).
- Estes dois periféricos (I2C e RS485) não têm conflito de pinos entre si
  nem com os pinos de *strapping* de boot do ESP32.

Se o hardware definitivo usar uma variante diferente do ESP32 (S3, C3,
etc.), os pinos podem precisar de ajuste — essas variantes têm GPIOs
restritos diferentes do WROOM-32 clássico assumido aqui.

A fórmula do ângulo em `AngleSensor.cpp` (`atan2(ay, az)`) ainda assume uma
orientação de montagem do MPU6050 **não confirmada** — pode precisar
trocar os eixos/sinais usados conforme a orientação real do sensor no
pan-tilt.

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
- Orientação de montagem do sensor ainda não confirmada, como descrito
  acima (a pinagem em si já está definida).
