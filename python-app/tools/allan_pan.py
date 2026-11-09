"""Variância de Allan do giroscópio do pan (caracterização de ruído).

É a ferramenta padrão de quem trabalha com giroscópio (IEEE Std 952/1293)
para separar os ruídos que importam numa integração:
- ARW (angle random walk, °/√h): ruído branco da taxa; vira um passeio
  aleatório no ângulo integrado — σ_ângulo ≈ ARW·√t;
- instabilidade de bias (°/s e °/h): o mínimo da curva, o quanto o zero do
  giro "passeia" — é o que o ZUPT precisa acompanhar;
- σ da média de 1 s: o ruído da média de uma janela do ZUPT, que deve
  ficar bem abaixo do limiar de janela parada (PAN_ZUPT_RATE_THRESHOLD_DPS).

Os limiares do ZUPT do firmware foram escolhidos de forma empírica; esta
ferramenta os confere contra o ruído medido NESTA unidade.

Dados: uma captura do Modo Vibração com o pan PARADO (placa imóvel, sem
vento), de preferência longa e em taxa baixa (ex.: 600 s a 10 Hz = 6000
amostras), lida do histórico do app (amostras de taxa de pan, °/s).

Uso:
    python tools/allan_pan.py                       # última captura do histórico
    python tools/allan_pan.py --captura 12 --db caminho/inclinometro_historico.db
    python tools/allan_pan.py --autoteste
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def adev(rate: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Desvio de Allan sobreposto da taxa, em τ logaritmicamente espaçados."""
    theta = np.cumsum(rate) / fs  # ângulo integrado
    n = rate.size
    ms = np.unique(np.logspace(0, math.log10(max(1, n // 9)), 60).astype(int))
    taus, devs = [], []
    for m in ms:
        tau = m / fs
        d = theta[2 * m:] - 2 * theta[m:-m] + theta[:-2 * m]
        if d.size < 2:
            continue
        taus.append(tau)
        devs.append(math.sqrt(np.mean(d**2) / (2 * tau**2)))
    return np.array(taus), np.array(devs)


def analisa(rate: np.ndarray, fs: float, limiar_zupt: float = 0.1) -> dict:
    rate = rate - np.mean(rate)
    taus, devs = adev(rate, fs)
    s1 = float(np.interp(1.0, taus, devs)) if taus[0] <= 1.0 <= taus[-1] else float("nan")
    i_min = int(np.argmin(devs))
    bi = devs[i_min] / 0.664
    arw = s1 * 60  # °/s·√s -> °/√h  (σ(τ=1 s) = N)
    print(f"Amostras: {rate.size} a {fs:g} Hz ({rate.size / fs:.0f} s)")
    print(f"ARW (ruído branco):            {arw:.3f} °/√h  -> passeio do ângulo ≈ {s1:.4f}°·√t(s)")
    print(f"Instabilidade de bias:         {bi:.4f} °/s  ({bi * 3600:.1f} °/h) em τ ≈ {taus[i_min]:.0f} s")
    print(f"σ da média de 1 s (janela):    {s1:.4f} °/s")
    print(f"Limiar de janela parada atual: {limiar_zupt:.3f} °/s  = {limiar_zupt / s1:.0f}x o ruído da janela"
          if s1 == s1 else "")
    if s1 == s1:
        if limiar_zupt < 4 * s1:
            print("  ATENÇÃO: limiar menor que 4σ — janelas paradas podem ser lidas como giro (ruído alto nesta unidade).")
        else:
            print("  OK: o limiar está folgado em relação ao ruído (o que limita é o passeio do bias, não o ruído).")
    print("\n   τ (s)     σ_Allan (°/s)")
    for t, d in zip(taus[:: max(1, len(taus) // 15)], devs[:: max(1, len(taus) // 15)]):
        print(f"  {t:8.2f}   {d:.5f}")
    return {"arw": arw, "bi": bi, "s1": s1}


def le_captura(db: Path, captura: int | None) -> tuple[np.ndarray, float]:
    con = sqlite3.connect(str(db))
    if captura is None:
        row = con.execute("SELECT id, rate_hz FROM vibration_captures ORDER BY started_at DESC LIMIT 1").fetchone()
    else:
        row = con.execute("SELECT id, rate_hz FROM vibration_captures WHERE id = ?", (captura,)).fetchone()
    if row is None:
        raise SystemExit("Nenhuma captura do Modo Vibração no histórico.")
    cid, fs = row
    rates = [r[0] for r in con.execute(
        "SELECT pan_rate_dps FROM vibration_samples WHERE capture_id = ? ORDER BY timestamp", (cid,))]
    if not rates or any(r is None for r in rates):
        raise SystemExit("A captura não tem a taxa do pan (firmware anterior à v1.3.0).")
    print(f"Captura {cid} do histórico {db}")
    return np.array(rates, dtype=float), float(fs)


def autoteste() -> int:
    """Ruído branco de 0,05 °/s por amostra a 100 Hz (σ da média de 1 s =
    0,005 °/s) mais um passeio do bias: a ferramenta tem de achar o ARW."""
    rng = np.random.default_rng(3)
    fs, n = 100.0, 60000
    rate = 0.05 * rng.standard_normal(n) + np.cumsum(0.0002 * rng.standard_normal(n))
    r = analisa(rate, fs)
    ok = abs(r["s1"] - 0.005) < 0.0015
    print("\nAUTOTESTE:", "OK" if ok else "FALHOU")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", type=Path, help="histórico do app (padrão: o da instalação)")
    p.add_argument("--captura", type=int, help="id da captura (padrão: a mais recente)")
    p.add_argument("--autoteste", action="store_true")
    a = p.parse_args()
    if a.autoteste:
        return autoteste()
    db = a.db
    if db is None:
        from limits.history_store import DEFAULT_DB_PATH
        db = DEFAULT_DB_PATH
    rate, fs = le_captura(db, a.captura)
    if rate.size < 100:
        print("Captura curta demais: use pelo menos alguns minutos.")
        return 2
    analisa(rate, fs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
