# Changelog — Easy Game Translator v4

Todas as mudanças das versões 4.x. Datas no formato AAAA-MM-DD.

## 4.0.7 — 2026-10-27

- **Link do tutorial atualizado**: o botão **Tutorial** da janela de Ajuda agora abre o tutorial novo e completo, em 20 idiomas:
  <https://cleitinhodev.github.io/homepage/projects/easy-game-translator-tutorial/> (antes: página antiga da v1 no bugzinho.com).
  Os demais links (site, doação `https://www.bugzinho.com/donate`, YouTube, Patreon, GitHub) não mudaram. README e `homepage` do
  `package.json` também apontam para o tutorial novo; `npm run check:links` e o E2E da janela de Ajuda conferem o endereço.
- **Linux no `main`**: o ajuste do `EGTBackend.spec` da branch `linux-build` (não empacota as bibliotecas X11/libstdc++/libgcc de
  quem compila, para rodar em distros com glibc mais antiga) foi incorporado; o release passa a trazer Windows (instalador e
  portátil) **e** Linux (AppImage e `.deb`) juntos. Não afeta o Windows.
- Sem outras mudanças de funcionamento. A 4.0.6 continua como versão estável (branch `stable-4.0.6`).

## 4.0.6 — 2026-10-19

- **Chaves de API criptografadas** (Gemini, Azure/Microsoft, LibreTranslate). Windows: **DPAPI** (`CryptProtectData`, escopo do
  usuário atual, entropia própria do app, sem diálogos) — o `settings.json` guarda `{"enc": "dpapi:v1:…"}` e uma cópia dele não
  funciona em outro PC/usuário. Linux: chaveiro do sistema (Secret Service) quando disponível; senão AES-256-GCM com chave
  derivada (scrypt) de `/etc/machine-id` + usuário + sal aleatório em `vault.salt` (0600) — mais fraco que o DPAPI (documentado).
  Migração automática na 1ª abertura: o texto puro é criptografado e apagado (gravação atômica, sem `.bak`/`.tmp` com a chave).
  Chave ilegível neste PC → tratada como "sem chave", com o aviso *"A chave salva não pode ser lida neste computador. Cole a
  chave novamente."*. As chaves nunca vão para log (filtro que mascara padrões de chave em todo log e na aba Reportar Erros),
  nem para a interface (máscara), exportações ou perfis; o Gemini lê a chave só na hora da chamada.
- **Remover chave** (Opções › IA e Opções › Tradução), com confirmação: regrava as configurações sem a chave sobrescrevendo a
  cópia antiga, apaga sobras `.tmp`/`.bak`/`.old`, procura a chave em logs e arquivos da pasta de configuração (texto e SQLite) e
  troca por `[chave removida]`, limpa o backend (motores e esperas) e a interface. Se houver `GEMINI_API_KEY`/`GOOGLE_API_KEY`,
  avisa; no Windows oferece (2ª confirmação) apagar a variável **do usuário** (`HKCU\Environment` + aviso `WM_SETTINGCHANGE`);
  variável do sistema (HKLM) nunca é tocada — o app explica como remover manualmente.
- **Aba IA refeita**: um único seletor **Desligada | Gemini | Ollama** (substitui o interruptor + provedor; configurações antigas
  são migradas). Só a IA escolhida entra na cadeia — com Ollama selecionado o Gemini nunca é chamado. Cartões separados, cada um
  com seu **Testar** (testa sem precisar selecionar e sem mexer no outro):
  - **Gemini**: aviso no topo para acompanhar o consumo de tokens no site oficial (link para o Google AI Studio), lista de
    modelos (`gemini-3.5-flash-lite` recomendado/padrão, `gemini-3.8-flash`, `gemini-flash-latest`, **Outro…** para digitar)
    — uma escolha explícita nunca é trocada sozinha. Erros amigáveis e traduzidos: 404 → *modelo não disponível para a sua chave,
    escolha gemini-3.5-flash-lite*; 400/401/403 → *chave inválida ou sem permissão*; 429 → limite de uso.
  - **Ollama**: endereço, status do servidor (rodando / não encontrado), modelos instalados (`/api/tags`) + **Outro…**.
  - Novos endpoints (todos com o token): `POST /api/ai/test {provider, model?, url?}`, `POST /api/ai/ollama/status`,
    `POST /api/secrets/remove`, `GET /api/secrets/env`, `POST /api/secrets/env/remove`.
- **Intro**: as luzes giram sem parar até a música acabar (antes a animação de piscar anulava a posição das luzes e elas sumiam
  atrás da logo) e a logo cresce devagar durante toda a intro (1,0 → 1,07, com brilho pulsando). Pular (clique/Esc/Enter),
  "Tocar a intro completa", fim pelo áudio/temporizador e "reduzir animações" (sem rotação, escala mínima) continuam.
- README: bloco **Iniciantes** (passo a passo para Windows e Linux), **Perguntas frequentes** e **Segurança e privacidade** (o que
  fica no PC, o que é enviado e para onde, criptografia por sistema e como remover a chave).
