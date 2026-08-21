#pragma once

#include <Arduino.h>

// ============================================================================
// Configuração de hardware — pinagem definida para ESP32 DevKit clássico
// (WROOM-32). Ver firmware/README.md para o mapeamento completo.
//
// Comunicação com o PC é via cabo USB direto (porta serial nativa do ESP32,
// a mesma usada para gravar o firmware) — não usa mais RS485, então não há
// pinos nem módulo transceptor adicionais para essa parte.
// ============================================================================

// I2C do MPU6050 (padrão do ESP32 DevKit). AD0 do sensor deve ir para GND
// (endereço 0x68, o que o driver em Mpu6050.h assume).
constexpr int PIN_I2C_SDA = 21;
constexpr int PIN_I2C_SCL = 22;

// ============================================================================
// Versão do firmware — bump manual a cada mudança relevante de contrato ou
// comportamento. FIRMWARE_VERSION_CODE codifica a mesma versão como inteiro
// (major*10000 + minor*100 + patch) para caber num único registrador
// Modbus/characteristic BLE de 16 bits (ex: "1.0.0" -> 10000).
// ============================================================================
constexpr char FIRMWARE_VERSION[] = "1.3.0";
constexpr uint16_t FIRMWARE_VERSION_CODE = 10300;

// ============================================================================
// Parâmetros Modbus RTU — devem bater com python-app/data_source/modbus_source.py
// ============================================================================
constexpr uint8_t MODBUS_SLAVE_ID = 1;
constexpr uint32_t MODBUS_BAUDRATE = 9600;

constexpr uint16_t REG_ANGLE_INPUT = 0;       // input register: ângulo de tilt * ANGLE_SCALE (int16 com sinal, faixa -60~+60°)
constexpr uint16_t REG_PAN_INPUT = 1;         // input register: ângulo de pan * ANGLE_SCALE (int16 com sinal, faixa PAN_MIN_DEG~PAN_MAX_DEG)
constexpr uint16_t COIL_CALIBRATE = 0;        // coil: write true -> zera os dois eixos (tilt e pan)
constexpr uint16_t COIL_VIBRATION_START = 1;  // coil: write true -> inicia captura de vibração
constexpr uint16_t REG_FIRMWARE_VERSION = 40; // input register: FIRMWARE_VERSION_CODE (somente leitura)

constexpr uint16_t REG_VIBRATION_DURATION = 10;  // holding register: duração da captura (s)
constexpr uint16_t REG_VIBRATION_RATE = 11;      // holding register: taxa de amostragem (Hz)

constexpr uint16_t REG_VIBRATION_STATUS = 20;       // input register: 0=ocioso,1=capturando,2=pronto,3=erro
constexpr uint16_t REG_VIBRATION_PROGRESS = 21;     // input register: percentual 0-100
constexpr uint16_t REG_VIBRATION_SAMPLE_COUNT = 22; // input register: total de amostras (quando pronto)

constexpr uint16_t REG_VIBRATION_CURSOR = 30;       // holding register: índice inicial do bloco a ler (vale para os dois eixos)
constexpr uint16_t REG_VIBRATION_BLOCK_START = 31;  // input register: início do bloco de amostras de TILT
constexpr uint16_t VIBRATION_BLOCK_SIZE = 32;       // amostras por bloco de leitura
constexpr uint16_t REG_VIBRATION_PAN_BLOCK_START = 70;  // input register: início do bloco de amostras de PAN (taxa * PAN_RATE_SCALE)

// ============================================================================
// Parâmetros BLE — devem bater com python-app/data_source/ble_source.py e
// android-app/.../datasource/BleContract.kt
// ============================================================================
constexpr char BLE_DEVICE_NAME[] = "Inclinometro-ESP32";
constexpr char SERVICE_UUID[] = "6e6e0001-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr char CHAR_ANGLE_UUID[] = "6e6e0002-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr char CHAR_CALIBRATE_UUID[] = "6e6e0003-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr char CHAR_VIBRATION_CONFIG_UUID[] = "6e6e0004-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr char CHAR_VIBRATION_STATUS_UUID[] = "6e6e0005-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr char CHAR_VIBRATION_DATA_UUID[] = "6e6e0006-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr char CHAR_FIRMWARE_VERSION_UUID[] = "6e6e0007-3c17-4a2e-8f4b-1a2b3c4d5e6f";
// Pan em characteristic própria, e não anexado à de ângulo, de propósito: os
// apps já instalados esperam exatamente 2 bytes em CHAR_ANGLE_UUID: estender
// aquela mensagem quebraria quem não foi atualizado. Assim a mudança é
// puramente aditiva — quem não conhece a characteristic nova simplesmente a
// ignora e continua funcionando.
constexpr char CHAR_PAN_UUID[] = "6e6e0008-3c17-4a2e-8f4b-1a2b3c4d5e6f";
// Dados de vibração do eixo de pan, em characteristic própria e com o mesmo
// formato de pacote da de tilt (índice + amostras int16 LE) — de novo para a
// mudança ser aditiva: um app que não a conhece continua recebendo a captura
// de tilt exatamente como antes.
constexpr char CHAR_VIBRATION_PAN_DATA_UUID[] = "6e6e0009-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr uint32_t BLE_NOTIFY_INTERVAL_MS = 200;  // taxa de notificação do ângulo em modo contínuo
constexpr uint32_t BLE_VIBRATION_STATUS_NOTIFY_INTERVAL_MS = 300;  // limita notify() de status/progresso durante a captura
constexpr uint32_t BLE_VIBRATION_CHUNK_INTERVAL_MS = 20;  // intervalo entre pacotes de dados da captura (evita congestionar o BLE)

