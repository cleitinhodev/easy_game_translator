import { AnimatePresence, motion, animate, useReducedMotion } from 'motion/react'
import { createContext, forwardRef, useCallback, useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { IChevron, ICheck } from './icons'
import { SOFT_RAINBOW } from '@/lib/format'

/* ------------------------------------------------------------------ Tooltip */
export function Tip({ label, children, side = 'bottom', delay = 450 }: { label: ReactNode; children: ReactNode; side?: 'top' | 'bottom'; delay?: number }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const ref = useRef<HTMLSpanElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const id = useId()
  const show = useCallback(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      const r = ref.current?.getBoundingClientRect()
      if (!r) return
      setPos({ x: r.left + r.width / 2, y: side === 'bottom' ? r.bottom + 8 : r.top - 8 })
      setOpen(true)
    }, delay)
  }, [delay, side])
  const hide = useCallback(() => { clearTimeout(timer.current); setOpen(false) }, [])
  useEffect(() => () => clearTimeout(timer.current), [])
  if (!label) return <>{children}</>
  return (
    <span ref={ref} className="tip-wrap" onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide} onPointerDown={hide} aria-describedby={open ? id : undefined}>
      {children}
      {createPortal(
        <AnimatePresence>
          {open && pos && (
            <motion.div id={id} role="tooltip" className={`tooltip ${side}`} style={{ left: pos.x, top: pos.y }}
              initial={{ opacity: 0, y: side === 'bottom' ? -4 : 4, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.97 }} transition={{ duration: 0.14 }}>
              {label}
            </motion.div>
          )}
        </AnimatePresence>, document.body)}
    </span>
  )
}

/* ------------------------------------------------------------------ Buttons */
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'primary' | 'ghost' | 'danger' | 'success'; size?: 'sm' | 'md'; icon?: ReactNode; tip?: ReactNode; busy?: boolean }
export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button({ variant = 'default', size = 'md', icon, tip, busy, children, className = '', disabled, ...rest }, ref) {
  const btn = (
    <motion.button ref={ref as never} type="button" className={`btn ${variant} ${size} ${className}`} disabled={disabled || busy} whileTap={{ scale: 0.96 }} transition={{ type: 'spring', stiffness: 600, damping: 30 }} {...(rest as object)}>
      {busy ? <span className="spinner" aria-hidden /> : icon}
      {children != null && <span className="btn-label">{children}</span>}
    </motion.button>
  )
  return tip ? <Tip label={tip}>{btn}</Tip> : btn
})

export function IconButton({ label, children, className = '', ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <Tip label={label}>
      <motion.button type="button" aria-label={label} className={`icon-btn ${className}`} whileTap={{ scale: 0.9 }} transition={{ type: 'spring', stiffness: 600, damping: 28 }} {...(rest as object)}>
        {children}
      </motion.button>
    </Tip>
  )
}

/* ------------------------------------------------------------------ Switch / Segmented */
export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} className={`switch ${checked ? 'on' : ''}`} onClick={() => onChange(!checked)}>
      <motion.span className="knob" layout transition={{ type: 'spring', stiffness: 700, damping: 34 }} />
    </button>
  )
}

export function Segmented<T extends string>({ value, options, onChange, label, size = 'md' }: { value: T; options: { value: T; label: ReactNode; tip?: ReactNode }[]; onChange: (v: T) => void; label?: string; size?: 'sm' | 'md' }) {
  const gid = useId()
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const onKey = (e: React.KeyboardEvent, i: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    const n = (i + (e.key === 'ArrowRight' ? 1 : -1) + options.length) % options.length
    onChange(options[n].value); refs.current[n]?.focus()
  }
  return (
    <div className={`seg ${size}`} role="radiogroup" aria-label={label}>
      {options.map((o, i) => {
        const on = o.value === value
        const b = (
          <button key={o.value} ref={(el) => { refs.current[i] = el }} type="button" role="radio" aria-checked={on} tabIndex={on ? 0 : -1} className={on ? 'on' : ''} onClick={() => onChange(o.value)} onKeyDown={(e) => onKey(e, i)}>
            {on && <motion.span layoutId={`seg-${gid}`} className="seg-pill" transition={{ type: 'spring', stiffness: 520, damping: 38 }} />}
            <span className="seg-label">{o.label}</span>
          </button>
        )
        return o.tip ? <Tip key={o.value} label={o.tip}>{b}</Tip> : b
      })}
    </div>
  )
}

