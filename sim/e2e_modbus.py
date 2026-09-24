"""Teste de ponta a ponta do modo USB (Modbus RTU): firmware REAL em tempo
real (modbus_sim) numa porta serial virtual <-> código REAL do app
(data_source/modbus_source.py) com o pymodbus de verdade.

Cada cenário sobe um ESP32 simulado novo, que reinicia toda vez que o app
abre a porta (como o auto-reset por DTR/RTS da placa real), e opcionalmente
perde/corrompe bytes nos dois sentidos. Uso: python3 e2e_modbus.py <modbus_sim>
"""
import os
import subprocess
import sys
import threading
import time

APP = os.environ.get("APPDIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python-app")
sys.path.insert(0, APP)

import pymodbus  # noqa: E402
from data_source import modbus_source as ms  # noqa: E402
from limits.limit_tracker import TILT_AXIS  # noqa: E402
from limits.vibration_stats import analyze_axis  # noqa: E402

EXE = sys.argv[1]
_cfg = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware", "src", "Config.h")).read()
FW = _cfg.split('FIRMWARE_VERSION[] = "')[1].split('"')[0]
failures = 0


def check(name, ok, detail=""):
    global failures
    print(f"  {'OK    ' if ok else 'FALHOU'} {name}{(': ' + detail) if detail else ''}")
    if not ok:
        failures += 1


