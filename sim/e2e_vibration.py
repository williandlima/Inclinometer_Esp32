"""Teste de ponta a ponta do Modo Vibração via BLE: firmware REAL simulado
(fw_sim) <-> BleakClient falso <-> código REAL do app (captura, retransmissão,
decodificação e análise espectral)."""
import asyncio, random, subprocess, sys, time
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python-app"))
from data_source.ble_source import BleAngleSource
from limits.vibration_stats import analyze_axis
from limits.limit_tracker import TILT_AXIS, PAN_AXIS
from tools.diagnostico_pan import parse_diagnostics

DATA_UUIDS = {"6e6e0006-3c17-4a2e-8f4b-1a2b3c4d5e6f", "6e6e0009-3c17-4a2e-8f4b-1a2b3c4d5e6f"}


class FakeBleakClient:
    """Imita a BleakClient: characteristic inexistente dá o mesmo erro do bleak."""

    def __init__(self, exe, drop_rate=0.0, seed=1):
        self.p = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.callbacks, self.drop_rate, self.rng = {}, drop_rate, random.Random(seed)
        self.dropped = self.delivered = 0
        self.chars = set(self._cmd("LIST")[0].split()[1:])

    def _cmd(self, line, until=None):
        self.p.stdin.write(line + "\n"); self.p.stdin.flush()
        out = []
        while True:
            l = self.p.stdout.readline().rstrip("\n")
            out.append(l)
            if until is None or l == until:
                return out

    def _check(self, uuid):
        if uuid not in self.chars:
            raise Exception(f"Characteristic {uuid} was not found!")

    async def start_notify(self, uuid, cb):
        self._check(uuid); self.callbacks[uuid] = cb

    async def stop_notify(self, uuid):
        self.callbacks.pop(uuid, None)

    async def write_gatt_char(self, uuid, data, response=True):
        self._check(uuid); self._cmd(f"WRITE {uuid} {bytes(data).hex()}")

    async def read_gatt_char(self, uuid):
        self._check(uuid); return bytearray.fromhex(self._cmd(f"READ {uuid}")[0].split()[1])

    def run(self, ms):
        for l in self._cmd(f"RUN {ms}", until="END")[:-1]:
            _, uuid, h = l.split(" ", 2) if l.count(" ") == 2 else (*l.split(" "), "")
            cb = self.callbacks.get(uuid)
            if cb is None:
                continue
            if uuid in DATA_UUIDS and self.rng.random() < self.drop_rate:
                self.dropped += 1; continue  # pacote perdido no rádio
            self.delivered += 1
            cb(None, bytearray.fromhex(h))

    def close(self):
        self.p.stdin.write("QUIT\n"); self.p.stdin.flush(); self.p.wait()


async def capture(exe, duration_s, rate_hz, drop_rate=0.0):
    client = FakeBleakClient(exe, drop_rate)
    client.run(2000)  # boot: ZUPT do pan estabelece o bias
    src = BleAngleSource("sim"); src._client = client
    result = {}
    stop = asyncio.Event()

    async def pump():
        while not stop.is_set():
            client.run(20)            # 20 ms de tempo simulado do firmware
            await asyncio.sleep(0)

    def on_done(readings, err):
        result["readings"], result["err"] = readings, err

    t0 = time.monotonic()
    pump_task = asyncio.create_task(pump())
    await src._run_vibration_capture_async(duration_s, rate_hz, lambda *a: None, on_done)
    stop.set(); await pump_task
    client.close()
    return result, client, time.monotonic() - t0


def report(title, result, client, wall):
    print(f"\n=== {title} ===")
    if result.get("err"):
        print(f"  ERRO: {result['err']}")
        return False
    r = result["readings"]
    tilt = analyze_axis(r, RATE, TILT_AXIS).stats
    pan = analyze_axis(r, RATE, PAN_AXIS).stats
    print(f"  amostras: {len(r)}  pacotes entregues/perdidos: {client.delivered}/{client.dropped}  ({wall:.1f}s de parede)")
    print(f"  tilt: {tilt.dominant_freq_hz:.3f} Hz, amplitude {tilt.dominant_amplitude_deg:.4f}°  (esperado 3,000 Hz, 0,5000°)")
    print(f"  pan : {pan.dominant_freq_hz:.3f} Hz, amplitude {pan.dominant_amplitude_deg:.4f}°  (esperado 4,500 Hz, {2.0/(2*3.14159265*4.5):.4f}°)")
    ok = (len(r) == DUR * RATE and abs(tilt.dominant_freq_hz - 3.0) < 0.05 and abs(tilt.dominant_amplitude_deg - 0.5) < 0.02
          and abs(pan.dominant_freq_hz - 4.5) < 0.05 and abs(pan.dominant_amplitude_deg - 0.0707) < 0.005)
    print("  RESULTADO:", "OK" if ok else "FALHOU")
    return ok


DUR, RATE = 10, 500
ALL_UUIDS = {f"6e6e00{n}-3c17-4a2e-8f4b-1a2b3c4d5e6f" for n in ("02", "03", "04", "05", "06", "07", "08", "09", "0a", "0b", "0c", "0d")}


async def main():
    exe = sys.argv[1]
    client = FakeBleakClient(exe)
    missing = ALL_UUIDS - client.chars
    version = await client.read_gatt_char("6e6e0007-3c17-4a2e-8f4b-1a2b3c4d5e6f") if not missing else b"??"
    diag_ok = True
    if not missing:
        # Diagnóstico do pan, decodificado pelo MESMO parser da ferramenta de campo.
        client.run(5000)
        d = parse_diagnostics(await client.read_gatt_char("6e6e000d-3c17-4a2e-8f4b-1a2b3c4d5e6f"))
        diag_ok = (d["bias_pronto"] == 1 and abs(d["bias_gy"] - 3.0) < 0.2 and abs(d["bias_gz"] + 2.0) < 0.2
                   and 450 <= d["amostras"] <= 510 and d["falhas_i2c"] == 0)
        print(f"diagnóstico do pan: bias gy={d['bias_gy']:.3f} gz={d['bias_gz']:.3f} (esperado 3,0/-2,0), "
              f"amostras={d['amostras']}, pronto={d['bias_pronto']}  {'OK' if diag_ok else 'FALHOU'}")
    client.close()
    print(f"characteristics registrados: {len(client.chars)}/{len(ALL_UUIDS)}"
          + (f"  FALTANDO: {sorted(missing)}" if missing else "  OK"))
    ok = not missing and diag_ok
    if not missing:
        code = version[0] | (version[1] << 8)
        print(f"versão do firmware lida via BLE: {code // 10000}.{(code // 100) % 100}.{code % 100}")
    for drop in (0.0, 0.05, 0.30):
        r, c, w = await capture(exe, DUR, RATE, drop_rate=drop)
        ok &= report(f"500 Hz / 10 s, {drop:.0%} dos pacotes perdidos", r, c, w)
    print("\nVIBRAÇÃO BLE: TUDO OK" if ok else "\nVIBRAÇÃO BLE: HOUVE FALHA")
    sys.exit(0 if ok else 1)

asyncio.run(main())
