'use strict'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
module.exports = async ({ app, getMain }) => {
  const main = getMain(); const wc = main.webContents; const js = (c) => wc.executeJavaScript(c, true)
  await sleep(2500); await js(`document.querySelector('.intro')?.click()`); await sleep(800)
  for (const w of [1180, 1280, 1400]) {
    main.setSize(w, 780); await sleep(900)
    console.log('PROBE', w, JSON.stringify(await js(`(() => { const r = [...document.querySelectorAll('.tb-row.options .opt-group')].map(g => { const b = g.getBoundingClientRect(); return [g.querySelector('.opt-label')?.innerText, Math.round(b.left), Math.round(b.right), Math.round(b.top)] }); return { iw: innerWidth, r } })()`)))
  }
  app.quit()
}
