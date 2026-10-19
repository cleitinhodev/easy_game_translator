'use strict'
// Hook de E2E (só em modo dev: EGT_E2E=<este arquivo>): dirige a UI real e salva screenshots via capturePage.
const fs = require('node:fs')
const path = require('node:path')
const OUT = process.env.EGT_SHOTS || 'screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const { BrowserWindow } = require('electron')
module.exports = async ({ app, getMain, getBox, openBox, selectRegion, backend }) => {
  fs.mkdirSync(OUT, { recursive: true })
  const main = getMain()
  main.webContents.on('console-message', (_e, level, msg, line, src) => console.log('[renderer]', level, msg, src + ':' + line))
  const wc = () => main.webContents
  const js = (code) => wc().executeJavaScript(code, true)
  const shot = async (name, win = main) => {
    await sleep(450)
    const img = await win.webContents.capturePage()
    fs.writeFileSync(path.join(OUT, name + '.png'), img.toPNG())
    console.log('[shot]', name, img.getSize().width + 'x' + img.getSize().height)
  }
  const api = async (p, method = 'GET', body) => {
    const r = await backend.api(p, { method, body: body ? JSON.stringify(body) : undefined })
    return r
  }
  const click = (match) => js(`(() => { const m = ${JSON.stringify(match)}; const els = [...document.querySelectorAll('button,[role=tab],[role=button],a')];
    const el = els.find(b => (b.getAttribute('aria-label')||'') === m || (b.textContent||'').trim() === m || (b.getAttribute('aria-label')||'').includes(m)) ; if (!el) return 'NOT FOUND: ' + m; el.click(); return 'ok' })()`)
  const log = (...a) => console.log('[e2e]', ...a)

  try {
    main.setSize(1280, 800); main.center()
    await sleep(1200)
    if (process.env.EGT_SHOT_INTRO !== '0') {
      await shot('01-intro-early')
      await sleep(1200)
      await shot('02-intro-late')
    }
    await js(`document.querySelector('.intro')?.click()`)
    await sleep(1400)
    await shot('03-main-empty')
    // fluxo real do seletor de região (overlay por monitor + arrasto simulado)
    const pr = selectRegion('uni')
    await sleep(1800)
    const sel = BrowserWindow.getAllWindows().find((w) => w.webContents.getURL().includes('#/select'))
    if (sel) {
      await shot('03b-selector', sel)
      const ev = (type, x, y) => sel.webContents.sendInputEvent({ type, x, y, button: 'left', clickCount: 1 })
      sel.webContents.sendInputEvent({ type: 'mouseMove', x: 180, y: 300 })
      ev('mouseDown', 180, 300)
      for (let i = 1; i <= 12; i++) { sel.webContents.sendInputEvent({ type: 'mouseMove', x: 180 + i * 50, y: 300 + i * 6, buttons: ['left'] }); await sleep(30) }
      await shot('03c-selector-drag', sel)
      ev('mouseUp', 780, 372)
    } else log('seletor não encontrado')
    log('region', JSON.stringify(await Promise.race([pr, sleep(4000).then(() => 'timeout')])))
    await api('/api/profile', 'PATCH', { ocr_engine: 'rapidocr', target: 'pt' })
    await sleep(900)
    await shot('04-main-region')
    log('start', await click('Iniciar'))
    await sleep(6500)
    await shot('05-main-running')
    await sleep(2500)
    await shot('06-main-running-2')
    log('stop', await click('Parar'))
    // dual
    await api('/api/profile', 'PATCH', { mode: 'dual' })
    await api('/api/profile/region', 'POST', { channel: 'a', bbox: [100, 220, 760, 300] })
    await api('/api/profile/region', 'POST', { channel: 'b', bbox: [100, 340, 760, 420] })
    await sleep(800)
    await click('Iniciar')
    await sleep(7500)
    await shot('07-main-dual')
    main.setSize(940, 660); await sleep(700); await shot('07b-main-dual-narrow')
    main.setSize(1280, 800); await sleep(500)
    await js(`(() => { const b=[...document.querySelectorAll('.select')].find(x=>x.getAttribute('aria-label')==='Traduzir para'); b && b.click() })()`)
    await sleep(500); await shot('07c-select-open')
    await js(`document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))`); await sleep(300)
    await click('Parar')
    await api('/api/profile', 'PATCH', { mode: 'single' })
    await sleep(600)
    // gaveta de opções
    log('settings', await click('Opções'))
    await sleep(900)
    await shot('08-settings-general')
    for (const [tab, n] of [['OCR', '09'], ['Tradução', '10'], ['Substituir', '11'], ['IA', '12'], ['Histórico', '13'], ['Atualizações', '14'], ['Reportar Erros', '15']]) {
      log(tab, await js(`(() => { const b=[...document.querySelectorAll('.drawer-nav button')].find(x=>x.textContent.trim()===${JSON.stringify(tab)}); if(!b) return 'NF'; b.click(); return 'ok' })()`))
      await sleep(700)
      await shot(`${n}-settings-${tab.toLowerCase().replace(/[^a-z]/g, '')}`)
    }
    await js(`document.querySelector('.drawer-layer .scrim')?.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))`)
    await sleep(700)
    log('manual', await click('Manual'))
    await sleep(800)
    await js(`(() => { const t=document.querySelector('.manual-text'); if(!t) return; const set=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set; set.call(t,'Precisamos partir antes que a tempestade chegue.'); t.dispatchEvent(new Event('input',{bubbles:true})) })()`)
    await sleep(2200)
    await shot('16-manual')
    await js(`document.querySelector('.modal-layer .scrim')?.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))`)
    await sleep(600)
    log('help', await click('Ajuda'))
    await sleep(900)
    await shot('17-help')
    await js(`document.querySelector('.modal-layer .scrim')?.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))`)
    await sleep(500)
    // box
    await api('/api/profile', 'PATCH', { box_open: true })
    await click('Iniciar')
    await openBox()
    await sleep(7500)
    const box = getBox()
    if (box) { box.setBounds({ x: 120, y: 120, width: 760, height: 190 }); await shot('18-box', box) }
    await click('Parar')
    await sleep(400)
    await shot('19-main-with-box')
    log('done')
  } catch (e) {
    console.log('[e2e] ERRO', e && e.stack || e)
  }
  setTimeout(() => app.quit(), 500)
}
