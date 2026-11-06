"""Teste do indicador de conexão da janela principal (app desktop) — sem hardware.

O "● Conectado" verde tem de significar DADOS CHEGANDO da fonte em execução,
não "o botão Iniciar foi clicado" nem "a pilha Bluetooth acha que o link está
de pé". Cobre, com uma fonte BLE falsa controlada pelo teste (emite de uma
thread própria, como as fontes reais), na janela REAL em Qt sem tela:

  1. Iniciar sem o ESP32 responder: "◐ Conectando...", nunca verde, e a
     barra de status não diz "Conectado";
  2. primeira leitura: verde e "Conectado: ..." na barra;
  3. leituras param (ESP32 desligado, fora de alcance) sem a fonte avisar:
     sai do verde em ~2 s ("◐ Sem dados do ESP32");
  4. erro da fonte (queda detectada): vermelho; leituras voltam: verde;
  5. leitura/erro atrasados de uma fonte já parada (fila do Qt após "Parar"):
     indicador continua "○ Parado" e nada é gravado no histórico;
  6. após reiniciar com uma fonte nova, leituras da fonte antiga são
     ignoradas;
  7. modo Simulação continua mostrando "● Simulação (interna)".

Ver run.sh. Requer PyQt5 (python-app/requirements.txt).
"""

import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python-app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

import ui.main_window as mw  # noqa: E402
from data_source.base import AngleReading  # noqa: E402
from limits.history_store import HistoryStore  # noqa: E402

failures = 0
TMP = tempfile.mkdtemp(prefix="conexao_test_")


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    print(f"  {'OK    ' if ok else 'FALHOU'} {name}{': ' + detail if detail else ''}")
    if not ok:
        failures += 1


def pump(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


class FakeBle:
    """Fonte BLE falsa: o teste decide quando ela 'conecta', manda leituras,
    silencia ou reporta erro. Emite de uma thread própria, como a real."""

    instances: list["FakeBle"] = []

    def __init__(self, device_address: str = "") -> None:
        self.on_reading = None
        self.on_error = None
        self.streaming = False
        self._stop = threading.Event()
        self._thread = None
        FakeBle.instances.append(self)

    label = "Bluetooth BLE (AA:BB:CC:DD:EE:FF)"
    firmware_version = "1.6.18"
    supports_calibration = True
    supports_peak_reset = False
    supports_vibration_capture = False

    def start(self, on_reading, on_error=None) -> None:
        self.on_reading, self.on_error = on_reading, on_error
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.streaming:
                self.on_reading(AngleReading(angle_deg=1.0, timestamp=time.time(), pan_deg=2.0))
            time.sleep(0.2)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def error(self, msg: str) -> None:
        threading.Thread(target=self.on_error, args=(msg,), daemon=True).start()


mw.BleAngleSource = FakeBle
mw.HistoryStore = lambda: HistoryStore(os.path.join(TMP, "h.db"))

w = mw.MainWindow()
w._settings.mode = "ble"
w._settings.ble_address = "AA:BB:CC:DD:EE:FF"
status = lambda: w.connection_label.text()  # noqa: E731
bar = lambda: w.statusBar().currentMessage()  # noqa: E731

print("=== indicador de conexão (janela real, fonte BLE falsa) ===")
check("parado ao abrir", status() == "○ Parado", status())

w._start()
src = FakeBle.instances[-1]
pump(3.0)
check("1. ESP32 sem responder: 'Conectando', nunca verde", status() == "◐ Conectando...", status())
check("1. barra de status não diz 'Conectado'", not bar().startswith("Conectado"), bar())

src.streaming = True
pump(0.8)
check("2. primeira leitura: verde", status() == "● Conectado", status())
check("2. barra: 'Conectado: ...'", bar().startswith("Conectado: "), bar())

src.streaming = False  # some sem a fonte avisar (o caso do relato)
pump(1.0)
check("3. logo após parar de chegar dado: ainda verde (< 2 s)", status() == "● Conectado", status())
pump(2.0)
check("3. sem dados há > 2 s: sai do verde", status() == "◐ Sem dados do ESP32", status())
check("3. barra explica", "Sem leituras do ESP32" in bar(), bar())

src.error("Conexão Bluetooth perdida — verifique se o ESP32 está ligado e ao alcance.")
pump(0.5)
check("4. erro da fonte: vermelho", status() == "● Falha de conexão", status())
src.streaming = True
pump(0.8)
check("4. leituras voltam: verde de novo", status() == "● Conectado", status())
check("4. aviso de falha sai da barra", bar().startswith("Conectado: "), bar())

sid = w._history.current_session_id
w._stop()
n_antes = w._history.count_readings(sid)
# Leitura e erro que estavam na fila (ou chegam da thread ainda terminando)
# depois do "Parar":
src.on_reading(AngleReading(angle_deg=9.0, timestamp=time.time(), pan_deg=9.0))
src.on_error("erro atrasado")
pump(0.5)
check("5. leitura atrasada após Parar: continua 'Parado'", status() == "○ Parado", status())
check("5. leitura atrasada não é gravada", w._history.count_readings(sid) == n_antes,
      f"{n_antes} -> {w._history.count_readings(sid)}")
check("5. tela não mostra a leitura atrasada", "9" not in w._axis_widgets[mw.TILT_AXIS]["value"].text(),
      w._axis_widgets[mw.TILT_AXIS]["value"].text())

w._start()
novo = FakeBle.instances[-1]
pump(0.5)
src.on_reading(AngleReading(angle_deg=9.0, timestamp=time.time(), pan_deg=9.0))
pump(0.5)
check("6. leitura da fonte antiga após reiniciar: ignorada", status() == "◐ Conectando...", status())
novo.streaming = True
pump(0.8)
check("6. fonte nova: verde", status() == "● Conectado", status())
w._stop()

w._settings.mode = "simulado"
w._start()
pump(1.0)
check("7. Simulação: '● Simulação (interna)'", status() == "● Simulação (interna)", status())
pump(2.5)
check("7. Simulação não cai em 'Sem dados'", status() == "● Simulação (interna)", status())
w._stop()
w.close()

print("CONEXÃO: TUDO OK" if failures == 0 else "CONEXÃO: HOUVE FALHA")
sys.exit(1 if failures else 0)
