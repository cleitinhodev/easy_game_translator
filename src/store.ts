import { useCallback } from 'react'
import { create } from 'zustand'
import { api, connectEvents, configureApi, type WsMessage } from '@/api/client'
import type { Channel, ChannelView, CompJob, Metrics, Profile, Settings, Snapshot, TrEngine, OcrEngine } from '@/lib/types'
import { mapBackend } from '@/lib/backendMsg'
import { resolveLang, systemLanguages, translate, type Lang } from '@/lib/i18n'

export type ToastKind = 'info' | 'ok' | 'warn' | 'error'
export interface Toast { id: number; kind: ToastKind; text: string; ttl: number }
export type ModalId = null | 'manual' | 'help' | 'profile-save' | 'about'
export type TabId = 'general' | 'ocr' | 'translation' | 'replace' | 'ai' | 'history' | 'updates' | 'bugs'

const emptyView = (): ChannelView => ({ original: '', translated: '', ok: true, error: '', engine: '', cached: false, confidence: null, ms: 0, src: '', rev: 0, orev: 0, ts: 0, empty: false, pending: false })

interface State {
  conn: 'connecting' | 'online' | 'offline'
  ready: boolean
  snapshot: Snapshot | null
  profile: Profile | null
  settings: Settings | null
  profiles: string[]
  ocr: OcrEngine[]
  engines: TrEngine[]
  metrics: Metrics | null
  running: boolean
  channels: Record<Channel, ChannelView>
  thumbs: Record<Channel, string>
  toasts: Toast[]
  drawer: { open: boolean; tab: TabId }
  modal: ModalId
  boxOpen: boolean
  clickThrough: boolean
  logs: string[]
  historyTick: number
  historyEvent: any | null
  compJobs: Record<string, CompJob>
  compTick: number
  confirm: { text: string; ok: string; danger?: boolean; resolve: (v: boolean) => void } | null
  lang: Lang
  /** versão do app (Electron); o backend pode ser reaproveitado de uma build anterior */
  appVersion: string
  // ações
  init: () => Promise<void>
  toast: (kind: ToastKind, text: string, ttl?: number) => void
  dismissToast: (id: number) => void
  t: (key: string, params?: Record<string, string | number>) => string
  openDrawer: (tab?: TabId) => void
  closeDrawer: () => void
  setTab: (tab: TabId) => void
  setModal: (m: ModalId) => void
  ask: (text: string, ok: string, danger?: boolean) => Promise<boolean>
  patchProfile: (p: Record<string, unknown>) => Promise<void>
  patchSettings: (changes: Record<string, unknown>) => Promise<Settings | null>
  toggle: () => Promise<void>
  translateNow: () => Promise<void>
  selectRegion: (ch: Channel) => Promise<void>
  clearRegion: (ch: Channel) => Promise<void>
  refreshThumb: (ch: Channel) => Promise<void>
  toggleBox: () => Promise<void>
}

let toastId = 1
let initialized = false
const pendingTimers: Record<string, ReturnType<typeof setTimeout>> = {}

