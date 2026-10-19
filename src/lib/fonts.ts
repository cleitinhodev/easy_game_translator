// Famílias de fonte do texto traduzido (janela principal e Modo Caixa).
// Fontes embutidas: licença OFL (ver resources/licenses/FONTS-OFL.txt). As demais são fontes do sistema, com pilhas de reserva.
export interface FontOpt { id: string; label: string; stack: string; bundled?: boolean; kind: 'ui' | 'system' | 'bundled' }

// Reserva para escritas que a fonte escolhida não tem (japonês, chinês, coreano, árabe, tailandês, hindi…).
const FALLBACK = "'Segoe UI', 'Yu Gothic UI', 'Yu Gothic', Meiryo, 'Microsoft YaHei UI', 'Microsoft YaHei', 'Microsoft JhengHei', 'Malgun Gothic', " +
  "'Noto Sans CJK JP', 'Noto Sans CJK SC', 'Noto Sans CJK KR', 'Noto Sans JP', 'Noto Sans SC', 'Noto Sans KR', 'Noto Sans Arabic', " +
  "'Leelawadee UI', 'Noto Sans Thai', 'Nirmala UI', 'Noto Sans Devanagari', 'Noto Sans', system-ui, sans-serif"
const SERIF_FALLBACK = "'Noto Serif', 'Noto Serif CJK JP', 'Noto Serif CJK SC', 'Yu Mincho', 'MS Mincho', SimSun, 'Noto Sans CJK JP', " + FALLBACK

export const DEFAULT_FONT = 'default'

export const FONTS: FontOpt[] = [
  { id: 'default', label: 'Segoe UI / Inter', kind: 'ui', stack: '' },
  { id: 'arial', label: 'Arial', kind: 'system', stack: `Arial, 'Liberation Sans', Helvetica, ${FALLBACK}` },
  { id: 'verdana', label: 'Verdana', kind: 'system', stack: `Verdana, 'DejaVu Sans', Geneva, ${FALLBACK}` },
  { id: 'georgia', label: 'Georgia', kind: 'system', stack: `Georgia, 'Times New Roman', 'Liberation Serif', ${SERIF_FALLBACK}` },
  { id: 'comic', label: 'Comic Sans MS', kind: 'system', stack: `'Comic Sans MS', 'Comic Neue', 'Chalkboard SE', ${FALLBACK}` },
  { id: 'consolas', label: 'Consolas', kind: 'system', stack: `Consolas, 'Cascadia Mono', 'DejaVu Sans Mono', Menlo, monospace, ${FALLBACK}` },
  { id: 'impact', label: 'Impact', kind: 'system', stack: `Impact, Haettenschweiler, 'Arial Narrow Bold', 'Anton', ${FALLBACK}` },
  { id: 'inter', label: 'Inter', kind: 'bundled', bundled: true, stack: `'Inter Variable', Inter, ${FALLBACK}` },
  { id: 'nunito', label: 'Nunito', kind: 'bundled', bundled: true, stack: `Nunito, ${FALLBACK}` },
  { id: 'poppins', label: 'Poppins', kind: 'bundled', bundled: true, stack: `Poppins, ${FALLBACK}` },
  { id: 'atkinson', label: 'Atkinson Hyperlegible', kind: 'bundled', bundled: true, stack: `'Atkinson Hyperlegible', ${FALLBACK}` },
  { id: 'pixel', label: 'Press Start 2P', kind: 'bundled', bundled: true, stack: `'Press Start 2P', ${FALLBACK}` },
  { id: 'orbitron', label: 'Orbitron', kind: 'bundled', bundled: true, stack: `Orbitron, ${FALLBACK}` },
  { id: 'bangers', label: 'Bangers', kind: 'bundled', bundled: true, stack: `Bangers, ${FALLBACK}` },
]

export const fontById = (id?: string | null): FontOpt => FONTS.find((f) => f.id === id) ?? FONTS[0]

/** Aplica a família ao documento (variável CSS --tr-font). 'default' remove a variável: aparência idêntica à das versões anteriores. */
export function applyFont(id?: string | null) {
  const f = fontById(id)
  const el = document.documentElement
  if (!f.stack) el.style.removeProperty('--tr-font')
  else el.style.setProperty('--tr-font', f.stack)
  el.dataset.trFont = f.id
}
