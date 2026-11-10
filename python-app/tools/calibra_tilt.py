"""Calibração do TILT a partir de pontos de bancada — modelo físico do acelerômetro.

Por que existe (análise na seção "Tilt: erro maior no lado negativo" de
firmware/README.md): o firmware lê o tilt como atan2(ay, az) e corrige com
um fator de escala por lado (TILT_SCALE_CORRECTION_NEG/_POS). Esse modelo é
linear por lado, com uma quebra no zero do ângulo bruto, e não representa o
erro real de um acelerômetro, que é:

    ay = k·sin(θ+β)·g + b_y          (ganho relativo k, offset b_y)
    az =   cos(θ+β)·g + b_z          (offset b_z)
    bruto = atan2(ay, az)

O offset b_y produz um erro PAR (≈ −b_y·θ²/2): mesmo sinal dos dois lados,
o que faz o fator "medido" sair diferente em cada lado e mudar com a faixa
usada no ajuste — exatamente o histórico dos fatores (lado positivo de 1,063
para 1,066 ao estender a faixa até 21,5°; lado negativo ajustado só até
−8,6°). Fora da faixa calibrada, o fator linear erra cada vez mais.

Esta ferramenta ajusta (k, b_y, b_z, β) aos pontos medidos por mínimos
quadrados e devolve as constantes TILT_ACCEL_* para firmware/src/Config.h
(com elas, os fatores NEG/POS voltam a 1,0). Só a RAZÃO dos ganhos Y/Z entra
no atan2, então a tolerância de ganho de cada eixo não atrapalha.

Entrada: CSV com as colunas
    referencia  — ângulo do instrumento de referência (°), ex.: Mitutoyo PRO3600
    bruto       — ângulo BRUTO do sensor (°), coluna "tilt" do CSV gravado por
                  tools/diagnostico_pan.py (média de alguns segundos parado)
    leitura     — opcional: o que o app mostrou, só para comparar

Use pontos dos DOIS lados e na faixa toda de uso (ex.: −60 a +60 a cada 5°
ou 10°). O ponto 0 da referência é o zero da calibração.

Uso:
    python tools/calibra_tilt.py pontos.csv
    python tools/calibra_tilt.py --autoteste
"""
from __future__ import annotations

import argparse
import csv
import math
import sys

import numpy as np

# Fatores atuais do firmware (1.6.25+; o lado negativo era 1,042 até a 1.6.24), para comparação.
FATOR_NEG = 1.066
FATOR_POS = 1.066


def modelo_bruto(theta_deg: np.ndarray, k: float, by: float, bz: float, beta_deg: float) -> np.ndarray:
    t = np.radians(theta_deg + beta_deg)
    return np.degrees(np.arctan2(k * np.sin(t) + by, np.cos(t) + bz))


def erro_corrigido(ref: np.ndarray, bruto: np.ndarray, k: float, by: float, bz: float, beta: float) -> np.ndarray:
    """Erro que o firmware terá com as constantes. Ele calcula
    atan2((ay−b_y)/k, az−b_z) com os ay, az REAIS em g, que vale θ+β se o
    modelo estiver certo; o que sobra é o desvio do bruto medido em relação
    ao modelo, levado de graus de bruto para graus de tilt pela inclinação
    local da curva. (Não dá para reconstruir ay, az a partir do bruto: o
    atan2 perde |a|, e com offset isso não é desprezível.)"""
    h = 0.01
    slope = (modelo_bruto(ref + h, k, by, bz, beta) - modelo_bruto(ref - h, k, by, bz, beta)) / (2 * h)
    resid = (bruto - modelo_bruto(ref, k, by, bz, beta) + 180) % 360 - 180
    return resid / slope


def ajusta(ref: np.ndarray, bruto: np.ndarray) -> tuple[float, float, float, float]:
    """Gauss-Newton em (k, b_y, b_z, β) minimizando o erro em graus do bruto."""
    x = np.array([1.0, 0.0, 0.0, float(np.interp(0.0, ref[np.argsort(ref)], bruto[np.argsort(ref)]))])
    for _ in range(100):
        f0 = modelo_bruto(ref, *x)
        res = bruto - f0
        res = (res + 180) % 360 - 180
        J = np.empty((ref.size, 4))
        for i in range(4):
            h = 1e-6 if i < 3 else 1e-4
            xp = x.copy()
            xp[i] += h
            J[:, i] = (modelo_bruto(ref, *xp) - f0) / h
        dx = np.linalg.lstsq(J, res, rcond=None)[0]
        x += dx
        if np.abs(dx).max() < 1e-10:
            break
    return tuple(float(v) for v in x)  # type: ignore[return-value]


def leitura_atual(bruto: np.ndarray, bruto_zero: float) -> np.ndarray:
    """Modelo do firmware atual: fator por lado pelo sinal do bruto, menos o zero."""
    s = np.where(bruto < 0, FATOR_NEG, FATOR_POS)
    s0 = FATOR_NEG if bruto_zero < 0 else FATOR_POS
    return s * bruto - s0 * bruto_zero