/* ------------------------------------------------------------------ Slider */
export function Slider({ value, min, max, step = 1, onChange, onCommit, label, format, width }: { value: number; min: number; max: number; step?: number; onChange?: (v: number) => void; onCommit?: (v: number) => void; label?: string; format?: (v: number) => string; width?: number | string }) {
  const [v, setV] = useState(value)
  const drag = useRef(false)
  useEffect(() => { if (!drag.current) setV(value) }, [value])
  const pct = ((v - min) / (max - min)) * 100
  return (
    <div className="slider-wrap" style={{ width }}>
      <input type="range" className="slider" min={min} max={max} step={step} value={v} aria-label={label} style={{ '--pct': `${pct}%` } as React.CSSProperties}
        onPointerDown={() => { drag.current = true }}
        onChange={(e) => { const n = Number(e.target.value); setV(n); onChange?.(n) }}
        onPointerUp={() => { drag.current = false; onCommit?.(v) }}
        onKeyUp={() => onCommit?.(v)}
        onBlur={() => { drag.current = false }} />
      {format && <span className="slider-val">{format(v)}</span>}
    </div>
  )
}

/* ------------------------------------------------------------------ Select (popover acessível) */
export interface Opt { value: string; label: ReactNode; sub?: ReactNode; disabled?: boolean }

/** Posição do menu suspenso (sempre dentro da janela): margem de 8 px, abre para cima quando há mais espaço acima,
 *  desliza na horizontal para caber (também em RTL) e limita altura/largura ao espaço disponível (com rolagem interna). */
export interface MenuPos { left: number; top?: number; bottom?: number; maxHeight: number; maxWidth: number; minWidth: number; flip: boolean; originX: 'left' | 'right' }
const EDGE = 8, GAP = 6, MAX_H = 320
export function placeMenu(r: DOMRect, menuW: number, menuH: number, opts: { minWidth: number; align: 'left' | 'right'; rtl: boolean; vw?: number; vh?: number }): MenuPos {
  const vw = opts.vw ?? window.innerWidth, vh = opts.vh ?? window.innerHeight
  const maxWidth = Math.max(80, vw - 2 * EDGE)
  const minWidth = Math.min(opts.minWidth, maxWidth)
  const w = Math.min(Math.max(menuW, minWidth), maxWidth)
  const below = vh - r.bottom - GAP - EDGE, above = r.top - GAP - EDGE
  const want = Math.min(MAX_H, menuH || MAX_H)
  const flip = want > below && above > below
  const maxHeight = Math.max(60, Math.min(MAX_H, flip ? above : below))
  const endAligned = opts.align === 'right' ? !opts.rtl : opts.rtl        // 'right' = alinhado ao fim do botão
  let left = endAligned ? r.right - w : r.left
  left = Math.max(EDGE, Math.min(left, vw - EDGE - w))
  const originX = left + w / 2 < r.left + r.width / 2 ? 'right' : 'left'
  return flip ? { left, bottom: vh - r.top + GAP, maxHeight, maxWidth, minWidth, flip, originX } : { left, top: r.bottom + GAP, maxHeight, maxWidth, minWidth, flip, originX }
}

