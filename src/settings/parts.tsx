import type { ReactNode } from 'react'
import { motion } from 'motion/react'

export function Section({ title, desc, children, right }: { title: ReactNode; desc?: ReactNode; children: ReactNode; right?: ReactNode }) {
  return (
    <motion.section className="s-section" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.28, ease: [0.22, 0.9, 0.24, 1] }}>
      <div className="s-head">
        <div><h4>{title}</h4>{desc && <p className="muted">{desc}</p>}</div>
        {right}
      </div>
      <div className="s-body">{children}</div>
    </motion.section>
  )
}

export function Row({ label, hint, children, stack }: { label: ReactNode; hint?: ReactNode; children: ReactNode; stack?: boolean }) {
  return (
    <div className={`s-row ${stack ? 'stack' : ''}`}>
      <div className="s-row-label"><span>{label}</span>{hint && <small>{hint}</small>}</div>
      <div className="s-row-ctl">{children}</div>
    </div>
  )
}

export function Result({ ok, children }: { ok: boolean | null; children: ReactNode }) {
  if (ok === null) return null
  return <motion.div className={`result ${ok ? 'ok' : 'err'}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>{ok ? '✔' : '✖'} {children}</motion.div>
}
