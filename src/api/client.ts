// Cliente HTTP/WebSocket do backend Python (127.0.0.1 + token da sessão).
import type { Snapshot } from '@/lib/types'

let base = ''
let token = ''

export function configureApi(port: number, tok: string) {
  base = `http://127.0.0.1:${port}`
  token = tok
}
export const isConfigured = () => !!base

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function req<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(base + path, {
    method,
    signal,
    headers: { 'X-EGT-Token': token, ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* corpo vazio */ }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export const api = {
  get: <T,>(p: string) => req<T>('GET', p),
  post: <T,>(p: string, b: unknown = {}) => req<T>('POST', p, b),
  patch: <T,>(p: string, b: unknown) => req<T>('PATCH', p, b),
  put: <T,>(p: string, b: unknown) => req<T>('PUT', p, b),
  del: <T,>(p: string) => req<T>('DELETE', p),
  async blob(path: string, body: unknown): Promise<Blob> {
    const res = await fetch(base + path, { method: 'POST', headers: { 'X-EGT-Token': token, 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({ detail: res.statusText }))).detail)
    return res.blob()
  },
  async raw<T>(path: string, data: Blob, contentType: string): Promise<T> {
    const res = await fetch(base + path, { method: 'POST', headers: { 'X-EGT-Token': token, 'Content-Type': contentType }, body: data })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({ detail: res.statusText }))).detail)
    return (await res.json()) as T
  },
  state: () => req<Snapshot>('GET', '/api/state'),
}

export interface WsMessage { type: string; channel?: string; data?: any; ts?: number; level?: string; line?: string }

/** WebSocket com reconexão automática (backoff até 4 s). Devolve função para fechar. */
export function connectEvents(onMessage: (m: WsMessage) => void, onState: (up: boolean) => void): () => void {
  let ws: WebSocket | null = null
  let closed = false
  let retry = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  const open = () => {
    if (closed || !base) return
    ws = new WebSocket(`${base.replace('http', 'ws')}/ws?token=${encodeURIComponent(token)}`)
    ws.onopen = () => { retry = 0; onState(true) }
    ws.onmessage = (ev) => { try { onMessage(JSON.parse(ev.data as string)) } catch { /* ignora */ } }
    ws.onclose = () => {
      onState(false)
      if (closed) return
      retry = Math.min(retry + 1, 8)
      timer = setTimeout(open, Math.min(4000, 250 * 2 ** retry))
    }
    ws.onerror = () => ws?.close()
  }
  open()
  return () => { closed = true; clearTimeout(timer); ws?.close() }
}