export function Select({ value, options, onChange, label, width, placeholder, align = 'left', icon, className = '', display, menuWidth }: { display?: ReactNode; menuWidth?: number; value: string; options: Opt[]; onChange: (v: string) => void; label?: string; width?: number | string; placeholder?: string; align?: 'left' | 'right'; icon?: ReactNode; className?: string }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<MenuPos | null>(null)
  const [hi, setHi] = useState(0)
  const btn = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const follow = useRef(true)        // rolar até a opção destacada só na abertura / pelo teclado (não ao passar o mouse)
  const id = useId()
  const cur = options.find((o) => o.value === value)
  const place = useCallback(() => {
    const b = btn.current; if (!b) return
    const r = b.getBoundingClientRect()
    const l = list.current
    // tamanho de layout (borda + barra de rolagem incluídas; não afetado pela escala da animação)
    const natW = l ? Math.ceil(l.offsetWidth) + 1 : 0
    const natH = l ? l.scrollHeight + (l.offsetHeight - l.clientHeight) : 0
    const rtl = getComputedStyle(b).direction === 'rtl'
    const next = placeMenu(r, natW, natH, { minWidth: Math.max(r.width, menuWidth ?? 0), align, rtl })
    setPos((p) => (p && p.left === next.left && p.top === next.top && p.bottom === next.bottom && p.maxHeight === next.maxHeight && p.maxWidth === next.maxWidth && p.minWidth === next.minWidth ? p : next))
  }, [align, menuWidth])
  const openMenu = () => {
    const r = btn.current!.getBoundingClientRect()
    setPos(placeMenu(r, 0, MAX_H, { minWidth: Math.max(r.width, menuWidth ?? 0), align, rtl: getComputedStyle(btn.current!).direction === 'rtl' }))
    follow.current = true
    setHi(Math.max(0, options.findIndex((o) => o.value === value)))
    setOpen(true)
  }
  const close = (refocus = true) => { setOpen(false); if (refocus) btn.current?.focus() }
  // mede o menu já renderizado e reposiciona antes de pintar
  useLayoutEffect(() => { if (open) place() }, [open, options.length, place])
  useEffect(() => {
    if (!open) return
    const down = (e: MouseEvent) => { if (!list.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) setOpen(false) }
    const key = (e: KeyboardEvent) => {
      follow.current = true
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close() }
      else if (e.key === 'ArrowDown') { e.preventDefault(); setHi((h) => Math.min(options.length - 1, h + 1)) }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setHi((h) => Math.max(0, h - 1)) }
      else if (e.key === 'Home') setHi(0)
      else if (e.key === 'End') setHi(options.length - 1)
      else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); const o = options[hi]; if (o && !o.disabled) { onChange(o.value); close() } }
      else if (e.key === 'Tab') setOpen(false)
    }
    // reposiciona em resize/zoom/rolagem (rolagem dentro do próprio menu não conta) e fecha se a janela perder o foco
    const rs = () => place()
    const sc = (e: Event) => { if (!list.current?.contains(e.target as Node)) place() }
    const blur = () => setOpen(false)
    const ro = new ResizeObserver(() => place())
    if (btn.current) ro.observe(btn.current)
    if (list.current) ro.observe(list.current)
    ro.observe(document.documentElement)
    document.addEventListener('mousedown', down); document.addEventListener('keydown', key, true)
    window.addEventListener('resize', rs); window.addEventListener('scroll', sc, true); window.addEventListener('blur', blur)
    window.visualViewport?.addEventListener('resize', rs)
    return () => {
      ro.disconnect()
      document.removeEventListener('mousedown', down); document.removeEventListener('keydown', key, true)
      window.removeEventListener('resize', rs); window.removeEventListener('scroll', sc, true); window.removeEventListener('blur', blur)
      window.visualViewport?.removeEventListener('resize', rs)
    }
  })
  useLayoutEffect(() => { if (open && follow.current) list.current?.querySelector<HTMLElement>('[data-hi="true"]')?.scrollIntoView({ block: 'nearest' }) }, [hi, open, pos?.maxHeight])
  return (
    <>
      <button ref={btn} type="button" className={`select ${open ? 'open' : ''} ${className}`} style={{ width }} aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? id : undefined} aria-label={label}
        onClick={() => (open ? close(false) : openMenu())} onKeyDown={(e) => { if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); openMenu() } }}>
        {icon && <span className="select-icon">{icon}</span>}
        <span className="select-value">{display ?? (cur ? cur.label : <span className="ph">{placeholder}</span>)}</span>
        <IChevron size={15} className="select-chev" />
      </button>
      {createPortal(
        <AnimatePresence>
          {open && pos && (
            <motion.div ref={list} id={id} role="listbox" className="select-menu no-drag" data-interactive data-flip={pos.flip ? 'up' : 'down'}
              style={{ left: pos.left, top: pos.top, bottom: pos.bottom, minWidth: pos.minWidth, maxWidth: pos.maxWidth, maxHeight: pos.maxHeight, transformOrigin: `${pos.originX} ${pos.flip ? 'bottom' : 'top'}` }}
              initial={{ opacity: 0, y: pos.flip ? 6 : -6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.98, transition: { duration: 0.1 } }} transition={{ type: 'spring', stiffness: 640, damping: 34 }}>
              {options.map((o, i) => (
                <div key={o.value} role="option" aria-selected={o.value === value} aria-disabled={o.disabled} data-hi={i === hi} className={`opt ${o.value === value ? 'sel' : ''} ${i === hi ? 'hi' : ''} ${o.disabled ? 'dis' : ''}`}
                  onMouseEnter={() => { follow.current = false; setHi(i) }} onClick={() => { if (!o.disabled) { onChange(o.value); close() } }}>
                  <span className="opt-main">{o.label}{o.sub && <small>{o.sub}</small>}</span>
                  {o.value === value && <ICheck size={15} />}
                </div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>, document.body)}
    </>
  )
}

/* ------------------------------------------------------------------ Texto, badges, campos */
export function Chip({ children, tone = 'default', title }: { children: ReactNode; tone?: 'default' | 'ok' | 'warn' | 'err' | 'accent'; title?: string }) {
  return <span className={`chip ${tone}`} title={title}>{children}</span>
}
export function Kbd({ children }: { children: ReactNode }) { return <kbd className="kbd">{children}</kbd> }

export function Field({ label, hint, children, row }: { label: ReactNode; hint?: ReactNode; children: ReactNode; row?: boolean }) {
  return (
    <div className={`field ${row ? 'row' : ''}`}>
      <div className="field-label"><span>{label}</span>{hint && <small>{hint}</small>}</div>
      <div className="field-ctl">{children}</div>
    </div>
  )
}

export const TextInput = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function TextInput({ className = '', ...p }, ref) {
  return <input ref={ref} className={`input ${className}`} spellCheck={false} {...p} />
})

/* ------------------------------------------------------------------ Número animado */
export function AnimatedNumber({ value, format = (n: number) => String(Math.round(n)), className }: { value: number; format?: (n: number) => string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const prev = useRef(value)
  const reduce = useReducedMotion()
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (reduce) { el.textContent = format(value); prev.current = value; return }
    const c = animate(prev.current, value, { duration: 0.5, ease: [0.22, 0.9, 0.24, 1], onUpdate: (n) => { el.textContent = format(n) } })
    prev.current = value
    return () => c.stop()
  }, [value, reduce]) // eslint-disable-line react-hooks/exhaustive-deps
  return <span ref={ref} className={className} dir="ltr" style={{ unicodeBidi: 'isolate' }}>{format(value)}</span>
}

/* ------------------------------------------------------------------ Revelação de texto (digitação / palavras) */
const SEGMENTER = typeof Intl !== 'undefined' && 'Segmenter' in Intl ? new Intl.Segmenter(undefined, { granularity: 'grapheme' }) : null
export function RevealText({ text, rev, typewriter = true, className = '', style }: { text: string; rev: number; typewriter?: boolean; className?: string; style?: React.CSSProperties }) {
  const ref = useRef<HTMLDivElement>(null)
  const caret = useRef<HTMLSpanElement | null>(null)
  const reduce = useReducedMotion()
  const first = useRef(true)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.textContent = ''
    const textNode = document.createTextNode('')
    el.appendChild(textNode)
    if (first.current || reduce || !typewriter || !text) {
      first.current = false
      textNode.data = text
      return
    }
    const chars = SEGMENTER ? Array.from(SEGMENTER.segment(text), (s) => s.segment) : Array.from(text)
    const c = document.createElement('span')
    c.className = 'caret'
    el.appendChild(c)
    caret.current = c
    const total = Math.min(1100, Math.max(260, chars.length * 16))
    const t0 = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / total)
      const eased = 1 - Math.pow(1 - p, 2.2)
      textNode.data = chars.slice(0, Math.ceil(eased * chars.length)).join('')
      if (p < 1) raf = requestAnimationFrame(tick)
      else { c.classList.add('done'); setTimeout(() => c.remove(), 700) }
    }
    raf = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(raf); c.remove(); textNode.data = text }
  }, [rev, text === '' ? 0 : 1]) // eslint-disable-line react-hooks/exhaustive-deps
  return <div ref={ref} className={`reveal ${className}`} style={style} aria-live="polite" aria-label={text} />
}

