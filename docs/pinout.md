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

## Pinos livres

Como o projeto não usa mais RS485, os pinos que antes eram reservados para
isso (GPIO 16, 17 e 4) estão livres para uso futuro — por exemplo, o pino
INT do MPU6050 (ver tabela acima), um LED de status, ou um botão físico de
calibração.

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
