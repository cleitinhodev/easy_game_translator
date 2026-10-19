'use strict'
// Ponte segura (contextIsolation): expõe apenas funções específicas ao renderer.
const { contextBridge, ipcRenderer } = require('electron')

const on = (channel, cb) => {
  const h = (_e, ...args) => cb(...args)
  ipcRenderer.on(channel, h)
  return () => ipcRenderer.removeListener(channel, h)
}

contextBridge.exposeInMainWorld('egt', {
  platform: process.platform,
  systemLocales: (() => { try { return ipcRenderer.sendSync('app:system-locales') } catch { return [] } })(),
  getConfig: () => ipcRenderer.invoke('app:config'),
  onBackendChange: (cb) => on('backend:changed', cb),
  restartBackend: () => ipcRenderer.invoke('backend:restart'),
  win: {
    minimize: () => ipcRenderer.send('win:minimize'),
    toggleMaximize: () => ipcRenderer.send('win:toggle-maximize'),
    close: () => ipcRenderer.send('win:close'),
    setAlwaysOnTop: (v) => ipcRenderer.send('win:always-on-top', !!v),
    isMaximized: () => ipcRenderer.invoke('win:is-maximized'),
    onMaximized: (cb) => on('win:maximized', cb),
    showMenu: (pt) => ipcRenderer.send('win:menu', pt),
  },
  region: {
    select: (channel) => ipcRenderer.invoke('region:select', channel),
    done: (rect) => ipcRenderer.send('region:done', rect),
    cancel: () => ipcRenderer.send('region:cancel'),
  },
  box: {
    open: () => ipcRenderer.invoke('box:open'),
    close: () => ipcRenderer.invoke('box:close'),
    toggle: () => ipcRenderer.invoke('box:toggle'),
    isOpen: () => ipcRenderer.invoke('box:is-open'),
    setClickThrough: (v) => ipcRenderer.send('box:click-through', !!v),
    setHover: (v) => ipcRenderer.send('box:hover', !!v),
    setExclude: (v) => ipcRenderer.send('box:exclude', !!v),
    getBounds: () => ipcRenderer.invoke('box:get-bounds'),
    setBounds: (b) => ipcRenderer.send('box:set-bounds', b),
    onState: (cb) => on('box:state', cb),
  },
  hotkeys: {
    apply: (map) => ipcRenderer.invoke('hotkeys:apply', map),
  },
  components: {
    openFolder: (id) => ipcRenderer.invoke('components:open-folder', id),
    pickFolder: (opts) => ipcRenderer.invoke('components:pick-folder', opts),
  },
  app: {
    setState: (s) => ipcRenderer.send('app:state', s),
    onAction: (cb) => on('app:action', cb),
    quit: () => ipcRenderer.send('app:quit'),
    openPath: (p) => ipcRenderer.invoke('app:open-path', p),
    openExternal: (u) => ipcRenderer.send('app:open-external', u),
    saveFile: (name, content) => ipcRenderer.invoke('app:save-file', name, content),
    pickFile: (opts) => ipcRenderer.invoke('app:pick-file', opts),
    setLanguage: (l) => ipcRenderer.send('app:language', l),
    setMaterial: (m) => ipcRenderer.send('app:material', m),
  },
})
