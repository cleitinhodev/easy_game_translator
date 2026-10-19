'use strict'
// Janelas: principal (Mica/acrílico quando possível), Box Mode (transparente, sempre no topo) e seletor de região.
const path = require('node:path')
const { BrowserWindow, screen, shell, app } = require('electron')
const { readJson, writeJson, winBuild } = require('./util.cjs')

const PRELOAD = path.join(__dirname, 'preload.cjs')
// ícone da Nina (dentro do asar: resources/); .ico no Windows, .png no Linux/dev
const ICON = path.join(__dirname, '..', 'resources', process.platform === 'win32' ? 'icon.ico' : 'icon.png')
const BASE_BG = '#1c1f44'

function webPrefs(extra = {}) {
  return {
    preload: PRELOAD, sandbox: true, contextIsolation: true, nodeIntegration: false, webSecurity: true,
    spellcheck: false, autoplayPolicy: 'no-user-gesture-required', ...extra,
  }
}

/** Mantém a janela dentro do app: bloqueia navegação e abre links https no navegador do sistema. */
function lockNavigation(win, appOrigin) {
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https:\/\//i.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (e, url) => { if (!url.startsWith(appOrigin)) e.preventDefault() })
}

function visibleBounds(b) {
  if (!b) return null
  const d = screen.getDisplayMatching({ x: b.x, y: b.y, width: b.width, height: b.height })
  const wa = d.workArea
  const w = Math.min(b.width, wa.width), h = Math.min(b.height, wa.height)
  const x = Math.min(Math.max(b.x, wa.x), wa.x + wa.width - Math.min(w, 120))
  const y = Math.min(Math.max(b.y, wa.y), wa.y + wa.height - Math.min(h, 60))
  return { x, y, width: w, height: h }
}

/** 'x,y,w,h' (v4) ou 'WxH+X+Y' (v3). */
function parseGeometry(s) {
  if (!s) return null
  let m = /^(-?\d+),(-?\d+),(\d+),(\d+)$/.exec(s)
  if (m) return { x: +m[1], y: +m[2], width: +m[3], height: +m[4] }
  m = /^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$/.exec(s)
  if (m) return { x: +m[3], y: +m[4], width: +m[1], height: +m[2] }
  return null
}

function resolveMaterial(pref) {
  // 'auto' → Mica no Windows 11 (build 22621+); acrílico exige 22000+. Outros sistemas: sólido.
  const build = winBuild()
  if (pref === 'none' || process.platform !== 'win32') return 'none'
  if (pref === 'acrylic') return build >= 22000 ? 'acrylic' : 'none'
  if (pref === 'mica') return build >= 22000 ? 'mica' : 'none'
  return build >= 22621 ? 'mica' : 'none'
}

function createMainWindow({ url, appOrigin, material, onClose }) {
  const st = readJson('window-state.json', null)
  const bounds = visibleBounds(st && st.bounds)
  const mat = resolveMaterial(material)
  const isWin = process.platform === 'win32'
  const win = new BrowserWindow({
    width: bounds?.width ?? 1180, height: bounds?.height ?? 780, x: bounds?.x, y: bounds?.y,
    minWidth: 940, minHeight: 640, show: false, title: 'Easy Game Translator', icon: ICON,
    backgroundColor: mat === 'none' ? BASE_BG : '#00000000',
    ...(mat !== 'none' ? { backgroundMaterial: mat } : {}),
    titleBarStyle: 'hidden',
    ...(process.platform !== 'darwin'
      ? { titleBarOverlay: { color: '#00000000', symbolColor: '#d7dbff', height: 44 } } : {}),
    webPreferences: webPrefs({ backgroundThrottling: false }),
  })
  win.egtMaterial = mat
  lockNavigation(win, appOrigin)
  if (st && st.maximized) win.maximize()
  const save = () => {
    if (win.isDestroyed() || win.isMinimized() || win.isFullScreen()) return
    writeJson('window-state.json', { bounds: win.isMaximized() ? (st && st.bounds) || win.getNormalBounds() : win.getBounds(), maximized: win.isMaximized() })
  }
  let t
  const debounced = () => { clearTimeout(t); t = setTimeout(save, 400) }
  win.on('resize', debounced); win.on('move', debounced)
  win.on('maximize', save); win.on('unmaximize', save)
  win.on('close', (e) => { save(); if (onClose) onClose(e) })
  win.once('ready-to-show', () => win.show())
  win.loadURL(url)
  return win
}

