# Firmware — Inclinômetro ESP32

**Versão atual: `1.0.1`** (`firmware/src/Config.h`, `FIRMWARE_VERSION`) —
exposta em runtime tanto por Modbus (input register `REG_FIRMWARE_VERSION`)
quanto por BLE (characteristic `CHAR_FIRMWARE_VERSION_UUID`), como inteiro
`major*10000 + minor*100 + patch` (`FIRMWARE_VERSION_CODE`; ex: `1.0.0` →
`10000`). Bump manual em `Config.h` a cada mudança relevante de contrato ou
comportamento — sem isso os apps não têm como saber qual versão do firmware
estão falando.

Firmware do ESP32 que expõe o ângulo do MPU6050 tanto por **Modbus RTU via
cabo USB direto** quanto por **Bluetooth LE**, simultaneamente, seguindo os
contratos já assumidos e documentados nos dois apps:

- `python-app/data_source/modbus_source.py` (Modbus RTU / USB)
- `python-app/data_source/ble_source.py` (BLE)
- `android-app/app/.../datasource/BleContract.kt` (BLE)

A comunicação com o PC usa a porta serial USB nativa do ESP32 (a mesma já
usada para gravar o firmware) — **não usa RS485**. Essa decisão foi tomada
porque a distância até o painel de controle (~7m, no mastro do pan-tilt)
excede o alcance confiável de USB simples (~5m), mas um **cabo de extensão
USB ativo** (com amplificador de sinal embutido, vendido pronto para
10-20m) resolve isso sem precisar de RS485/transceptor/terminação de
barramento.

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
    ModbusSlave.h/.cpp    escravo Modbus RTU sobre a porta serial USB (UART0)
    BleServer.h/.cpp      servidor BLE (GATT)
```

## Pinagem (ESP32 DevKit clássico / WROOM-32)

Hardware confirmado: placa **ESP32 DevKit clássico (WROOM-32)**, com chip
conversor USB-serial **CH9102X** (WCH) — mapeamento definido, refletido em
`firmware/src/Config.h`. Como a comunicação com o PC vai pela porta USB
nativa do ESP32, o único hardware extra é o MPU6050:

| Sinal | Pino ESP32 | Vai para | Observação |
|---|---|---|---|
| SDA | GPIO 21 | SDA do MPU6050 | Padrão I2C do ESP32 |
| SCL | GPIO 22 | SCL do MPU6050 | Padrão I2C do ESP32 |
| — | 3.3V | VCC do MPU6050 | Não usar 5V (linhas I2C ficam em 5V e podem danificar o ESP32) |
| — | GND | GND do MPU6050 | |
| — | GND | AD0 do MPU6050 | Fixa endereço I2C em `0x68` (o que `Mpu6050.h` assume) |

Se o hardware definitivo usar uma variante diferente do ESP32 (S3, C3,
etc.), os pinos podem precisar de ajuste — essas variantes têm GPIOs
restritos diferentes do WROOM-32 clássico assumido aqui.

A fórmula do ângulo em `AngleSensor.cpp` (`atan2(ay, az)`) assume uma
orientação de montagem do MPU6050 já **recomendada, mas ainda não
confirmada fisicamente**: eixo X do sensor alinhado ao eixo mecânico de
giro do pan-tilt, com a rotação de 0-120° acontecendo no plano Y-Z (os
dois eixos usados no `atan2`). Essa combinação mantém a sensibilidade da
leitura quase constante em toda a faixa — sem a zona de baixa sensibilidade
que um único eixo teria perto de 90°, o que é essencial para o **Modo
Vibração** detectar variações de frações de grau em torno do zero
calibrado. Ver "Orientação de montagem do sensor" em `docs/pinout.md`
para o detalhamento e o teste de bancada de confirmação.

## Contrato implementado

### Modbus RTU via USB (escravo, ID configurável em `Config.h`, padrão 1)

Trafega pela mesma porta serial que aparece no PC como uma porta COM/tty
normal quando o ESP32 é conectado por USB — o app desktop (`python-app`)
já espera exatamente isso (não faz distinção entre "porta serial real" e
"porta serial via USB do ESP32", já que ambas são portas seriais comuns do
ponto de vista do `pyserial`).

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
| Input reg. 40 | leitura | Versão do firmware (`FIRMWARE_VERSION_CODE`, ver acima) |

### BLE (serviço `6e6e0001-...`)

| Characteristic | Propriedade | Função |
|---|---|---|
| `6e6e0002-...` (ângulo) | read/notify | Ângulo atual * 100 (uint16 LE), a cada ~200ms |
| `6e6e0003-...` (calibrar) | write | Byte `0x01` → calibra |
| `6e6e0004-...` (config vibração) | write | 4 bytes LE: duração(s) + taxa(Hz) → inicia captura |
| `6e6e0005-...` (status vibração) | notify | status/progresso/total de amostras |
| `6e6e0006-...` (dados vibração) | notify | Amostras em pacotes (índice + até 8 amostras int16 LE) |
| `6e6e0007-...` (versão firmware) | read | `FIRMWARE_VERSION_CODE` (uint16 LE, ver acima) — valor fixo, sem notify |

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
sensor, nem os protocolos Modbus RTU (via USB)/BLE foram validados contra
hardware físico.

## Limitações conhecidas / próximos passos

- **[1.0.1]** `BleServer::updateVibrationNotify()` notificava o status
  "pronto" da captura de vibração *antes* de terminar de transmitir todas
  as amostras pela characteristic de dados, e chamava `notify()` sem
  nenhum controle de taxa (a cada iteração do `loop()`) — o app Python
  (`ble_source.py`) libera o resultado assim que recebe o "pronto", então
  isso causava dados truncados/perdidos no Modo Vibração via BLE, além do
  risco de sobrecarregar a fila de notificação do BLE numa captura longa.
  Corrigido: agora os dados são enviados primeiro (com um intervalo mínimo
  de `BLE_VIBRATION_CHUNK_INTERVAL_MS` entre pacotes) e o "pronto" só é
  notificado depois que o último bloco foi enviado; o status/progresso
  durante a captura também passou a ser limitado por
  `BLE_VIBRATION_STATUS_NOTIFY_INTERVAL_MS`. Ainda não validado contra
  hardware real (só revisão de código) — atenção especial a isso ao testar
  o Modo Vibração via BLE.
- Buffer de captura de vibração limitado a `VIBRATION_MAX_SAMPLES = 6000`
  amostras (~12KB de RAM) — captura pedida além disso é truncada
  silenciosamente (menos amostras que o solicitado, mas sem erro).
- Calibração não é persistida entre reboots (offset fica só em RAM).
- Framing Modbus RTU usa um timeout fixo simplificado (5ms de silêncio)
  para detectar fim de frame, em vez do cálculo exato de 3.5 caracteres
  do padrão — funciona bem na baudrate usada no projeto (9600), mas pode
  precisar de ajuste fino em baudrates mais altas.
- A UART0 (porta USB) fica dedicada ao protocolo Modbus RTU — não há canal
  de log/debug separado disponível hoje (ver comentário em `main.cpp`).
- Orientação de montagem do sensor tem recomendação definida (eixo X no
  giro, plano Y-Z), mas confirmação física em bancada ainda pendente,
  como descrito acima (a pinagem em si já está definida).
- Para o cabo até o painel de controle (~7m), use um **cabo de extensão
  USB ativo** — USB simples sem amplificação só é confiável até uns 5m.
