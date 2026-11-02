#!/usr/bin/env python3
# Modelo básico para o modo Scripts do Easy Game Translator (contrato v1).
# Recebe uma ou duas entradas em string e retorna uma ou duas saídas em string.
#
# ENTRADA (o EGT escreve no stdin, JSON em UTF-8):
#   {"version": 1, "mode": "single" ou "dual",
#    "inputs": ["texto"] ou ["texto do canal A", "texto do canal B"],
#    "source_lang": "en" (ou "auto"), "target_lang": "pt", "channels": ["uni"] ou ["a", "b"]}
#
# SAÍDA (o script imprime no stdout, UTF-8):
#   {"outputs": ["tradução"]} ou {"outputs": ["tradução A", "tradução B"]}  (mesma quantidade das entradas)
#   Para mostrar um erro ao usuário: {"error": "mensagem"}
#   Também vale texto puro: canal único = todo o texto; canal duplo = duas partes separadas por uma linha só com ---
#
# Dicas: uma entrada pode chegar vazia ("") no canal duplo quando aquele canal ainda não tem texto — devolva "".
# O script roda sem shell, na pasta dele, com tempo limite (padrão 15 s) e sem as chaves/variáveis do app.
import json
import sys


def traduzir(texto, origem, destino):
    # Troque isto pela sua tradução (uma API, um dicionário, um modelo local...).
    if not texto:
        return ""
    return f"[{destino}] {texto}"


def main():
    pedido = json.load(sys.stdin)
    origem = pedido.get("source_lang", "auto")
    destino = pedido.get("target_lang", "pt")
    saidas = [traduzir(t, origem, destino) for t in pedido["inputs"]]
    sys.stdout.write(json.dumps({"outputs": saidas}, ensure_ascii=False))


if __name__ == "__main__":
    main()
