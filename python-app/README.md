# Inclinômetro — Software Desktop (PyQt5)

Software desktop para leitura em tempo real da inclinação do inclinômetro ESP32,
via RS485/Modbus RTU ou Bluetooth Low Energy (BLE), com registro de limites
(mínimo/máximo) e geração de relatório em PDF.

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
- **Modo Simulação**: gera ângulos sintéticos (oscilação suave em torno de 60°),
  útil para desenvolver/testar sem o hardware pronto.
- **Real (RS485/Modbus RTU)**: conecta via porta serial (escolha porta, baud rate
  e endereço do escravo Modbus).
- **Real (Bluetooth BLE)**: conecta via Bluetooth do próprio notebook — use
  **Escanear** para listar dispositivos próximos ou informe o endereço
  manualmente. Requer a biblioteca `bleak` (já incluída no `requirements.txt`),
  que usa o adaptador Bluetooth nativo do computador (sem dongle extra).

Em qualquer um dos modos reais, o botão **"Testar conexão com ESP32"** faz uma
leitura única para confirmar a comunicação antes de iniciar uma sessão —
mostra o ângulo lido (verde) ou o erro específico (vermelho).

O firmware do ESP32 ainda não existe nesta fase do projeto — os dois modos
reais estão prontos para quando ele estiver disponível: RS485 lê o registrador
de entrada Modbus configurado em `data_source/modbus_source.py`; BLE segue o
contrato de serviço/característica documentado em `data_source/ble_source.py`
(o mesmo usado pelo app Android, para os dois transportes ficarem consistentes).

Também é possível **calibrar** (zerar o eixo de tilt do acelerômetro na posição
atual) pelo botão **Calibrar**, disponível com a leitura em execução — em modo
real (RS485 ou BLE), envia um comando ao ESP32; em modo simulação, aplica um
deslocamento equivalente aos dados sintéticos.

O indicador abaixo do modo mostra o estado da conexão com o ESP32
(conectando/conectado/falha), atualizado a cada leitura ou erro, seja via
RS485 ou BLE.

## Identidade visual (Avibras Aeroco)

A interface usa a paleta azul marinho + laranja da Avibras Aeroco
(`ui/main_window.py`, constantes `NAVY`/`ORANGE`). Para exibir a logo no
cabeçalho, coloque o arquivo em `assets/logo.png` (PNG com fundo
transparente) — se o arquivo não existir, o app mostra só o título em texto
com as mesmas cores.

## Estrutura

```
assets/        logo (assets/logo.png, não versionado — ver acima)
data_source/   fontes de dados de ângulo (simulada, Modbus RTU real e BLE real)
limits/        rastreamento de limites (mín/máx) e histórico persistente (SQLite)
ui/            janela principal e diálogo de configurações (PyQt5)
report/        geração de relatório em PDF a partir do histórico
```
