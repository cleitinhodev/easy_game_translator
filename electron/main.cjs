'use strict'
// Easy Game Translator v4 — processo principal do Electron.
const path = require('node:path')
const fs = require('node:fs')
const { pathToFileURL } = require('node:url')
const {
  app, BrowserWindow, ipcMain, globalShortcut, Menu, Tray, nativeImage, screen, shell, dialog, protocol, net, session,
} = require('electron')
const { Backend } = require('./backend.cjs')
const W = require('./windows.cjs')
const CV = require('./components.cjs')
const { makeT, readJson, writeJson, resolveLang, systemLanguages } = require('./util.cjs')

const ROOT = path.join(__dirname, '..')
const DEV_URL = process.env.EGT_DEV_URL || ''
const IS_E2E = !app.isPackaged && !!process.env.EGT_E2E
const APP_ORIGIN = DEV_URL ? new URL(DEV_URL).origin : 'egt://app'
const APP_URL = DEV_URL || 'egt://app/index.html'
const DIST = path.join(ROOT, 'dist')

protocol.registerSchemesAsPrivileged([
  { scheme: 'egt', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true, corsEnabled: true } },
])

if (process.platform === 'linux' || process.env.EGT_NO_GPU) {
  if (process.env.EGT_NO_GPU) app.disableHardwareAcceleration()
}
if (process.env.EGT_USER_DATA) app.setPath('userData', process.env.EGT_USER_DATA)

const gotLock = IS_E2E ? true : app.requestSingleInstanceLock()
if (!gotLock) { app.quit(); process.exit(0) }

/** @type {Backend} */
let backend
let mainWin = null
let boxWin = null
let tray = null
let selecting = null          // {resolve, selectors, channel}
let quitting = false
let t = makeT('pt-BR')
let settings = {}             // cópia das configurações do backend (somente leitura aqui)
const appState = { running: false, dual: false, boxOpen: false, clickThrough: false }
let hotkeyMap = {}

// ------------------------------------------------------------------ utilidades
const isTrusted = (e) => {
  try { const u = new URL(e.senderFrame.url); return `${u.protocol}//${u.host}` === APP_ORIGIN } catch { return false }
}
const handle = (ch, fn) => ipcMain.handle(ch, (e, ...a) => { if (!isTrusted(e)) throw new Error('remetente não confiável'); return fn(e, ...a) })
const listen = (ch, fn) => ipcMain.on(ch, (e, ...a) => { if (isTrusted(e)) fn(e, ...a) })
const sendMain = (ch, ...a) => { if (mainWin && !mainWin.isDestroyed()) mainWin.webContents.send(ch, ...a) }
const sendAll = (ch, ...a) => { for (const w of BrowserWindow.getAllWindows()) if (!w.isDestroyed()) w.webContents.send(ch, ...a) }

async function api(pathname, init) {
  try {
    const r = await backend.api(pathname, init)
    return r.ok ? await r.json() : null
  } catch { return null }
}

function showMain() {
  if (!mainWin || mainWin.isDestroyed()) return
  if (mainWin.isMinimized()) mainWin.restore()
  mainWin.show(); mainWin.focus()
}

// ------------------------------------------------------------------ protocolo egt://
function registerAppProtocol() {
  protocol.handle('egt', (req) => {
    const url = new URL(req.url)
    let rel = decodeURIComponent(url.pathname)
    if (rel === '/' || rel === '') rel = '/index.html'
    const file = path.normalize(path.join(DIST, rel))
    if (!file.startsWith(DIST + path.sep)) return new Response('forbidden', { status: 403 })
    return net.fetch(pathToFileURL(file).toString())
  })
}

// ------------------------------------------------------------------ backend
async function bootBackend() {
  backend = new Backend({ packaged: app.isPackaged, root: ROOT, resources: process.resourcesPath })
  backend.on('crashed', (code) => {
    sendAll('backend:changed', { state: 'down', code })
  })
  await backend.start()
  const s = await api('/api/settings')
  if (s) { settings = s; t = makeT(resolveLang(s.ui?.language)) }
}

