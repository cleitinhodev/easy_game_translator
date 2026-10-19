import locales from '@i18n/_locales.json'

export interface LocaleInfo { code: string; native: string; rtl: boolean }
export const LOCALES: LocaleInfo[] = locales
export type Lang = string          // código de um idioma em LOCALES ('pt-BR', 'en', 'ja', …)
export const FALLBACK_LANG = 'en'

// Todos os dicionários vão embutidos (app offline); chaves ausentes caem em inglês e depois em pt-BR.
const mods = import.meta.glob('../../shared/i18n/*.json', { eager: true, import: 'default' }) as Record<string, Record<string, string>>
const dicts: Record<string, Record<string, string>> = {}
for (const [p, d] of Object.entries(mods)) { const code = p.split('/').pop()!.replace(/\.json$/, ''); if (!code.startsWith('_')) dicts[code] = d }

export const isLang = (l: unknown): l is Lang => typeof l === 'string' && LOCALES.some((x) => x.code === l)
export const isRtl = (l: Lang) => !!LOCALES.find((x) => x.code === l)?.rtl
/** Código BCP-47 para formatar datas/números (árabe com dígitos latinos, como no resto da interface). */
export const numLocale = (l: Lang) => (l === 'ar' ? 'ar-u-nu-latn' : l)

/** Um idioma do sistema ('pt-PT', 'zh-Hant-TW', 'ja-JP'…) → idioma suportado, ou null. */
export function matchLocale(tag: string): Lang | null {
  const t = tag.replace('_', '-').toLowerCase()
  const exact = LOCALES.find((x) => x.code.toLowerCase() === t)
  if (exact) return exact.code
  const [base, ...rest] = t.split('-')
  if (base === 'zh') return rest.some((r) => ['tw', 'hk', 'mo', 'hant'].includes(r)) ? 'zh-TW' : 'zh-CN'
  if (base === 'pt') return 'pt-BR'
  if (base === 'nb' || base === 'nn') return null
  return LOCALES.find((x) => x.code.toLowerCase() === base)?.code ?? null
}

/** Resolve a preferência ('auto' ou um código) usando a lista de idiomas do sistema; sem correspondência → inglês. */
export function resolveLang(pref: string | undefined, system: readonly string[] = []): Lang {
  if (pref && pref !== 'auto') return isLang(pref) ? pref : (matchLocale(pref) ?? FALLBACK_LANG)
  for (const s of system) { const m = matchLocale(s); if (m) return m }
  return FALLBACK_LANG
}

export function systemLanguages(): string[] {
  const fromElectron = (window as unknown as { egt?: { systemLocales?: string[] } }).egt?.systemLocales
  const nav = typeof navigator !== 'undefined' ? [...(navigator.languages ?? []), navigator.language] : []
  return [...(fromElectron ?? []), ...nav].filter(Boolean)
}

export function translate(lang: Lang, key: string, params?: Record<string, string | number>): string {
  let s = dicts[lang]?.[key] ?? dicts[FALLBACK_LANG]?.[key] ?? dicts['pt-BR']?.[key] ?? key
  if (params) for (const [k, v] of Object.entries(params)) s = s.split(`{${k}}`).join(String(v))
  return s
}
