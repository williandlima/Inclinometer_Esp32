#!/usr/bin/env bash
# Testes do firmware e do app SEM hardware: compila o código REAL do firmware
# (firmware/src) no computador, contra um MPU6050 e uma lib BLE simulados
# (mock/), e dirige a captura de vibração com o código REAL do app Python.
#   pan_sim         -> pan com mudanças de posição da placa e bias de fábrica
#   soak_sim        -> firmware inteiro (com o driver I2C real) por 30 min
#                      simulados x SOAK_SEEDS sementes, contra um MPU6050
#                      emulado com falhas de hardware injetadas (ver o
#                      cabeçalho de soak_sim.cpp)
#   e2e_modbus      -> modo USB (Modbus RTU) de ponta a ponta, em tempo real:
#                      firmware real numa porta serial virtual <-> app real
#                      com o pymodbus de verdade; placa reinicia a cada
#                      abertura da porta, reset no meio, linha com ruído
#                      (~1,5 min; SKIP_MODBUS=1 pula)
#   e2e_vibration   -> characteristics BLE registrados + Modo Vibração 500 Hz/10 s
#                      ponta a ponta, com 0%, 5% e 30% de pacotes perdidos
#   exibicao_test   -> resolução da tela (0,25°/0,1° por eixo): regra de
#                      arredondamento/histerese e a janela REAL do app
#                      desktop em Qt sem tela (offscreen); com kotlinc
#                      disponível, a mesma regra do app Android
#                      (AngleDisplayTest.kt) e a igualdade entre os dois
#   relatorio_test  -> relatório PDF e a aquisição que o alimenta: rastreador
#                      de mín/máx, histórico (com migração de banco antigo),
#                      resumo da aquisição, conteúdo do PDF (pdftotext) e a
#                      aquisição com tempo programado na janela REAL (offscreen)
#   conexao_test    -> indicador de conexão da janela REAL: verde só com dados
#                      chegando da fonte em execução (sem dados, erro, leitura
#                      atrasada após Parar, fonte antiga após reiniciar)
# O mock BLE reproduz a contabilidade de handles GATT do Bluedroid
# (default de 15 por serviço). Requer g++, python3, numpy e as dependências
# do app (pip install -r python-app/requirements.txt: pymodbus, pyserial).
set -euo pipefail
cd "$(dirname "$0")"
SRC=../firmware/src
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
FLAGS="-std=gnu++17 -O2 -Wall -Wextra -Wno-unused-parameter -Imock -I$SRC"
g++ $FLAGS pan_sim.cpp $SRC/PanSensor.cpp $SRC/PeakHold.cpp -o "$OUT/pan_sim"
g++ $FLAGS fw_sim.cpp $SRC/main.cpp $SRC/BleServer.cpp $SRC/VibrationCapture.cpp \
    $SRC/AngleSensor.cpp $SRC/PanSensor.cpp $SRC/PeakHold.cpp $SRC/ModbusSlave.cpp -o "$OUT/fw_sim"
g++ $FLAGS soak_sim.cpp $SRC/main.cpp $SRC/Mpu6050.cpp $SRC/BleServer.cpp $SRC/VibrationCapture.cpp \
    $SRC/AngleSensor.cpp $SRC/PanSensor.cpp $SRC/PeakHold.cpp $SRC/ModbusSlave.cpp -o "$OUT/soak_sim"
"$OUT/pan_sim"
echo
"$OUT/soak_sim" "${SOAK_SEEDS:-20}"
echo
python3 e2e_vibration.py "$OUT/fw_sim"
echo
python3 exibicao_test.py 2>/dev/null
echo
python3 relatorio_test.py 2>/dev/null
echo
python3 conexao_test.py 2>/dev/null
echo
python3 ../python-app/tools/calibra_tilt.py --autoteste | tail -1
python3 ../python-app/tools/calibra_pan.py --autoteste | tail -1
python3 ../python-app/tools/allan_pan.py --autoteste | tail -1
# Mesma regra no app Android (AngleDisplay.kt), com kotlinc puro, se houver
# (KOTLINC=/caminho/kotlinc ou kotlinc no PATH; o SDK do Android não é preciso).
KOTLINC=${KOTLINC:-$(command -v kotlinc || true)}
if [ -n "$KOTLINC" ]; then
    echo
    "$KOTLINC" ../android-app/app/src/main/java/com/williandlima/inclinometro/ui/AngleDisplay.kt AngleDisplayTest.kt \
        -include-runtime -d "$OUT/angle_display_test.jar" 2>/dev/null
    java -Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8 -jar "$OUT/angle_display_test.jar"
fi
if [ -z "${SKIP_MODBUS:-}" ]; then
    g++ $FLAGS modbus_sim.cpp $SRC/main.cpp $SRC/BleServer.cpp $SRC/VibrationCapture.cpp \
        $SRC/AngleSensor.cpp $SRC/PanSensor.cpp $SRC/PeakHold.cpp $SRC/ModbusSlave.cpp -o "$OUT/modbus_sim"
    echo
    python3 e2e_modbus.py "$OUT/modbus_sim" 2>/dev/null
fi
