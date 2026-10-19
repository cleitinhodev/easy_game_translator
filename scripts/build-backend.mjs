// npm run build:backend — gera backend/dist/EGTBackend/ com o PyInstaller (onedir).
//  • no Windows: usa a .venv (precisa de `pip install -r backend/requirements-bundle.txt`)
//  • no Linux/macOS: gera o executável nativo daquele sistema (para o .exe use o Wine — veja README)
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import fs from 'node:fs'
const root = path.resolve(import.meta.dirname, '..')
const win = process.platform === 'win32'
const py = process.env.EGT_PYTHON || (win ? path.join(root, '.venv', 'Scripts', 'python.exe') : path.join(root, '.venv', 'bin', 'python'))
if (!fs.existsSync(py) && !process.env.EGT_PYTHON) { console.error('Rode "npm run setup:python" primeiro.'); process.exit(1) }
const cwd = path.join(root, 'backend')
// rapidocr v3 (Python 3.13+) baixa os modelos na 1ª leitura: faz uma leitura antes, para os modelos irem DENTRO do pacote (o AppImage é só leitura)
const PREFETCH = "import importlib.util as u\nif not u.find_spec('rapidocr_onnxruntime') and u.find_spec('rapidocr'):\n    import numpy as np\n    from PIL import Image, ImageDraw, ImageFont\n    from rapidocr import RapidOCR\n    img = Image.new('RGB', (420, 80), 'white')\n    ImageDraw.Draw(img).text((10, 15), 'Hello 123', fill='black', font=ImageFont.load_default(size=40))\n    RapidOCR()(np.asarray(img))\n    print('modelos do RapidOCR prontos')\n"
const pre = spawnSync(py, ['-c', PREFETCH], { stdio: 'inherit', cwd })
if (pre.status !== 0) { console.error('Falhou ao preparar os modelos do RapidOCR (precisa de internet na 1ª vez).'); process.exit(pre.status || 1) }
const r = spawnSync(py, ['-m', 'PyInstaller', '--noconfirm', '--clean', 'EGTBackend.spec'], { stdio: 'inherit', cwd })
if (r.status !== 0) process.exit(r.status || 1)
const exe = path.join(cwd, 'dist', 'EGTBackend', win ? 'EGTBackend.exe' : 'EGTBackend')
const models = path.join(cwd, 'dist', 'EGTBackend', '_internal', 'rapidocr', 'models')
if (fs.existsSync(path.dirname(models)) && !(fs.existsSync(models) && fs.readdirSync(models).some((f) => f.endsWith('.onnx')))) { console.error('\n✘ modelos do RapidOCR não entraram no pacote'); process.exit(1) }
console.log(fs.existsSync(exe) ? `\n✔ Backend empacotado: ${exe}` : '\n✘ executável não encontrado')