function config() {
  return {
    port: backend?.port || 0, token: backend?.token || '', platform: process.platform, version: app.getVersion(),
    isDev: !!DEV_URL, material: mainWin?.egtMaterial || 'none', appOrigin: APP_ORIGIN, e2e: IS_E2E,
    userData: app.getPath('userData'), e2eBox: process.env.EGT_E2E_BOX === '1',
  }
}

// ------------------------------------------------------------------ janela principal
function openMainWindow() {
  mainWin = W.createMainWindow({
    url: APP_URL, appOrigin: APP_ORIGIN, material: settings.ui?.material || 'auto',
    onClose: (e) => {
      if (!quitting && settings.ui?.close_to_tray !== false && tray) { e.preventDefault(); mainWin.hide() }
    },
  })
  mainWin.on('maximize', () => sendMain('win:maximized', true))
  mainWin.on('unmaximize', () => sendMain('win:maximized', false))
  mainWin.on('closed', () => { mainWin = null })
}

// ------------------------------------------------------------------ Box Mode
async function openBox() {
  if (boxWin && !boxWin.isDestroyed()) return true
  const prof = await api('/api/profile')
  const set = (await api('/api/settings')) || settings
  boxWin = W.createBoxWindow({
    url: APP_URL + '#/box', appOrigin: APP_ORIGIN, geometry: prof?.box_geometry,
    exclude: set.box?.exclude_from_capture !== false,
    onClosed: () => { boxWin = null; appState.boxOpen = false; appState.clickThrough = false; broadcastBox(); refreshTray() },
  })
  appState.boxOpen = true
  if (set.box?.click_through) setClickThrough(true)
  broadcastBox(); refreshTray()
  api('/api/profile', { method: 'PATCH', body: JSON.stringify({ box_open: true }) })
  return true
}
function closeBox() {
  if (boxWin && !boxWin.isDestroyed()) boxWin.close()
  api('/api/profile', { method: 'PATCH', body: JSON.stringify({ box_open: false }) })
  return true
}
async function toggleBox() { return boxWin && !boxWin.isDestroyed() ? closeBox() : openBox() }
function setClickThrough(v) {
  if (!boxWin || boxWin.isDestroyed()) return
  appState.clickThrough = !!v
  if (v) boxWin.setIgnoreMouseEvents(true, { forward: true })
  else boxWin.setIgnoreMouseEvents(false)
  broadcastBox()
}
function broadcastBox() { sendAll('box:state', { open: appState.boxOpen, clickThrough: appState.clickThrough }) }

