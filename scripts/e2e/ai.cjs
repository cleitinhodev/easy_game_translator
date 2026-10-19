'use strict'
// Aba IA (4.0.6): seletor único Desligada|Gemini|Ollama, cartões separados com "Testar" próprio, aviso de consumo do Gemini,
// dropdown de modelos + "Outro…", status do Ollama, "Remover chave" com confirmação e limpeza; nada de chave em texto puro no disco.
const fs = require('node:fs'); const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const CFG = process.env.EGT_CONFIG_DIR; const UD = process.env.EGT_USER_DATA
const KEY = 'AI' + 'zaSyE2E_teste_0123456789abcdefghijklmno'   // chave falsa (partida para o scanner de segredos)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const grepDir = (dir, needle) => {
  const hits = []
  const walk = (d) => { let ents = []; try { ents = fs.readdirSync(d, { withFileTypes: true }) } catch { return }
    for (const e of ents) { const p = path.join(d, e.name); if (e.isDirectory()) walk(p); else { try { const b = fs.readFileSync(p); if (b.includes(needle) || b.includes(Buffer.from(needle, 'utf16le'))) hits.push(p) } catch { /* */ } } } }
  walk(dir); return hits
}
module.exports = async ({ app, getMain, backend }) => {
  const main = getMain(); const wc = main.webContents
  const js = (c) => wc.executeJavaScript(c, true)
  const api = async (p, m = 'GET', b) => { const r = await backend.api(p, { method: m, body: b ? JSON.stringify(b) : undefined }); return { status: r.status, body: await r.json() } }
  const shot = async (n, d = 350) => { await sleep(d); fs.writeFileSync(path.join(OUT, n + '.png'), (await wc.capturePage()).toPNG()) }
  const wait = async (cond, ms = 8000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await js(cond)) return true; await sleep(120) } return false }
  const rep = { checks: [] }
  const ok = (name, pass, extra) => { rep.checks.push({ name, pass: !!pass, ...(extra !== undefined ? { extra } : {}) }); console.log(pass ? 'PASS' : 'FAIL', name, extra !== undefined ? JSON.stringify(extra).slice(0, 300) : '') }
  const setLang = async (l) => { await api('/api/settings', 'PATCH', { changes: { 'ui.language': l } }); await js(`window.egt.app.setLanguage(${JSON.stringify(l)})`); return wait(`document.documentElement.lang === ${JSON.stringify(l)}`) }
  const clickText = (sel, text) => js(`(() => { const b = [...document.querySelectorAll(${JSON.stringify(sel)})].find(x => x.innerText.trim() === ${JSON.stringify(text)}); if (b) { b.click(); return true } return false })()`)
  try {
    main.setSize(1180, 900)
    await sleep(2500); await js(`document.querySelector('.intro')?.click()`); await sleep(1000)
    await setLang('pt-BR')
    await js(`window.__egt.getState().openDrawer('ai'); 0`); await sleep(900)
    ok('ai-tab:warning-visible', await js(`(() => { const w = document.querySelector('[data-testid=gemini-warning]'); return !!w && w.getBoundingClientRect().height > 20 && /responsabilidade/.test(w.innerText) })()`))
    ok('ai-tab:mode-3-options', await js(`[...document.querySelectorAll('.s-page .segmented button, .s-page [role=radio]')].map(b => b.innerText.trim()).join('|')`).then((s) => /Desligada/.test(s) && /Gemini/.test(s) && /Ollama/.test(s) ? s : false))
    ok('ai-tab:separate-test-buttons', await js(`!!document.querySelector('[data-testid=test-gemini]') && !!document.querySelector('[data-testid=test-ollama]')`))
    await wait(`/não encontrado|rodando/.test(document.querySelector('[data-testid=ollama-status]')?.innerText || '')`, 6000)
    ok('ai-tab:ollama-status', await js(`document.querySelector('[data-testid=ollama-status]')?.innerText`))
    await shot('ai-01-pt-BR')
    // seletor único (com uma chave do Gemini salva: mesmo assim o Gemini não pode rodar quando Ollama está selecionado)
    await api('/api/settings', 'PATCH', { changes: { 'ai.gemini_key': KEY } }); await sleep(300)
    const attempts = async (txt) => (await api('/api/translation/test', 'POST', { text: txt, src: 'en', tgt: 'pt' })).body.attempts || []
    await clickText('.s-page .segmented button, .s-page [role=radio]', 'Ollama'); await sleep(700)
    let s = (await api('/api/settings')).body
    ok('mode:ollama-saved', s.ai.mode === 'ollama', s.ai.mode)
    let at = await attempts('e2e chain probe ollama ' + Date.now())
    ok('mode:ollama-only-ollama-in-chain', JSON.stringify(at).includes('ollama') && !JSON.stringify(at).includes('gemini'), at)
    await clickText('.s-page .segmented button, .s-page [role=radio]', 'Desligada'); await sleep(700)
    at = await attempts('e2e chain probe off ' + Date.now())
    ok('mode:off-no-ai', (await api('/api/settings')).body.ai.mode === 'off' && !/ollama|gemini/.test(JSON.stringify(at)), at)
    // link do aviso
    await js(`document.querySelector('[data-testid=gemini-warning] .link').click(); 0`); await sleep(300)
    ok('warning:link-aistudio', (global.__egtExternal || []).some((u) => u.startsWith('https://aistudio.google.com')), global.__egtExternal)
    // modelos do Gemini
    const opened = await js(`(async () => { const b = [...document.querySelectorAll('.s-page .select')].find(x => /gemini-3\\.5-flash-lite/.test(x.innerText)); if (!b) return null; b.click(); await new Promise(r => setTimeout(r, 500)); return [...document.querySelectorAll('.select-menu [role=option]')].map(o => o.innerText.replace(/\\s+/g, ' ').trim()) })()`)
    ok('gemini:model-options', opened && opened.length === 4 && /recomendado/.test(opened[0]) && /Outro/.test(opened[3]), opened)
    await shot('ai-02-model-dropdown', 100)
    await clickText('.select-menu [role=option]', 'Outro…'); await sleep(300)
    ok('gemini:custom-input', await js(`!!document.querySelector('.s-page input[placeholder="gemini-…"]')`))
    // chave: salvar → mascarada, criptografada no disco
    await api('/api/settings', 'PATCH', { changes: { 'ai.gemini_key': KEY } }); await sleep(800)
    s = (await api('/api/settings')).body
    ok('key:masked', s.ai.gemini_key === '••••••••' && !JSON.stringify(s).includes(KEY) && s.secrets.state['ai.gemini_key'] === 'ok', s.secrets)
    ok('key:not-plaintext-on-disk', grepDir(CFG, KEY).length === 0 && grepDir(UD, KEY).length === 0, [...grepDir(CFG, KEY), ...grepDir(UD, KEY)])
    const disk = JSON.parse(fs.readFileSync(path.join(CFG, 'settings.json'), 'utf8'))
    ok('key:encrypted-blob', typeof disk.ai.gemini_key === 'object' && /^(aesgcm|keyring|dpapi):v1:/.test(disk.ai.gemini_key.enc), disk.ai.gemini_key.enc.slice(0, 12))
    ok('key:remove-visible', await wait(`!!document.querySelector('[data-testid=gemini-remove]')`))
    await js(`document.querySelector('[data-testid=test-ollama]').scrollIntoView({ block: 'center' }); 0`)
    await js(`document.querySelector('[data-testid=test-ollama]').click(); 0`)
    await wait(`/Ollama não encontrado|Server|servidor/i.test([...document.querySelectorAll('.result')].map(r => r.innerText).join(' '))`, 8000)
    ok('ollama:test-friendly-error', await js(`[...document.querySelectorAll('.result')].map(r => r.innerText).join(' | ')`))
    ok('ollama:test-did-not-change-mode', (await api('/api/settings')).body.ai.mode === 'off')
    await js(`document.querySelector('[data-testid=gemini-warning]').scrollIntoView({ block: 'start' }); 0`)
    await shot('ai-03-key-saved')
    // remover chave: diálogo de confirmação
    await js(`document.querySelector('[data-testid=gemini-remove]').click(); 0`)
    ok('remove:dialog', await wait(`!!document.querySelector('.modal .confirm-text')`))
    ok('remove:dialog-text', await js(`document.querySelector('.modal .confirm-text').innerText`))
    await shot('ai-04-remove-dialog')
    await js(`document.querySelector('.modal-foot .btn.danger').click(); 0`)
    await wait(`!document.querySelector('[data-testid=gemini-remove]')`)
    await sleep(600)
    s = (await api('/api/settings')).body
    ok('remove:state-none', s.secrets.state['ai.gemini_key'] === 'none' && s.ai.gemini_key === '', s.secrets)
    ok('remove:result-shown', await js(`[...document.querySelectorAll('.result')].map(r => r.innerText).join(' | ')`).then((t) => /Chave removida/.test(t) ? t : false))
    ok('remove:nothing-on-disk', grepDir(CFG, KEY).length === 0 && grepDir(UD, KEY).length === 0)
    ok('remove:env-notice', process.env.GEMINI_API_KEY ? await js(`!!document.querySelector('[data-testid=env-notice]')`) : true)
    await shot('ai-05-removed')
    // outro idioma
    for (const l of ['ja', 'ar']) {
      await setLang(l); await sleep(700)
      await js(`document.querySelector('.drawer .s-page')?.scrollTo?.(0, 0); document.querySelector('.drawer-body')?.scrollTo?.(0, 0); 0`)
      ok(`${l}:warning-localized`, await js(`document.querySelector('[data-testid=gemini-warning]')?.innerText`).then((t) => t && !/responsabilidade|responsibility/.test(t) && t.includes('Google') ? t.slice(0, 80) : false))
      await shot(`ai-06-${l}`)
    }
    ok('env-key:never-on-disk', !process.env.GEMINI_API_KEY || (grepDir(CFG, process.env.GEMINI_API_KEY).length === 0 && grepDir(UD, process.env.GEMINI_API_KEY).length === 0))
  } catch (e) { rep.checks.push({ name: 'error', pass: false, extra: String(e && e.stack || e) }); console.log('ERROR', e) }
  rep.failed = rep.checks.filter((c) => !c.pass).map((c) => c.name)
  fs.writeFileSync(path.join(OUT, 'ai-report.json'), JSON.stringify(rep, null, 1))
  app.quit()
}
