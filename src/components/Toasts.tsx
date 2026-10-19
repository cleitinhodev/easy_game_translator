import { AnimatePresence, motion } from 'motion/react'
import { useEffect } from 'react'
import { useStore, type Toast } from '@/store'
import { ICheck, IInfo, IX } from './icons'

function Item({ toast }: { toast: Toast }) {
  const dismiss = useStore((s) => s.dismissToast)
  useEffect(() => { const t = setTimeout(() => dismiss(toast.id), toast.ttl); return () => clearTimeout(t) }, [toast.id, toast.ttl, dismiss])
  return (
    <motion.div layout className={`toast ${toast.kind}`} role={toast.kind === 'error' ? 'alert' : 'status'}
      initial={{ opacity: 0, y: 24, scale: 0.92 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, x: 40, scale: 0.95, transition: { duration: 0.18 } }} transition={{ type: 'spring', stiffness: 520, damping: 34 }}>
      <span className="toast-ico">{toast.kind === 'ok' ? <ICheck size={16} /> : <IInfo size={16} />}</span>
      <span className="toast-text">{toast.text}</span>
      <button type="button" className="toast-x" aria-label="×" onClick={() => dismiss(toast.id)}><IX size={13} /></button>
      <motion.i className="toast-bar" initial={{ scaleX: 1 }} animate={{ scaleX: 0 }} transition={{ duration: toast.ttl / 1000, ease: 'linear' }} />
    </motion.div>
  )
}

export function Toasts() {
  const toasts = useStore((s) => s.toasts)
  return (
    <div className="toasts" aria-live="polite">
      <AnimatePresence initial={false}>{toasts.map((t) => <Item key={t.id} toast={t} />)}</AnimatePresence>
    </div>
  )
}
