'use strict'
// Validações do gerenciador de componentes no processo principal (o renderer nunca escolhe o caminho a abrir).
const path = require('node:path')
const fs = require('node:fs')

const ID_RE = /^[a-z][a-z0-9_]{0,30}$/

const validId = (id) => typeof id === 'string' && ID_RE.test(id)

/** O caminho devolvido pelo backend é seguro para abrir? Absoluto, sem "..", sem NUL, e é uma pasta existente. */
function validFolder(p) {
  if (typeof p !== 'string' || !p || p.includes('\0') || p.length > 1024) return false
  if (!path.isAbsolute(p)) return false
  if (p.split(/[\\/]+/).includes('..')) return false
  if (path.parse(p).root === p) return false          // nunca a raiz do disco
  try { return fs.statSync(p).isDirectory() } catch { return false }
}

module.exports = { validId, validFolder, ID_RE }