- Linux a partir do código: `backend/requirements.txt` usa o `rapidocr` v3 no Python 3.13+ e `cryptography` (fora do Windows);
  novo `npm run dist:linux` (AppImage).
- `check:links` também confere os links do README/docs. Testes novos: `backend/tests/test_secrets.py` (DPAPI simulado,
  AES-GCM, migração, nada em texto puro no disco, remoção, variável de ambiente simulada, seleção da IA, teste por provedor e
  mapeamento de erros) e E2E `scripts/e2e/ai.cjs` e `scripts/e2e/introframes.cjs`.

## 4.0.5 — 2026-10-19

- **Menus suspensos sempre inteiros dentro da janela** (Fonte, Perfil, Alfabeto, OCR, Traduzir para, idioma e fonte nas
  Configurações, fonte no painel do Box): o menu é desenhado por cima de tudo (portal, `position: fixed`) e posicionado a partir
  do botão com margem de 8 px — abre **para cima** quando há mais espaço acima, **desliza na horizontal** para caber (também em
  árabe/RTL), limita **altura e largura** ao espaço disponível com rolagem interna (a opção escolhida já aparece visível) e se
  **reposiciona** ao redimensionar, rolar ou mudar o zoom. Fecha com Esc, clique fora ou quando a janela perde o foco.
  Animação (a origem segue o lado em que abriu), teclado (↑ ↓ Home End Enter) e "reduzir animações" continuam iguais.
- Teste E2E `scripts/e2e/dropdowns.cjs`: 800×500, 940×640 (mínimo), 1000×600, 1280×800 e maximizada, em pt-BR, árabe (RTL) e
  alemão, zoom 80 %/125 %, redimensionar com o menu aberto, Configurações e painel do Box (780×210, 420×300, 320×520) —
  confere que o retângulo de cada menu fica 100 % dentro da janela.
- A versão exibida (barra de título, Ajuda, Atualizações) vem do app; o backend é o mesmo da 4.0.4 (sem mudanças).

## 4.0.4 — 2026-10-19

- **Fonte do texto**: seletor ao lado do tamanho da fonte (barra principal), nas Configurações › Geral e no painel do Box —
  14 opções (padrão, 6 de sistema e 7 embutidas sob licença OFL: Inter, Nunito, Poppins, Atkinson Hyperlegible, Press Start 2P,
  Orbitron, Bangers), cada uma com alternativas para CJK, árabe, tailandês, hindi e cirílico. Salva no perfil.
- **Interface em 20 idiomas**: pt-BR, en, es, fr, de, it, ru, uk, pl, tr, nl, id, vi, th, ar (direita→esquerda), hi, ja, ko,
  zh-CN, zh-TW. Escolha em Configurações › Geral; na primeira execução segue o idioma do sistema (senão, inglês).
  Menus da bandeja e caixas de diálogo seguem o idioma escolhido.
- Link de doação da Ajuda: <https://www.bugzinho.com/donate>.

### Ajude a traduzir (veja o README)
Os textos ficam em `shared/i18n/<código>.json` (chaves planas; `pt-BR.json` é a referência). Os idiomas além de pt-BR e en foram
gerados com **ajuda de tradução automática** e revisados nos termos principais — podem ter frases estranhas. Para corrigir, edite o
arquivo do idioma mantendo `{n}`, `{name}` etc. e os nomes OCR, Tesseract, CleitinhoDEV e Nina, rode `npm run check:i18n` e envie.
Fontes e licenças: `THIRD_PARTY_NOTICES.md`.

## 4.0.3 — 2026-10-19

**Gerenciador de componentes** em *Opções › Atualizações* — uma ajuda **opcional** para instalar o que o programa pode usar.
O programa continua funcionando exatamente como antes, sem instalar nada: tudo que já vem junto segue valendo.

- **Linguagem simples**: cada linha mostra "Já está funcionando", "Faltando" ou "Opcional", com o tamanho ("Precisa baixar (45 MB)") e
  **um botão principal** (Instalar / Atualizar / Como instalar). No topo aparece "Tudo certo, nada a instalar" quando não falta nada.
  O que é recomendado depende só do que você escolheu usar (por exemplo, o leitor de texto/idioma selecionado, tradução offline ou o modelo de IA).
- **Como funciona cada download**: o programa **verifica** a fonte oficial → mostra o **tamanho** → você **confirma** → baixa com **barra de progresso**
  (velocidade, tempo restante, cancelar e continuar de onde parou). Sem internet, mostra uma mensagem calma e as instruções manuais.
- **Só fontes oficiais** (HTTPS): PyPI/pythonhosted, python.org, GitHub (releases e tessdata), ollama.com/registry.ollama.ai, UB Mannheim (instalador do Tesseract)
  e argos-net.com. Outros endereços são recusados, inclusive em redirecionamentos. A integridade é conferida com SHA-256 (PyPI, GitHub) ou hash do Git (idiomas do Tesseract) quando a fonte publica.
  O site do Tesseract e o do Python não publicam hash junto do instalador: o programa avisa e você confere a assinatura ao abrir.
