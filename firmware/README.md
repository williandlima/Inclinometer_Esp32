# Firmware — Inclinômetro ESP32

**Versão atual: `1.4.0`** (`firmware/src/Config.h`, `FIRMWARE_VERSION`) —
exposta em runtime tanto por Modbus (input register `REG_FIRMWARE_VERSION`)
quanto por BLE (characteristic `CHAR_FIRMWARE_VERSION_UUID`), como inteiro
`major*10000 + minor*100 + patch` (`FIRMWARE_VERSION_CODE`; ex: `1.0.0` →
`10000`). Bump manual em `Config.h` a cada mudança relevante de contrato ou
comportamento — sem isso os apps não têm como saber qual versão do firmware
estão falando.

Firmware do ESP32 que expõe os **dois eixos** medidos pelo MPU6050 — a
inclinação (**tilt**, pelo acelerômetro) e o azimute (**pan**, pelo
giroscópio; ver "Azimute (pan)" abaixo) — tanto por **Modbus RTU via cabo
USB direto** quanto por **Bluetooth LE**, simultaneamente, seguindo os
contratos já assumidos e documentados nos dois apps:

- `python-app/data_source/modbus_source.py` (Modbus RTU / USB)
- `python-app/data_source/ble_source.py` (BLE)
- `android-app/app/.../datasource/BleContract.kt` (BLE)

A comunicação com o PC usa a porta serial USB nativa do ESP32 (a mesma já
usada para gravar o firmware) — **não usa RS485**. Essa decisão foi tomada
porque a distância até o painel de controle (~7m, no mastro do pan-tilt)
excede o alcance confiável de USB simples (~5m), mas um **cabo de extensão
USB ativo** (com amplificador de sinal embutido, vendido pronto para
10-20m) resolve isso sem precisar de RS485/transceptor/terminação de
barramento.

## Estrutura

```
firmware/
  platformio.ini
  src/
    main.cpp             setup()/loop(), instancia e conecta os módulos abaixo
    Config.h              pinagem + constantes de protocolo (Modbus/BLE)
    Mpu6050.h/.cpp         driver I2C mínimo do MPU6050 (sem lib externa)
    AngleSensor.h/.cpp     tilt por atan2 do acelerômetro + calibração (offset)
    PanSensor.h/.cpp       pan por integração do giroscópio + ZUPT
    VibrationCapture.h/.cpp  motor de captura em alta taxa, compartilhado
                             pelos dois transportes
    ModbusSlave.h/.cpp    escravo Modbus RTU sobre a porta serial USB (UART0)
    BleServer.h/.cpp      servidor BLE (GATT)
```

## Pinagem (ESP32 DevKit clássico / WROOM-32)

Hardware confirmado: placa **ESP32 DevKit clássico (WROOM-32)**, com chip
conversor USB-serial **CH9102X** (WCH) — mapeamento definido, refletido em
`firmware/src/Config.h`. Como a comunicação com o PC vai pela porta USB
nativa do ESP32, o único hardware extra é o MPU6050:

| Sinal | Pino ESP32 | Vai para | Observação |
|---|---|---|---|
| SDA | GPIO 21 | SDA do MPU6050 | Padrão I2C do ESP32 |
| SCL | GPIO 22 | SCL do MPU6050 | Padrão I2C do ESP32 |
| — | 3.3V | VCC do MPU6050 | Não usar 5V (linhas I2C ficam em 5V e podem danificar o ESP32) |
| — | GND | GND do MPU6050 | |
| — | GND | AD0 do MPU6050 | Fixa endereço I2C em `0x68` (o que `Mpu6050.h` assume) |

Se o hardware definitivo usar uma variante diferente do ESP32 (S3, C3,
etc.), os pinos podem precisar de ajuste — essas variantes têm GPIOs
restritos diferentes do WROOM-32 clássico assumido aqui.

