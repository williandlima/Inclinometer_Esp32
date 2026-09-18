# docs

Documentação do projeto do inclinômetro/azimutímetro eletrônico ESP32,
reunida numa única pasta: os entregáveis formais em padrão ABNT e a
documentação técnica de referência mantida junto ao código.

## Entregáveis formais (padrão ABNT — NBR 14724)

Relatório e lista de materiais, com capa, folha de rosto, histórico de
revisões, sumário automático, margens 3-2-3-2cm, fonte Times New Roman 12pt,
espaçamento 1,5.

| Documento | Rev. | Conteúdo |
|---|---|---|
| [relatorio-tecnico-inclinometro.docx](relatorio-tecnico-inclinometro.docx) | 02 | Relatório técnico do projeto: fundamentação teórica, arquitetura do sistema, cálculos e modelagem matemática, protocolos de comunicação, modos de operação e resultados/validação. |
| [lista-de-materiais-hardware.docx](lista-de-materiais-hardware.docx) | 00 | Lista de materiais (BOM): componentes, especificações técnicas, datasheets dos fabricantes, ligações elétricas do sensor e opções de alimentação em avaliação. |

A revisão 01 do relatório técnico acompanha o firmware **1.4.0**: taxa de
amostragem do Modo Vibração de até 500 Hz, retransmissão de amostras perdidas
na transferência via BLE e os dois refinamentos do pipeline de análise
espectral (interpolação do pico em decibéis e piso de ruído medido em janela
local). A revisão 02 acompanha o firmware **1.6.0**: filtro adaptativo
"1-euro" na leitura contínua exibida na tela, e extremos (mín./máx.) medidos
pelo próprio firmware a 100 Hz, em caminho de filtragem separado do caminho
de exibição — ver `firmware/README.md`.

## Procedimentos de teste e instalação (formulário padrão da empresa)

Caixa de identificação (título/tipo/revisão/folha/código/PN) e rodapé de
aprovação (feito por/aprovado por/projeto-contrato/página) em todas as
páginas, fonte Arial, sem capa/sumário separados — modelo fornecido pelo
usuário. Estrutura fixa em 5 seções: Objetivo, Equipamentos e materiais
utilizados, Setup, o procedimento propriamente dito, e Resolução de
problemas.

| Documento | Tipo | Rev. | Conteúdo |
|---|---|---|---|
| [procedimento-teste-funcional-bancada.docx](procedimento-teste-funcional-bancada.docx) | PTE | 00 | Teste funcional completo em bancada: instalação do software desktop (modo notebook), setup de teste e verificação de todos os modos de conexão e funcionalidades, com tabela de registro de resultados e resolução de problemas. |
| [procedimento-instalacao-software-python.docx](procedimento-instalacao-software-python.docx) | PTI | 00 | Instalação e verificação do software desktop (Python/PyQt5) em PC. |
| [procedimento-instalacao-software-android.docx](procedimento-instalacao-software-android.docx) | PTI | 00 | Compilação e instalação do aplicativo Android (Kotlin/Jetpack Compose). |
| [procedimento-gravacao-firmware.docx](procedimento-gravacao-firmware.docx) | PTG | 00 | Compilação e gravação (upload) do firmware do ESP32 via PlatformIO. |

Os códigos de tipo (PTE/PTI/PTG), revisão, folha, código e PN nas caixas de
identificação são inferência própria a partir do modelo mostrado (campos
deixados em branco no original) — ajustar conforme a numeração real da
empresa antes de uso formal.

**Instalação e gravação são sempre em Windows (10/11) e sem internet**, a
partir de mídia arquivada no repositório físico da fábrica, no padrão de
identificação da empresa — CD(1) DAD (Ambiente de Desenvolvimento: Python,
VS Code e pacotes offline), CD(2) DSF (Código Fonte) e CD(3) DSE
(Executável) — não
compilação no local. A compilação em si (Python offline via
`python-app/windows/build_offline_bundle.bat`, o `.apk` do Android, e os
binários do firmware via PlatformIO) é feita à parte, com internet, por
quem mantém cada software, e o resultado é o que vai em cada mídia. O
procedimento de instalação do software Python (seção 4) detalha o
conteúdo de cada CD e como combiná-los. O procedimento de teste funcional
traz um diagrama em blocos do setup de bancada (seção 3).

**Para o operador final (sem conhecimento de programação), o único
caminho de instalação do software Python é o CD(3) DSE via instalador
(Setup.exe)** — cria ícone na Área de Trabalho e no Menu Iniciar, com a
logo da Avibras Aeroco, abrindo por duplo clique como qualquer programa
do Windows. Os caminhos por código-fonte (CD1+CD2) ou pasta executável
solta são só para desenvolvimento/manutenção do software — nenhum dos
dois cria ícone de atalho.

Na gravação de firmware, o `esptool` (standalone, na mídia) precisa estar
acessível pelo **PATH do Windows** na máquina de gravação — o procedimento
traz o passo com `setx PATH` para isso (seção 3, passo 5); sem isso, o
comando `esptool` só funciona se o terminal for aberto exatamente na pasta
onde o executável foi copiado.

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
