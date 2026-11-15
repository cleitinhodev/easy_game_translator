#!/usr/bin/env python3
# Modelo básico de SCRIPT DE OCR do Easy Game Translator (contrato v1, "kind": "ocr").
# Recebe uma ou duas imagens (uma por canal) e retorna uma ou duas saídas em string (o texto lido de cada imagem).
# Não precisa instalar nada: este modelo NÃO lê texto de verdade — ele só mostra o tamanho de cada imagem,
# para você ver o contrato funcionando. Troque a função ler_imagem() pelo seu OCR.
#
# ENTRADA (o EGT escreve no stdin, JSON em UTF-8):
#   {"version": 1, "kind": "ocr", "mode": "single" ou "dual",
#    "images": [{"channel": "uni" (ou "a"/"b"),
#                "path": ".../uni.png",       <- imagem JÁ pré-processada (a mesma que os OCRs do app recebem)
#                "width": 1320, "height": 160,
#                "raw_path": ".../uni_raw.png", <- captura original da tela (sem pré-processamento)
#                "raw_width": 660, "raw_height": 80}],
#    "channels": ["uni"] ou ["a", "b"],
#    "alphabet": "abc(EN)", "ocr_lang": "eng" (código do Tesseract), "lang_hint": "en", "cjk": false,
#    "preprocess": {"scale": 2.0, "grayscale": true, ...}}
#   No canal duplo chegam SEMPRE 2 imagens, na ordem [canal A, canal B].
#
# SAÍDA (o script imprime no stdout, UTF-8) — UMA saída por imagem, na mesma ordem:
#   {"outputs": ["texto da imagem"]} ou {"outputs": ["texto A", "texto B"]}
#   Opcional: confiança 0–100 por imagem  -> {"outputs": [{"text": "texto", "confidence": 91.5}]}
#   Nenhum texto na imagem: devolva ""  (como os OCRs do app).   Erro para o usuário: {"error": "mensagem"}
#   Também vale texto puro: canal único = todo o texto; canal duplo = duas partes separadas por uma linha só com ---
#
# O que o app faz por você: captura a tela, faz a miniatura, pré-processa, apaga os PNGs depois,
# limpa o texto, aplica as regras de substituição e os filtros, e depois traduz (tradutores, IA ou script de tradução).
# O script roda sem shell, na pasta dele, com tempo limite (padrão 20 s) e sem as chaves/variáveis do app.
import json
import struct
import sys


def tamanho_png(caminho):
    """Lê largura e altura do cabeçalho do PNG (sem bibliotecas)."""
    with open(caminho, "rb") as f:
        cabecalho = f.read(24)
    if cabecalho[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("não é um PNG")
    return struct.unpack(">II", cabecalho[16:24])


def ler_imagem(imagem, pedido):
    # Troque isto pelo seu OCR (Tesseract, RapidOCR, um modelo local, uma API...).
    # imagem["path"] = imagem pré-processada; imagem["raw_path"] = captura original.
    largura, altura = tamanho_png(imagem["path"])
    canal = {"uni": "único", "a": "A", "b": "B"}.get(imagem["channel"], imagem["channel"])
    return {"text": f"Canal {canal}: imagem de {largura} x {altura} recebida", "confidence": 100}


def main():
    pedido = json.load(sys.stdin)
    saidas = [ler_imagem(img, pedido) for img in pedido["images"]]
    sys.stdout.write(json.dumps({"outputs": saidas}, ensure_ascii=False))


if __name__ == "__main__":
    main()
