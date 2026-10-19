import { numLocale } from './i18n'
export const fmtMs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`)
export const fmtPct = (v: number) => `${Math.round(v * 100)}%`
export function fmtTime(ts: number, lang: string) {
  return new Date(ts * 1000).toLocaleTimeString(numLocale(lang), { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
export function bboxSize(b?: number[] | null) {
  return b ? { w: Math.abs(b[2] - b[0]), h: Math.abs(b[3] - b[1]) } : null
}
/** 'Control+Alt+S' → ['Ctrl','Alt','S'] para exibição (macOS/Windows). */
export function accelParts(a: string, platform: string): string[] {
  return a.split('+').map((p) => {
    if (p === 'CommandOrControl') return platform === 'darwin' ? '⌘' : 'Ctrl'
    if (p === 'Control') return 'Ctrl'
    if (p === 'Super') return platform === 'darwin' ? '⌘' : 'Win'
    return p
  })
}
export const SOFT_RAINBOW = ['#6a00ff', '#8c00e6', '#aa00cc', '#c400aa', '#de0088', '#f00066', '#ff4444', '#ff7744', '#ffaa44', '#ffee44', '#ccff44', '#88ff66', '#44ffaa', '#44ccff', '#4488ff', '#4455ff']