// ============================================================================
// Compartilhados entre os dois transportes
// ============================================================================
constexpr float ANGLE_SCALE = 100.0f;  // valor no protocolo = ângulo * ANGLE_SCALE
constexpr float ANGLE_MIN_DEG = -60.0f;
constexpr float ANGLE_MAX_DEG = 60.0f;

// ============================================================================
// Filtro da leitura contínua (só do ângulo "normal" — o Modo Vibração NÃO
// passa por aqui, de propósito).
//
// Mesmo com o filtro interno do MPU6050 ligado (ver Mpu6050.h), uma amostra
// isolada do acelerômetro ainda carrega ruído suficiente para a leitura
// tremular nos centésimos de grau. A leitura de ângulo do dia a dia precisa
// ser estável; já a captura de vibração precisa justamente do sinal cru, com
// toda a sensibilidade — por isso os dois caminhos são separados em
// AngleSensor (readAngleDeg filtrado vs readRelativeAngleDeg instantâneo).
//
// Média móvel exponencial alimentada a cada ANGLE_SAMPLE_INTERVAL_MS. Com
// 10ms de amostragem e 0.5s de constante de tempo, o ruído branco cai cerca
// de 10x, com ~0.5s para a leitura acompanhar um movimento real.
// ============================================================================
constexpr uint32_t ANGLE_SAMPLE_INTERVAL_MS = 10;     // 100Hz de amostragem interna
constexpr float ANGLE_FILTER_TIME_CONSTANT_S = 0.5f;  // maior = mais estável, porém mais lento
constexpr uint16_t VIBRATION_MAX_SAMPLES = 6000;  // limite de memória do buffer de captura

// ============================================================================
// Eixo de azimute (pan) — medido pelo GIROSCÓPIO do MPU6050 (ver PanSensor.h).
//
// O acelerômetro é fisicamente cego a rotação em torno da vertical, mas o
// giroscópio não é: integrando a velocidade angular sai o ângulo de pan
// relativo ao zero calibrado. O que torna isso confiável aqui é o padrão de
// uso — o eixo fica parado a maior parte do tempo e se move em rajadas de
// poucos segundos — combinado com ZUPT (re-estimar o bias do giro sempre que
// está parado). Sem ZUPT, o bias viraria uma rampa de graus por minuto.
// ============================================================================

// Faixa mecânica do pan. PLACEHOLDER: o curso é limitado (sem volta
// completa), mas o valor exato depende da mecânica final — ajustar aqui
// quando estiver definido, como já foi feito quando a faixa do tilt mudou de
// 0-120° para -60~+60°. Só limita o valor reportado; o integrador interno não
// é clampado, então voltar para dentro da faixa recupera a leitura correta.
constexpr float PAN_MIN_DEG = -90.0f;
constexpr float PAN_MAX_DEG = 90.0f;

// Janela de avaliação do ZUPT. Também define o menor movimento preservado:
// um deslocamento total abaixo de PAN_ZUPT_RATE_THRESHOLD_DPS * janela
// (1.0°/s * 1.0s = 1°) é interpretado como ruído e cancelado. Diminuir a
// janela melhora esse piso, mas piora a média usada para estimar o bias.
constexpr uint32_t PAN_ZUPT_WINDOW_MS = 1000;

// Limiar de "parado", aplicado à MÉDIA da janela (não ao pico). Usar a média
// deixa o detector imune a vibração, que é de média zero: o mastro pode estar
// balançando sob vento que a janela ainda é corretamente classificada como
// parada. A separação é confortável — o motor gira a ~20-30°/s.
constexpr float PAN_ZUPT_RATE_THRESHOLD_DPS = 1.0f;

// Velocidade com que o bias persegue a média das janelas paradas. Baixo de
// propósito: um movimento real lento o suficiente para passar pelo limiar
// acima precisaria persistir por muitas janelas para ser absorvido no bias.
constexpr float PAN_ZUPT_BIAS_ALPHA = 0.1f;

// Correção do fator de escala do giroscópio (tolerância de fábrica ~+-3%).
// Este é o erro dominante depois que o ZUPT resolve o bias, e é proporcional
// ao deslocamento atual em relação ao zero — não se acumula com o tempo nem
// com o número de movimentos. Calibração de bancada: girar o eixo entre duas
// posições de separação angular conhecida e usar (ângulo real / integrado).
constexpr float PAN_SCALE_CORRECTION = 1.0f;

// Teto para o dt de uma única integração. Protege contra um loop que atrasou
// muito (ou millis() dando a volta) virar um salto grande no ângulo.
constexpr float PAN_MAX_INTEGRATION_DT_S = 0.1f;

// Escala das amostras de vibração do eixo de pan no protocolo. Diferente do
// tilt, o que trafega aqui é VELOCIDADE ANGULAR (graus/s), não ângulo — ver
// "Modo Vibração no eixo de pan" em firmware/README.md. Com escala 100 e
// int16, a faixa vai a +-327°/s, cobrindo com folga o fundo de escala de
// +-250°/s do giroscópio: nenhum movimento fisicamente possível satura.
constexpr float PAN_RATE_SCALE = 100.0f;
