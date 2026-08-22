"""Identidade desta versão do app desktop.

Esta é a **versão 1**, que mede apenas a inclinação (tilt). A versão 2, que
mede também o azimute (pan), vive na branch principal e tem identidade
própria — nome, pasta de instalação, `AppId` do Inno Setup e pasta de dados
diferentes — para que as duas possam ficar **instaladas ao mesmo tempo** na
mesma máquina, sem uma substituir a outra.

Manter em sincronia com `windows/Inclinometro.iss`, que precisa dos mesmos
valores mas não consegue importar Python.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_VERSION = "1.0.0"

# Nome exibido na janela e nos atalhos.
APP_NAME = "Inclinômetro"

# Sufixo usado em nomes de pasta/arquivo. Vazio nesta versão: a pasta de
# dados fica simplesmente "Inclinometro", enquanto a versão 2 usa
# "Inclinometro2Eixos".
APP_VARIANT = ""


def user_data_dir() -> Path:
    """Pasta onde esta versão guarda dados que ela mesma escreve (o banco de
    histórico).

    Rodando a partir do código-fonte, fica ao lado do projeto — prático para
    desenvolvimento. Já instalado (executável do PyInstaller), o app mora em
    Program Files, onde um usuário **sem privilégio de administrador não pode
    escrever**: gravar o banco ali falharia, e o histórico simplesmente não
    seria registrado. Então vai para a pasta de dados do próprio usuário, com
    o nome da variante no caminho — o que também mantém separados os
    históricos das duas versões instaladas lado a lado.
    """
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / ".local" / "share"
        directory = root / f"Inclinometro{APP_VARIANT}"
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    return Path(__file__).resolve().parent
