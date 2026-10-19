// Verifica os links externos: a doação deve ser https://www.bugzinho.com/donate (e nenhum link antigo pode sobrar no projeto).
import fs from 'node:fs'
import path from 'node:path'
const root = path.resolve(import.meta.dirname, '..')
const DONATE = 'https://www.bugzinho.com/donate'
const SKIP = new Set(['node_modules', 'dist', 'release', '.venv', 'screenshots', '.git', 'build', '__pycache__'])
const files = []
const walk = (d) => { for (const e of fs.readdirSync(d, { withFileTypes: true })) { if (SKIP.has(e.name)) continue; const p = path.join(d, e.name); e.isDirectory() ? walk(p) : /\.(tsx?|cjs|mjs|js|json|md|py|html|yml|txt|css)$/.test(e.name) && !/package-lock/.test(e.name) && files.push(p) } }
walk(root)
let bad = 0
const help = fs.readFileSync(path.join(root, 'src/components/HelpModal.tsx'), 'utf8')
const m = /donate:\s*'([^']+)'/.exec(help)
if (!m || m[1] !== DONATE) { console.log('HelpModal LINKS.donate =', m && m[1], '≠', DONATE); bad++ }
for (const f of files) {
  const s = fs.readFileSync(f, 'utf8')
  if (/doa%C3%A7|doações-donate|doacoes-donate/i.test(s) && !f.endsWith('check-links.mjs')) { console.log('link de doação antigo em', path.relative(root, f)); bad++ }
  for (const u of s.matchAll(/https?:\/\/(?:www\.)?bugzinho\.com[^\s'"`)<>\]]*/g)) {
    if (u[0] !== DONATE && u[0] !== 'https://www.bugzinho.com' && u[0] !== 'https://www.bugzinho.com/easygametranslator' && !/^https:\/\/www\.bugzinho\.com\/?$/.test(u[0])) { console.log('URL bugzinho inesperada:', u[0], 'em', path.relative(root, f)); bad++ }
  }
}
// o IPC app:open-external só aceita https:// (a URL nova passa); a CSP não restringe navegação externa (abre no navegador do sistema)
const main = fs.readFileSync(path.join(root, 'electron/main.cjs'), 'utf8')
if (!/app:open-external[\s\S]{0,200}\^https:/.test(main)) { console.log('allow-list de app:open-external mudou'); bad++ }
console.log(bad ? `${bad} problema(s)` : `links OK (doação = ${DONATE})`)
process.exit(bad ? 1 : 0)
