'use strict'
// Inicia/encerra o backend Python (FastAPI) e descobre porta + token da sessão.
const { spawn, spawnSync } = require('node:child_process')
const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')
const EventEmitter = require('node:events')

const READY_RE = /^EGT_READY\s+(\{.*\})\s*$/

function findPython(root) {
  const candidates = []
  if (process.env.EGT_PYTHON) candidates.push(process.env.EGT_PYTHON)
  const venv = process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python')
  candidates.push(venv)
  candidates.push(process.platform === 'win32' ? 'python' : 'python3', 'python')
  for (const c of candidates) {
    if (path.isAbsolute(c) && !fs.existsSync(c)) continue
    const r = spawnSync(c, ['--version'], { windowsHide: true })
    if (r.status === 0) return c
  }
  return null
}

class Backend extends EventEmitter {
  /** @param {{packaged:boolean, root:string, resources:string}} opts */
  constructor(opts) {
    super()
    this.opts = opts
    this.proc = null
    this.port = 0
    this.token = crypto.randomBytes(32).toString('base64url')
    this.stderr = []
    this.stopping = false
    this.ready = false
  }

  get base() { return `http://127.0.0.1:${this.port}` }

  command() {
    const { packaged, root, resources } = this.opts
    if (packaged) {
      const exe = path.join(resources, 'backend', process.platform === 'win32' ? 'EGTBackend.exe' : 'EGTBackend')
      if (!fs.existsSync(exe)) throw new Error(`Backend empacotado não encontrado: ${exe}`)
      return { cmd: exe, args: [], cwd: path.dirname(exe) }
    }
    const py = findPython(root)
    if (!py) throw new Error('Python não encontrado. Rode "npm run setup:python" (cria .venv) ou defina EGT_PYTHON.')
    return { cmd: py, args: ['-u', path.join(root, 'backend', 'main.py')], cwd: path.join(root, 'backend') }
  }

  start(timeoutMs = 90000) {
    this.token = crypto.randomBytes(32).toString('base64url')   // novo token a cada (re)início
    this.stopping = false
    this.ready = false
    const { cmd, args, cwd } = this.command()
    const env = { ...process.env, EGT_TOKEN: this.token, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8', EGT_PORT: '0' }
    this.proc = spawn(cmd, args, { cwd, env, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] })
    const proc = this.proc
    return new Promise((resolve, reject) => {
      let settled = false
      const fail = (err) => { if (!settled) { settled = true; clearTimeout(timer); reject(err) } }
      const timer = setTimeout(() => fail(new Error('O backend demorou demais para iniciar.')), timeoutMs)
      let buf = ''
      proc.stdout.setEncoding('utf8')
      proc.stdout.on('data', (chunk) => {
        buf += chunk
        let i
        while ((i = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, i).trimEnd()
          buf = buf.slice(i + 1)
          const m = READY_RE.exec(line)
          if (m && !settled) {
            try {
              this.port = JSON.parse(m[1]).port
              this.ready = true
              settled = true
              clearTimeout(timer)
              resolve({ port: this.port, token: this.token })
            } catch (e) { fail(e) }
          } else if (line) {
            this.stderr.push(line); if (this.stderr.length > 200) this.stderr.shift()
          }
        }
      })
      proc.stderr.setEncoding('utf8')
      proc.stderr.on('data', (c) => {
        for (const l of String(c).split(/\r?\n/)) if (l) { this.stderr.push(l); if (this.stderr.length > 200) this.stderr.shift() }
      })
      proc.on('error', fail)
      proc.on('exit', (code, sig) => {
        this.ready = false
        if (!settled) fail(new Error(`Backend encerrou (código ${code ?? sig}).\n${this.stderr.slice(-15).join('\n')}`))
        else if (!this.stopping) this.emit('crashed', code ?? sig)
        this.emit('exit', code)
      })
    })
  }

  async api(pathname, init = {}) {
    const res = await fetch(this.base + pathname, {
      ...init,
      headers: { 'X-EGT-Token': this.token, 'Content-Type': 'application/json', ...(init.headers || {}) },
    })
    return res
  }

  async stop(graceMs = 4000) {
    const proc = this.proc
    if (!proc || proc.exitCode !== null) return
    this.stopping = true
    const exited = new Promise((r) => proc.once('exit', r))
    try { await this.api('/api/shutdown', { method: 'POST', signal: AbortSignal.timeout(1500) }) } catch { /* ignora */ }
    try { proc.stdin.end() } catch { /* ignora */ }
    const timer = new Promise((r) => setTimeout(r, graceMs, 'timeout'))
    const res = await Promise.race([exited, timer])
    if (res === 'timeout' && proc.exitCode === null) {
      if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(proc.pid), '/T', '/F'], { windowsHide: true })
      else proc.kill('SIGKILL')
    }
  }
}

module.exports = { Backend }
