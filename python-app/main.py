"""Ponto de entrada do painel desktop do inclinômetro (PyQt5)."""
import os
import sys

# Garante que a raiz de python-app/ esteja no sys.path mesmo quando o
# interpretador é iniciado de outro diretório de trabalho ou por uma
# ferramenta (VSCode, atalho, .exe empacotado) que não faz isso por conta
# própria — os módulos do projeto (ui, data_source, limits, report) são
# importados de forma absoluta a partir desta pasta.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from ui.main_window import MainWindow  # noqa: E402

# Sem isso, num notebook com escala de tela >100% (muito comum em painéis
# industriais com monitor 4K/QHD) o Qt desenha os widgets no tamanho físico
# em pixels, ignorando a escala do sistema — telas e botões saem menores (e
# desproporcionais entre monitores diferentes) do que o usuário vê no resto
# do sistema operacional. Precisa ser definido antes de criar o QApplication.
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
