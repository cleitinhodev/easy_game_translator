export type Channel = 'uni' | 'a' | 'b'

export interface Profile {
  name: string
  mode: 'single' | 'dual'
  region_single: number[] | null
  region_a: number[] | null
  region_b: number[] | null
  ocr_engine: string
  alphabet: string
  target: string
  interval: number
  preprocess: { scale: number; grayscale: boolean; auto_invert: boolean; contrast: boolean; threshold: boolean; sharpen: boolean; pad: number }
  font_size: number
  font_family: string
  box_geometry: string
  box_open: boolean
  channels: Record<string, number[]>
}

export interface OcrEngine { id: string; name: string; available: boolean; detail: string; pip_hint: string; note: string }
export interface TrEngine { id: string; name: string; online: boolean; available: boolean; detail: string; enabled: boolean; cooldown: number; error: string }
export interface Alphabet { key: string; title: string; tesseract: string; cjk: boolean }
export interface Language { code: string; name: string }
export interface Monitor { left: number; top: number; width: number; height: number }

export interface Metrics {
  running: boolean
  busy: boolean
  fps: number
  ocr_ms: number
  cycle_ms: number
  latency_ms: number
  hit_rate: number
  cache_count: number
  stats: { requests: number; cache_hits: number; live: number; errors: number; passthrough: number }
  ocr_engine: string
  net: 'online' | 'offline' | 'cache' | 'unknown'
  engines: Record<string, { fails: number; cooldown: number; error: string }>
  uptime: number
}

export interface Settings {
  ui: { language: string; play_intro: boolean; intro_full: boolean; always_on_top: boolean; font_size: number; clear_on_empty: boolean; material: string; close_to_tray: boolean; reduce_motion: 'system' | 'on' | 'off'; typewriter: boolean }
  capture: { interval: number }
  filters: { stable_ms: number; max_wait_ms: number; min_chars: number; min_alnum_ratio: number; min_confidence: number; diff_mean: number; similarity: number }
  ocr: { engine: string; tesseract_path: string; tesseract_psm: number; easyocr_gpu: boolean }
  translation: { order: string[]; enabled: string[]; cache_only: boolean; libre_url: string; libre_key: string; lingva_url: string; microsoft_key: string; microsoft_region: string; timeout: number }
  ai: { enabled: boolean; provider: 'gemini' | 'ollama'; gemini_key: string; gemini_model: string; ollama_url: string; ollama_model: string; context: string; env_key_found: boolean }
  box: { alpha: number; borderless: boolean; click_through: boolean; auto_font: boolean; font_size: number; text_color: string; bg_color: string; show_original: boolean; exclude_from_capture: boolean }
  hotkeys: { enabled: boolean; toggle: string; translate_now: string; toggle_box: string }
  config_path: string
}

export interface Snapshot {
  app: { name: string; version: string; author: string }
  profile: Profile
  profiles: string[]
  settings: Settings
  running: boolean
  ocr: OcrEngine[]
  alphabets: Alphabet[]
  languages: Language[]
  monitors: Monitor[]
  engines: TrEngine[]
  metrics: Metrics
}

export interface ChannelView {
  original: string
  translated: string
  ok: boolean
  error: string
  engine: string
  cached: boolean
  confidence: number | null
  ms: number
  src: string
  /** incrementa a cada tradução nova (dispara a animação de revelação) */
  rev: number
  /** incrementa a cada texto original novo */
  orev: number
  ts: number
  empty: boolean
  /** reprocessando após mudar idioma/OCR/regras (mostra "Traduzindo…") */
  pending: boolean
}

export interface HistoryItem { id: number; ts: number; channel: string; original: string; translated: string; src: string; tgt: string; engine: string; from_cache: number; profile: string }

// ---- gerenciador de componentes (Configurações > Atualizações)
export type CompStatus = 'ok' | 'update' | 'missing' | 'unavailable'
export type CompAction = 'install' | 'update' | 'howto' | 'goto_ai' | 'none'
export interface CompItem { id: string; name?: string; installed: boolean | null; user?: boolean; size?: number | null; needed?: boolean }
export interface CompJob {
  id: string; component: string; item: string; label: string; state: 'queued' | 'running' | 'done' | 'error' | 'cancelled'
  done: number; total: number; speed: number; eta: number | null; error: string; remedy: string; verified: string; dest: string
  phase: 'downloading' | 'installing' | 'working' | 'done'; installer: boolean; host: string
}
export interface CompView {
  id: string; category: string; status: CompStatus; installed: boolean; builtin: boolean; version: string; latest: string; location: string
  needed: boolean; offer: boolean; primary: { action: CompAction; item?: string; optional?: boolean }; blocker: string; heavy: boolean
  size: number | null; checked: boolean; check_error: string; offline: boolean; note: string; folder: string | null; folder_custom: boolean
  items: CompItem[]; removable: boolean
  manual: { links: { label: string; url: string }[]; commands: { label: string; cmd: string }[]; notes: string[] }
  add_files: { key: string; exts: string[] } | null; job: CompJob | null
  detect_extra: Record<string, any>
}
export interface CompList {
  components: CompView[]; summary: { all_ok: boolean; needed: string[] }
  paths: { root: string; default_root: string; dirs: Record<string, string | null>; downloads: string }
  demo: boolean; frozen: boolean; platform: string; jobs: CompJob[]
}