// ------------------------------------------------------------------ seleção de região
function dipToPhysical(win, d, rect) {
  const abs = { x: Math.round(d.bounds.x + rect.x), y: Math.round(d.bounds.y + rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }
  if (process.platform === 'win32') return screen.dipToScreenRect(win, abs)
  const sf = d.scaleFactor || 1
  return { x: Math.round(abs.x * sf), y: Math.round(abs.y * sf), width: Math.round(abs.width * sf), height: Math.round(abs.height * sf) }
}
function physicalToDip(rect) {
  if (process.platform === 'win32') return screen.screenToDipRect(null, rect)
  const d = screen.getDisplayMatching(rect)
  const sf = d.scaleFactor || 1
  return { x: Math.round(rect.x / sf), y: Math.round(rect.y / sf), width: Math.round(rect.width / sf), height: Math.round(rect.height / sf) }
}

function endSelection(result) {
  if (!selecting) return
  const s = selecting
  selecting = null
  s.selectors.close()
  if (s.hidMain && mainWin && !mainWin.isDestroyed()) { mainWin.show(); if (!IS_E2E) mainWin.focus() }
  if (s.hidBox && boxWin && !boxWin.isDestroyed()) boxWin.showInactive()
  s.resolve(result)
}

function selectRegion(channel) {
  if (selecting) endSelection(null)
  return new Promise((resolve) => {
    const hidMain = !!(mainWin && mainWin.isVisible() && !IS_E2E)
    if (hidMain) mainWin.hide()
    const hidBox = !!(boxWin && !boxWin.isDestroyed() && boxWin.isVisible() && !IS_E2E)
    if (hidBox) boxWin.hide()
    const selectors = W.createSelectors({ baseUrl: APP_URL, appOrigin: APP_ORIGIN, channel, lang: resolveLang(settings.ui?.language) })
    selecting = { resolve, selectors, channel, hidMain, hidBox }
  })
}

// ------------------------------------------------------------------ atalhos globais
const ACTIONS = ['toggle', 'translate_now', 'toggle_box']
async function runAction(action) {
  if (action === 'toggle_box') { await toggleBox(); return }
  const ep = action === 'toggle' ? '/api/pipeline/toggle' : '/api/pipeline/translate-now'
  const res = await api(ep, { method: 'POST' })
  if (res && !res.ok) sendMain('app:action', { type: 'toast', kind: 'warn', key: res.error === 'no_region' ? 'toast.no_region' : 'toast.action_failed' })
}
function applyHotkeys(map) {
  globalShortcut.unregisterAll()
  hotkeyMap = map || {}
  const out = {}
  const enabled = hotkeyMap.enabled !== false
  for (const a of ACTIONS) {
    const acc = hotkeyMap[a]
    if (!acc) { out[a] = { ok: false, error: 'empty' }; continue }
    if (!enabled) { out[a] = { ok: false, error: 'disabled' }; continue }
    try {
      const ok = globalShortcut.register(acc, () => runAction(a))
      out[a] = ok ? { ok: true } : { ok: false, error: 'in-use' }
    } catch { out[a] = { ok: false, error: 'invalid' } }
  }
  return out
}

// ------------------------------------------------------------------ bandeja e menu
function trayIcon() {
  const img = nativeImage.createFromPath(path.join(ROOT, 'resources', 'tray.png'))
  return img.isEmpty() ? img : img.resize({ width: 20, height: 20, quality: 'best' })
}
function menuTemplate(full) {
  const tpl = [
    { label: appState.running ? t('menu.stop') : t('menu.start'), accelerator: undefined, click: () => runAction('toggle') },
    { label: t('menu.translate_now'), click: () => runAction('translate_now') },
    { label: appState.boxOpen ? t('menu.box_hide') : t('menu.box_show'), click: () => toggleBox() },
    { type: 'separator' },
    { label: t('menu.manual'), click: () => { showMain(); sendMain('app:action', { type: 'open', what: 'manual' }) } },
    { label: t('menu.settings'), click: () => { showMain(); sendMain('app:action', { type: 'open', what: 'settings' }) } },
    { label: t('menu.help'), click: () => { showMain(); sendMain('app:action', { type: 'open', what: 'help' }) } },
  ]
  if (full) {
    tpl.push({ type: 'separator' },
      { label: t('menu.on_top'), type: 'checkbox', checked: !!mainWin?.isAlwaysOnTop(), click: (i) => { mainWin?.setAlwaysOnTop(i.checked); sendMain('app:action', { type: 'always-on-top', value: i.checked }) } },
      { label: t('menu.open_config'), click: async () => { const a = await api('/api/about'); if (a) shell.openPath(a.config_dir) } },
      { label: t('menu.devtools'), visible: !app.isPackaged, click: () => mainWin?.webContents.toggleDevTools() })
  }
  tpl.push({ type: 'separator' }, { label: t('menu.quit'), click: () => app.quit() })
  return Menu.buildFromTemplate(tpl)
}
function refreshTray() {
  if (!tray) return
  try { tray.setContextMenu(menuTemplate(false)); tray.setToolTip(`Easy Game Translator${appState.running ? ' — ' + t('status.running') : ''}`) } catch { /* ignora */ }
}
function createTray() {
  try {
    const icon = trayIcon()
    if (icon.isEmpty()) return
    tray = new Tray(icon)
    tray.on('click', () => { if (mainWin?.isVisible() && mainWin.isFocused()) mainWin.hide(); else showMain() })
    refreshTray()
  } catch { tray = null }
}

// ------------------------------------------------------------------ IPC
function registerIpc() {
  handle('app:config', () => config())
  handle('backend:restart', async () => {
    try { await backend.stop(1500) } catch { /* ignora */ }
    try {
      await backend.start()
      sendAll('backend:changed', { state: 'up', ...config() })
      return { ok: true }
    } catch (e) { return { ok: false, error: String(e.message || e) } }
  })
  listen('win:minimize', (e) => BrowserWindow.fromWebContents(e.sender)?.minimize())
  listen('win:toggle-maximize', (e) => { const w = BrowserWindow.fromWebContents(e.sender); if (w) w.isMaximized() ? w.unmaximize() : w.maximize() })
  listen('win:close', (e) => BrowserWindow.fromWebContents(e.sender)?.close())
  listen('win:always-on-top', (e, v) => BrowserWindow.fromWebContents(e.sender)?.setAlwaysOnTop(!!v, v ? 'floating' : undefined))
  handle('win:is-maximized', (e) => !!BrowserWindow.fromWebContents(e.sender)?.isMaximized())
  listen('win:menu', (e, pt) => {
    const w = BrowserWindow.fromWebContents(e.sender)
    menuTemplate(true).popup({ window: w, x: Math.round(pt?.x ?? 0), y: Math.round(pt?.y ?? 0) })
  })

  handle('region:select', (_e, channel) => selectRegion(String(channel || 'uni')))
  listen('region:done', (e, rect) => {
    if (!selecting) return
    const win = BrowserWindow.fromWebContents(e.sender)
    const d = win?.egtDisplay
    if (!win || !d || !rect || rect.width < 4 || rect.height < 4) return
    const p = dipToPhysical(win, d, rect)
    const bbox = [p.x, p.y, p.x + p.width, p.y + p.height]
    const ch = selecting.channel
    endSelection({ bbox, channel: ch })
    if (!IS_E2E) W.flashRegion({ baseUrl: APP_URL, appOrigin: APP_ORIGIN, rectDip: physicalToDip(p), label: ch === 'a' ? 'A' : ch === 'b' ? 'B' : '' })
  })
  listen('region:cancel', () => endSelection(null))

  handle('box:open', () => openBox())
  handle('box:close', () => closeBox())
  handle('box:toggle', () => toggleBox())
  handle('box:is-open', () => !!(boxWin && !boxWin.isDestroyed()))
  listen('box:click-through', (_e, v) => setClickThrough(v))
  listen('box:hover', (_e, over) => {
    if (!boxWin || boxWin.isDestroyed() || !appState.clickThrough) return
    if (over) boxWin.setIgnoreMouseEvents(false)
    else boxWin.setIgnoreMouseEvents(true, { forward: true })
  })
  listen('box:exclude', (_e, v) => { if (boxWin && !boxWin.isDestroyed()) boxWin.setContentProtection(!!v) })
  handle('box:get-bounds', () => (boxWin && !boxWin.isDestroyed() ? boxWin.getBounds() : null))
  listen('box:set-bounds', (_e, b) => {
    if (!boxWin || boxWin.isDestroyed() || !b) return
    const [minW, minH] = boxWin.getMinimumSize()
    boxWin.setBounds({ x: Math.round(b.x), y: Math.round(b.y), width: Math.max(minW, Math.round(b.width)), height: Math.max(minH, Math.round(b.height)) })
  })

  handle('hotkeys:apply', (_e, map) => applyHotkeys(map))
  listen('app:state', (_e, s) => { Object.assign(appState, { running: !!s.running, dual: !!s.dual }); refreshTray() })
  listen('app:quit', () => app.quit())
  listen('app:language', (_e, l) => { t = makeT(resolveLang(typeof l === 'string' ? l : 'auto')); refreshTray() })
  ipcMain.on('app:system-locales', (e) => { e.returnValue = systemLanguages() })
  listen('app:material', () => { /* aplicado no próximo início */ })
  handle('app:open-path', async (_e, p) => {
    const about = await api('/api/about')
    const allowed = about ? [about.config_dir, about.logs_dir] : []
    if (allowed.includes(p)) return shell.openPath(p)
    return 'caminho não permitido'
  })
  listen('app:open-external', (_e, u) => {
    if (!/^https:\/\//i.test(String(u))) return
    if (IS_E2E) { (global.__egtExternal ||= []).push(String(u)); return }     // testes: só registra
    shell.openExternal(String(u))
  })
  handle('app:save-file', async (e, name, content) => {
    const win = BrowserWindow.fromWebContents(e.sender)
    const ext = path.extname(String(name)).slice(1) || 'txt'
    const r = await dialog.showSaveDialog(win, { defaultPath: path.basename(String(name)), filters: [{ name: ext.toUpperCase(), extensions: [ext] }] })
    if (r.canceled || !r.filePath) return null
    fs.writeFileSync(r.filePath, String(content), { encoding: 'utf8' })
    return r.filePath
  })
  // ---- gerenciador de componentes (Configurações > Atualizações)
  // O renderer só manda o ID do componente; quem decide a pasta é o backend (que valida contra as pastas dos componentes)
  // e aqui validamos de novo antes de abrir.
  handle('components:open-folder', async (_e, id) => {
    if (!CV.validId(id)) return { ok: false, error: 'bad_id' }
    let folder = ''
    try {
      const r = await backend.api(`/api/components/${id}/folder`, { method: 'POST', body: '{}' })
      if (!r.ok) return { ok: false, error: 'backend_' + r.status }
      folder = (await r.json()).path
    } catch { return { ok: false, error: 'backend_down' } }
    if (!CV.validFolder(folder)) return { ok: false, error: 'bad_path' }
    if (IS_E2E) { (global.__egtComponentCalls ||= []).push({ fn: 'open-folder', id, path: folder }); return { ok: true, path: folder } }
    const err = await shell.openPath(folder)
    return err ? { ok: false, error: 'open_failed', detail: err } : { ok: true, path: folder }
  })
  handle('components:pick-folder', async (e, opts) => {
    const title = typeof opts?.title === 'string' ? opts.title.slice(0, 120) : undefined
    if (IS_E2E) { const p = process.env.EGT_E2E_PICK || null; (global.__egtComponentCalls ||= []).push({ fn: 'pick-folder', path: p }); return p }
    const win = BrowserWindow.fromWebContents(e.sender)
    const r = await dialog.showOpenDialog(win, { title, properties: ['openDirectory', 'createDirectory'] })
    return r.canceled ? null : r.filePaths[0]
  })
  handle('app:pick-file', async (e, opts) => {
    const win = BrowserWindow.fromWebContents(e.sender)
    const r = await dialog.showOpenDialog(win, { properties: ['openFile'], filters: opts?.filters })
    return r.canceled ? null : r.filePaths[0]
  })
}

// ------------------------------------------------------------------ ciclo de vida
function permissions() {
  // Só o microfone (tradução manual por voz) é permitido, e só para o nosso app.
  session.defaultSession.setPermissionRequestHandler((wc, perm, cb, details) => {
    const ok = perm === 'media' && (details.requestingUrl || '').startsWith(APP_ORIGIN)
    cb(ok)
  })
  session.defaultSession.setPermissionCheckHandler((_wc, perm, origin) => perm === 'media' && origin.startsWith(APP_ORIGIN))
}

app.on('second-instance', () => showMain())

app.whenReady().then(async () => {
  if (process.platform === "win32") app.setAppUserModelId("com.cleitinhodev.easygametranslator")  // ícone/agrupamento correto na barra de tarefas
  Menu.setApplicationMenu(null)
  if (!DEV_URL) registerAppProtocol()
  permissions()
  registerIpc()
  try {
    await bootBackend()
  } catch (err) {
    await dialog.showMessageBox({ type: 'error', title: 'Easy Game Translator', message: t('error.backend_title'), detail: String(err.message || err) })
    app.exit(1)
    return
  }
  openMainWindow()
  if (!IS_E2E) createTray()
  const hk = settings.hotkeys
  if (hk && !IS_E2E) applyHotkeys(hk)
  if (!IS_E2E) { const prof = await api('/api/profile'); if (prof && prof.box_open) openBox() }
  if (IS_E2E && require('node:fs').existsSync(process.env.EGT_E2E)) require(process.env.EGT_E2E)({ app, getMain: () => mainWin, getBox: () => boxWin, openBox, selectRegion, backend })
})

app.on('before-quit', (e) => {
  if (quitting) return
  quitting = true
  e.preventDefault()
  globalShortcut.unregisterAll()
  Promise.resolve(backend?.stop()).finally(() => app.exit(0))
})
app.on('window-all-closed', () => { if (process.platform !== 'darwin' && !tray) app.quit() })
