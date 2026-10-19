// npm run test:backend — roda o pytest do backend na .venv.
import { spawnSync } from 'node:child_process'
import path from 'node:path'
const root = path.resolve(import.meta.dirname, '..')
const py = process.platform === 'win32' ? path.join(root, '.venv', 'Scripts', 'python.exe') : path.join(root, '.venv', 'bin', 'python')
const r = spawnSync(py, ['-m', 'pytest', '-q', ...process.argv.slice(2)], { stdio: 'inherit', cwd: path.join(root, 'backend') })
process.exit(r.status ?? 1)
