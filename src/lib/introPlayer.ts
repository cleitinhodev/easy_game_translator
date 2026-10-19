/**
 * Reprodução da música de abertura: a intro só termina quando o áudio chega ao FIM ('ended').
 * Se o áudio não carregar/tocar (sem dispositivo, erro, travado) usa a duração conhecida como temporizador
 * (+ margem), e há um limite máximo de segurança (duração + 3 s) para nunca ficar preso.
 */
export const INTRO_AUDIO_MS = 7060          // bemvindo.mp3 = 7,057 s (ffprobe)
export const INTRO_MARGIN_MS = 400
export const INTRO_HARD_EXTRA_MS = 3000
export const INTRO_STALL_MS = 1600          // tocando mas o relógio do áudio não anda => cai no temporizador

export type IntroEnd = 'ended' | 'fallback' | 'hard-timeout' | 'skipped'

export interface IntroAudioLike {
  play(): Promise<void> | void
  pause(): void
  addEventListener(type: string, cb: () => void): void
  removeEventListener(type: string, cb: () => void): void
  duration: number
  currentTime: number
  volume: number
}

export interface IntroLogEntry { t: number; ev: string }
export const introLog: IntroLogEntry[] = []
;(globalThis as unknown as { __introLog?: IntroLogEntry[] }).__introLog = introLog   // para o teste E2E

export interface IntroOpts {
  create: () => IntroAudioLike
  onDone: (how: IntroEnd) => void
  knownMs?: number
  marginMs?: number
  hardExtraMs?: number
  stallMs?: number
  volume?: number
}

/** Inicia o áudio; devolve `cancel()` (que também pausa). `onDone` é chamado no máximo uma vez. */
export function startIntroPlayback(o: IntroOpts): { cancel: () => void; skip: () => void } {
  const known = o.knownMs ?? INTRO_AUDIO_MS
  const margin = o.marginMs ?? INTRO_MARGIN_MS
  const hardExtra = o.hardExtraMs ?? INTRO_HARD_EXTRA_MS
  const stall = o.stallMs ?? INTRO_STALL_MS
  const t0 = performance.now()
  introLog.length = 0
  const log = (ev: string) => { introLog.push({ t: Math.round(performance.now() - t0), ev }); console.info(`[intro +${Math.round(performance.now() - t0)}ms] ${ev}`) }
  let done = false
  let fbTimer: ReturnType<typeof setTimeout> | undefined
  let stallTimer: ReturnType<typeof setTimeout> | undefined
  let hardTimer: ReturnType<typeof setTimeout> | undefined
  let audio: IntroAudioLike | null = null

  const cleanup = () => {
    clearTimeout(fbTimer); clearTimeout(stallTimer); clearTimeout(hardTimer)
    if (audio) {
      audio.removeEventListener('ended', onEnded); audio.removeEventListener('error', onError); audio.removeEventListener('loadedmetadata', onMeta)
      try { audio.pause() } catch { /* ignore */ }
    }
  }
  const finish = (how: IntroEnd) => { if (done) return; done = true; log(`done: ${how}`); cleanup(); o.onDone(how) }
  const armFallback = (why: string) => {
    if (done || fbTimer) return
    const wait = Math.max(0, known + margin - (performance.now() - t0))
    log(`fallback timer ${Math.round(wait)}ms (${why})`)
    fbTimer = setTimeout(() => finish('fallback'), wait)
  }
  function onEnded() { log('audio ended'); finish('ended') }
  function onError() { log('audio error'); armFallback('error') }
  function onMeta() {
    if (audio && isFinite(audio.duration) && audio.duration > 0) {
      log(`duration ${audio.duration.toFixed(2)}s`)
      clearTimeout(hardTimer)
      hardTimer = setTimeout(() => finish('hard-timeout'), Math.max(known, audio.duration * 1000) + hardExtra - (performance.now() - t0))
    }
  }

  hardTimer = setTimeout(() => finish('hard-timeout'), known + hardExtra)
  try {
    audio = o.create()
    audio.volume = o.volume ?? 0.85
    audio.addEventListener('ended', onEnded)
    audio.addEventListener('error', onError)
    audio.addEventListener('loadedmetadata', onMeta)
    const p = audio.play()
    if (p && typeof (p as Promise<void>).then === 'function') {
      ;(p as Promise<void>).then(() => {
        log('play() ok')
        // dispositivo ausente/áudio parado: o relógio não anda -> usa o temporizador
        stallTimer = setTimeout(() => { if (!done && audio && audio.currentTime <= 0.05) armFallback('stalled') }, stall)
      }, (e) => { log(`play() rejected: ${e?.name || e}`); armFallback('play-rejected') })
    }
  } catch (e) {
    log(`create/play threw: ${(e as Error)?.message}`)
    armFallback('exception')
  }
  return { cancel: () => { if (!done) { done = true; cleanup() } }, skip: () => finish('skipped') }
}
