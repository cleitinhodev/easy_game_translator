import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import ninaPng from '@/assets/nina.png'
import bemvindo from '@/assets/bemvindo.mp3'
import { INTRO_AUDIO_MS, startIntroPlayback, type IntroAudioLike } from '@/lib/introPlayer'
import { SOFT_RAINBOW } from '@/lib/format'
import { useT } from '@/store'

export const INTRO_MS = 3400

/** E2E: permite injetar um áudio falso e acelerar os tempos (só quando window.__EGT_INTRO_TEST existir). */
interface IntroTest { create?: () => IntroAudioLike; knownMs?: number; marginMs?: number; hardExtraMs?: number; stallMs?: number }

export function Intro({ show, full = true, onDone }: { show: boolean; full?: boolean; onDone: () => void }) {
  const t = useT()
  const orbit = useMemo(() => Array.from({ length: 24 }, (_, i) => ({ a: (i / 24) * 360, c: SOFT_RAINBOW[Math.floor((i / 24) * SOFT_RAINBOW.length)] })), [])
  const [ms, setMs] = useState(full ? INTRO_AUDIO_MS : INTRO_MS)
  const skipRef = useRef<() => void>(() => onDone())
  useEffect(() => {
    if (!show) return
    const test: IntroTest | undefined = (window as unknown as { __EGT_INTRO_TEST?: IntroTest }).__EGT_INTRO_TEST
    const create = test?.create ?? (() => new Audio(bemvindo) as IntroAudioLike)
    let cleanup = () => {}
    if (full) {
      // toca até o FIM: só então a intro some (fade-out) e revela a janela principal
      setMs(test?.knownMs ?? INTRO_AUDIO_MS)
      const pb = startIntroPlayback({ create, onDone: () => onDone(), knownMs: test?.knownMs, marginMs: test?.marginMs, hardExtraMs: test?.hardExtraMs, stallMs: test?.stallMs })
      skipRef.current = pb.skip
      cleanup = pb.cancel
    } else {
      // modo curto (Tocar intro completa = desligado): 3,4 s com fade do som
      const a = create()
      a.volume = 0.85
      Promise.resolve(a.play()).catch(() => { /* sem permissão de áudio: segue sem som */ })
      const fade = setTimeout(() => {
        const iv = setInterval(() => { if (a.volume > 0.06) a.volume = Math.max(0, a.volume - 0.07); else { a.pause(); clearInterval(iv) } }, 40)
      }, INTRO_MS - 700)
      const end = setTimeout(onDone, INTRO_MS)
      skipRef.current = () => onDone()
      cleanup = () => { clearTimeout(fade); clearTimeout(end); a.pause() }
    }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape' || e.key === 'Enter' || e.key === ' ') skipRef.current() }
    window.addEventListener('keydown', key)
    return () => { cleanup(); window.removeEventListener('keydown', key) }
  }, [show]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <AnimatePresence>
      {show && (
        <motion.div className="intro" onClick={() => skipRef.current()} role="presentation" initial={{ opacity: 1 }} exit={{ opacity: 0, scale: 1.04, filter: 'blur(8px)' }} transition={{ duration: 0.55, ease: [0.4, 0, 0.2, 1] }}>
          <div className="intro-bg" aria-hidden />
          <div className="intro-stage">
            <div className="intro-orbit" aria-hidden>
              {orbit.map((o, i) => <i key={i} style={{ transform: `rotate(${o.a}deg) translateY(-168px)`, background: o.c, animationDelay: `${i * 70}ms` }} />)}
            </div>
            <motion.span className="intro-glow" aria-hidden initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: [0, 0.9, 0.55], scale: [0.6, 1.15, 1] }} transition={{ duration: 1.6 }} />
            <motion.img src={ninaPng} alt="Nina" draggable={false} className="intro-nina" initial={{ opacity: 0, scale: 0.55, rotate: -6, y: 20 }} animate={{ opacity: 1, scale: [0.55, 1.04, 1], rotate: 0, y: 0 }} transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }} />
          </div>
          <motion.h1 className="intro-title" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.7, duration: 0.7, ease: [0.22, 0.9, 0.24, 1] }}>
            {t('intro.welcome')}
          </motion.h1>
          <motion.p className="intro-sub" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.15, duration: 0.7 }}>Easy Game Translator · v4.0.5 by CleitinhoDEV</motion.p>
          <motion.span className="intro-progress" aria-hidden initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: ms / 1000, ease: 'linear' }} />
          <motion.span className="intro-skip" initial={{ opacity: 0 }} animate={{ opacity: 0.6 }} transition={{ delay: 1.6 }}>{t('intro.skip')}</motion.span>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
