# Avisos de terceiros / Third-party notices

Easy Game Translator — Copyright (C) 2026 CleitinhoDEV — licenciado sob a GNU GPL v3 ou posterior (veja `LICENSE`).
Os componentes abaixo mantêm as próprias licenças, todas compatíveis com a distribuição junto de um programa GPL-3.0.

## Aplicativo (Electron / renderer)
| Componente | Licença |
|---|---|
| Electron (inclui Chromium e Node.js; licenças em `LICENSES.chromium.html` no app instalado) | MIT (Chromium: BSD-3-Clause e outras; FFmpeg: LGPL-2.1) |
| React, React DOM | MIT |
| motion (Framer Motion) | MIT |
| zustand | MIT |

## Backend Python embutido (PyInstaller)
| Componente | Licença |
|---|---|
| Python | PSF-2.0 |
| FastAPI, pydantic, anyio, h11, mss, urllib3, onnxruntime, pyclipper, PyYAML, gTTS, tqdm | MIT |
| uvicorn, starlette, websockets, click, idna, numpy, shapely, SpeechRecognition, protobuf | BSD |
| Pillow | MIT-CMU (HPND) |
| requests, pytesseract, rapidocr-onnxruntime, opencv-python-headless, flatbuffers | Apache-2.0 |
| certifi | MPL-2.0 |
| PyInstaller (bootloader) | GPL-2.0-or-later com exceção para o bootloader |

Componentes **opcionais** instalados pelo usuário (Tesseract — Apache-2.0; EasyOCR — Apache-2.0; Argos Translate — MIT;
Ollama — MIT) não são distribuídos com o programa.

Serviços de tradução online (Google, Microsoft/Bing, Yandex, MyMemory, Mozhi, Apertium, LibreTranslate, DeepL, Azure, Google
Cloud, Baidu, Youdao, NiuTrans) são acessados por HTTP com código próprio do programa — nenhuma biblioteca deles é distribuída.
O uso de cada serviço segue os termos do próprio serviço (marcas pertencem aos respectivos donos).

## Fontes embutidas (seletor "Fonte do texto")
Arquivos woff2 sem modificação (subconjuntos latin, latin-ext, cyrillic, greek, vietnamese quando disponíveis), obtidos dos pacotes
npm [@fontsource](https://fontsource.org) e servidos localmente (sem CDN). Todas sob a **SIL Open Font License 1.1**.
Textos completos das licenças: `resources/licenses/FONTS-OFL.txt`.

| Fonte | Autores | Licença |
|---|---|---|
| Inter | The Inter Project Authors | OFL-1.1 |
| Nunito | The Nunito Project Authors | OFL-1.1 |
| Poppins | Indian Type Foundry | OFL-1.1 |
| Atkinson Hyperlegible | Braille Institute of America | OFL-1.1 |
| Press Start 2P | CodeMan38 | OFL-1.1 |
| Orbitron | The Orbitron Project Authors | OFL-1.1 |
| Bangers | Vernon Adams | OFL-1.1 |

As opções "de sistema" (Arial, Verdana, Georgia, Comic Sans MS, Consolas, Impact, Segoe UI) **não** são distribuídas:
usam a fonte instalada no Windows, com alternativas para CJK, árabe, tailandês, devanágari e cirílico.

## Traduções da interface
Os idiomas além de pt-BR e en foram rascunhados com tradução automática e revisados à mão nos termos mais visíveis;
podem conter imperfeições. Veja "Ajude a traduzir" no README.
