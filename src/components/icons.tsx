import type { SVGProps } from 'react'
import startPng from '@/assets/start_btn.png'
import stopPng from '@/assets/stop_btn.png'
import capturePng from '@/assets/capture_btn.png'
import channelsPng from '@/assets/channels_btn.png'
import translatePng from '@/assets/translate_btn.png'
import boxPng from '@/assets/box_btn.png'
import speakPng from '@/assets/to_speak.png'
import listenPng from '@/assets/to_listen.png'
import doubleAPng from '@/assets/double_a.png'
import doubleBPng from '@/assets/double_b.png'

/** Os PNGs do usuário (brancos, fundo transparente) pintados com a cor atual via máscara. */
export const PNG = { start: startPng, stop: stopPng, capture: capturePng, channels: channelsPng, translate: translatePng, box: boxPng, speak: speakPng, listen: listenPng, a: doubleAPng, b: doubleBPng }

export function PngIcon({ src, size = 22, className = '' }: { src: string; size?: number; className?: string }) {
  const url = `url(${src})`
  return <span aria-hidden className={`png-icon ${className}`} style={{ width: size, height: size, WebkitMaskImage: url, maskImage: url }} />
}

type P = SVGProps<SVGSVGElement> & { size?: number }
const base = (size = 18): SVGProps<SVGSVGElement> => ({
  width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true,
})
const mk = (d: React.ReactNode) => ({ size, ...p }: P) => <svg {...base(size)} {...p}>{d}</svg>

export const IGear = mk(<><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>)
export const IMenu = mk(<><path d="M4 7h16M4 12h16M4 17h16" /></>)
export const ICheck = mk(<path d="M5 12.5l4.5 4.5L19 7.5" />)
export const IX = mk(<path d="M6 6l12 12M18 6L6 18" />)
export const IChevron = mk(<path d="M6 9l6 6 6-6" />)
export const IChevronRight = mk(<path d="M9 6l6 6-6 6" />)
export const ICopy = mk(<><rect x="9" y="9" width="11" height="11" rx="2.5" /><path d="M5 15V6a2 2 0 0 1 2-2h8" /></>)
export const ITrash = mk(<><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" /></>)
export const IRefresh = mk(<><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" /></>)
export const IFolder = mk(<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />)
export const IDownload = mk(<><path d="M12 4v11M7 11l5 5 5-5M5 20h14" /></>)
export const IPlus = mk(<path d="M12 5v14M5 12h14" />)
export const IUp = mk(<path d="M6 15l6-6 6 6" />)
export const IDown = mk(<path d="M6 9l6 6 6-6" />)
export const IInfo = mk(<><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>)
export const IWifi = mk(<><path d="M2 9a15 15 0 0 1 20 0M5 12.5a10.5 10.5 0 0 1 14 0M8.5 16a5.5 5.5 0 0 1 7 0" /><path d="M12 19.5h.01" /></>)
export const IWifiOff = mk(<><path d="M2 2l20 20M8.5 16a5.5 5.5 0 0 1 7 0M5 12.5a10.5 10.5 0 0 1 5-2.7M2 9a15 15 0 0 1 6-3.3M16 6.2A15 15 0 0 1 22 9M19 12.5a10.5 10.5 0 0 0-2-1.4" /><path d="M12 19.5h.01" /></>)
export const ICpu = mk(<><rect x="5" y="5" width="14" height="14" rx="2.5" /><rect x="9" y="9" width="6" height="6" rx="1" /><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" /></>)
export const IZap = mk(<path d="M13 2L4 14h7l-1 8 9-12h-7z" />)
export const IDatabase = mk(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>)
export const IClock = mk(<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>)
export const IGlobe = mk(<><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></>)
export const IKey = mk(<><circle cx="8" cy="15" r="4" /><path d="M11 12l9-9M16 7l3 3" /></>)
export const ISliders = mk(<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4" />)
export const IBug = mk(<><rect x="8" y="8" width="8" height="12" rx="4" /><path d="M9 8a3 3 0 0 1 6 0M4 13h4M16 13h4M5 7l3 2M19 7l-3 2M5 19l3-2M19 19l-3-2" /></>)
export const IHistory = mk(<><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 8v4l3 2" /></>)
export const IScan = mk(<><path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2" /><path d="M7 12h10" /></>)
export const ILanguages = mk(<><path d="M4 5h9M8.5 3v2M6 5c.5 4 3 7 6 8M12 5c-.5 4-3 7-7 9" /><path d="M13 20l4-9 4 9M14.5 17h5" /></>)
export const IReplace = mk(<><path d="M4 7h12l-3-3M20 17H8l3 3" /></>)
export const ISparkles = mk(<><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z" /></>)
export const IDownloadCloud = mk(<><path d="M8 17a5 5 0 1 1 1-9.9A6 6 0 0 1 20 10a4 4 0 0 1-1 7.9M12 12v8M9 17l3 3 3-3" /></>)
export const IHelp = mk(<><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01" /></>)
export const IMonitor = mk(<><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></>)
export const IPin = mk(<path d="M9 4h6l-1 5 4 4H6l4-4zM12 13v8" />)
export const ISave = mk(<><path d="M5 4h11l3 3v13H5z" /><path d="M8 4v5h7V4M8 20v-6h8v6" /></>)
export const IMousePointer = mk(<path d="M5 4l14 6-6 2-2 6z" />)
export const IEye = mk(<><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>)
export const IKeyboard = mk(<><rect x="2" y="6" width="20" height="12" rx="2.5" /><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10" /></>)
export const IUndo = mk(<><path d="M9 14L4 9l5-5" /><path d="M4 9h10a6 6 0 0 1 0 12h-3" /></>)
