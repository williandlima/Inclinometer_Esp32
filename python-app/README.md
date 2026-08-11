# Inclinômetro — Software Desktop (PyQt5)

Software desktop para leitura em tempo real da inclinação do inclinômetro ESP32,
via RS485/Modbus RTU, com registro de limites (mínimo/máximo) e geração de
relatório em PDF.

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

```bash
python main.py
```

Na tela, use **Configurações** para escolher entre:
- **Modo Simulação**: gera ângulos sintéticos (oscilação + ruído entre 0° e 120°),
  útil para desenvolver/testar sem o hardware pronto.
- **Modo Real**: conecta via RS485/Modbus RTU (escolha a porta serial, baud rate e
  endereço do escravo Modbus).

O firmware do ESP32 ainda não existe nesta fase do projeto — o modo real está
pronto para quando ele estiver disponível, lendo o ângulo do registrador de
entrada Modbus configurado em `data_source/modbus_source.py`.

Também é possível **calibrar** (zerar o eixo de tilt do acelerômetro na posição
atual) pelo botão **Calibrar**, disponível com a leitura em execução — em modo
real, envia um comando ao ESP32 via Modbus (contrato documentado em
`data_source/modbus_source.py`); em modo simulação, aplica um deslocamento
equivalente aos dados sintéticos.

O indicador abaixo do modo mostra o estado da conexão RS485 com o ESP32
(conectando/conectado/falha), atualizado a cada leitura ou erro do Modbus.

## Identidade visual (Avibras Aeroco)

A interface usa a paleta azul marinho + laranja da Avibras Aeroco
(`ui/main_window.py`, constantes `NAVY`/`ORANGE`). Para exibir a logo no
cabeçalho, coloque o arquivo em `assets/logo.png` (PNG com fundo
transparente) — se o arquivo não existir, o app mostra só o título em texto
com as mesmas cores.

## Estrutura

```
assets/        logo (assets/logo.png, não versionado — ver acima)
data_source/   fontes de dados de ângulo (simulada e Modbus RTU real)
limits/        rastreamento de limites (mín/máx) e histórico persistente (SQLite)
ui/            janela principal e diálogo de configurações (PyQt5)
report/        geração de relatório em PDF a partir do histórico
```