A fórmula do ângulo em `AngleSensor.cpp` (`atan2(ay, az)`) assume uma
orientação de montagem do MPU6050 já **recomendada, mas ainda não
confirmada fisicamente**: eixo X do sensor alinhado ao eixo mecânico de
giro do pan-tilt, com a rotação de -60° a +60° acontecendo no plano Y-Z (os
dois eixos usados no `atan2`). Essa combinação mantém a sensibilidade da
leitura quase constante em toda a faixa — sem a zona de baixa sensibilidade
que um único eixo teria perto de 90°, o que é essencial para o **Modo
Vibração** detectar variações de frações de grau em torno do zero
calibrado. Ver "Orientação de montagem do sensor" em `docs/pinout.md`
para o detalhamento e o teste de bancada de confirmação.

## Contrato implementado

### Modbus RTU via USB (escravo, ID configurável em `Config.h`, padrão 1)

Trafega pela mesma porta serial que aparece no PC como uma porta COM/tty
normal quando o ESP32 é conectado por USB — o app desktop (`python-app`)
já espera exatamente isso (não faz distinção entre "porta serial real" e
"porta serial via USB do ESP32", já que ambas são portas seriais comuns do
ponto de vista do `pyserial`).

| Registrador | Tipo | Função |
|---|---|---|
| Input reg. 0 | leitura | Ângulo de **tilt** * 100 (int16, com sinal, faixa -60~+60°) |
| Input reg. 1 | leitura | Ângulo de **pan** * 100 (int16, com sinal, faixa `PAN_MIN_DEG`~`PAN_MAX_DEG`) |
| Coil 0 | escrita | `true` → calibra (zera **os dois eixos**, tilt e pan) |
| Coil 1 | escrita | `true` → inicia captura de vibração |
| Holding reg. 10 | escrita | Duração da captura (s) |
| Holding reg. 11 | escrita | Taxa de amostragem (Hz) |
| Input reg. 20-22 | leitura | Status / progresso (%) / total de amostras da captura |
| Holding reg. 30 | escrita | Cursor (índice inicial do bloco a ler) — vale para os dois eixos |
| Input reg. 31-62 | leitura | Bloco de até 32 amostras de **tilt** (int16, ângulo relativo * 100) |
| Input reg. 70-101 | leitura | Bloco de até 32 amostras de **pan** (int16, **velocidade angular** em °/s * 100) |
| Input reg. 40 | leitura | Versão do firmware (`FIRMWARE_VERSION_CODE`, ver acima) |

### BLE (serviço `6e6e0001-...`)

| Characteristic | Propriedade | Função |
|---|---|---|
| `6e6e0002-...` (tilt) | read/notify | Ângulo de tilt * 100 (int16 LE, com sinal, faixa -60~+60°), a cada ~200ms |
| `6e6e0003-...` (calibrar) | write | Byte `0x01` → calibra **os dois eixos** |
| `6e6e0004-...` (config vibração) | write | 4 bytes LE: duração(s) + taxa(Hz) → inicia captura |
| `6e6e0005-...` (status vibração) | notify | status/progresso/total de amostras |
| `6e6e0006-...` (dados vibração) | notify | Amostras em pacotes (índice + até 8 amostras int16 LE) |
| `6e6e0007-...` (versão firmware) | read | `FIRMWARE_VERSION_CODE` (uint16 LE, ver acima) — valor fixo, sem notify |
| `6e6e0008-...` (pan) | read/notify | Ângulo de pan * 100 (int16 LE, com sinal), na mesma cadência do tilt |
| `6e6e0009-...` (dados vibração pan) | notify | Amostras de pan em pacotes (índice + até 8 int16 LE), em **velocidade angular** °/s * 100 |

O pan entrou numa characteristic própria, e não anexado à de tilt, de
propósito: os apps já instalados esperam exatamente 2 bytes em
`6e6e0002-...`, então estender aquela mensagem os quebraria. Do jeito que
está, a mudança é puramente aditiva — um app que não conhece
`6e6e0008-...` simplesmente a ignora e continua funcionando como antes.

Detalhes byte a byte de cada mensagem estão comentados no topo de
`ModbusSlave.cpp`/`BleServer.cpp` e nos módulos Python/Kotlin equivalentes.

## Build

