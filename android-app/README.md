# Inclinômetro — App Android (Kotlin)

App Android para leitura em tempo real da inclinação do inclinômetro ESP32,
via BLE, com registro de limites (mínimo/máximo), calibração, Modo Vibração
e geração de relatório em PDF — equivalente ao software desktop em PyQt5,
na mesma experiência, e ao firmware em `firmware/`.

## Requisitos

- Android Studio (Koala ou mais recente) com Android SDK 34 instalado.
- JDK 17.

## Abrir o projeto

Abra a pasta `android-app/` no Android Studio ("Open" → selecione esta
pasta). O Android Studio vai baixar as dependências (AndroidX, Compose,
Room) e configurar o SDK automaticamente na primeira sincronização.

> Este projeto foi criado fora do Android Studio (sem Android SDK disponível
> no ambiente de desenvolvimento usado), então **ainda não foi compilado
> com o Gradle/AGP real**. Como verificação parcial, o algoritmo de FFT
> (`limits/Fft.kt`) foi extraído e testado isoladamente com `kotlinc` puro
> (sem dependências Android) contra um sinal senoidal conhecido, confirmando
> que identifica a frequência dominante corretamente — o resto do código
> (Compose, BLE, Room) foi revisado manualmente, mas a primeira
> sincronização no Android Studio é o jeito confiável de confirmar que
> compila — abra o projeto lá antes de dar como validado.

## Uso

Na tela, escolha entre:
- **Simulação**: gera ângulos sintéticos (mesmos parâmetros do app desktop),
  para desenvolver/testar sem hardware.
- **Real (BLE)**: informe o endereço MAC do inclinômetro ESP32 (ainda não há
  tela de scan/pareamento dedicada — meta para uma próxima etapa). O app
  segue o contrato BLE definido em `datasource/BleContract.kt`, o mesmo
  implementado no firmware (`firmware/src/BleServer.cpp`).

O indicador de conexão mostra o estado (conectando/conectado/falha), a
exemplo do app desktop.

Com a leitura em execução, o botão **Calibrar** zera o eixo de tilt na
posição atual (envia comando ao ESP32 em modo real; aplica um deslocamento
equivalente em modo simulação).

O botão **Modo Vibração** faz uma captura em alta taxa configurável
(duração + taxa de amostragem), útil para caracterizar variação angular por
vento/vibração — ao final, mostra desvio padrão/RMS/pico-a-pico e permite
salvar um relatório em PDF com o gráfico no tempo e o espectro de frequência
(FFT). Cada captura fica salva separada das sessões de monitoramento
contínuo no histórico.

O modo real (BLE) segue o mesmo contrato implementado no firmware do ESP32
(`firmware/`), mas ainda não foi validado contra hardware físico.

## Identidade visual (Avibras Aeroco)

A interface usa a paleta azul marinho + laranja da Avibras Aeroco
(`ui/theme/Color.kt`), mesma identidade do app desktop. Para exibir uma
logo no cabeçalho, adicione um recurso `res/drawable/logo.png` (ou
`.xml`/vetor) — se não existir, o app mostra só o título em texto com as
mesmas cores (checagem em tempo de execução, via
`resources.getIdentifier`).

## Estrutura

```
datasource/    fontes de dados de ângulo (simulada e BLE real) + contrato BLE
limits/        rastreamento de limites (mín/máx), histórico persistente (Room/SQLite),
               estatísticas/FFT de vibração
ui/            ViewModel + tela principal (Jetpack Compose)
report/        geração de relatório em PDF nativo (PdfDocument), sem dependência externa
```
