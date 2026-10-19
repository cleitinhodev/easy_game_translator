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
// README / docs: links externos só https e de sites oficiais; links relativos apontam para arquivos que existem; âncoras existem
const OFFICIAL = new Set(['github.com', 'www.bugzinho.com', 'www.patreon.com', 'aka.ms', 'learn.microsoft.com', 'nodejs.org',
  'www.python.org', 'ollama.com', 'aistudio.google.com', 'www.gnu.org', 'fontsource.org'])
const slug = (h) => h.trim().toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu, '').replace(/\s/g, '-')
const external = []
for (const doc of ['README.md', 'CHANGELOG.md', 'THIRD_PARTY_NOTICES.md', 'scripts/publish-github.md']) {
  const fp = path.join(root, doc); if (!fs.existsSync(fp)) continue
  const md = fs.readFileSync(fp, 'utf8')
  const anchors = new Set([...md.matchAll(/^#{1,6}\s+(.+)$/gm)].map((h) => slug(h[1])))
  const noCode = md.replace(/```[\s\S]*?```/g, '')
  const links = [...noCode.matchAll(/\]\(([^)\s]+)\)/g)].map((x) => x[1]).concat([...noCode.matchAll(/<(https?:\/\/[^>\s]+)>/g)].map((x) => x[1]))
  for (const l of links) {
    if (/^https?:/.test(l)) {
      const u = new URL(l)
      if (u.protocol !== 'https:') { console.log(`${doc}: link sem https: ${l}`); bad++ }
      else if (!OFFICIAL.has(u.hostname)) { console.log(`${doc}: domínio fora da lista de sites oficiais: ${l}`); bad++ }
      else external.push(l)
    } else if (l.startsWith('#')) {
      if (!anchors.has(decodeURIComponent(l.slice(1)))) { console.log(`${doc}: âncora inexistente: ${l}`); bad++ }
    } else if (!l.startsWith('../../')) {          // ../../releases etc. = páginas do GitHub
      const target = path.join(path.dirname(fp), decodeURIComponent(l.split('#')[0]))
      if (!fs.existsSync(target)) { console.log(`${doc}: arquivo inexistente: ${l}`); bad++ }
    }
  }
}
if (process.argv.includes('--online')) {            // opcional: confere que cada link externo responde (precisa de internet)
  for (const l of [...new Set(external)]) {
    try { const r = await fetch(l, { method: 'GET', redirect: 'follow' }); if (r.status >= 400 && r.status !== 403 && !(r.status === 404 && /github\.com\/cleitinhodev\/easy_game_translator/.test(l)))   /* repositório privado: 404 sem login */ { console.log('link quebrado:', r.status, l); bad++ } else console.log(r.status, l, '→', new URL(r.url).hostname) }
    catch (e) { console.log('falhou:', l, String(e)); bad++ }
  }
}
console.log(bad ? `${bad} problema(s)` : `links OK (doação = ${DONATE}; README/docs: ${external.length} links externos oficiais, âncoras e arquivos conferidos)`)
process.exit(bad ? 1 : 0)
