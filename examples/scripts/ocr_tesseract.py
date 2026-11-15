#!/usr/bin/env python3
# Exemplo REAL de SCRIPT DE OCR do Easy Game Translator (contrato v1, "kind": "ocr"):
# lê o texto de cada imagem com o programa Tesseract OCR (gratuito, offline, roda no seu PC).
# Só usa a biblioteca padrão do Python — não precisa de "pip install". Precisa do Tesseract instalado:
#   Windows: instalador da UB Mannheim (github.com/UB-Mannheim/tesseract/wiki) ou o Tesseract baixado pela aba
#            Componentes do próprio Easy Game Translator.
#   Linux:   sudo apt install tesseract-ocr  (outros idiomas: tesseract-ocr-por, tesseract-ocr-jpn ...)
# Se o Tesseract estiver num lugar diferente, coloque o caminho completo em TESSERACT, logo abaixo.
#
# ENTRADA (stdin, JSON UTF-8): {"version": 1, "kind": "ocr", "mode": "single"|"dual",
#     "images": [{"channel": "uni"|"a"|"b", "path": "...png (pré-processada)", "raw_path": "...png (original)", ...}],
#     "ocr_lang": "eng" (código do Tesseract para o alfabeto escolhido), "alphabet": "abc(EN)", ...}
# SAÍDA (stdout, JSON UTF-8): {"outputs": [{"text": "...", "confidence": 0-100}, ...]}  — uma por imagem, na ordem
#     Erro: {"error": "mensagem"}
import csv
import io
import json
import os
import shutil
import subprocess
import sys

TESSERACT = ""        # opcional: caminho completo do tesseract (ex.: C:\Program Files\Tesseract-OCR\tesseract.exe)
PSM = "6"             # modo de página do Tesseract: 6 = um bloco de texto (bom para caixas de diálogo)
USAR_ORIGINAL = False  # True = lê a captura original (raw_path) em vez da imagem pré-processada pelo app
TEMPO = 15            # segundos por imagem


def pasta_componentes():
    """Pasta de componentes do Easy Game Translator (onde a aba Componentes baixa o Tesseract)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "EasyGameTranslator", "components")


def achar_tesseract():
    if TESSERACT and os.path.isfile(TESSERACT):
        return TESSERACT
    achado = shutil.which("tesseract")
    if achado:
        return achado
    candidatos = [os.path.join(pasta_componentes(), "tesseract", "tesseract.exe"),
                  os.path.join(pasta_componentes(), "tesseract", "Tesseract-OCR", "tesseract.exe"),
                  os.path.join(pasta_componentes(), "tesseract", "tesseract")]
    if os.name == "nt":
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                candidatos += [os.path.join(base, "Tesseract-OCR", "tesseract.exe"),
                               os.path.join(base, "Programs", "Tesseract-OCR", "tesseract.exe")]
    else:
        candidatos += ["/usr/bin/tesseract", "/usr/local/bin/tesseract", "/opt/homebrew/bin/tesseract"]
    for c in candidatos:
        if os.path.isfile(c):
            return c
    return None


def ler(tesseract, caminho, idioma):
    cmd = [tesseract, caminho, "stdout", "-l", idioma, "--psm", PSM]
    tessdata = os.path.join(pasta_componentes(), "tessdata")      # idiomas baixados pela aba Componentes
    if all(os.path.isfile(os.path.join(tessdata, p + ".traineddata")) for p in idioma.split("+")):
        cmd += ["--tessdata-dir", tessdata]
    cmd.append("tsv")
    extra = {"creationflags": 0x08000000} if os.name == "nt" else {}      # sem janela preta no Windows
    r = subprocess.run(cmd, capture_output=True, timeout=TEMPO, **extra)
    if r.returncode != 0:
        erro = r.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(erro[-1] if erro else f"tesseract saiu com código {r.returncode}")
    # TSV: uma linha por palavra (com bloco/parágrafo/linha e confiança) → reconstrói as linhas
    linhas, confs = {}, []
    leitor = csv.DictReader(io.StringIO(r.stdout.decode("utf-8", "replace")), delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in leitor:
        palavra = (row.get("text") or "").strip()
        if not palavra:
            continue
        try:
            c = float(row.get("conf", -1))
        except ValueError:
            c = -1
        if c >= 0:
            confs.append(c)
        chave = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        linhas.setdefault(chave, []).append(palavra)
    texto = "\n".join(" ".join(p) for _, p in sorted(linhas.items()))
    return {"text": texto, "confidence": round(sum(confs) / len(confs), 1) if confs else None}


def main():
    pedido = json.load(sys.stdin)
    tesseract = achar_tesseract()
    if not tesseract:
        print(json.dumps({"error": "Tesseract não encontrado. Instale o Tesseract OCR ou coloque o caminho em "
                                   "TESSERACT no começo do script."}, ensure_ascii=False))
        return
    idioma = pedido.get("ocr_lang") or "eng"
    saidas = []
    for img in pedido["images"]:
        caminho = img["raw_path"] if USAR_ORIGINAL else img["path"]
        try:
            saidas.append(ler(tesseract, caminho, idioma))
        except subprocess.TimeoutExpired:
            print(json.dumps({"error": f"o Tesseract demorou mais de {TEMPO} s"}, ensure_ascii=False))
            return
        except Exception as erro:  # idioma não instalado, imagem inválida...
            print(json.dumps({"error": f"Tesseract: {erro}"}, ensure_ascii=False))
            return
    sys.stdout.write(json.dumps({"outputs": saidas}, ensure_ascii=False))


if __name__ == "__main__":
    main()
