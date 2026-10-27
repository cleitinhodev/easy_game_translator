import { motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import helpPng from '@/assets/nina_window_help.png'
import { useStore, useT } from '@/store'
import { Modal } from './Modal'
import { Button } from './ui'
import { SOFT_RAINBOW } from '@/lib/format'

// Links do help_window.py do v3 (CleitinhoDEV)
export const LINKS = {
  website: 'https://www.bugzinho.com/',
  tutorial: 'https://cleitinhodev.github.io/homepage/projects/easy-game-translator-tutorial/',
  donate: 'https://www.bugzinho.com/donate',
  channel: 'https://www.youtube.com/@CleitinhoDEV',
  patreon: 'https://www.patreon.com/CleitinhoDEV',
  github: 'https://github.com/cleitinhodev',
}

function openLink(url: string) {
  if (window.egt) window.egt.app.openExternal(url)
  else window.open(url, '_blank', 'noopener')
}

function Fireflies() {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const cv = ref.current!
    const ctx = cv.getContext('2d')!
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    const W = cv.clientWidth, H = cv.clientHeight
    cv.width = W * dpr; cv.height = H * dpr
    ctx.scale(dpr, dpr)
    const ps = Array.from({ length: 26 }, (_, i) => ({ x: Math.random() * W, y: Math.random() * H, r: 1 + Math.random() * 2.2, dx: (Math.random() - 0.5) * 0.35, dy: (Math.random() - 0.5) * 0.35, ph: Math.random() * 6.28, c: SOFT_RAINBOW[(i * 3) % SOFT_RAINBOW.length] }))
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    const draw = () => {
      ctx.clearRect(0, 0, W, H)
      for (const p of ps) {
        if (!still) { p.x += p.dx; p.y += p.dy; p.ph += 0.03 }
        if (p.x < 0 || p.x > W) p.dx *= -1
        if (p.y < 0 || p.y > H) p.dy *= -1
        const a = 0.25 + 0.55 * (0.5 + 0.5 * Math.sin(p.ph))
        ctx.beginPath(); ctx.fillStyle = p.c; ctx.globalAlpha = a; ctx.shadowColor = p.c; ctx.shadowBlur = 10
        ctx.arc(p.x, p.y, p.r, 0, 6.28); ctx.fill()
      }
      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => cancelAnimationFrame(raf)
  }, [])
  return <canvas ref={ref} className="fireflies" aria-hidden />
}

function Typed({ text, delay = 0, speed = 38, className }: { text: string; delay?: number; speed?: number; className?: string }) {
  const [n, setN] = useState(0)
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setN(text.length); return }
    let i = 0
    let iv: ReturnType<typeof setInterval>
    const st = setTimeout(() => { iv = setInterval(() => { i++; setN(i); if (i >= text.length) clearInterval(iv) }, speed) }, delay)
    return () => { clearTimeout(st); clearInterval(iv) }
  }, [text, delay, speed])
  return <span className={className}>{text.slice(0, n)}<i className="caret" style={{ opacity: n < text.length ? 1 : 0 }} /></span>
}

export function HelpModal() {
  const t = useT()
  const open = useStore((s) => s.modal === 'help')
  const setModal = useStore((s) => s.setModal)
  const version = useStore((s) => s.appVersion || s.snapshot?.app.version || '4.0.7')
  const links: [string, string, string][] = [
    [t('help.website'), LINKS.website, 'site'], [t('help.tutorial'), LINKS.tutorial, 'tut'], [t('help.donate'), LINKS.donate, 'don'],
    [t('help.channel'), LINKS.channel, 'yt'], [t('help.support'), LINKS.patreon, 'pat'], [t('help.projects'), LINKS.github, 'git'],
  ]
  return (
    <Modal open={open} onClose={() => setModal(null)} width={620} title={t('help.title')} className="help">
      <div className="help-hero">
        <Fireflies />
        <motion.img src={helpPng} alt="Nina" className="help-img" draggable={false} initial={{ opacity: 0, scale: 1.12 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.7, ease: [0.22, 0.9, 0.24, 1] }} />
        <div className="help-titles">
          {open && <h2><Typed text="Easy Game Translator" speed={42} /></h2>}
          {open && <p><Typed text={`v${version.split('.').slice(0, 2).join('.')} by CleitinhoDEV`} delay={950} speed={55} /></p>}
        </div>
      </div>
      <div className="link-grid">
        {links.map(([label, url, id], i) => (
          <motion.div key={id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 + i * 0.05 }}>
            <Button className={`link-btn ${id}`} onClick={() => openLink(url)} tip={url.replace('https://', '')}>{label}</Button>
          </motion.div>
        ))}
      </div>
    </Modal>
  )
}
