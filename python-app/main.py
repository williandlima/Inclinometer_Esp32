"""Ponto de entrada do painel desktop do inclinômetro (PyQt5)."""
import os
import sys

# Garante que a raiz de python-app/ esteja no sys.path mesmo quando o
# interpretador é iniciado de outro diretório de trabalho ou por uma
# ferramenta (VSCode, atalho, .exe empacotado) que não faz isso por conta
# própria — os módulos do projeto (ui, data_source, limits, report) são
# importados de forma absoluta a partir desta pasta.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from ui.main_window import MainWindow  # noqa: E402


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