Projeto [PlatformIO](https://platformio.org/), ambiente `esp32dev`
(framework Arduino, sem bibliotecas externas — só o que já vem com o core
`espressif32`: `Wire`, UART, e a lib BLE clássica `BLEDevice`).

```bash
cd firmware
pio run              # compila
pio run -t upload    # compila e grava no ESP32 conectado por USB
pio device monitor    # abre o monitor serial (115200 baud)
```

**Não foi possível compilar neste ambiente de desenvolvimento**: o
`pio run` precisa baixar o toolchain/plataforma `espressif32` da internet
na primeira vez, e o acesso de rede deste sandbox bloqueia esse download
(mesma limitação de rede já encontrada antes neste projeto, ex: para
baixar a logo da Avibras Aeroco). O código foi revisado manualmente com
cuidado (tipos, includes, formato de cada mensagem confrontado byte a byte
com os módulos Python/Kotlin), mas **precisa ser compilado e testado em
hardware real** antes de considerar o firmware pronto — nem a lógica de
sensor, nem os protocolos Modbus RTU (via USB)/BLE foram validados contra
hardware físico.

## Estabilidade da leitura (v1.1.0)

Nos primeiros testes com hardware real a leitura não parava de variar nos
centésimos de grau. Eram duas causas, as duas no firmware:

1. **O filtro passa-baixa interno do MPU6050 nunca era configurado.** O chip
   liga com `DLPF_CFG=0`, ou seja, 260Hz de banda passante no acelerômetro —
   praticamente sem filtro. Todo o ruído mecânico/térmico de alta frequência
   entrava em cada amostra. Isso ainda causava **aliasing** no Modo Vibração:
   amostrando a 50Hz (Nyquist 25Hz) um sinal de 260Hz de banda, o ruído acima
   de 25Hz era rebatido para dentro da faixa medida e sujava a FFT. Agora
   `Mpu6050::begin()` configura `DLPF_CFG=4` (21Hz), que corta esse ruído no
   hardware e serve de anti-aliasing, ainda deixando passar com folga as
   frequências de interesse do ensaio (1-5Hz).
2. **A leitura contínua não tinha filtragem nenhuma.** Cada leitura Modbus /
   notify BLE disparava uma única amostra instantânea direto no `atan2`.
   Agora `AngleSensor::update()` (chamado no `loop()`) amostra o sensor a
   100Hz e mantém uma média móvel exponencial com constante de tempo de 0.5s
   (`ANGLE_FILTER_TIME_CONSTANT_S`), e é esse valor filtrado que
   `readAngleDeg()` devolve.

**O Modo Vibração não passa por esse filtro, de propósito** — é justamente
ali que a sensibilidade a frações de grau é o objetivo. A captura continua
usando `readRelativeAngleDeg()`, que faz uma leitura instantânea a cada
amostra. Os dois caminhos estão separados em `AngleSensor.h`.

A calibração também passou a usar o valor filtrado em vez de uma amostra
isolada, ficando repetível mesmo com o sensor sob vibração.

Do lado dos apps, a exibição do valor em tempo real é arredondada para
degraus de 0,25° com histerese (evita alternar entre dois degraus quando o
valor fica na fronteira). Isso é só apresentação: histórico, mín/máx e
relatórios continuam usando o ângulo bruto.

## Azimute (pan) pelo giroscópio (v1.2.0)

O acelerômetro mede a direção do vetor gravidade — e girar em torno da
vertical **não muda esse vetor**. Ele é fisicamente cego ao pan; não é
questão de código. Mas o MPU6050 é 6-DOF: o **giroscópio** que já estava na
placa (e que o firmware não configurava nem lia até a v1.1.0) mede
velocidade angular em torno de qualquer eixo, inclusive o vertical.
Integrando essa taxa sai o ângulo de pan relativo ao zero calibrado — mesmo
paradigma que o tilt já usa. **Nenhum hardware novo foi adicionado.**

O problema clássico de integrar giro é o drift: um bias residual vira uma
rampa de graus por minuto. O que torna a abordagem confiável aqui é o padrão
de uso — o eixo de pan fica **parado a maior parte do tempo** e se move em
rajadas de poucos segundos — combinado com **ZUPT**. Quatro mecanismos
trabalham juntos em `PanSensor.h/.cpp` (cada um documentado em detalhe no
cabeçalho do header):

1. **Compensação de tilt.** O sensor está na parte que inclina, então o eixo
   Z dele não aponta pra vertical. Pegar `gz` cru subestimaria a taxa por
   `cos(tilt)` — a 60° de tilt a leitura sairia pela metade. A taxa correta é
   a projeção sobre a vertical escrita em coordenadas do corpo:
   `ω_pan = gz·cos(θ) − gy·sin(θ)`, com `θ` vindo do **mesmo burst I2C**.
   Por ser uma projeção (produto escalar), e não a fórmula de taxa de Euler
   `(gy·sinφ + gz·cosφ)/cosθ`, não há singularidade em nenhum tilt.
2. **ZUPT.** A cada 1s, se a **média** da taxa na janela estiver perto do
   bias corrente, a janela é dada como parada e o bias é refinado. Usar a
   média (e não o pico) deixa o detector imune a vibração, que é de média
   zero: o mastro pode estar balançando sob vento que a janela ainda é
   corretamente reconhecida como parada.
3. **Cancelamento de janela parada.** O que foi integrado dentro de uma
   janela classificada como parada é subtraído de volta — parado, o ângulo
   fica cravado, sem random walk.
4. **Fator de escala** (`PAN_SCALE_CORRECTION`). Resolvido o bias, o erro
   dominante vira a tolerância de sensibilidade do giro (~±3% de fábrica).
   Ele é proporcional ao **deslocamento atual** em relação ao zero — não se
   acumula com o tempo nem com o número de movimentos — e some quando o eixo
   volta ao zero.

### Validação feita até agora

O `PanSensor.cpp` real foi compilado contra um MPU6050 falso e exercitado com
sinais sintéticos (bias de fábrica de 5°/s, ruído, vibração, tilt fixo):

| Cenário | Resultado |
|---|---|
| Parado 60s com bias de 5°/s | 0,003° de deriva |
| Movimento de 60° e 30s parado depois | 60,003° |
| Parado 60s sob vibração de 3°/s de pico | 0,004° de deriva |
| 60° de pan com o sensor a 60° de tilt | 60,02° (sem a compensação daria 30°) |
| 40 movimentos de ±45°, voltando ao zero | 0,066° de erro residual |

O piso de detecção medido bate com o previsto (`limiar × janela` = 1°/s × 1s):
movimentos de até ~1° são descartados como ruído, e a partir de ~2° são
preservados integralmente.

**Isso valida a matemática, não o hardware.** Falta rodar contra o MPU6050
real — ver as duas confirmações de bancada nas limitações abaixo.

## Modo Vibração no eixo de pan (v1.3.0)

A captura de vibração agora amostra os dois eixos. Mas eles carregam
**grandezas diferentes**, e a razão é o próprio ZUPT:

- **tilt**: o ângulo relativo à calibração, em graus;
- **pan**: a **velocidade angular**, em graus/s.

Guardar o ângulo de pan integrado não funcionaria. O ângulo de pan sai da
integração com ZUPT, e o mecanismo 3 acima *cancela de propósito* o que foi
integrado enquanto o eixo está parado — que é exatamente a condição de um
ensaio de vibração. O firmware apagaria o sinal que se quer medir. A
velocidade angular não passa por integração nem por cancelamento, e ainda
deixa o bias residual concentrado em 0 Hz, onde a análise espectral já o
descarta por construção.

Os apps integram (regra do trapézio) e removem a tendência linear — o bias é
uma constante somada à taxa, e integrar constante dá exatamente uma rampa,
que a reta ajustada elimina.

### Um detalhe que quase virou bug

A detecção de frequência dominante compara o pico com a **mediana** do
espectro, o que só é justo se o piso de ruído for plano. No tilt é: o ruído
do acelerômetro é branco no ângulo. No pan **não é**: o ruído do giroscópio é
branco na *taxa*, e integrar ruído branco dá um passeio aleatório, cujo
espectro cai com 1/f². Nessa forma a mediana global fica dominada pelas
frequências altas, e qualquer bin de baixa frequência vira um "pico" enorme.

Em teste, com a primeira versão do código, **ruído puro era apontado como
frequência dominante em 100% das tentativas** (0,37 Hz, com folga de SNR).
A correção foi rodar a detecção do pico no espectro da *taxa* — onde o ruído
é branco de verdade — e converter só a amplitude do pico para graus, por
`A = R(f) / (2·pi·f)`. Por isso as amostras de pan guardam as duas séries: a
taxa (para a detecção) e o ângulo integrado (para os gráficos no tempo e as
estatísticas). Depois da correção: 0 falsos positivos em 48 capturas de
ruído puro em 4 durações diferentes, mantendo 30/30 de detecção de sinal
real, inclusive com amplitude de 0,02°.

## Sensibilidade da leitura contínua (v1.4.0)

O filtro da leitura contínua deixou de ser uma média móvel exponencial de
constante fixa (0,5s) e passou a ser um **filtro adaptativo "1-euro"**
(Casiez et al.): a frequência de corte sobe quando o ângulo está mudando de
verdade e desce quando o eixo está parado.

O motivo é que, com constante de tempo fixa, estabilidade e rapidez são um
cabo de guerra — mais suave é sempre mais lento. Separando os dois regimes dá
para ganhar nos dois. Medido em simulação da cadeia completa (ruído do
MPU6050 → DLPF de 21Hz → `atan2` → filtro), com o eixo parado e depois com
uma rampa real de 10°:

| | média móvel (0,5s) | 1-euro adaptativo |
|---|---|---|
| Ruído com o eixo parado | 0,016° RMS | **0,005° RMS** |
| Atraso p/ acompanhar 90% de um movimento | 0,63 s | **0,21 s** |

Ou seja, ~3x menos ruído **e** ~3x mais rápido — não é troca.

**O degrau de exibição continua em 0,25°**, o mesmo da versão 1 — é requisito,
e mantém a comparação entre as duas versões direta. Com esse degrau a tela já
era estável com o filtro antigo (meio degrau é muito maior que o ruído), então
o ganho do filtro novo **não aparece na estabilidade da tela**: aparece em
duas outras coisas.

**1. O mín/máx e o relatório ficam mais limpos.** Eles usam o ângulo bruto, não
o degrau da tela — e extremos são justamente o que o ruído mais infla. Numa
sessão de 10 min com o eixo *parado*, a faixa mín/máx registrada:

| | média móvel (0,5s) | 1-euro adaptativo |
|---|---|---|
| Faixa falsa, só de ruído | 0,120° | **0,040°** |

**2. A tela assenta mais rápido no degrau certo** depois de um movimento:
1,75s → 1,50s no ruído nominal, e 1,75s → 0,75s com 3x o ruído.

### De onde vem o ruído, e o que NÃO adiantaria mexer

| Etapa | Contribuição |
|---|---|
| Acelerômetro após o DLPF de 21Hz | 2,2 mg |
| Ângulo cru, via `atan2` | 0,127° RMS |
| Após o filtro adaptativo | **0,005° RMS** |
| Quantização do protocolo (0,01°) | 0,003° — desprezível |

Duas coisas que pareceriam melhorias e não são:

- **Baixar o DLPF do MPU6050** (de 21Hz para 5Hz) cortaria o ruído pela
  metade antes mesmo do filtro. Mas o DLPF é compartilhado com o Modo
  Vibração, que precisa da banda até ~5Hz e usa os 21Hz como anti-aliasing
  a 50 amostras/s. Cortar ali destruiria o ensaio de vibração.
- **Aumentar a resolução do protocolo** (`ANGLE_SCALE` acima de 100) não
  ajuda: a quantização de 0,01° já contribui menos que o ruído do sensor.

O caminho que sobra, se um dia precisar de mais, é reduzir o
`ANGLE_FILTER_MIN_CUTOFF_HZ` — ao custo de o filtro demorar mais para
assentar depois de um movimento.

## Limitações conhecidas / próximos passos

- **[1.4.0] O filtro adaptativo não foi confirmado em hardware.** Os números
  acima vêm de simulação da cadeia, e o código real do `AngleSensor.cpp` foi
  conferido contra essa simulação (bate até 8e-6°, só arredondamento de
  `float`). Mas ruído real inclui vibração mecânica, montagem e temperatura,
  que a simulação não modela. Se a leitura tremular no ESP32 real, o primeiro
  ajuste é baixar `ANGLE_FILTER_MIN_CUTOFF_HZ`; se ficar lenta demais para
  acompanhar o movimento, subir `ANGLE_FILTER_BETA`.

- **[1.3.1]** O ESP32 não voltava a anunciar por BLE depois que um cliente
  desconectava. O rádio para de anunciar sozinho ao aceitar uma conexão, e a
  lib BLE do Arduino não retoma o anúncio na desconexão — resultado: o
  dispositivo sumia do scan até ser resetado na mão. Aparecia ao trocar de
  app, ou só ao reabrir o mesmo app, e parecia defeito de hardware. Agora
  `BleServer` registra um `BLEServerCallbacks` que marca a desconexão, e o
  anúncio é reiniciado no `loop()` — e não dentro do próprio callback, que
  roda na task do stack BLE, onde essa chamada tende a falhar em silêncio.

- **[1.2.0] Faixa do pan é placeholder.** `PAN_MIN_DEG`/`PAN_MAX_DEG` estão
  em ±90° até a mecânica do pan estar definida. Só limita o valor
  reportado — o integrador interno não é clampado, então voltar para dentro
  da faixa recupera a leitura correta.
- **[1.2.0] `PAN_SCALE_CORRECTION` ainda em 1.0.** Calibração de bancada
  pendente: girar o eixo entre duas posições de separação angular conhecida
  e usar `(ângulo real / integrado)`. Sem isso, sobra a tolerância de
  fábrica do giro (~±3%, ou ~2,7° no extremo de um curso de ±90°).
- **[1.2.0] Sinal do termo de compensação de tilt a confirmar.** O termo
  `−gy·sin(θ)` depende da handedness real da montagem. Perto de `θ=0` ele
  some (só sobra `gz·cos θ`), então um sinal trocado **não apareceria** nos
  testes feitos com o tilt zerado — testar panning com o tilt em ±45°/±60° e
  conferir se bate com a mesma medida feita em `θ=0`. Resolve junto com a
  confirmação de montagem do `atan2(ay, az)`, que já estava pendente.
- **[1.2.0] Boot com o eixo em movimento estraga o bias inicial.** A
  primeira janela de ZUPT é aceita sem limiar (o zero-rate de fábrica do
  MPU6050 chega a ±20°/s e nenhum limiar razoável o aceitaria), ou seja,
  assume-se o sensor parado ao ligar. Se não estiver, o bias sai errado e as
  janelas paradas seguintes passam a ser rejeitadas. **Pressionar Calibrar
  com o eixo parado recupera** — `PanSensor::calibrate()` refaz a estimativa
  do zero do giro junto com o zero do ângulo (confirmado em teste).
- **[1.2.0] Movimentos menores que ~1° são descartados** como ruído, por
  causa do cancelamento de janela parada. É o compromisso da abordagem:
  ajustável em `PAN_ZUPT_RATE_THRESHOLD_DPS`/`PAN_ZUPT_WINDOW_MS`, ao custo
  de uma estimativa de bias pior.
- **[1.2.0] Mudança de tilt durante o pan** desloca ligeiramente o bias
  projetado (o bias é estimado sobre a taxa já projetada, que depende de
  `θ`). Irrelevante no uso normal, em que o tilt fica aproximadamente fixo
  enquanto se mede pan; a janela de ZUPT seguinte reabsorve a diferença.
- **[1.3.0] Memória do buffer de captura dobrou** para ~24KB (dois buffers
  de `VIBRATION_MAX_SAMPLES` int16, em `VibrationCapture.h`). Cabe com folga
  no ESP32 mesmo com o stack BLE ativo, mas é o maior consumo de RAM do
  firmware — é aqui que o limite aperta se um dia precisar de capturas mais
  longas.
- **[1.3.0] Carga do barramento I2C subiu**: durante uma captura de vibração
  são duas transações por amostra (tilt e pan), somadas às do loop contínuo.
  Na taxa padrão de 50Hz a ocupação fica em torno de 40% a 100kHz, com folga
  confortável. Em taxas de amostragem bem mais altas isso pode apertar — a
  saída é subir o barramento para 400kHz (`Wire.setClock`), que o MPU6050
  suporta. Não foi feito de propósito: mexeria numa temporização já validada
  em hardware sem necessidade comprovada.
- **[1.2.0] Os dois apps já consomem o pan** (Modbus reg. 1 e BLE
  `6e6e0008-...`), com segundo display, segundo par de mín/máx e segundo
  gráfico no relatório. Ambos detectam sozinhos um ESP32 com firmware
  anterior à v1.2.0 e seguem só com a inclinação, sem gravar zeros falsos.
- **[1.0.2]** Faixa de medição mudou de 0°~120° para -60°~+60° (0° agora é
  a posição calibrada, não mais um extremo mecânico). Isso muda a
  codificação do ângulo em `REG_ANGLE_INPUT` (Modbus) e na characteristic
  de ângulo (BLE): antes era sempre não-negativo, agora é `int16` com
  sinal — os dois apps (`modbus_source.py`/`ble_source.py`,
  `BleAngleDataSource.kt`) já foram atualizados pra decodificar como
  valor com sinal. Firmware em si não mudou nada na codificação (o cast
  pra `uint16_t` já produzia o padrão de bits correto em complemento de
  dois para valores negativos) — só os limites `ANGLE_MIN_DEG`/
  `ANGLE_MAX_DEG` em `Config.h`.
- **[1.0.1]** `BleServer::updateVibrationNotify()` notificava o status
  "pronto" da captura de vibração *antes* de terminar de transmitir todas
  as amostras pela characteristic de dados, e chamava `notify()` sem
  nenhum controle de taxa (a cada iteração do `loop()`) — o app Python
  (`ble_source.py`) libera o resultado assim que recebe o "pronto", então
  isso causava dados truncados/perdidos no Modo Vibração via BLE, além do
  risco de sobrecarregar a fila de notificação do BLE numa captura longa.
  Corrigido: agora os dados são enviados primeiro (com um intervalo mínimo
  de `BLE_VIBRATION_CHUNK_INTERVAL_MS` entre pacotes) e o "pronto" só é
  notificado depois que o último bloco foi enviado; o status/progresso
  durante a captura também passou a ser limitado por
  `BLE_VIBRATION_STATUS_NOTIFY_INTERVAL_MS`. Ainda não validado contra
  hardware real (só revisão de código) — atenção especial a isso ao testar
  o Modo Vibração via BLE.
- Buffer de captura de vibração limitado a `VIBRATION_MAX_SAMPLES = 6000`
  amostras (~12KB de RAM) — captura pedida além disso é truncada
  silenciosamente (menos amostras que o solicitado, mas sem erro).
- Calibração não é persistida entre reboots (offset fica só em RAM).
- Framing Modbus RTU usa um timeout fixo simplificado (5ms de silêncio)
  para detectar fim de frame, em vez do cálculo exato de 3.5 caracteres
  do padrão — funciona bem na baudrate usada no projeto (9600), mas pode
  precisar de ajuste fino em baudrates mais altas.
- A UART0 (porta USB) fica dedicada ao protocolo Modbus RTU — não há canal
  de log/debug separado disponível hoje (ver comentário em `main.cpp`).
- Orientação de montagem do sensor tem recomendação definida (eixo X no
  giro, plano Y-Z), mas confirmação física em bancada ainda pendente,
  como descrito acima (a pinagem em si já está definida).
- Para o cabo até o painel de controle (~7m), use um **cabo de extensão
  USB ativo** — USB simples sem amplificação só é confiável até uns 5m.
