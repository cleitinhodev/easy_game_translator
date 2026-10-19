// npm run dev: sobe o Vite (HMR) e o Electron apontando para ele; o Electron inicia o backend Python.
import { spawn } from 'node:child_process'
import { createServer } from 'vite'
import electron from 'electron'
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const venvPy = process.platform === 'win32' ? path.join(root, '.venv', 'Scripts', 'python.exe') : path.join(root, '.venv', 'bin', 'python')
if (!fs.existsSync(venvPy) && !process.env.EGT_PYTHON) {
  console.warn('\n⚠  .venv não encontrado. Rode "npm run setup:python" antes (ou defina EGT_PYTHON).\n')
}

const server = await createServer({ root, server: { port: 5173, host: 'localhost' } })
await server.listen()
const url = server.resolvedUrls?.local?.[0] ?? 'http://localhost:5173/'
console.log('Vite em', url)

const args = ['.']
if (process.platform === 'linux') args.unshift('--no-sandbox')
const child = spawn(electron, args, { cwd: root, stdio: 'inherit', env: { ...process.env, EGT_DEV_URL: url.replace(/\/$/, '') + '/' } })
const stop = async (code = 0) => { try { await server.close() } catch { /* ignora */ } process.exit(code) }
child.on('exit', (code) => stop(code ?? 0))
process.on('SIGINT', () => { child.kill(); })
process.on('SIGTERM', () => { child.kill(); })
