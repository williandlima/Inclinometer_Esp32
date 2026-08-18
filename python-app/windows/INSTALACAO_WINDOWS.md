# Instalação no Windows

Este pacote instala todas as bibliotecas e dependências do Inclinômetro
Avibras Aeroco em qualquer computador Windows 10/11 (64 bits), sem mexer
na instalação global do Python da máquina (tudo fica isolado em um
ambiente virtual dentro da própria pasta `python-app`).

Existem dois caminhos, dependendo da necessidade:

## Opção 1 — Instalar e rodar a partir do código-fonte (recomendado)

Requisito: **Python 3.10 ou superior** instalado no computador.
Se não tiver, baixe em https://www.python.org/downloads/ e, na tela de
instalação, marque a opção **"Add python.exe to PATH"**.

Passos:

1. Copie a pasta `python-app` inteira para o computador Windows.
2. Dê duplo clique em `windows\install.bat`.
   - Cria um ambiente virtual em `python-app\.venv`.
   - Baixa e instala automaticamente: PyQt5, pymodbus, pyserial, bleak,
     reportlab e matplotlib (todos listados em `requirements.txt`).
3. Para abrir o software (agora e nas próximas vezes), dê duplo clique
   em `windows\run.bat`.

Não é necessário rodar `install.bat` de novo, a menos que o
`requirements.txt` mude (nesse caso, rode novamente para atualizar as
dependências).

## Opção 2 — Gerar um executável autônomo (não precisa de Python instalado)

Útil para instalar em computadores onde não se quer/pode instalar Python
(ex: máquina de produção/chão de fábrica). Gera uma pasta com um
`Inclinometro.exe` que roda sozinho.

**Importante:** o executável precisa ser **gerado em um computador
Windows** (o PyInstaller não faz cross-compilação de Linux/macOS para
`.exe`). O passo a passo abaixo é feito uma vez, em qualquer PC Windows
com Python instalado; o resultado (pasta `dist\Inclinometro`) pode então
ser copiado para quantos computadores forem necessários, mesmo sem
Python.

Passos (em um Windows com Python instalado):

1. Rode `windows\install.bat` (Opção 1, passo 2) se ainda não rodou.
2. Dê duplo clique em `windows\build_exe.bat`.
   - Instala o PyInstaller e empacota o app.
   - Ao final, gera a pasta `dist\Inclinometro\`, contendo
     `Inclinometro.exe` e todos os arquivos necessários.
3. Copie a pasta `dist\Inclinometro` inteira para o computador de
   destino (pendrive, rede, etc.) e rode `Inclinometro.exe` diretamente
   — não precisa instalar nada nesse computador.

## Opção 3 — Gerar um instalador (Setup.exe) com atalhos e desinstalador

A forma mais próxima de um "programa instalado de verdade": um único
arquivo `Inclinometro-Setup-1.0.0.exe` que, ao ser executado no computador
de destino, instala o programa em `Arquivos de Programas`, cria atalho no
Menu Iniciar (e, opcionalmente, na Área de Trabalho) e registra um
desinstalador em "Adicionar ou remover programas" — sem precisar de Python
em nenhum dos dois computadores (o de geração nem o de destino).

**Requisito extra** (só na máquina onde o instalador é **gerado**, uma
única vez): instalar o [Inno Setup](https://jrsoftware.org/isdl.php)
(gratuito) — instalação padrão, sem opções especiais.

Passos (em um Windows com Python **e** Inno Setup instalados):

1. Rode `windows\install.bat` (Opção 1, passo 2) se ainda não rodou.
2. Dê duplo clique em `windows\build_installer.bat`.
   - Gera o executável autônomo (mesmo processo da Opção 2).
   - Compila o instalador com o Inno Setup.
   - Ao final, gera `windows\installer_output\Inclinometro-Setup-1.0.0.exe`.
3. Copie esse único arquivo `.exe` para o(s) computador(es) de destino e
   execute — o assistente de instalação cuida do resto. Não precisa
   instalar Python nem Inno Setup nesses computadores.

Esse arquivo é o mais indicado para distribuir para os usuários finais do
software (ex: equipe de chão de fábrica); as Opções 1 e 2 continuam úteis
para desenvolvimento/testes.

## Observações

- **Antivírus/SmartScreen:** executáveis gerados com PyInstaller às
  vezes disparam um alerta de "aplicativo desconhecido" na primeira
  execução (falso positivo comum, por não terem assinatura digital). Se
  isso acontecer, use "Mais informações → Executar assim mesmo" ou
  adicione uma exceção no antivírus. Assinar digitalmente o `.exe` é uma
  opção futura se isso incomodar no ambiente corporativo.
- **Logo/ícone:** a logo da Avibras Aeroco já está versionada em
  `assets/logo.png` (empacotada automaticamente ao gerar o executável — ver
  seção "Identidade visual" no `README.md` principal) e um ícone derivado
  dela em `assets/logo.ico` é usado no `.exe`, no instalador e nos atalhos
  gerados.
- **Bluetooth (BLE):** o modo de leitura via Bluetooth usa o adaptador
  Bluetooth nativo do próprio computador (via `bleak`); não precisa de
  dongle extra, mas o computador precisa ter Bluetooth.
- **USB/Modbus:** o modo via cabo USB direto ao ESP32 pode precisar do
  driver do chip USB-serial da placa (CP2102, CH340 ou FTDI, dependendo do
  modelo). **A placa usada no projeto tem um chip CH9102X (WCH)** — se a
  porta COM não aparecer sozinha no Gerenciador de Dispositivos ao
  conectar, procure e instale o driver oficial "CH9102" do fabricante WCH;
  para os demais chips, o driver normalmente já vem com o Windows. Para
  distâncias maiores que ~5m, use um cabo de extensão USB ativo.

## Solução de problemas

| Problema | Causa provável | Solução |
|---|---|---|
| `'python' não é reconhecido como um comando...` | Python não está no PATH | Reinstale o Python marcando "Add python.exe to PATH" |
| Falha ao instalar dependências (`pip install`) | Sem internet ou proxy corporativo bloqueando | Verifique a conexão; em rede corporativa, configure o proxy do `pip` ou peça liberação de acesso ao PyPI |
| Executável não abre / fecha sozinho | Antivírus bloqueou ou faltou gerar em máquina Windows | Veja "Antivírus/SmartScreen" acima; gere o `.exe` novamente em um Windows |
