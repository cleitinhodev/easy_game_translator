/// <reference types="vite/client" />

type Accel = { ok: boolean; error?: string }

interface EgtBridge {
  platform: string
  getConfig(): Promise<EgtConfig>
  onBackendChange(cb: (info: { state: 'up' | 'down'; port?: number; token?: string; code?: number }) => void): () => void
  restartBackend(): Promise<{ ok: boolean; error?: string }>
  win: {
    minimize(): void
    toggleMaximize(): void
    close(): void
    setAlwaysOnTop(v: boolean): void
    isMaximized(): Promise<boolean>
    onMaximized(cb: (v: boolean) => void): () => void
    showMenu(pt: { x: number; y: number }): void
  }
  region: {
    select(channel: string): Promise<{ bbox: number[]; channel: string } | null>
    done(rect: { x: number; y: number; width: number; height: number }): void
    cancel(): void
  }
  box: {
    open(): Promise<boolean>
    close(): Promise<boolean>
    toggle(): Promise<boolean>
    isOpen(): Promise<boolean>
    setClickThrough(v: boolean): void
    setHover(v: boolean): void
    setExclude(v: boolean): void
    getBounds(): Promise<{ x: number; y: number; width: number; height: number } | null>
    setBounds(b: { x: number; y: number; width: number; height: number }): void
    onState(cb: (s: { open: boolean; clickThrough: boolean }) => void): () => void
  }
  hotkeys: { apply(map: Record<string, string | boolean>): Promise<Record<string, Accel>> }
  components: {
    openFolder(id: string): Promise<{ ok: boolean; error?: string; path?: string }>
    pickFolder(opts?: { title?: string }): Promise<string | null>
  }
  app: {
    setState(s: { running: boolean; dual: boolean }): void
    onAction(cb: (a: { type: string; [k: string]: unknown }) => void): () => void
    quit(): void
    openPath(p: string): Promise<string>
    openExternal(u: string): void
    saveFile(name: string, content: string): Promise<string | null>
    pickFile(opts?: { filters?: { name: string; extensions: string[] }[] }): Promise<string | null>
    setLanguage(l: string): void
    setMaterial(m: string): void
  }
}

interface EgtConfig {
  port: number
  token: string
  platform: string
  version: string
  isDev: boolean
  material: 'none' | 'mica' | 'acrylic'
  appOrigin: string
  e2e: boolean
  userData: string
}

interface Window {
  egt?: EgtBridge
}
