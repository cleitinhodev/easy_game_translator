// Verifica: (1) toda chave i18n usada no código existe em pt-BR e en; (2) TODOS os idiomas de shared/i18n/_locales.json têm exatamente as mesmas chaves,
// os mesmos {placeholders} e os nomes de produto (OCR, Tesseract, CleitinhoDEV, Nina…) preservados; (3) não há arquivo de idioma fora da lista.
import fs from 'node:fs'
import path from 'node:path'
const root = path.resolve(import.meta.dirname, '..')
const load = (n) => JSON.parse(fs.readFileSync(path.join(root, 'shared/i18n', n + '.json'), 'utf8'))
const pt = load('pt-BR'), en = load('en')
const prefixes = new Set(Object.keys(pt).map((k) => k.split('.')[0]))
const files = []
const walk = (d) => { for (const f of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, f.name); f.isDirectory() ? walk(p) : /\.(tsx?|cjs)$/.test(f.name) && files.push(p) } }
walk(path.join(root, 'src')); walk(path.join(root, 'electron'))
const used = new Set()
for (const f of files) {
  const s = fs.readFileSync(f, 'utf8')
  for (const m of s.matchAll(/\bt\(\s*['"`]([\w.-]+)['"`]/g)) used.add(m[1])
  for (const m of s.matchAll(/['"`]([a-z]+)\.([a-z0-9_.-]+)['"`]/gi)) if (prefixes.has(m[1]) && /^[a-z]+\.[a-z0-9_]+$/.test(m[0].slice(1, -1)) && m[0].slice(1,-1) !== 'main.py') used.add(m[1] + '.' + m[2])
}
let bad = 0
for (const k of [...used].sort()) if (!(k in pt) && /^(ai|banner|box|bug|common|empty|gen|help|hist|hk|intro|main|manual|menu|ocr|rep|status|toast|tr|upd|tab|sel|set|settings)\./.test(k)) { console.log('FALTA em pt-BR:', k); bad++ }
for (const k of Object.keys(pt)) if (!(k in en)) { console.log('FALTA em en:', k); bad++ }
for (const k of Object.keys(en)) if (!(k in pt)) { console.log('FALTA em pt-BR (só em en):', k); bad++ }

// ---- todos os idiomas
const locales = JSON.parse(fs.readFileSync(path.join(root, 'shared/i18n/_locales.json'), 'utf8'))
const PRODUCT = ['OCR', 'Tesseract', 'CleitinhoDEV', 'Nina', 'RapidOCR', 'EasyOCR', 'PaddleOCR', 'Ollama', 'Gemini', 'Google', 'YouTube', 'Patreon', 'GPU']
const phs = (v) => (v.match(/\{[a-z_]+\}/g) || []).sort().join(',')
const prods = (v) => PRODUCT.filter((p) => new RegExp(`(^|[^A-Za-z])${p}([^A-Za-z]|$)`).test(v))
const codes = new Set(locales.map((l) => l.code))
for (const f of fs.readdirSync(path.join(root, 'shared/i18n'))) {
  if (f.startsWith('_') || !f.endsWith('.json')) continue
  if (!codes.has(f.slice(0, -5))) { console.log('Arquivo de idioma fora de _locales.json:', f); bad++ }
}
for (const { code } of locales) {
  let d
  try { d = load(code) } catch { console.log('FALTA arquivo do idioma:', code); bad++; continue }
  let n = 0
  for (const k of Object.keys(en)) {
    if (!(k in d)) { if (n++ < 5) console.log(`[${code}] FALTA chave:`, k); bad++; continue }
    if (typeof d[k] !== 'string' || !d[k].trim()) { console.log(`[${code}] vazio:`, k); bad++; continue }
    if (phs(d[k]) !== phs(en[k])) { console.log(`[${code}] placeholders diferentes em ${k}: ${phs(en[k])} vs ${phs(d[k])}`); bad++ }
    for (const p of prods(en[k])) if (!d[k].includes(p)) { console.log(`[${code}] nome de produto '${p}' ausente em ${k}`); bad++ }
  }
  for (const k of Object.keys(d)) if (!(k in en)) { console.log(`[${code}] chave extra:`, k); bad++ }
}
console.log(bad ? `${bad} problema(s)` : `i18n OK (${Object.keys(pt).length} chaves × ${locales.length} idiomas)`)
process.exit(bad ? 1 : 0)
