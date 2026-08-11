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

## Observações

- **Antivírus/SmartScreen:** executáveis gerados com PyInstaller às
  vezes disparam um alerta de "aplicativo desconhecido" na primeira
  execução (falso positivo comum, por não terem assinatura digital). Se
  isso acontecer, use "Mais informações → Executar assim mesmo" ou
  adicione uma exceção no antivírus. Assinar digitalmente o `.exe` é uma
  opção futura se isso incomodar no ambiente corporativo.
- **Logo:** para a logo da Avibras Aeroco aparecer no cabeçalho, o
  arquivo `assets/logo.png` precisa existir antes de gerar o executável
  (ver seção "Identidade visual" no `README.md` principal).
- **Bluetooth (BLE):** o modo de leitura via Bluetooth usa o adaptador
  Bluetooth nativo do próprio computador (via `bleak`); não precisa de
  dongle extra, mas o computador precisa ter Bluetooth.
- **RS485/Modbus:** o modo via porta serial precisa do driver do
  conversor USB-RS485 usado (normalmente instalado junto com o
  Windows ou disponível no site do fabricante do conversor).

## Solução de problemas

| Problema | Causa provável | Solução |
|---|---|---|
| `'python' não é reconhecido como um comando...` | Python não está no PATH | Reinstale o Python marcando "Add python.exe to PATH" |
| Falha ao instalar dependências (`pip install`) | Sem internet ou proxy corporativo bloqueando | Verifique a conexão; em rede corporativa, configure o proxy do `pip` ou peça liberação de acesso ao PyPI |
| Executável não abre / fecha sozinho | Antivírus bloqueou ou faltou gerar em máquina Windows | Veja "Antivírus/SmartScreen" acima; gere o `.exe` novamente em um Windows |
