# Doc

Relatórios e procedimentos técnicos do projeto, em padrão ABNT (NBR 14724):
capa, folha de rosto, histórico de revisões, sumário automático, margens
3-2-3-2cm, fonte Times New Roman 12pt, espaçamento 1,5.

| Documento | Rev. | Conteúdo |
|---|---|---|
| [relatorio-tecnico-inclinometro.docx](relatorio-tecnico-inclinometro.docx) | 01 | Relatório técnico do projeto: fundamentação teórica, arquitetura do sistema, cálculos e modelagem matemática, protocolos de comunicação, modos de operação e resultados/validação. |
| [lista-de-materiais-hardware.docx](lista-de-materiais-hardware.docx) | 00 | Lista de materiais (BOM): componentes, especificações técnicas, datasheets dos fabricantes, ligações elétricas do sensor e opções de alimentação em avaliação. |
| [procedimento-instalacao-software.docx](procedimento-instalacao-software.docx) | 00 | Procedimento técnico de instalação e verificação dos dois softwares de supervisão: desktop (Python/PyQt5) e aplicativo Android (Kotlin/Jetpack Compose). |
| [procedimento-gravacao-firmware.docx](procedimento-gravacao-firmware.docx) | 00 | Procedimento técnico de compilação e gravação (upload) do firmware do ESP32 via PlatformIO. |

A revisão 01 do relatório técnico acompanha o firmware **1.4.0**: taxa de
amostragem do Modo Vibração de até 500 Hz, retransmissão de amostras perdidas
na transferência via BLE e os dois refinamentos do pipeline de análise
espectral (interpolação do pico em decibéis e piso de ruído medido em janela
local).

Documentação técnica de referência mantida junto ao código — README de cada
módulo, pinagem ([`docs/pinout.md`](../docs/pinout.md)), fluxograma e a versão
de consulta rápida da lista de materiais
([`HARDWARE/README.md`](../HARDWARE/README.md)) — permanece nas respectivas
pastas. Os documentos desta pasta são os entregáveis formais; aqueles são a
fonte da verdade de engenharia, e devem ser atualizados primeiro.