class Esp32:
    def __init__(self, **env):
        e = dict(os.environ, **{k: str(v) for k, v in env.items()})
        self.p = subprocess.Popen([EXE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, env=e)
        self.port = self.p.stdout.readline().strip()

    def cmd(self, c):
        self.p.stdin.write(c + "\n"); self.p.stdin.flush()

    def close(self):
        self.p.kill(); self.p.wait()


class Reader:
    """Liga o ModbusAngleSource e guarda o que chega."""

    def __init__(self, port):
        self.src = ms.ModbusAngleSource(port, 9600, 1)
        self.readings, self.errors = [], []
        self.src.start(lambda r: self.readings.append(r), lambda m: self.errors.append((time.time(), m)))

    def wait_readings(self, n, timeout):
        t0 = time.time()
        start = len(self.readings)
        while time.time() - t0 < timeout:
            if len(self.readings) - start >= n:
                return time.time() - t0
            time.sleep(0.05)
        return None

    def stop(self):
        self.src.stop()


def vibration(src, dur, rate, timeout):
    done = {}
    ev = threading.Event()

    def on_done(readings, err):
        done["r"], done["e"] = readings, err
        ev.set()

    t0 = time.time()
    src.start_vibration_capture(dur, rate, lambda *a: None, on_done)
    ev.wait(timeout)
    return done, time.time() - t0


def scenario(title, **env):
    print(f"\n=== {title} ===")
    return Esp32(**env)


# --------------------------------------------------------------- biblioteca
print(f"pymodbus {pymodbus.__version__} (requirements.txt pede 3.14.0)")
check("versão do pymodbus igual à do requirements.txt", pymodbus.__version__ == "3.14.0")

# ------------------------------------------------------------ linha limpa
esp = scenario("linha limpa, ESP32 reinicia a cada abertura da porta")
t0 = time.time()
try:
    r = ms.test_connection(esp.port, 9600, 1)
    check("Testar conexão", abs(r.angle_deg - 10) < 1 and r.firmware_version == FW,
          f"{time.time() - t0:.1f} s, tilt {r.angle_deg}°, firmware {r.firmware_version}")
except Exception as e:  # noqa: BLE001
    check("Testar conexão", False, f"{time.time() - t0:.1f} s: {e}")
rd = Reader(esp.port)
dt = rd.wait_readings(1, 15)
check("primeira leitura contínua", dt is not None, f"{dt:.1f} s após Iniciar" if dt else "nenhuma em 15 s")
dt = rd.wait_readings(12, 6)
check("leitura contínua ~4/s", dt is not None, f"12 leituras em {dt:.1f} s" if dt else "")
if rd.readings:
    check("tilt ~10°", abs(rd.readings[-1].angle_deg - 10) < 1, f"{rd.readings[-1].angle_deg}°")
    check("pan presente", rd.readings[-1].pan_deg is not None)
try:
    rd.src.calibrate()
    rd.wait_readings(4, 3)
    check("calibrar zera o tilt", abs(rd.readings[-1].angle_deg) < 1, f"{rd.readings[-1].angle_deg}°")
    rd.src.reset_peaks()
    check("resetar extremos", True)
except Exception as e:  # noqa: BLE001
    check("calibrar/resetar", False, str(e))
done, wall = vibration(rd.src, 3, 100, 60)
if done.get("r"):
    st = analyze_axis(done["r"], 100, TILT_AXIS).stats
    check("Modo Vibração 3 s @ 100 Hz", len(done["r"]) == 300 and abs(st.dominant_freq_hz - 3) < 0.1
          and abs(st.dominant_amplitude_deg - 0.5) < 0.05,
          f"{len(done['r'])} amostras, {st.dominant_freq_hz:.2f} Hz, {st.dominant_amplitude_deg:.3f}°, {wall:.1f} s")
else:
    check("Modo Vibração 3 s @ 100 Hz", False, str(done.get("e", "sem resposta")))
rd.stop()
esp.close()

# ------------------------------------------------- reset no meio da sessão
esp = scenario("ESP32 reinicia sozinho no meio da leitura (queda de alimentação)")
rd = Reader(esp.port)
rd.wait_readings(4, 15)
esp.cmd("RESET")
t_reset = time.time()
time.sleep(0.2)
n0 = len(rd.readings)
dt = None
while time.time() - t_reset < 60:
    if len(rd.readings) > n0 + 2:
        dt = time.time() - t_reset
        break
    time.sleep(0.05)
check("leitura volta sozinha após o reset", dt is not None and dt < 10,
      f"{dt:.1f} s" if dt else "não voltou em 60 s")
rd.stop()
esp.close()

# ----------------------------------------------------- linha com ruído
esp = scenario("linha ruidosa: 0,2% dos bytes perdidos e 0,2% corrompidos, nos dois sentidos (~10% das transações)",
               DROP_RX=0.002, CORRUPT_RX=0.002, DROP_TX=0.002, CORRUPT_TX=0.002)
t0 = time.time()
ok = 0
for _ in range(10):
    try:
        r = ms.test_connection(esp.port, 9600, 1)
        ok += r.firmware_version == FW
    except Exception:  # noqa: BLE001
        pass
check("Testar conexão (10 vezes, com versão)", ok == 10, f"{ok}/10 em {time.time() - t0:.1f} s")
rd = Reader(esp.port)
rd.wait_readings(1, 15)
n0, t0 = len(rd.readings), time.time()
time.sleep(10)
rate = (len(rd.readings) - n0) / (time.time() - t0)
check("leitura contínua segue viva", rate > 2.5, f"{rate:.1f} leituras/s")
done, wall = vibration(rd.src, 3, 100, 120)
check("Modo Vibração com ruído na linha", bool(done.get("r")) and len(done["r"]) == 300,
      f"{len(done['r'])} amostras em {wall:.1f} s" if done.get("r") else str(done.get("e")))
rd.stop()
esp.close()

# --------------------------------------------------------- ESP32 mudo
esp = scenario("porta abre mas o ESP32 não responde (placa travada / porta errada)", BOOT_MS=10**9)
t0 = time.time()
try:
    ms.test_connection(esp.port, 9600, 1)
    check("Testar conexão falha", False, "respondeu?!")
except Exception as e:  # noqa: BLE001
    dt = time.time() - t0
    check("Testar conexão falha em tempo razoável", dt < 20, f"{dt:.1f} s: {e}")
esp.close()

print("\nMODBUS/USB: TUDO OK" if failures == 0 else f"\nMODBUS/USB: {failures} FALHA(S)")
sys.exit(1 if failures else 0)
