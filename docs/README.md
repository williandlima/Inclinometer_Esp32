# docs

Documentação do projeto do inclinômetro/azimutímetro eletrônico ESP32,
reunida numa única pasta: os entregáveis formais em padrão ABNT e a
documentação técnica de referência mantida junto ao código.

## Entregáveis formais (padrão ABNT — NBR 14724)

Relatórios e procedimentos técnicos com capa, folha de rosto, histórico de
revisões, sumário automático, margens 3-2-3-2cm, fonte Times New Roman 12pt,
espaçamento 1,5.

| Documento | Rev. | Conteúdo |
|---|---|---|
| [relatorio-tecnico-inclinometro.docx](relatorio-tecnico-inclinometro.docx) | 01 | Relatório técnico do projeto: fundamentação teórica, arquitetura do sistema, cálculos e modelagem matemática, protocolos de comunicação, modos de operação e resultados/validação. |
| [lista-de-materiais-hardware.docx](lista-de-materiais-hardware.docx) | 00 | Lista de materiais (BOM): componentes, especificações técnicas, datasheets dos fabricantes, ligações elétricas do sensor e opções de alimentação em avaliação. |
| [procedimento-instalacao-software.docx](procedimento-instalacao-software.docx) | 00 | Procedimento técnico de instalação e verificação dos dois softwares de supervisão: desktop (Python/PyQt5) e aplicativo Android (Kotlin/Jetpack Compose). |
| [procedimento-gravacao-firmware.docx](procedimento-gravacao-firmware.docx) | 00 | Procedimento técnico de compilação e gravação (upload) do firmware do ESP32 via PlatformIO. |
| [procedimento-teste-funcional-bancada.docx](procedimento-teste-funcional-bancada.docx) | 00 | Procedimento de teste funcional completo em bancada: instalação do software desktop (modo notebook), setup de teste e verificação de todos os modos de conexão e funcionalidades, com tabela de registro de resultados. |

A revisão 01 do relatório técnico acompanha o firmware **1.4.0**: taxa de
amostragem do Modo Vibração de até 500 Hz, retransmissão de amostras perdidas
na transferência via BLE e os dois refinamentos do pipeline de análise
espectral (interpolação do pico em decibéis e piso de ruído medido em janela
local). O firmware evoluiu desde então para a **1.6.0** (extremos medidos no
próprio firmware e filtro adaptativo da leitura contínua — ver
`firmware/README.md`); os relatórios ainda não foram revisados para refletir
essa mudança.

## Documentação técnica de referência

Mantida junto ao código, e atualizada primeiro (é a fonte da verdade de
engenharia — os entregáveis formais acima devem refletir o que está aqui, não
o contrário):

| Documento | Conteúdo |
|---|---|
| [pinout.md](pinout.md) | Mapeamento completo de pinos do ESP32 (MPU6050 via I²C, comunicação USB). |
| [fluxograma-python-app.md](fluxograma-python-app.md) | Arquitetura e fluxos de execução do software desktop (`python-app/`, PyQt5). |
| [`HARDWARE/README.md`](../HARDWARE/README.md) | Versão de consulta rápida da lista de materiais (BOM), com datasheets linkados. |
| README de cada módulo (`python-app/`, `android-app/`, `firmware/`) | Instalação, uso e detalhes de implementação específicos de cada software. |