function createBoxWindow({ url, appOrigin, geometry, exclude, onClosed }) {
  const g = visibleBounds(parseGeometry(geometry)) || (() => {
    const wa = screen.getPrimaryDisplay().workArea
    return { width: 560, height: 280, x: wa.x + Math.round((wa.width - 560) / 2), y: wa.y + wa.height - 340 }
  })()
  const win = new BrowserWindow({
    ...g, minWidth: 240, minHeight: 100, frame: false, transparent: true, hasShadow: false, resizable: true,
    alwaysOnTop: true, skipTaskbar: false, show: false, title: 'Box Mode', icon: ICON, backgroundColor: '#00000000',
    webPreferences: webPrefs({ backgroundThrottling: false }),
  })
  win.setAlwaysOnTop(true, 'screen-saver')
  win.setContentProtection(!!exclude)     // Windows 10 2004+: a caixa some das capturas (o OCR não lê a si mesma)
  lockNavigation(win, appOrigin)
  win.once('ready-to-show', () => win.showInactive())
  win.on('closed', () => onClosed && onClosed())
  win.loadURL(url)
  return win
}

/** Uma janela transparente por monitor; devolve {wins, done(): fecha todas}. */
function createSelectors({ baseUrl, appOrigin, channel, lang }) {
  const wins = []
  for (const d of screen.getAllDisplays()) {
    const win = new BrowserWindow({
      x: d.bounds.x, y: d.bounds.y, width: d.bounds.width, height: d.bounds.height,
      frame: false, transparent: true, hasShadow: false, resizable: false, movable: false, minimizable: false,
      maximizable: false, fullscreenable: false, alwaysOnTop: true, skipTaskbar: true, show: false,
      backgroundColor: '#00000000', enableLargerThanScreen: true,
      webPreferences: webPrefs(),
    })
    win.egtDisplay = d
    win.setAlwaysOnTop(true, 'screen-saver')
    win.setBounds(d.bounds)
    lockNavigation(win, appOrigin)
    win.once('ready-to-show', () => { win.show(); win.focus() })
    win.loadURL(`${baseUrl}#/select?ch=${encodeURIComponent(channel)}&sf=${d.scaleFactor}&lang=${lang}&dw=${d.bounds.width}&dh=${d.bounds.height}`)
    wins.push(win)
  }
  return {
    wins,
    close() { for (const w of wins) if (!w.isDestroyed()) w.close() },
  }
}

/** Contorno rápido da região escolhida (janela que ignora o mouse e some sozinha). */
function flashRegion({ baseUrl, appOrigin, rectDip, label }) {
  const pad = 6
  const win = new BrowserWindow({
    x: rectDip.x - pad, y: rectDip.y - pad, width: rectDip.width + pad * 2, height: rectDip.height + pad * 2,
    frame: false, transparent: true, hasShadow: false, resizable: false, focusable: false, alwaysOnTop: true,
    skipTaskbar: true, show: false, backgroundColor: '#00000000',
    webPreferences: webPrefs(),
  })
  win.setIgnoreMouseEvents(true)
  win.setAlwaysOnTop(true, 'screen-saver')
  win.setContentProtection(true)
  lockNavigation(win, appOrigin)
  win.once('ready-to-show', () => win.showInactive())
  win.loadURL(`${baseUrl}#/flash?label=${encodeURIComponent(label || '')}`)
  setTimeout(() => { if (!win.isDestroyed()) win.close() }, 1500)
  return win
}

module.exports = { createMainWindow, createBoxWindow, createSelectors, flashRegion, parseGeometry, resolveMaterial, visibleBounds }
