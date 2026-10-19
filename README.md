# Easy Game Translator v4

**Tradutor de jogos em tempo real com OCR** — por **CleitinhoDEV**.

Captura uma região da tela, lê o texto (OCR) e mostra a tradução na hora — na janela principal ou numa janela
flutuante (**Box Mode**) por cima do jogo. Interface em **Electron + React**, motor em **Python** (backend local FastAPI).
Funciona **offline** depois de instalado (OCR local, cache de traduções e motores offline opcionais).

![Janela principal traduzindo](docs/screenshots/translating.png)

> 🇺🇸 [English summary below](#english-summary)

## Recursos

- **Vários motores de OCR**: RapidOCR (embutido, já funciona sem instalar nada), Tesseract, EasyOCR; Paddle/WinOCR experimentais.
  Pré-processamento (escala, cinza, inversão automática, contraste, limiar, nitidez), detecção de mudança e estabilização do texto.
- **Tradutores online e offline** em ordem de prioridade, com **cache SQLite** e modo **somente cache/offline** (Argos Translate opcional).
- **Box Mode**: janela transparente, sempre no topo, arrastável/redimensionável, fonte automática, click-through opcional e
  excluída de prints/gravações (para o OCR não ler a própria tradução).
- **Canal duplo**: duas regiões ao mesmo tempo (ex.: chat + legenda).
- **Perfis por jogo**, **glossário/substituições**, histórico (exportar TXT/CSV/JSON), atalhos globais configuráveis.
- **IA opcional** (desligada por padrão): Gemini ou Ollama local para revisar traduções.
- **Gerenciador de componentes** (Opções › Atualizações): instala só o que você escolher usar, com tamanho, confirmação e progresso.
- **Interface em 20 idiomas** (pt-BR, en, es, fr, de, it, ru, uk, pl, tr, nl, id, vi, th, ar com RTL, hi, ja, ko, zh-CN, zh-TW).
- **14 fontes** para o texto traduzido (de sistema + 7 embutidas sob OFL), com alternativas para CJK, árabe, tailandês, hindi e cirílico.
- Tradução manual (digitar ou falar) com narração, intro com a Nina, Mica/Acrílico no Windows 11.

| | |
|---|---|
| ![Tela inicial](docs/screenshots/main.png) | ![Canal duplo](docs/screenshots/dual-channel.png) |
| ![Seletor de fonte](docs/screenshots/font-picker.png) | ![Interface em árabe (RTL)](docs/screenshots/arabic-rtl.png) |
| ![Gerenciador de componentes](docs/screenshots/components.png) | ![Box Mode, canal duplo](docs/screenshots/box-mode-dual.png) |

## Download e instalação

Baixe a versão mais recente em **[Releases](../../releases/latest)**:

- `EasyGameTranslator-<versão>-setup.exe` — instalador (Windows 10/11 x64; permite escolher a pasta);
- `EasyGameTranslator-<versão>-portable.exe` — versão portátil, sem instalar.

Confira o SHA-256 com `SHA256SUMS.txt` (PowerShell: `Get-FileHash .\arquivo.exe`).

> **Aviso do SmartScreen**: o executável **não é assinado** digitalmente, então o Windows pode mostrar
> "O Windows protegeu o computador". Clique em **Mais informações → Executar assim mesmo**.

## Como usar

1. Abra o jogo (de preferência em **janela sem borda** — tela cheia exclusiva não permite janelas por cima).
2. Clique em **Selecionar região** e arraste sobre a área onde aparece o texto (legenda, diálogo, chat).
3. Escolha o **Alfabeto** do jogo, o **OCR** e o idioma em **Traduzir para**.
4. Clique em **Iniciar** (ou `Ctrl+Alt+S`). A tradução aparece em tempo real; `Ctrl+Alt+T` traduz na hora.
5. Opcional: **Box Mode** (`Ctrl+Alt+B`) para ver a tradução por cima do jogo; **Canal duplo** para duas regiões;
   salve um **perfil** por jogo.

## Requisitos

- **Usar**: Windows 10/11 x64. Nada mais é obrigatório (o RapidOCR já vem junto). Tesseract, EasyOCR, Argos, Ollama etc. são opcionais.
- **Desenvolver**: Node.js 20+ e Python 3.10+ (recomendado 3.12).

## Compilar a partir do código

```bash
npm install
npm run setup:python          # cria .venv e instala o backend  (use --optional para os extras)
npm run dev                   # Vite (HMR) + Electron + backend Python
```

| Comando | O que faz |
|---|---|
| `npm run build` | typecheck (tsc) + build do renderer (Vite) em `dist/` |
| `npm test` | confere i18n + typecheck + testes do backend (pytest) |
| `npm run check:links` | confere links externos / CSP |
| `npm run build:backend` | empacota o backend com PyInstaller (onedir) em `backend/dist/EGTBackend/` |
| `npm run dist:win` | gera instalador NSIS + portátil em `release/` (precisa do backend empacotado) |
| `npm run e2e:shots` | Electron sob `xvfb` em modo demonstração (ex.: `bash scripts/e2e/run.sh dropdowns.cjs`) |

Variáveis úteis: `EGT_PYTHON` (outro Python), `EGT_CONFIG_DIR` (pasta de configuração), `EGT_DEMO=1` (captura e tradutor sintéticos — só para testes de UI).

### Gerar o executável do Windows

No **Windows** (recomendado):

```powershell
npm install
python -m venv .venv ; .\.venv\Scripts\pip install -r backend\requirements-bundle.txt
npm run build:backend         # backend\dist\EGTBackend\EGTBackend.exe
npm run dist:win              # release\EasyGameTranslator-<versão>-setup.exe  e  ...-portable.exe
```

No **Linux** (cross-build com Wine; foi como o pacote de teste foi gerado):

```bash
# Python 3.12 do Windows dentro do Wine (~/.wine/drive_c/Python312)
wine ~/.wine/drive_c/Python312/python.exe -m pip install -r backend/requirements-bundle.txt
(cd backend && wine ~/.wine/drive_c/Python312/python.exe -m PyInstaller --noconfirm --clean EGTBackend.spec)
npx electron-builder --win dir --x64           # pasta release/win-unpacked/
```

Versões fixadas no pacote do Windows: numpy 1.26.4, onnxruntime 1.20.1, opencv-python-headless 4.10.0.84, rapidocr-onnxruntime 1.4.4.
O executável do backend tem um autoteste oculto: `EGTBackend.exe --selftest` (lê uma imagem gerada com o RapidOCR).

### Arquitetura

```
┌──────────────────────── Electron (Node) ────────────────────────┐
│ main.cjs  → janelas (principal, Box Mode, seletores de região), │
│            tray, atalhos globais, menu nativo, instância única   │
│ backend.cjs → inicia/encerra o Python, lê "EGT_READY {porta}"   │
│ preload.cjs → contextBridge: expõe só funções específicas       │
└──────────────┬──────────────────────────────────────────────────┘
               │ porta + token (aleatórios a cada execução)
┌──────────────▼────────────── Renderer (React + TS + Vite) ──────┐
│ UI, i18n (shared/i18n/*.json), animações (motion), zustand      │
└──────────────┬──────────────────────────────────────────────────┘
               │ REST (comandos/config) + WebSocket (eventos ao vivo)
┌──────────────▼────────────── Backend Python (FastAPI) ──────────┐
│ 127.0.0.1 · porta livre aleatória · token obrigatório            │
│ captura (mss) → pré-processo → OCR → substituições → tradução    │
│ (cache SQLite → motores em ordem) → histórico                    │
└──────────────────────────────────────────────────────────────────┘
```

Segurança: o backend só escuta em `127.0.0.1`, exige o token em **toda** rota (header `X-EGT-Token`; `?token=` no WebSocket),
valida o header `Host` (anti DNS-rebinding) e a origem (CORS) e mascara chaves secretas nas respostas.
O renderer roda com `contextIsolation`, `sandbox`, `nodeIntegration` desligado e CSP estrita; links externos só `https`.
**Nenhuma chave de API vai no projeto**: chaves (Gemini/Azure/Libre) vêm de variável de ambiente
(`GEMINI_API_KEY`) ou das Opções, e ficam só na pasta de configuração do usuário
(Windows: `%APPDATA%\EasyGameTranslator`; Linux: `~/.config/EasyGameTranslator`).

## Estrutura

```
backend/   egt/ (motor v3 adaptado + server/ FastAPI)  main.py  tests/  EGTBackend.spec
electron/  main.cjs  windows.cjs  backend.cjs  preload.cjs  util.cjs
src/       App.tsx  store.ts  components/  settings/  views/  styles/  lib/  api/
shared/    i18n/<idioma>.json (20 idiomas) + _locales.json
scripts/   dev.mjs  check-links.mjs  publish-github.md  setup-python.mjs  build-backend.mjs  test-backend.mjs  check-i18n.mjs  e2e/
build/ resources/   ícones (.ico/.png), bandeja e licenças das fontes
docs/      screenshots/
```

## Ajude a traduzir
Os textos ficam em `shared/i18n/<código>.json` (chaves planas; `pt-BR.json` é a referência). Os idiomas além de pt-BR e en foram
gerados com **ajuda de tradução automática** e revisados nos termos principais — podem ter frases estranhas. Para corrigir, edite o
arquivo do idioma mantendo `{n}`, `{name}` etc. e os nomes OCR, Tesseract, CleitinhoDEV e Nina, rode `npm run check:i18n` e envie.
Fontes e licenças: `THIRD_PARTY_NOTICES.md`.

## Limitações conhecidas

- Click-through, exclusão de captura, Mica/Acrílico, atalhos globais, bandeja e DPI do seletor dependem do Windows real;
  foram implementados seguindo a API do Electron, mas só puderam ser testados em Linux/xvfb durante o desenvolvimento.
- Jogos em **tela cheia exclusiva** não permitem janelas por cima: use "Janela sem borda" no jogo.
- Microfone: usa o reconhecimento do Google (precisa de internet). Narração: gTTS (internet).
- EasyOCR/Argos baixam modelos grandes e ficam fora do pacote por padrão (instale com `pip` — veja Opções › OCR).

## Histórico de versões

Veja o [CHANGELOG.md](CHANGELOG.md).

## Licença

Copyright (C) 2026 CleitinhoDEV

Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob os termos da **GNU General Public License**
publicada pela Free Software Foundation, **versão 3** da licença ou (a seu critério) qualquer versão posterior
(`GPL-3.0-or-later`). Ele é distribuído na esperança de ser útil, mas **SEM QUALQUER GARANTIA**. Veja o arquivo [LICENSE](LICENSE).

Componentes de terceiros (fontes OFL, Electron, bibliotecas Python etc.): [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Links

- Site: <https://www.bugzinho.com/easygametranslator>
- Patreon: <https://www.patreon.com/CleitinhoDEV>
- GitHub: <https://github.com/cleitinhodev>
- **Doações**: <https://www.bugzinho.com/donate>

---

## English summary

**Easy Game Translator** is a real-time screen translator for games by **CleitinhoDEV**: select a region of the screen,
it reads the text with OCR (RapidOCR built in; Tesseract/EasyOCR optional) and shows the translation live — in the main
window or in a transparent always-on-top **Box Mode** overlay. Features: online and offline translators with SQLite cache,
dual channel (two regions), per-game profiles, glossary/replacements, history export, optional AI (Gemini/Ollama),
an optional component manager, **20 UI languages** (including Arabic RTL) and 14 fonts for the translated text.

- **Download**: see [Releases](../../releases/latest) (`-setup.exe` installer or `-portable.exe`, Windows 10/11 x64).
  The executables are **not code-signed**, so SmartScreen may warn: click *More info → Run anyway*.
- **Use**: *Select region* → choose alphabet/OCR/target language → *Start* (`Ctrl+Alt+S`). `Ctrl+Alt+B` toggles Box Mode.
- **Build**: `npm install && npm run setup:python && npm run dev`; release build: `npm run build:backend && npm run dist:win`.
- **Translate the UI**: edit `shared/i18n/<code>.json` (keep `{placeholders}` and product names), run `npm run check:i18n`.
  Non-Portuguese/English locales were machine-assisted and may contain mistakes — fixes are welcome.
- **License**: GPL-3.0-or-later — Copyright (C) 2026 CleitinhoDEV. Donations: <https://www.bugzinho.com/donate>