/* ------------------------------------------------------------------ Luzes arco-íris (acento sutil) */
export function Lights({ active, count = 14 }: { active: boolean; count?: number }) {
  const dots = useMemo(() => Array.from({ length: count }, (_, i) => SOFT_RAINBOW[Math.floor((i / count) * SOFT_RAINBOW.length)]), [count])
  return (
    <span className={`lights ${active ? 'active' : ''}`} aria-hidden>
      {dots.map((c, i) => <i key={i} style={{ background: c, animationDelay: `${i * 90}ms` }} />)}
    </span>
  )
}

/* ------------------------------------------------------------------ Foco preso em modais/gaveta */
export function useFocusTrap(active: boolean, ref: React.RefObject<HTMLElement | null>, onEscape?: () => void) {
  useEffect(() => {
    if (!active) return
    const el = ref.current
    const prev = document.activeElement as HTMLElement | null
    const focusables = () => Array.from(el?.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])') ?? []).filter((n) => n.offsetParent !== null)
    const t = setTimeout(() => { el?.focus({ preventScroll: true }) }, 40)
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !document.querySelector('.select-menu')) { e.stopPropagation(); onEscape?.() }
      if (e.key !== 'Tab') return
      const f = focusables(); if (!f.length) return
      const first = f[0], last = f[f.length - 1]
      if (e.shiftKey && (document.activeElement === first || document.activeElement === el)) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', key)
    return () => { clearTimeout(t); document.removeEventListener('keydown', key); prev?.focus?.() }
  }, [active]) // eslint-disable-line react-hooks/exhaustive-deps
}

/* ------------------------------------------------------------------ Contexto de tamanho de fonte */
export const FontCtx = createContext<number>(18)
export const useFontSize = () => useContext(FontCtx)
