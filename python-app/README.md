# Inclinômetro — Software Desktop (PyQt5)

Software desktop para leitura em tempo real dos **dois eixos** do inclinômetro
ESP32 — inclinação (tilt) e azimute (pan) — via Modbus RTU (cabo USB direto)
ou Bluetooth Low Energy (BLE), com registro de limites (mínimo/máximo) por
eixo e geração de relatório em PDF.

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:** use o pacote de instalação pronto em
[`windows/`](windows/INSTALACAO_WINDOWS.md) — instala tudo com um duplo
clique (`windows\install.bat`) e também permite gerar um executável
autônomo, ou um instalador completo (`Setup.exe` com atalhos e
desinstalador) via `windows\build_installer.bat`, que roda em qualquer
computador Windows sem precisar instalar Python.

## Uso

```bash
python main.py
```

Na tela, use **Configurações** para escolher entre:
- **Modo Simulação**: gera ângulos sintéticos (oscilação suave em torno de 60°),
  útil para desenvolver/testar sem o hardware pronto.
- **Real (USB/Modbus RTU)**: conecta via cabo USB direto ao ESP32 (escolha a
  porta serial que o ESP32 aparecer, baud rate e endereço do escravo Modbus).
  Para distâncias maiores que ~5m, use um cabo de extensão USB ativo.
- **Real (Bluetooth BLE)**: conecta via Bluetooth do próprio notebook — use
  **Escanear** para listar dispositivos próximos ou informe o endereço
  manualmente. Requer a biblioteca `bleak` (já incluída no `requirements.txt`),
  que usa o adaptador Bluetooth nativo do computador (sem dongle extra).

Em qualquer um dos modos reais, o botão **"Testar conexão com ESP32"** faz uma
leitura única para confirmar a comunicação antes de iniciar uma sessão —
mostra o ângulo lido e a versão do firmware conectado (verde), ou o erro
específico (vermelho).

O firmware do ESP32 já implementa os dois modos reais (`firmware/`), mas
ainda não foi validado contra hardware físico: USB/Modbus RTU lê o
registrador de entrada Modbus configurado em `data_source/modbus_source.py`;
BLE segue o contrato de serviço/característica documentado em
`data_source/ble_source.py` (o mesmo usado pelo app Android, para os dois
transportes ficarem consistentes).

Também é possível **calibrar** (zerar os dois eixos na posição atual) pelo
botão **Calibrar**, disponível com a leitura em execução — em modo real (USB
ou BLE), envia um comando ao ESP32; em modo simulação, aplica um deslocamento
equivalente aos dados sintéticos. É uma ação só de propósito: o firmware zera
tilt e pan no mesmo comando.

## Os dois eixos

A tela mostra os dois eixos lado a lado, cada um com seu valor em tempo real e
seu par de mínimo/máximo independente:

- **Inclinação (tilt)**, do acelerômetro, faixa -60° a +60°.
- **Azimute (pan)**, do giroscópio integrado com ZUPT no firmware (ver
  "Azimute (pan) pelo giroscópio" em `firmware/README.md`).

Compatibilidade: um ESP32 com firmware anterior à v1.2.0 não mede azimute. O
app detecta isso sozinho e segue funcionando só com a inclinação — o painel de
azimute mostra `--.--°` com a nota "firmware sem este eixo", e o eixo fica de
fora do histórico e do relatório em vez de registrar zeros falsos. No modo
USB/Modbus isso é detectado pela exceção de endereço inválido que o firmware
antigo devolve; no BLE, pela ausência da characteristic de pan.

No modo simulação os dois eixos têm comportamentos diferentes de propósito,
imitando o real: o tilt oscila continuamente com ruído, e o pan fica parado a
maior parte do tempo e se desloca em rajadas — que é justamente o padrão de
uso que torna a medição por giroscópio confiável.

O indicador abaixo do modo mostra o estado da conexão com o ESP32
(conectando/conectado/falha), atualizado a cada leitura ou erro, seja via
USB ou BLE.

## Modo Vibração

A leitura contínua normal (poll a cada ~250ms) é boa para acompanhar o
ângulo, mas lenta demais para caracterizar **vibração** — por exemplo, medir
a variação angular de um pan-tilt sob efeito de vento com o veículo parado.
Para isso existe o botão **"Modo Vibração"**, disponível com a leitura em
execução (habilite calibrando a posição de referência antes, com o botão
**Calibrar**, para que a variação registrada seja relativa a ela):

1. Escolha a **duração** (padrão 30s) e a **taxa de amostragem** (padrão
   50Hz) da captura.
2. O app mostra o progresso enquanto a captura acontece (pode ser cancelada).
3. Ao final, mostra um resumo estatístico: **desvio padrão, RMS, pico a
   pico, mínimo, máximo e a frequência dominante** (com amplitude e SNR —
   ou "nenhum pico confiável" se o sinal for compatível com ruído).
4. Opcionalmente, gera um **relatório em PDF** próprio, com o gráfico da
   variação angular no tempo e o **espectro de frequência (FFT)** — útil
   para identificar uma eventual frequência de ressonância dominante (ex:
   balanço do mastro sob vento), com a frequência dominante marcada no
   gráfico.

A análise espectral (`limits/vibration_stats.py`) segue um pipeline padrão
de processamento de sinais para o resultado ser confiável e fácil de ler:
remoção de tendência linear, janela de Hann (reduz vazamento espectral),
amplitude de um lado só corrigida (valor em graus bate com a amplitude
física real da oscilação) e detecção do pico dominante com interpolação
parabólica (sub-bin) e um limiar de SNR que se ajusta ao número de bins do
espectro (evita falso positivo em sinais só com ruído). O app Android usa
exatamente o mesmo pipeline (`limits/Fft.kt`).

Cada captura é salva separada das sessões de monitoramento contínuo no
histórico (`limits/history_store.py`), para não misturar os dois tipos de
dado. Em modo simulação, a captura gera uma vibração sintética (duas
oscilações de baixa amplitude + ruído) só para exercitar todo o fluxo sem
hardware — em modo real (USB ou BLE), segue o contrato implementado no
firmware, documentado nos módulos `data_source/modbus_source.py` e
`data_source/ble_source.py` (ainda não confirmado/testado com hardware real).

## Identidade visual (Avibras Aeroco)

A interface usa a paleta azul marinho + laranja da Avibras Aeroco
(`ui/main_window.py`, constantes `NAVY`/`ORANGE`). A logo oficial já está
versionada em `assets/logo.jpg` e aparece automaticamente no cabeçalho —
para trocar por um arquivo diferente, basta substituir por `assets/logo.png`,
`assets/logo.jpg` ou `assets/logo.jpeg` (o app procura nessa ordem); sem
nenhum desses, mostra só o título em texto com as mesmas cores.

## Estrutura

```
assets/        logo (assets/logo.jpg)
data_source/   fontes de dados de ângulo (simulada, Modbus RTU via USB e BLE real)
limits/        rastreamento de limites (mín/máx) e histórico persistente (SQLite)
ui/            janela principal e diálogo de configurações (PyQt5)
report/        geração de relatório em PDF a partir do histórico
```
