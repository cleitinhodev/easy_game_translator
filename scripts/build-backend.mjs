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
const r = spawnSync(py, ['-m', 'PyInstaller', '--noconfirm', '--clean', 'EGTBackend.spec'], { stdio: 'inherit', cwd })
if (r.status !== 0) process.exit(r.status || 1)
const exe = path.join(cwd, 'dist', 'EGTBackend', win ? 'EGTBackend.exe' : 'EGTBackend')
console.log(fs.existsSync(exe) ? `\n✔ Backend empacotado: ${exe}` : '\n✘ executável não encontrado')
