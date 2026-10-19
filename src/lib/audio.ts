// Gravação do microfone → WAV mono 16 kHz (para o backend enviar ao reconhecimento de fala).
export interface Recorder { stop: () => Promise<Blob>; level: () => number; cancel: () => void }

export async function startRecording(onSilence?: () => void, maxMs = 20000): Promise<Recorder> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } })
  const rec = new MediaRecorder(stream)
  const chunks: Blob[] = []
  rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
  const ctx = new AudioContext()
  const analyser = ctx.createAnalyser()
  analyser.fftSize = 512
  ctx.createMediaStreamSource(stream).connect(analyser)
  const buf = new Uint8Array(analyser.fftSize)
  let lvl = 0
  let lastVoice = performance.now()
  let heard = false
  const t0 = performance.now()
  const timer = setInterval(() => {
    analyser.getByteTimeDomainData(buf)
    let sum = 0
    for (const b of buf) { const v = (b - 128) / 128; sum += v * v }
    lvl = Math.min(1, Math.sqrt(sum / buf.length) * 4)
    const now = performance.now()
    if (lvl > 0.08) { lastVoice = now; heard = true }
    if ((heard && now - lastVoice > 1800) || now - t0 > maxMs) onSilence?.()
  }, 80)
  rec.start()
  const cleanup = () => { clearInterval(timer); stream.getTracks().forEach((t) => t.stop()); ctx.close().catch(() => {}) }
  return {
    level: () => lvl,
    cancel: () => { try { rec.stop() } catch { /* já parado */ } cleanup() },
    stop: () => new Promise<Blob>((resolve, reject) => {
      rec.onstop = async () => {
        cleanup()
        try { resolve(await toWav(new Blob(chunks, { type: rec.mimeType }))) } catch (e) { reject(e) }
      }
      try { rec.stop() } catch (e) { reject(e) }
    }),
  }
}

async function toWav(blob: Blob): Promise<Blob> {
  const arr = await blob.arrayBuffer()
  const ac = new AudioContext()
  const decoded = await ac.decodeAudioData(arr)
  await ac.close()
  const rate = 16000
  const off = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * rate)), rate)
  const src = off.createBufferSource()
  src.buffer = decoded
  src.connect(off.destination)
  src.start()
  const out = (await off.startRendering()).getChannelData(0)
  const pcm = new DataView(new ArrayBuffer(44 + out.length * 2))
  const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) pcm.setUint8(o + i, s.charCodeAt(i)) }
  w(0, 'RIFF'); pcm.setUint32(4, 36 + out.length * 2, true); w(8, 'WAVEfmt '); pcm.setUint32(16, 16, true)
  pcm.setUint16(20, 1, true); pcm.setUint16(22, 1, true); pcm.setUint32(24, rate, true); pcm.setUint32(28, rate * 2, true)
  pcm.setUint16(32, 2, true); pcm.setUint16(34, 16, true); w(36, 'data'); pcm.setUint32(40, out.length * 2, true)
  for (let i = 0; i < out.length; i++) pcm.setInt16(44 + i * 2, Math.max(-1, Math.min(1, out[i])) * 0x7fff, true)
  return new Blob([pcm.buffer], { type: 'audio/wav' })
}
