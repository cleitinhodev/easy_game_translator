import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// CSP estrita no build; um pouco mais frouxa no dev (HMR do Vite).
function csp(): Plugin {
  const base = [
    "default-src 'self'",
    "img-src 'self' data: blob:",
    "media-src 'self' blob: data:",
    "font-src 'self' data:",
    "style-src 'self' 'unsafe-inline'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-src 'none'",
  ]
  return {
    name: 'egt-csp',
    transformIndexHtml(html, ctx) {
      const dev = !!ctx.server
      const policy = dev
        ? [...base, "script-src 'self' 'unsafe-inline'", "connect-src 'self' ws://localhost:* http://localhost:* http://127.0.0.1:* ws://127.0.0.1:*"]
        : [...base, "script-src 'self'", "connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*"]
      return html.replace('<meta charset="UTF-8" />', `<meta charset="UTF-8" />\n    <meta http-equiv="Content-Security-Policy" content="${policy.join('; ')}" />`)
    },
  }
}

export default defineConfig({
  base: './',
  plugins: [react(), csp()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)), '@i18n': fileURLToPath(new URL('./shared/i18n', import.meta.url)) } },
  server: { port: 5173, strictPort: false, host: 'localhost' },
  build: { outDir: 'dist', emptyOutDir: true, target: 'chrome120', sourcemap: false, chunkSizeWarningLimit: 900 },
  assetsInclude: ['**/*.mp3'],
})