export const useStore = create<State>((set, get) => {
  const handle = (m: WsMessage) => {
    switch (m.type) {
      case 'hello': {
        const s = m.data as Snapshot
        applySnapshot(s)
        break
      }
      case 'profile': set({ profile: m.data as Profile }); break
      case 'profiles': set({ profiles: m.data as string[] }); break
      case 'settings': set({ settings: m.data as Settings, lang: resolveLang((m.data as Settings).ui.language, systemLanguages()) }); break
      case 'engines': set({ engines: m.data as TrEngine[] }); break
      case 'metrics': {
        const mt = m.data as Metrics
        set({ metrics: mt, running: mt.running })
        break
      }
      case 'state': {
        const d = m.data as { running: boolean; single_shot?: boolean }
        set({ running: !!d.running })
        break
      }
      case 'pending': {
        const ch = (m.channel || 'uni') as Channel
        set((s) => ({ channels: { ...s.channels, [ch]: { ...s.channels[ch], pending: true } } }))
        clearTimeout(pendingTimers[ch])      // rede de segurança: nunca fica preso em "Traduzindo…"
        pendingTimers[ch] = setTimeout(() => set((s) => ({ channels: { ...s.channels, [ch]: { ...s.channels[ch], pending: false } } })), 20000)
        break
      }
      case 'preview': {
        // miniatura da captura que gerou o texto: chega a cada imagem nova (data URL novo => <img> atualiza)
        const ch = (m.channel || 'uni') as Channel
        if (m.data?.image) set((s) => ({ thumbs: { ...s.thumbs, [ch]: m.data.image } }))
        break
      }
      case 'ocr': {
        const ch = (m.channel || 'uni') as Channel
        const d = m.data
        set((s) => ({ channels: { ...s.channels, [ch]: { ...s.channels[ch], original: d.text, confidence: d.confidence ?? null, orev: s.channels[ch].orev + 1, empty: false } } }))
        break
      }
      case 'empty': {
        const ch = (m.channel || 'uni') as Channel
        const clear = get().settings?.ui.clear_on_empty
        set((s) => ({ channels: { ...s.channels, [ch]: { ...s.channels[ch], original: clear ? '' : s.channels[ch].original, translated: clear ? '' : s.channels[ch].translated, empty: true, pending: false } } }))
        break
      }
      case 'translation': {
        const ch = (m.channel || 'uni') as Channel
        const d = m.data
        if (d.ok) {
          set((s) => ({
            channels: {
              ...s.channels,
              [ch]: { ...s.channels[ch], original: d.original, translated: d.translated, ok: true, error: '', engine: d.engine, cached: !!d.cached, ms: d.ms ?? 0, src: d.src || '', rev: s.channels[ch].rev + 1, ts: Date.now(), empty: false, pending: false },
            },
            historyTick: s.historyTick + 1,
            historyEvent: d.history || null,
          }))
        } else {
          set((s) => ({ channels: { ...s.channels, [ch]: { ...s.channels[ch], ok: false, error: d.error || '', pending: false } } }))
        }
        break
      }
      case 'history_cleared': set((s) => ({ historyTick: s.historyTick + 1, historyEvent: null })); break
      case 'error': {
        set((s) => ({ channels: Object.fromEntries(Object.entries(s.channels).map(([k, c]) => [k, { ...c, pending: false }])) as typeof s.channels }))
        const text = String(m.data?.message || '')
        if (text) get().toast('warn', mapError(text, get().t), 6000)
        break
      }
      case 'component_job': {
        const j = m.data as CompJob
        set((s) => ({ compJobs: { ...s.compJobs, [j.id]: j } }))
        break
      }
      case 'component_changed': set((s) => ({ compTick: s.compTick + 1 })); break
      case 'log': set((s) => ({ logs: [...s.logs.slice(-199), m.line || ''] })); break
      default: break
    }
  }

  const applySnapshot = (s: Snapshot) => {
    set((st) => ({
      snapshot: s, profile: s.profile, settings: s.settings, profiles: s.profiles, ocr: s.ocr, engines: s.engines,
      metrics: s.metrics, running: s.running, lang: resolveLang(s.settings.ui.language, systemLanguages()), ready: true,
      boxOpen: st.boxOpen,
    }))
  }

  return {
    conn: 'connecting', ready: false, snapshot: null, profile: null, settings: null, profiles: [], ocr: [], engines: [],
    metrics: null, running: false,
    channels: { uni: emptyView(), a: emptyView(), b: emptyView() },
    thumbs: { uni: '', a: '', b: '' },
    toasts: [], drawer: { open: false, tab: 'general' }, modal: null, boxOpen: false, clickThrough: false, logs: [],
    historyTick: 0, historyEvent: null, compJobs: {}, compTick: 0, confirm: null, lang: resolveLang('auto', systemLanguages()), appVersion: '',

    t: (key, params) => translate(get().lang, key, params),

    async init() {
      if (initialized) return
      initialized = true
      let cfg: EgtConfig | undefined
      if (window.egt) cfg = await window.egt.getConfig()
      else {
        const q = new URLSearchParams(location.search)   // modo navegador (testes/dev sem Electron)
        cfg = { port: Number(q.get('port')), token: q.get('token') || '', platform: 'linux', version: '4.0.7', isDev: true, material: 'none', appOrigin: '', e2e: false, userData: '' }
      }
      configureApi(cfg.port, cfg.token)
      set({ appVersion: cfg.version || '' })
      if (cfg.e2e) { (window as unknown as Record<string, unknown>).__egt = useStore; (window as unknown as Record<string, unknown>).__egtResolve = resolveLang }   // só no modo E2E de desenvolvimento
      try { applySnapshot(await api.state()) } catch { /* o WS tenta de novo */ }
      connectEvents(handle, (up) => {
        set({ conn: up ? 'online' : 'offline' })
        if (up) get().refreshThumb('uni')
      })
      window.egt?.onBackendChange(async (info) => {
        if (info.state === 'up' && info.port) { configureApi(info.port, info.token || ''); window.location.reload() }
        else set({ conn: 'offline' })
      })
      window.egt?.box.onState((s) => set({ boxOpen: s.open, clickThrough: s.clickThrough }))
      window.egt?.box.isOpen().then((o) => set({ boxOpen: o }))
      window.egt?.app.onAction((a) => {
        if (a.type === 'toast') get().toast((a.kind as ToastKind) || 'info', get().t(String(a.key)))
        else if (a.type === 'open') {
          if (a.what === 'settings') get().openDrawer()
          else get().setModal(a.what as ModalId)
        } else if (a.type === 'always-on-top') get().patchSettings({ 'ui.always_on_top': !!a.value })
      })
    },

    toast(kind, text, ttl = 4200) {
      const id = toastId++
      set((s) => ({ toasts: [...s.toasts.filter((x) => x.text !== text).slice(-3), { id, kind, text, ttl }] }))
    },
    dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
    openDrawer: (tab) => set((s) => ({ drawer: { open: true, tab: tab || s.drawer.tab } })),
    closeDrawer: () => set((s) => ({ drawer: { ...s.drawer, open: false } })),
    setTab: (tab) => set((s) => ({ drawer: { ...s.drawer, tab } })),
    setModal: (modal) => set({ modal }),
    ask: (text, ok, danger) => new Promise((resolve) => set({ confirm: { text, ok, danger, resolve: (v) => { set({ confirm: null }); resolve(v) } } })),

    async patchProfile(p) {
      if (get().running && ('target' in p || 'alphabet' in p || 'ocr_engine' in p || 'preprocess' in p))   // feedback imediato, antes do backend responder
        set((s) => ({ channels: Object.fromEntries(Object.entries(s.channels).map(([k, c]) => [k, { ...c, pending: c.translated !== '' || c.original !== '' }])) as typeof s.channels }))
      try { await api.patch('/api/profile', p) } catch (e: any) { get().toast('error', mapError(String(e.message), get().t)) }
    },
    async patchSettings(changes) {
      try {
        const r = await api.patch<{ settings: Settings }>('/api/settings', { changes })
        set({ settings: r.settings, lang: resolveLang(r.settings.ui.language, systemLanguages()) })
        return r.settings
      } catch (e: any) { get().toast('error', mapError(String(e.message), get().t)); return null }
    },
    async toggle() {
      const r = await api.post<{ ok: boolean; running: boolean; error: string }>('/api/pipeline/toggle')
      if (!r.ok) get().toast('warn', r.error === 'no_region' ? get().t('toast.no_region') : r.error || get().t('toast.action_failed'))
      set({ running: r.running })
    },
    async translateNow() {
      const r = await api.post<{ ok: boolean; error: string }>('/api/pipeline/translate-now')
      if (!r.ok) get().toast('warn', r.error === 'no_region' ? get().t('toast.no_region') : r.error)
    },
    async selectRegion(ch) {
      if (!window.egt) { get().toast('info', 'Electron necessário para selecionar a região'); return }
      const res = await window.egt.region.select(ch)
      if (!res) return
      try {
        await api.post('/api/profile/region', { channel: ch, bbox: res.bbox })
        const w = Math.abs(res.bbox[2] - res.bbox[0]), h = Math.abs(res.bbox[3] - res.bbox[1])
        get().toast('ok', get().t('toast.region_set', { w, h }))
        get().refreshThumb(ch)
      } catch (e: any) { get().toast('error', mapError(String(e.message), get().t)) }
    },
    async clearRegion(ch) {
      await api.post('/api/profile/region', { channel: ch, bbox: null })
      set((s) => ({ thumbs: { ...s.thumbs, [ch]: '' } }))
    },
    async refreshThumb(ch) {
      try {
        const r = await api.post<{ image: string }>('/api/capture/preview', { channel: ch, max_width: 520 })
        set((s) => ({ thumbs: { ...s.thumbs, [ch]: r.image } }))
      } catch { set((s) => ({ thumbs: { ...s.thumbs, [ch]: '' } })) }
    },
    async toggleBox() {
      if (!window.egt) return
      await window.egt.box.toggle()
    },
  }
})

const mapError = mapBackend

export function useT() {
  const lang = useStore((s) => s.lang)
  return useCallback((key: string, params?: Record<string, string | number>) => translate(lang, key, params), [lang])
}
