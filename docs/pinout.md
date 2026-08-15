# Pinout — Inclinômetro ESP32

Mapeamento completo de pinos do ESP32, para o hardware definido até aqui:
**MPU6050 via I2C** (sensor) + **comunicação com o PC via cabo USB direto**
(sem RS485 — decisão tomada explicitamente, ver `firmware/README.md`).
Placa assumida: **ESP32 DevKit clássico (WROOM-32)**.

## I2C — MPU6050 (acelerômetro)

| Sinal | Pino ESP32 | Vai para | Observação |
|---|---|---|---|
| SDA | **GPIO 21** | SDA do MPU6050 | Pino I2C padrão do ESP32 (`Wire.begin()` sem argumentos) |
| SCL | **GPIO 22** | SCL do MPU6050 | Pino I2C padrão do ESP32 |
| Alimentação | **3.3V** | VCC do MPU6050 | **Não usar 5V** — a maioria dos módulos GY-521 tem pull-up de SDA/SCL para o VCC; em 5V, as linhas I2C sobem a 5V e podem danificar as entradas do ESP32 |
| Terra | **GND** | GND do MPU6050 | Referência comum |
| Endereço | **GND** | AD0 do MPU6050 | Fixa o endereço I2C em `0x68`, o que o driver (`firmware/src/Mpu6050.h`) assume |
| Interrupção | *(não conectado)* | INT do MPU6050 | Não usado hoje (leitura por polling); ver "Próximos passos" |

## USB — comunicação com o PC

Não usa nenhum GPIO adicional: a comunicação Modbus RTU trafega pela **porta
USB nativa do ESP32** (o mesmo cabo/porta usado para gravar o firmware),
internamente ligada à UART0 do chip.

| Item | Valor | Observação |
|---|---|---|
| Cabo | USB padrão (A-MicroUSB ou A-C, conforme a placa) | Sem hardware adicional |
| Alcance sem amplificação | ~5m | Limite do USB 2.0 padrão |
| Alcance necessário no projeto | ~7m (mastro do pan-tilt) | **Excede o limite padrão** |
| Solução | **Cabo de extensão USB ativo** (10-20m, com amplificador embutido) | Vendido pronto, sem precisar de hub/alimentação extra no meio do caminho |

## Bluetooth LE

Não usa GPIO — o rádio BLE é interno ao módulo ESP32 (antena embutida na
maioria das placas DevKit). Nenhuma consideração de fiação adicional.

## Referência completa de pinos do ESP32 (WROOM-32)

Nomes dos pinos do próprio microcontrolador (GPIO), agrupados pelo que
determina se dá pra usar cada um livremente — útil para escolher onde
ligar algo novo no futuro.

### Em uso neste projeto

| Pino (GPIO) | Nome/alias | Uso |
|---|---|---|
| **GPIO21** | SDA | I2C — dados do MPU6050 |
| **GPIO22** | SCL | I2C — clock do MPU6050 |
| **GPIO1** | TX0 | UART0 — porta USB (Modbus RTU), TX |
| **GPIO3** | RX0 | UART0 — porta USB (Modbus RTU), RX |

### Livres para uso geral

| Pino (GPIO) | Observação |
|---|---|
| **GPIO4** | Livre — antes era o controle de direção do RS485 (removido) |
| **GPIO16** | Livre — antes era RX do RS485/UART2 (removido) |
| **GPIO17** | Livre — antes era TX do RS485/UART2 (removido) |
| **GPIO13**, **GPIO14**, **GPIO18**, **GPIO19**, **GPIO23** | Uso geral, sem restrição conhecida |
| **GPIO25**, **GPIO26**, **GPIO27** | Uso geral; GPIO25/26 também servem como saída analógica (DAC) |
| **GPIO32**, **GPIO33** | Uso geral; também entrada analógica (ADC1) |

### Somente entrada (sem pull-up/down interno)

| Pino (GPIO) | Observação |
|---|---|
| **GPIO34**, **GPIO35** | Só leitura (ex: sensor analógico, botão com pull-up externo) |
| **GPIO36** (alias **VP**) | Só leitura |
| **GPIO39** (alias **VN**) | Só leitura |

### Cuidado — pinos de boot/strapping

Definem o modo de boot do ESP32 ; usar como saída genérica pode impedir o
chip de iniciar se o nível ficar "errado" no momento do reset.

| Pino (GPIO) | Observação |
|---|---|
| **GPIO0** | Botão BOOT em muitas placas; deve ficar HIGH/flutuante no boot normal |
| **GPIO2** | Ligado ao LED onboard em muitas placas; deve ficar LOW/flutuante em certos modos de boot |
| **GPIO5** | Seleciona modo de boot SPI |
| **GPIO12** | Seleciona a tensão da flash (3.3V/1.8V) — cuidado extra, pode até impedir o boot |
| **GPIO15** | Controla verbosidade do log de boot |

### Nunca usar — reservados para a flash interna

**GPIO6 a GPIO11** — ligados internamente à memória flash do módulo. Usar
qualquer um deles trava o ESP32 (não consegue nem iniciar).

### Alimentação e reset (não são GPIO)

| Pino | Função |
|---|---|
| **3V3** | Saída 3.3V regulada (alimenta o MPU6050 neste projeto) |
| **GND** | Terra (vários pinos GND na placa, qualquer um serve) |
| **5V** / **VIN** | Entrada de alimentação externa (5V, antes do regulador da placa) |
| **EN** | Reset/enable do chip (botão RESET em muitas placas) |

## Notas

- **Orientação de montagem do sensor**: a fórmula do ângulo em
  `firmware/src/AngleSensor.cpp` (`atan2(ay, az)`) assume uma orientação
  específica dos eixos do MPU6050, que **ainda não foi confirmada** contra
  a montagem real no pan-tilt — pode precisar ajustar os eixos/sinais
  usados quando o sensor for montado fisicamente.
- **Variante de placa**: esta pinagem assume um ESP32 DevKit clássico
  (WROOM-32). Variantes diferentes (S3, C3, etc.) têm GPIOs restritos
  diferentes e podem precisar de ajuste.
- Fonte da verdade no código: `firmware/src/Config.h` (constantes de pino)
  e `firmware/README.md` (contexto e decisões).
