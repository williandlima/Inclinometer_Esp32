#!/usr/bin/env bash
# Testes do firmware e do app SEM hardware: compila o código REAL do firmware
# (firmware/src) no computador, contra um MPU6050 e uma lib BLE simulados
# (mock/), e dirige a captura de vibração com o código REAL do app Python.
#   pan_sim         -> pan com mudanças de posição da placa e bias de fábrica
#   e2e_vibration   -> characteristics BLE registrados + Modo Vibração 500 Hz/10 s
#                      ponta a ponta, com 0%, 5% e 30% de pacotes perdidos
# O mock BLE reproduz a contabilidade de handles GATT do Bluedroid
# (default de 15 por serviço). Requer g++, python3 e numpy.
set -euo pipefail
cd "$(dirname "$0")"
SRC=../firmware/src
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
FLAGS="-std=gnu++17 -O2 -Wall -Wextra -Wno-unused-parameter -Imock -I$SRC"
g++ $FLAGS pan_sim.cpp $SRC/PanSensor.cpp $SRC/PeakHold.cpp -o "$OUT/pan_sim"
g++ $FLAGS fw_sim.cpp $SRC/main.cpp $SRC/BleServer.cpp $SRC/VibrationCapture.cpp \
    $SRC/AngleSensor.cpp $SRC/PanSensor.cpp $SRC/PeakHold.cpp $SRC/ModbusSlave.cpp -o "$OUT/fw_sim"
"$OUT/pan_sim"
echo
python3 e2e_vibration.py "$OUT/fw_sim"
