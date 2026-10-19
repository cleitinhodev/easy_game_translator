import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { isLang, translate, type Lang } from '@/lib/i18n'

/** Sobreposição transparente por monitor. Devolve o retângulo em pixels CSS (DIP) da janela. */
export function SelectView() {
  const q = new URLSearchParams(location.hash.split('?')[1] || '')
  const ch = q.get('ch') || 'uni'
  const sf = Number(q.get('sf') || 1)
  const lang: Lang = isLang(q.get('lang')) ? q.get('lang')! : 'en'
  const t = (k: string, p?: Record<string, string | number>) => translate(lang, k, p)
  const [a, setA] = useState<{ x: number; y: number } | null>(null)
  const [b, setB] = useState<{ x: number; y: number } | null>(null)
  const [mouse, setMouse] = useState<{ x: number; y: number } | null>(null)
  const dragging = useRef(false)
  const rect = a && b ? { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y) } : null
  const title = ch === 'a' ? t('sel.title_a') : ch === 'b' ? t('sel.title_b') : t('sel.title')

  useEffect(() => {
    document.documentElement.style.background = 'transparent'
    document.body.style.background = 'transparent'
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') window.egt?.region.cancel() }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])

  const down = (e: React.PointerEvent) => {
    if (e.button === 2) { window.egt?.region.cancel(); return }
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    dragging.current = true
    setA({ x: e.clientX, y: e.clientY }); setB({ x: e.clientX, y: e.clientY })
  }
  const move = (e: React.PointerEvent) => {
    setMouse({ x: e.clientX, y: e.clientY })
    if (dragging.current) setB({ x: e.clientX, y: e.clientY })
  }
  const up = (e: React.PointerEvent) => {
    if (!dragging.current) return
    dragging.current = false
    const r = { x: Math.round(Math.min(a!.x, e.clientX)), y: Math.round(Math.min(a!.y, e.clientY)), width: Math.round(Math.abs(a!.x - e.clientX)), height: Math.round(Math.abs(a!.y - e.clientY)) }
    if (r.width >= 6 && r.height >= 6) window.egt?.region.done(r)
    else { setA(null); setB(null) }
  }
  const lw = rect ? Math.round(rect.w * sf) : 0, lh = rect ? Math.round(rect.h * sf) : 0
  return (
    <div className="selector" onPointerDown={down} onPointerMove={move} onPointerUp={up} onContextMenu={(e) => { e.preventDefault(); window.egt?.region.cancel() }}>
      {!rect && <div className="sel-dim" />}
      {mouse && !rect && (<><i className="guide v" style={{ left: mouse.x }} /><i className="guide h" style={{ top: mouse.y }} /></>)}
      {rect && (
        <>
          <div className="sel-rect" style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h }}>
            <i className="c tl" /><i className="c tr" /><i className="c bl" /><i className="c br" />
          </div>
          <div className="sel-size" style={{ left: Math.min(rect.x + rect.w + 10, window.innerWidth - 140), top: Math.min(rect.y + rect.h + 10, window.innerHeight - 40) }}>{lw} × {lh} px</div>
        </>
      )}
      <AnimatePresence>
        <motion.div className="sel-pill" initial={{ opacity: 0, y: -16 }} animate={{ opacity: 1, y: 0 }} transition={{ type: 'spring', stiffness: 420, damping: 30 }}>
          <b>{title}</b><span>{t('sel.hint')}</span>
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

export function FlashView() {
  const q = new URLSearchParams(location.hash.split('?')[1] || '')
  const label = q.get('label') || ''
  useEffect(() => { document.documentElement.style.background = 'transparent'; document.body.style.background = 'transparent' }, [])
  return (
    <motion.div className="flash" initial={{ opacity: 0, scale: 1.05 }} animate={{ opacity: [0, 1, 1, 0], scale: [1.05, 1, 1, 1] }} transition={{ duration: 1.4, times: [0, 0.15, 0.75, 1] }}>
      {label && <span className="flash-tag">{label}</span>}
    </motion.div>
  )
}
