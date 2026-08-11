# Inclinômetro — App Android (Kotlin)

App Android para leitura em tempo real da inclinação do inclinômetro ESP32,
via BLE, com registro de limites (mínimo/máximo) e geração de relatório em
PDF — equivalente ao software desktop em PyQt5, na mesma experiência.

## Requisitos

- Android Studio (Koala ou mais recente) com Android SDK 34 instalado.
- JDK 17.

## Abrir o projeto

Abra a pasta `android-app/` no Android Studio ("Open" → selecione esta
pasta). O Android Studio vai baixar as dependências (AndroidX, Compose,
Room) e configurar o SDK automaticamente na primeira sincronização.

> Este projeto foi criado fora do Android Studio (sem Android SDK disponível
> no ambiente de desenvolvimento usado), então **ainda não foi compilado**
> aqui. A estrutura segue os padrões oficiais do Gradle/AGP + Kotlin +
> Compose, mas a primeira sincronização no Android Studio é o jeito
> confiável de confirmar que compila — abra o projeto lá antes de dar como
> validado.

## Uso

Na tela, escolha entre:
- **Simulação**: gera ângulos sintéticos (mesmos parâmetros do app desktop),
  para desenvolver/testar sem hardware.
- **Real (BLE)**: informe o endereço MAC do inclinômetro ESP32 (ainda não há
  tela de scan/pareamento dedicada — meta para uma próxima etapa). O app
  espera o contrato BLE definido em `datasource/BleContract.kt`.

O firmware do ESP32 ainda não existe nesta fase do projeto — o modo real já
está implementado (conexão GATT, notificação de ângulo) seguindo esse
contrato, pronto para quando o firmware existir.

## Estrutura

```
datasource/    fontes de dados de ângulo (simulada e BLE real) + contrato BLE
limits/        rastreamento de limites (mín/máx) e histórico persistente (Room/SQLite)
ui/            ViewModel + tela principal (Jetpack Compose)
report/        geração de relatório em PDF nativo (PdfDocument), sem dependência externa
```
