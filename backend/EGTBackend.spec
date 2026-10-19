import os
# -*- mode: python ; coding: utf-8 -*-
# PyInstaller (onedir) do backend. Uso:  pyinstaller --noconfirm --clean EGTBackend.spec
# console=True de propósito: o Electron lê a linha "EGT_READY" do stdout (janela oculta via windowsHide).
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("rapidocr_onnxruntime", "rapidocr", "onnxruntime"):   # rapidocr = v3 (Python 3.13+, Linux); usa o que estiver instalado
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d; binaries += b; hiddenimports += h
for pkg in ("uvicorn", "fastapi", "starlette", "anyio", "websockets", "deep_translator", "gtts", "speech_recognition", "pytesseract"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass
for pkg in ("langdetect", "speech_recognition", "gtts", "certifi"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass
hiddenimports += ["egt.components." + m for m in ("net", "download", "store", "sysinfo", "base", "defs", "service", "demo")]
hiddenimports += ["egt.server.app", "egt.server.run", "egt.vault", "egt.secret_wipe", "egt.demo", "mss", "PIL.ImageGrab", "cv2", "yaml"]

a = Analysis(
    ["main.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hiddenimports, hookspath=[],
    excludes=["tkinter", "matplotlib", "pandas", "scipy", "torch", "torchvision", "IPython", "notebook", "pytest", "setuptools"],
    noarchive=False,
)
# enxuga o pacote: sem codec de vídeo do OpenCV e sem o modelo offline do pocketsphinx (usamos só o reconhecimento online)
a.binaries = [b for b in a.binaries if "opencv_videoio_ffmpeg" not in b[0]]
a.datas = [d for d in a.datas if "pocketsphinx" not in d[0].lower()]
# Linux: não leva as bibliotecas do sistema de quem compilou (X11/xcb, libstdc++, libgcc_s) — o AppImage usa as do PC
# do usuário (presentes em qualquer desktop) e assim roda em distros com glibc mais antiga. Não afeta o Windows.
import sys
if sys.platform.startswith("linux"):
    _SYS = ("libX11", "libXau.so", "libXdmcp", "libXext", "libXfixes", "libXrandr", "libXrender", "libxcb", "libstdc++", "libgcc_s")
    a.binaries = [b for b in a.binaries if not (os.path.basename(b[0]).startswith(_SYS) and b[1].startswith(("/usr/", "/lib")))]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="EGTBackend", console=True, upx=False, icon=os.path.join(SPECPATH, '..', 'build', 'icon.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="EGTBackend")
