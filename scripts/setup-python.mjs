// npm run setup:python — cria .venv e instala o backend (+ opcionais com --optional).
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const venv = path.join(root, '.venv')
const win = process.platform === 'win32'
const py = (win ? path.join(venv, 'Scripts', 'python.exe') : path.join(venv, 'bin', 'python'))
const withOptional = process.argv.includes('--optional')
const withDev = process.argv.includes('--dev')

const run = (cmd, args) => { const r = spawnSync(cmd, args, { stdio: 'inherit', cwd: root }); if (r.status !== 0) { console.error(`\nFalhou: ${cmd} ${args.join(' ')}`); process.exit(r.status || 1) } }

if (!fs.existsSync(py)) {
  const candidates = win ? [['py', ['-3.12']], ['py', ['-3']], ['python', []]] : [['python3.12', []], ['python3.11', []], ['python3', []]]
  let ok = false
  for (const [c, a] of candidates) {
    const t = spawnSync(c, [...a, '--version'], { encoding: 'utf8' })
    if (t.status === 0) { run(c, [...a, '-m', 'venv', venv]); ok = true; break }
  }
  if (!ok) { console.error('Python 3.10+ não encontrado. Instale em python.org (marque "Add to PATH").'); process.exit(1) }
}
run(py, ['-m', 'pip', 'install', '--upgrade', 'pip'])
run(py, ['-m', 'pip', 'install', '-r', path.join('backend', 'requirements.txt')])
if (withOptional) run(py, ['-m', 'pip', 'install', '-r', path.join('backend', 'requirements-optional.txt')])
if (withDev) run(py, ['-m', 'pip', 'install', '-r', path.join('backend', 'requirements-dev.txt')])
console.log('\n✔ Python pronto em', venv)