- **Instaladores nunca rodam sozinhos**: "Abrir instalador" pede confirmação e só abre arquivos baixados por este programa.
- **Botão Pasta** em cada linha abre a pasta do componente (para você colocar ou trocar arquivos), **Mudar pasta…** escolhe outro local
  (o que já existe é copiado, nada é apagado), **Reconhecer arquivos** relê a pasta e **Remover** (com confirmação) só apaga o que está dentro da pasta de componentes.
- **Avançado / Como instalar manualmente** (recolhido por padrão): links oficiais, comandos com botão de copiar, onde colocar arquivos e detalhes técnicos.

**Pasta de componentes (como funciona)**: tudo que o programa baixa fica numa pasta gravável do usuário — por padrão `<pasta de configuração>/components`
(no Windows, `%APPDATA%\Easy Game Translator\components`; abra pelo botão *Pasta dos componentes*), nunca dentro da pasta de instalação.
Na partida do backend essa pasta é preparada e o subdiretório `site-packages` é **adicionado ao fim** do caminho de módulos do Python:
o que vem embutido no programa sempre tem prioridade, então nada que você baixar pode substituir ou quebrar o que já funciona.
Pacotes Python são instalados com o `pip` de um Python **instalado no computador** (`pip install --target`), nunca no próprio programa;
se o Python do computador for de outra versão, o programa pede só binários compatíveis. Idiomas do Tesseract (`.traineddata`), modelos do RapidOCR
(`det/rec/cls.onnx`) e modelos do EasyOCR (`.pth`) colocados nas respectivas pastas são usados automaticamente.
A localização escolhida fica em `components.json` (fora do projeto).

**Limites honestos**: o programa instalado (.exe) é empacotado e **não consegue carregar** EasyOCR, PaddleOCR, Argos e o leitor do Windows
adicionados depois — nessas linhas aparece uma explicação simples e as instruções para rodar o programa a partir do código-fonte; o RapidOCR já vem dentro.
Tesseract, idiomas do Tesseract, Ollama (e seus modelos), gTTS e SpeechRecognition funcionam no programa instalado.
O Gemini não tem download: a linha leva para a aba IA, onde você cola a chave. Os instaladores baixados não são assinados por nós.
Esta versão não foi testada em um Windows real (testada em Linux com Electron + Wine para o empacotamento).

## 4.0.2 — 2026-10-18

- **Miniatura do painel "Original" sempre atual**: antes a imagem só era buscada ao definir a região (ou pelo botão de atualizar), então
  ficava presa na primeira captura. Agora o backend envia um evento `preview` (JPEG ≤480 px, qualidade 70) toda vez que a imagem capturada
  muda — mesmo que o texto lido seja igual — e também nos reprocessamentos forçados; vale para canal único e dual.
- **Ícone da Nina** (multi-tamanho 16–256 px) no aplicativo, barra de tarefas, bandeja, instalador, desinstalador, versão portátil e no executável do backend.
- **Intro completa**: a música de boas-vindas (`bemvindo.mp3`, ~7 s) toca até o fim antes de abrir a janela principal. Se o áudio falhar ou
  não houver dispositivo de som, usa a duração conhecida como temporizador (limite de segurança: duração + 3 s). Em *Opções › Geral* há
  "Tocar a intro completa" (desligado = intro curta de 3 s); "Mostrar a intro" desliga tudo como antes. Clique/Esc/Enter ainda pulam.

## 4.0.1 — 2026-10-16

- **Reprocessamento imediato**: trocar idioma de destino, motor/alfabeto de OCR, pré-processamento, glossário/substituições,
  "somente cache", motor de tradução ou perfil refaz a leitura na hora, mesmo com a imagem parada. Só o idioma/motor de tradução
  reaproveita o último texto do OCR; OCR/alfabeto/pré-processamento recapturam e rodam o OCR de novo. O cache inclui o idioma de destino.
  A interface mostra "Traduzindo…" (janela principal, canal duplo e Box Mode) até chegar a nova tradução.
- **Botão de fechar** das Opções, da Tradução manual, da Ajuda e dos demais painéis fica no canto superior esquerdo (com a
  faixa dos botões do Windows livre). `Esc` continua fechando.

## 4.0.0 — 2026-10-16

Primeira versão da v4: interface nova em **Electron + React** (no lugar do Tkinter da v3), mantendo o motor Python da v3 como
backend local (FastAPI, `127.0.0.1` + token). Canal único/duplo, Box Mode, perfis, glossário/substituições, histórico,
cache SQLite, vários motores de OCR (RapidOCR embutido, Tesseract, EasyOCR…) e de tradução, IA opcional, atalhos globais,
bandeja, intro com a Nina, interface em pt-BR e English.
