# Fluxograma — Software Desktop (`python-app/`, PyQt5)

Documentação inicial da arquitetura e dos fluxos de execução do software
desktop, para facilitar a leitura do código em análises futuras. Cobre tudo
que já foi implementado até este ponto do projeto (o app Android segue a
mesma arquitetura geral, mas com sua própria implementação em Kotlin).

## O que o software faz até aqui

- Lê o ângulo do inclinômetro (-60° a +60°) em tempo real, por um de três modos:
  **Simulação** (dados sintéticos), **USB/Modbus RTU** (cabo direto ao
  ESP32) ou **Bluetooth BLE** — o firmware do ESP32 já implementa os dois
  modos reais (`firmware/`), mas ainda não foi validado contra hardware
  físico.
- Rastreia os limites (mínimo/máximo) atingidos durante a sessão e destaca
  na tela quando um novo extremo é registrado.
- Permite **calibrar** (zerar o eixo de tilt na posição atual).
- Permite **testar a conexão** (USB ou BLE) antes de iniciar uma sessão.
- Grava cada leitura e cada evento de limite em SQLite, por sessão.
- Gera um **relatório em PDF** (gráfico do ângulo ao longo do tempo + tabela
  de eventos de limite + resumo) a partir do histórico de uma sessão.
- Permite um **Modo Vibração**: captura em alta taxa (ex: 50Hz) por um
  período configurável, para caracterizar variação angular por vento/vibração
  (ex: mastro de pan-tilt) — calcula desvio padrão/RMS/pico-a-pico e o
  espectro de frequência (FFT), com relatório em PDF próprio.
- Interface com a identidade visual da Avibras Aeroco (fundo azul marinho,
  detalhes em laranja, logo opcional no canto superior direito).

## 1. Arquitetura — módulos e dependências

```mermaid
graph TD
    main["main.py"] --> MainWindow

    subgraph ui["ui/"]
        MainWindow["MainWindow"]
        SettingsDialog["SettingsDialog"]
    end

    subgraph data_source["data_source/"]
        IAngleDataSource["IAngleDataSource (interface)"]
        Simulated["SimulatedAngleSource"]
        Modbus["ModbusAngleSource (USB)"]
        Ble["BleAngleSource (BLE)"]
    end

    subgraph limits["limits/"]
        LimitTracker["LimitTracker"]
        HistoryStore["HistoryStore (SQLite)"]
        VibrationStats["vibration_stats<br/>(compute_stats/compute_fft)"]
    end

    subgraph report["report/"]
        ReportGenerator["generate_report()"]
        VibrationReport["generate_vibration_report()"]
    end

    MainWindow --> SettingsDialog
    MainWindow --> IAngleDataSource
    IAngleDataSource -.implementa.-> Simulated
    IAngleDataSource -.implementa.-> Modbus
    IAngleDataSource -.implementa.-> Ble
    MainWindow --> LimitTracker
    MainWindow --> HistoryStore
    MainWindow --> ReportGenerator
    MainWindow --> VibrationStats
    MainWindow --> VibrationReport
    MainWindow --> VibrationDialog["ui.vibration_dialog<br/>(Config/Result)"]
    ReportGenerator --> HistoryStore
    VibrationReport --> VibrationStats
    SettingsDialog -.teste de conexão.-> Modbus
    SettingsDialog -.teste/scan.-> Ble
    IAngleDataSource -.captura de vibração.-> Simulated
    IAngleDataSource -.captura de vibração.-> Modbus
    IAngleDataSource -.captura de vibração.-> Ble
```

`IAngleDataSource` é o ponto-chave da arquitetura: a UI e toda a lógica de
limites/histórico/relatório trabalham só com essa interface, então trocar
entre simulação e hardware real (USB ou BLE) não exige nenhuma mudança no
resto do app.

## 2. Fluxo principal — Iniciar leitura

```mermaid
flowchart TD
    A["Usuário clica 'Iniciar'"] --> B{Config completa?<br/>porta serial / endereço BLE}
    B -- não --> B1["Aviso: configuração incompleta"]
    B -- sim --> C["Cria a fonte de dados<br/>(Simulated / Modbus / Ble)"]
    C --> D["tracker.reset()"]
    D --> E["history.start_session(modo)"]
    E --> F["source.start(on_reading, on_error)<br/>roda em thread própria"]
    F --> G["Indicador de conexão:<br/>'Simulação' ou 'Conectando...'"]

    F -.a cada leitura.-> H["on_reading(AngleReading)"]
    H --> I["_SignalBridge.reading.emit<br/>(thread da fonte → thread da UI)"]
    I --> J["_on_reading()"]
    J --> K["Indicador → 'Conectado' (badge verde)<br/>[modo real/BLE]"]
    J --> L["Atualiza label do ângulo (2 casas decimais)"]
    J --> M["history.add_reading()"]
    J --> N["tracker.process(reading)"]
    N --> O{Novo mínimo<br/>e/ou máximo?}
    O -- sim --> P["history.add_limit_event()<br/>Atualiza caixa Mín/Máx + flash laranja"]
    O -- não --> Q["(nada a destacar)"]

    F -.em caso de erro.-> R["on_error(mensagem)"]
    R --> S["_on_error()"]
    S --> T["Indicador → 'Falha de conexão' (vermelho)<br/>[modo real/BLE]"]
    S --> U["Mensagem na barra de status"]
```

## 3. Fluxo — Calibrar

