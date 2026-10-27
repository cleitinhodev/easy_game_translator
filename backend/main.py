"""Easy Game Translator v4 — backend local.

Uso (o Electron faz isso sozinho):
    python main.py                    # porta aleatória em 127.0.0.1, token aleatório
    python main.py --selftest [arq]   # lê uma imagem gerada com o RapidOCR e sai
Variáveis: EGT_TOKEN (token da sessão), EGT_PORT (porta fixa; padrão aleatória), EGT_CONFIG_DIR.
Ao ficar pronto imprime uma linha:  EGT_READY {"port": 12345, "token": "...", "version": "4.0.7"}
"""
from __future__ import annotations

import sys


def _selftest() -> int:
    """Flag oculta --selftest [arquivo]: roda o RapidOCR numa imagem gerada, imprime o resultado e sai."""
    import time
    from pathlib import Path

    from PIL import Image, ImageDraw, ImageFont

    out_path = sys.argv[sys.argv.index("--selftest") + 1:][:1]
    lines = []
    code = 1
    try:
        font = None
        for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial.ttf"):
            try:
                font = ImageFont.truetype(name, 38)
                break
            except OSError:
                continue
        img = Image.new("RGB", (460, 78), (250, 250, 250))
        ImageDraw.Draw(img).text((12, 14), "Hello World 123", font=font or ImageFont.load_default(),
                                 fill=(10, 10, 10))
        from egt.ocr.rapid import RapidOcrBackend
        t0 = time.perf_counter()
        res = RapidOcrBackend({}).recognize(img, "abc(EN)")
        lines.append(f"selftest rapidocr text={res.text!r} conf={res.confidence} "
                     f"ms={(time.perf_counter() - t0) * 1000:.0f}")
        code = 0 if "hello" in res.text.lower() else 2
        # também confere que o servidor HTTP importa e responde
        from egt.server.app import create_app  # noqa: F401
        import fastapi, uvicorn  # noqa: F401,E401
        lines.append("selftest server-imports ok")
        # cofre das chaves (DPAPI no Windows): ida e volta + adulterado/estrangeiro rejeitados
        import tempfile as _tf
        from egt import vault
        vres = vault.selftest(Path(_tf.mkdtemp(prefix="egt_vault_")))
        lines.append("selftest vault " + vres)
        if "roundtrip=True" not in vres or "tamper_rejected=True" not in vres or "foreign_rejected=True" not in vres:
            code = 4
        # gerenciador de componentes: importa, lista e carrega um módulo colocado na pasta do usuário (prioridade: embutidos primeiro)
        import importlib
        import tempfile

        from egt.components.service import ComponentService
        from egt.components.store import ComponentsStore, setup_environment
        tmp = Path(tempfile.mkdtemp(prefix="egt_selftest_"))
        store = ComponentsStore(tmp / "components.json")
        store.data["root"] = str(tmp / "comp")
        setup_environment(store)
        (store.site_packages() / "egt_selftest_mod.py").write_text("VALUE = 7\n", encoding="utf-8")
        importlib.invalidate_caches()
        user_ok = importlib.import_module("egt_selftest_mod").VALUE == 7 and sys.path[-1] == str(store.site_packages())
        view = ComponentService(store).list_view()
        st = {c["id"]: c["status"] for c in view["components"]}
        lines.append(f"selftest components frozen={view['frozen']} n={len(st)} user_dir_import={user_ok} " + " ".join(f"{k}={v}" for k, v in st.items()))
        if not user_ok or len(st) < 13:
            code = 3
    except Exception as exc:  # noqa: BLE001
        lines.append(f"selftest FALHOU: {type(exc).__name__}: {exc}")
    lines.append("selftest " + ("OK" if code == 0 else "FALHA"))
    text = "\n".join(lines)
    if sys.stdout is not None:
        print(text, flush=True)
    try:
        if out_path:
            Path(out_path[0]).write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass
    return code


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    from egt.server.run import main
    sys.exit(main())
