#!/usr/bin/env python3
# Exemplo REAL de SCRIPT DE OCR do Easy Game Translator (contrato v1, "kind": "ocr"):
# lê o texto com o RapidOCR (offline, roda no seu PC, bom para fontes estilizadas de jogos).
# Precisa do Python 3 e de UMA instalação, uma vez só, no terminal / Prompt de Comando:
#     pip install rapidocr_onnxruntime        (Python 3.8–3.12)
#     pip install rapidocr onnxruntime        (Python 3.13 ou mais novo — baixa os modelos na 1ª leitura)
# Lê latim/inglês e chinês com os modelos padrão.
#
# ENTRADA (stdin, JSON UTF-8): {"version": 1, "kind": "ocr", "mode": "single"|"dual",
#     "images": [{"channel": "uni"|"a"|"b", "path": "...png (pré-processada)", "raw_path": "...png (original)", ...}], ...}
# SAÍDA (stdout, JSON UTF-8): {"outputs": [{"text": "...", "confidence": 0-100}, ...]}  — uma por imagem, na ordem
#     Erro: {"error": "mensagem"}
import json
import sys

USAR_ORIGINAL = True   # o RapidOCR costuma ler melhor a captura original (colorida); False = imagem pré-processada


def carregar():
    try:
        from rapidocr_onnxruntime import RapidOCR          # versão 1.x
        motor = RapidOCR()
        return lambda caminho: motor(caminho)[0] or []
    except ImportError:
        pass
    from rapidocr import RapidOCR                          # versão 3.x
    motor = RapidOCR()

    def ler(caminho):
        r = motor(caminho)
        if r is None or r.boxes is None:
            return []
        return list(zip(r.boxes.tolist(), r.txts, r.scores))
    return ler


def juntar(caixas):
    """Ordena as caixas (polígono, texto, confiança) em linhas, de cima para baixo e da esquerda para a direita."""
    itens = []
    for caixa, texto, conf in caixas:
        texto = (texto or "").strip()
        if not texto:
            continue
        ys = [p[1] for p in caixa]
        xs = [p[0] for p in caixa]
        itens.append({"x": min(xs), "yc": (min(ys) + max(ys)) / 2, "h": max(1, max(ys) - min(ys)), "t": texto,
                      "c": float(conf)})
    itens.sort(key=lambda i: i["yc"])
    linhas = []
    for i in itens:
        if linhas and abs(i["yc"] - linhas[-1][-1]["yc"]) < 0.55 * max(i["h"], linhas[-1][-1]["h"]):
            linhas[-1].append(i)
        else:
            linhas.append([i])
    texto = "\n".join(" ".join(i["t"] for i in sorted(ln, key=lambda i: i["x"])) for ln in linhas)
    confs = [i["c"] for i in itens]
    conf = sum(confs) / len(confs) * 100 if confs else None          # RapidOCR dá 0–1; o contrato usa 0–100
    return {"text": texto, "confidence": round(conf, 1) if conf is not None else None}


def main():
    pedido = json.load(sys.stdin)
    try:
        ler = carregar()
    except ImportError:
        print(json.dumps({"error": "RapidOCR não instalado. No terminal: pip install rapidocr_onnxruntime"},
                         ensure_ascii=False))
        return
    saidas = []
    for img in pedido["images"]:
        try:
            saidas.append(juntar(ler(img["raw_path"] if USAR_ORIGINAL else img["path"])))
        except Exception as erro:
            print(json.dumps({"error": f"RapidOCR: {erro}"}, ensure_ascii=False))
            return
    sys.stdout.write(json.dumps({"outputs": saidas}, ensure_ascii=False))


if __name__ == "__main__":
    main()