```mermaid
flowchart TD
    A["Usuário clica 'Calibrar'"] --> B{Leitura em execução<br/>e fonte suporta calibração?}
    B -- não --> B1["Aviso: inicie a leitura /<br/>fonte não suporta calibração"]
    B -- sim --> C["Thread separada chama<br/>source.calibrate() (bloqueante)"]
    C --> D{Sucesso?}
    D -- sim --> E["USB: escreve coil CALIBRATE_COIL<br/>BLE: escreve característica de calibração<br/>Simulação: aplica offset interno"]
    E --> F["calibration_done(True, msg)"]
    F --> G["Mensagem de sucesso na barra de status"]
    F --> H["_reset_limits(): zera Mín/Máx exibidos<br/>(mantém sessão/histórico anterior)"]
    D -- não --> I["calibration_done(False, erro)"]
    I --> J["Aviso com a falha específica"]
```

## 4. Fluxo — Modo Vibração

```mermaid
flowchart TD
    A["Usuário clica 'Modo Vibração'<br/>(leitura em execução)"] --> B{Fonte suporta<br/>captura de vibração?}
    B -- não --> B1["Aviso: fonte não suporta"]
    B -- sim --> C["Diálogo: duração (s) e taxa (Hz)"]
    C --> D["source.start_vibration_capture(duração, taxa,<br/>on_progress, on_done) — não bloqueante"]
    D --> E["QProgressDialog exibe progresso<br/>(cancelável)"]

    D -.a cada atualização.-> F["on_progress(%)"]
    F --> G["_SignalBridge.vibration_progress.emit"]
    G --> H["Atualiza QProgressDialog"]

    D -.ao concluir.-> I["on_done(amostras, erro)"]
    I --> J["_SignalBridge.vibration_done.emit"]
    J --> K{Erro ou<br/>cancelado?}
    K -- sim --> K1["Mensagem de erro/cancelamento"]
    K -- não --> L["history.save_vibration_capture()<br/>(sessão separada do monitoramento contínuo)"]
    L --> M["vibration_stats.compute_stats()<br/>desvio padrão / RMS / pico-a-pico"]
    M --> N["vibration_stats.compute_fft()<br/>espectro de frequência"]
    N --> O["Diálogo de resultado: estatísticas<br/>+ opção 'Salvar relatório PDF'"]
    O -- sim --> P["generate_vibration_report()<br/>gráfico tempo + espectro FFT"]
    O -- não --> Q["(fim)"]
```

Simulação: gera uma vibração sintética (duas senoides de baixa amplitude +
ruído) — testável de ponta a ponta neste ambiente. USB/BLE seguem o
contrato implementado no firmware (registradores Modbus / características
BLE), ainda sem hardware real para validar.

## 5. Fluxo — Testar conexão (Configurações)

```mermaid
flowchart TD
    A["Usuário abre 'Configurações'"] --> B["Escolhe modo:<br/>Simulação / USB / BLE"]
    B --> C["Campos do modo escolhido aparecem<br/>(porta+baud+slave ou endereço BLE)"]
    C --> D["Opcional: 'Escanear' lista<br/>dispositivos BLE próximos"]
    C --> E["Clica 'Testar conexão'"]
    E --> F{Modo}
    F -- USB --> G["modbus_source.test_connection()<br/>lê 1x o registrador de ângulo"]
    F -- BLE --> H["ble_source.test_connection()<br/>conecta, lê 1x a característica, desconecta"]
    G --> I{Sucesso?}
    H --> I
    I -- sim --> J["✓ Ângulo lido, em verde"]
    I -- não --> K["✗ Erro específico, em vermelho"]
```

## 6. Fluxo — Gerar relatório PDF

```mermaid
flowchart TD
    A["Usuário clica 'Gerar relatório PDF'"] --> B{Sessão atual em andamento?}
    B -- sim --> C["Usa a sessão atual"]
    B -- não --> D["Usa a sessão mais recente do histórico<br/>(ou avisa se não houver nenhuma)"]
    C --> E["Escolhe onde salvar (QFileDialog)"]
    D --> E
    E --> F["history.get_readings(session_id)<br/>history.get_limit_events(session_id)"]
    F --> G["generate_report(path, session_info, readings, events)"]
    G --> H["matplotlib: gráfico ângulo × tempo<br/>com marcadores de novo mín/máx"]
    G --> I["reportlab: tabela-resumo da sessão<br/>+ tabela de eventos de limite"]
    H --> J["PDF salvo no caminho escolhido"]
    I --> J
```

## Notas para próximas análises

- Os fluxos reais (USB, BLE) seguem contratos já **implementados no
  firmware** (`firmware/`), documentados nos comentários de topo de
  `data_source/modbus_source.py` e `data_source/ble_source.py` — mas ainda
  precisam ser confirmados/ajustados quando o firmware for de fato
  compilado e testado em hardware real. Isso inclui o contrato de captura
  de vibração (registradores/coils Modbus e characteristics BLE) — só o
  caminho de **simulação** foi testado de ponta a ponta neste ambiente;
  USB/BLE não puderam ser validados contra hardware real.
- `LimitTracker` e `HistoryStore` são agnósticos à fonte de dados: qualquer
  nova fonte que implemente `IAngleDataSource` funciona sem alterações no
  resto do app.
- O app Android (`android-app/`) replica esta mesma arquitetura em
  Kotlin/Compose (fonte de dados plugável, rastreio de limites, histórico em
  Room, relatório em PDF nativo), mas ainda não teve o build validado neste
  ambiente — ver `android-app/README.md`.