def resumo(nome: str, ref: np.ndarray, erro: np.ndarray) -> None:
    for lado, m in (("negativo", ref < 0), ("positivo", ref > 0)):
        if m.any():
            e = erro[m]
            print(f"  {nome:34s} lado {lado}: máx {np.abs(e).max():5.2f}°  rms {math.sqrt(np.mean(e**2)):5.2f}°")


def analisa(ref: np.ndarray, bruto: np.ndarray, leitura: np.ndarray | None) -> dict:
    ordem = np.argsort(ref)
    bruto_zero = float(np.interp(0.0, ref[ordem], bruto[ordem]))
    k, by, bz, beta = ajusta(ref, bruto)
    erro_novo = erro_corrigido(ref, bruto, k, by, bz, beta)
    # O zero da calibração tira o erro no ponto 0 (como no firmware).
    erro_novo = erro_novo - float(np.interp(0.0, ref[ordem], erro_novo[ordem]))
    novo = ref + erro_novo
    atual = leitura_atual(bruto, bruto_zero)

    print(f"Pontos: {ref.size} ({int((ref < 0).sum())} negativos, {int((ref > 0).sum())} positivos), "
          f"faixa {ref.min():+.1f}° a {ref.max():+.1f}°; bruto no zero {bruto_zero:+.2f}°")
    print(f"Modelo ajustado: ganho Y/Z k = {k:.4f}, offset Y = {by * 1000:+.1f} mg, "
          f"offset Z = {bz * 1000:+.1f} mg, rotação da placa β = {beta:+.2f}°")
    print("\nErro (leitura − referência):")
    resumo("firmware atual (1,066 / 1,066)", ref, atual - ref)
    if leitura is not None:
        resumo("leitura do app (como medida)", ref, leitura - ref)
    resumo("modelo físico ajustado", ref, novo - ref)
    print("\nPonto a ponto:  referência   atual    ajustado")
    for r, a, n in sorted(zip(ref, atual - ref, novo - ref)):
        print(f"                {r:+8.2f}°  {a:+6.2f}°  {n:+6.3f}°")
    print("\nConstantes para firmware/src/Config.h:")
    print(f"constexpr float TILT_ACCEL_GAIN_Y = {k:.4f}f;")
    print(f"constexpr float TILT_ACCEL_OFFSET_Y_G = {by:.4f}f;")
    print(f"constexpr float TILT_ACCEL_OFFSET_Z_G = {bz:.4f}f;")
    print("constexpr float TILT_SCALE_CORRECTION_NEG = 1.0f;")
    print("constexpr float TILT_SCALE_CORRECTION_POS = 1.0f;")
    return {"k": k, "by": by, "bz": bz, "beta": beta, "novo": novo - ref, "atual": atual - ref}


def le_csv(caminho: str) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    ref, bruto, leit = [], [], []
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        amostra = f.readline()
        f.seek(0)
        leitor = csv.DictReader(f, delimiter=";" if ";" in amostra else ",")
        for linha in leitor:
            num = lambda s: float(str(s).replace(",", "."))  # noqa: E731
            ref.append(num(linha["referencia"]))
            bruto.append(num(linha["bruto"]))
            if linha.get("leitura") not in (None, ""):
                leit.append(num(linha["leitura"]))
    return np.array(ref), np.array(bruto), (np.array(leit) if len(leit) == len(ref) else None)


def autoteste() -> int:
    """Gera pontos de um sensor com ganho, offsets e rotação conhecidos (com
    ruído de 0,02° no bruto) e confere que o ajuste os recupera."""
    rng = np.random.default_rng(7)
    k, by, bz, beta = 0.9698, 0.136, -0.020, 2.5
    ref = np.arange(-60.0, 60.1, 5.0)
    bruto = modelo_bruto(ref, k, by, bz, beta) + 0.02 * rng.standard_normal(ref.size)
    r = analisa(ref, bruto, None)
    ok = (abs(r["k"] - k) < 0.003 and abs(r["by"] - by) < 0.003 and abs(r["bz"] - bz) < 0.005
          and np.abs(r["novo"]).max() < 0.08 and np.abs(r["atual"][ref < 0]).max() > 1.0)
    print("\nAUTOTESTE:", "OK" if ok else "FALHOU")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="?", help="CSV com referencia;bruto[;leitura]")
    p.add_argument("--autoteste", action="store_true")
    a = p.parse_args()
    if a.autoteste:
        return autoteste()
    if not a.csv:
        p.print_help()
        return 2
    ref, bruto, leit = le_csv(a.csv)
    if ref.size < 6 or not (ref < 0).any() or not (ref > 0).any():
        print("Preciso de pelo menos 6 pontos, com valores dos DOIS lados do zero.")
        return 2
    analisa(ref, bruto, leit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
