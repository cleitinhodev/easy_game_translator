import { AnimatePresence, motion } from 'motion/react'
import { useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useStore, useT } from '@/store'
import { IX } from './icons'
import { Button, IconButton, useFocusTrap } from './ui'

export function Modal({ open, onClose, title, children, width = 560, className = '', footer, bare }: { open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode; width?: number; className?: string; footer?: ReactNode; bare?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const t = useT()
  useFocusTrap(open, ref, onClose)
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div className="modal-layer" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: 0.16 } }} transition={{ duration: 0.2 }}>
          <div className="scrim" onMouseDown={onClose} />
          <motion.div ref={ref} role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : undefined} tabIndex={-1} className={`modal ${bare ? 'bare' : ''} ${className}`} style={{ width }}
            initial={{ opacity: 0, y: 24, scale: 0.94 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.97, transition: { duration: 0.14 } }} transition={{ type: 'spring', stiffness: 460, damping: 34 }}>
            {title && (
              <header className="modal-head">
                <IconButton label={`${t('common.close')} (Esc)`} onClick={onClose} className="close-left"><IX size={17} /></IconButton>
                <h3>{title}</h3>
              </header>
            )}
            <div className="modal-body">{children}</div>
            {footer && <footer className="modal-foot">{footer}</footer>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>, document.body)
}

export function ConfirmHost() {
  const c = useStore((s) => s.confirm)
  const t = useT()
  return (
    <Modal open={!!c} onClose={() => c?.resolve(false)} width={420} title={t('common.confirm')}
      footer={<><Button variant="ghost" onClick={() => c?.resolve(false)}>{t('common.cancel')}</Button><Button variant={c?.danger ? 'danger' : 'primary'} onClick={() => c?.resolve(true)}>{c?.ok}</Button></>}>
      <p className="confirm-text">{c?.text}</p>
    </Modal>
  )
}
