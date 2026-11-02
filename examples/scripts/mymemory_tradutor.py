#!/usr/bin/env python3
# Exemplo REAL para o modo Scripts do Easy Game Translator (contrato v1):
# traduz pela API pública e gratuita do MyMemory (https://mymemory.translated.net/doc/spec.php).
# Só usa a biblioteca padrão do Python (urllib) — não precisa instalar nada além do Python 3.
#
# ENTRADA (stdin, JSON UTF-8): {"version": 1, "mode": "single"|"dual", "inputs": ["..."] ou ["A", "B"],
#                               "source_lang": "en" ou "auto", "target_lang": "pt", "channels": [...]}
# SAÍDA   (stdout, JSON UTF-8): {"outputs": ["..."]} ou {"outputs": ["A", "B"]}; em caso de erro: {"error": "..."}
#
# Privacidade: o texto capturado vai para o MyMemory (Translated, Itália). Cota grátis: ~5.000 caracteres/dia;
# coloque seu e-mail em EMAIL para subir a cota (opcional — fica só neste arquivo, no seu PC).
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

EMAIL = ""            # opcional: seu e-mail aumenta a cota grátis do MyMemory
TIMEOUT = 10          # segundos por pedido (o EGT encerra o script depois de 15 s, por padrão)
API = "https://api.mymemory.translated.net/get"

# O MyMemory usa códigos com região para alguns idiomas
REGIAO = {"pt": "pt-BR", "zh": "zh-CN", "zh-cn": "zh-CN", "zh-tw": "zh-TW"}


def codigo(lang, padrao):
    lang = (lang or "").strip()
    if not lang or lang == "auto":
        return padrao
    return REGIAO.get(lang.lower(), lang)


def traduzir(texto, origem, destino):
    texto = (texto or "").strip()
    if not texto:
        return ""
    params = {"q": texto[:500], "langpair": f"{origem}|{destino}"}
    if EMAIL:
        params["de"] = EMAIL
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "EGT-script-exemplo/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        dados = json.loads(resp.read().decode("utf-8"))
    status = int(dados.get("responseStatus") or 0)
    saida = (dados.get("responseData") or {}).get("translatedText") or ""
    if status != 200 or not saida or "MYMEMORY WARNING" in saida.upper():
        raise RuntimeError(f"MyMemory recusou ({status}): {dados.get('responseDetails') or saida}"[:200])
    return saida


def main():
    pedido = json.load(sys.stdin)
    destino = codigo(pedido.get("target_lang"), "pt-BR")
    origem = codigo(pedido.get("source_lang"), "en")          # o MyMemory não detecta o idioma sozinho
    try:
        saidas = [traduzir(t, origem, destino) for t in pedido["inputs"]]
    except urllib.error.URLError as exc:
        print(json.dumps({"error": f"sem conexão com o MyMemory: {exc.reason}"}, ensure_ascii=False))
        return
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return
    print(json.dumps({"outputs": saidas}, ensure_ascii=False))


if __name__ == "__main__":
    main()
